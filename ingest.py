#!/usr/bin/env python3

"""

AMICUS AI - Voyage AI Production Ingestion Engine

Optimized for Idempotency State Tracking, Multi-Variant Schema Normalization, and Native JSON support.

Uses Voyage AI's voyage-law-2 (1024 Dim) for legal-domain vector generation via API,

with concurrent batch embedding to remove the local CPU bottleneck.

"""



import os

import sys

import glob

import json

import time

import logging

import argparse

import re

import hashlib

from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import List, Dict, Any, Tuple, Set, Optional

import pandas as pd

import tiktoken

from dotenv import load_dotenv

from pinecone import Pinecone, PineconeException

import voyageai

from tqdm import tqdm
from cleaner import legal_cleaner



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] %(message)s",

    datefmt="%Y-%m-%d %H:%M:%S"

)

logger = logging.getLogger(__name__)



load_dotenv()



PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not PINECONE_API_KEY:

    raise ValueError("PINECONE_API_KEY is missing from environment configurations!")



INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")

NAMESPACE = os.getenv("PINECONE_NAMESPACE", "judgments")



VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

if not VOYAGE_API_KEY:

    raise ValueError("VOYAGE_API_KEY is missing from environment configurations!")

VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-law-2")



TARGET_CHUNK_TOKENS = int(os.getenv("TARGET_CHUNK_TOKENS", "500"))

MIN_CHUNK_TOKENS = int(os.getenv("MIN_CHUNK_TOKENS", "200"))

MAX_CHUNK_TOKENS = int(os.getenv("MAX_CHUNK_TOKENS", "600"))

OVERLAP_TOKENS = int(os.getenv("OVERLAP_TOKENS", "50"))



BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))

BATCH_COOLDOWN_SECONDS = float(os.getenv("BATCH_COOLDOWN_SECONDS", "0"))

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "5.0"))



# Voyage embedding-specific batching. voyage-law-2 allows up to 1000 texts and

# ~120K tokens per request; 128 texts * ~500 target tokens stays well under that

# with margin for longer chunks, while EMBED_CONCURRENCY overlaps multiple

# in-flight requests to use up the 2000 RPM / 3M TPM tier-1 rate limit instead

# of running one batch at a time like the old local-model loop did.

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "128"))

EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "4"))



CONTENT_COLUMN = os.getenv("CONTENT_COLUMN")       

INPUT_DIR = os.getenv("INPUT_DIR", "datasets")

FAILURE_LOG = os.getenv("FAILURE_LOG", "failed_batches.jsonl")

STATE_FILE = os.getenv("INGESTION_STATE_FILE", "ingestion_state.json")



# Metadata Schema Column Mapping Aliases

COLUMN_ALIASES = {
    "case_id": ["unique_id", "case_id", "case_no", "statute_id", "section_id", "id", "serial_no", "reference_id"],
    "court": ["court", "category", "jurisdiction", "authority", "bench", "court_name", "tribunal", "journal"],
    "year": ["date_of_order", "decision_date", "date_of_hearing", "judgment_year", "year", "passed_year", "date", "session_year", "year_enacted", "date_issued"],
    "subject_matter": ["subject_matter", "legal_domain", "topic", "tags", "subject", "summary", "headnotes", "keywords"],
    "source_url": ["source_url", "link", "url", "source_link", "website"],
    "title": ["case_title", "title", "subject_title", "topic_title", "citation / title", "citation/title", "citation_title"],
    "citation": ["citation", "citation_no", "volume", "citation / title", "citation/title", "citation_title"]
}



# Embedding Client Initialization (Voyage AI, 1024 Dim)

logger.info(f"Initializing Voyage AI embedding client (model: {VOYAGE_MODEL})...")

try:

    voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

    logger.info("Voyage AI embedding client initialized successfully. Vector dimensions: 1024")

except Exception as error:

    logger.error(f"Failed to initialize the Voyage AI client: {error}")

    sys.exit(1)



def embed_batch_with_retry(texts: List[str],

                            retries: int = MAX_RETRIES,

                            base_delay: float = RETRY_BASE_DELAY) -> Optional[List[List[float]]]:

    """Embed a batch of document chunks via the Voyage AI API, with exponential backoff on transient errors."""

    for attempt in range(retries):

        try:

            result = voyage_client.embed(texts, model=VOYAGE_MODEL, input_type="document")

            return result.embeddings

        except Exception as e:

            err_msg = str(e)

            is_transient = any(code in err_msg for code in ["429", "5xx", "500", "502", "503", "timeout", "connection"])

            if is_transient and attempt < retries - 1:

                delay = base_delay * (2 ** attempt)

                logger.warning(f"Voyage embedding transient error (attempt {attempt + 1}/{retries}): {err_msg}. Retrying in {delay}s...")

                time.sleep(delay)

                continue

            logger.error(f"Voyage embedding failed permanently: {err_msg}")

            return None

    return None



_encoder = tiktoken.get_encoding("cl100k_base")



def count_tokens(text: str) -> int:

    return len(_encoder.encode(text))



def text_to_tokens(text: str) -> List[int]:

    return _encoder.encode(text)



def tokens_to_text(tokens: List[int]) -> str:

    return _encoder.decode(tokens)



# Canonical Case ID Generator for Deterministic In-Place Upserts
def generate_case_id(citation: str, title: str) -> str:
    """
    Generates a canonical, deterministic case_id slug/hash based on citation and title.
    Prevents duplicate entries across re-scrapes and re-ingestions.
    """
    citation_clean = (citation or "").strip().lower()
    title_clean = (title or "").strip().lower()
    
    # Strip commercial trademarks from canonical ID generation if present
    citation_clean = re.sub(r'\b(pld|scmr|mld|clc|pcrlj|ptd|plc|cld|ylr|gblr)\b', '', citation_clean)
    
    raw_str = f"{citation_clean}_{title_clean}".strip()
    slug = re.sub(r'[^a-z0-9]+', '-', raw_str).strip('-')
    
    if not slug or len(slug) > 80:
        hash_digest = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]
        slug = f"{slug[:60]}-{hash_digest}" if slug else f"case-{hash_digest}"
    
    return slug


# Metadata Cleaning Helpers

def clean_repeated_phrases(text: str) -> str:

    if not text:

        return ""

    text = re.sub(r'\s+', ' ', text).strip()

    prev_text = None

    while prev_text != text:

        prev_text = text

        text = re.sub(r'\b(\w+(?:\s+\w+){0,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)

    return text



def clean_court_name(court_name: str) -> str:
    if not court_name:
        return "High Court"
    court_name = court_name.strip()
    c_lower = court_name.lower()

    # AJK (Azad Jammu & Kashmir) courts are a SEPARATE jurisdiction from mainland Pakistan's
    # judiciary and must never collapse into "Supreme Court of Pakistan" / "<Province> High
    # Court" -- this check MUST run before the generic supreme/high-court checks below, because
    # e.g. "AJK Supreme Court" also contains the substring "supreme court". Getting this backwards
    # is what let real AJK Supreme Court judgments get relabeled as "Supreme Court of Pakistan"
    # and surface on mainland-court-specific queries (confirmed via diagnostics.py on 2026-08-23:
    # dataset_category='ajk_scp_vector' records were coming back with court='Supreme Court of
    # Pakistan').
    if any(x in c_lower for x in ("ajk", "azad jammu", "azad kashmir")):
        if "supreme court" in c_lower:
            return "AJK Supreme Court"
        if "high court" in c_lower:
            return "AJK High Court"
        if "service tribunal" in c_lower:
            return "AJK Service Tribunal"
        return "AJK Court (Other)"

    is_sc = any(x in c_lower for x in ("scmr", " pld sc ", " supreme "))
    court_name = re.sub(r'\b\d{4}\s+[A-Za-z]+\s+\d+\b', '', court_name, flags=re.IGNORECASE)
    court_name = re.sub(r'\b\d{4}\b', '', court_name)
    court_name = court_name.replace('-', ' ')
    court_name = re.sub(r'\s+', ' ', court_name).strip()
    c_lower = court_name.lower()
    if not court_name or c_lower in ("not specified", "unknown", "none"):
        return "Supreme Court of Pakistan" if is_sc else "High Court"
    if "supreme court" in c_lower or is_sc:
        return "Supreme Court of Pakistan"

    # Word-order-independent province/city matching. The old version only matched fixed phrase
    # orders ("Balochistan High Court", "High Court Sindh") and missed real variants seen in the
    # actual data -- "High Court Of Balochistan" and "High Court Of Sindh, Circuit Court, Larkana"
    # both fell through to the generic .title() fallback below instead of normalizing, which is
    # why Balochistan HC and some Sindh HC records looked like they didn't exist when filtering
    # on the exact string "Balochistan High Court" / "Sindh High Court" (confirmed via
    # diagnostics.py: 0 exact-match chunks for Balochistan HC despite real data being present).
    if "federal shariat" in c_lower:
        return "Federal Shariat Court"
    if "high court" in c_lower:
        if "sindh" in c_lower or "karachi" in c_lower:
            return "Sindh High Court"
        if "lahore" in c_lower:
            return "Lahore High Court"
        if "peshawar" in c_lower:
            return "Peshawar High Court"
        if "balochistan" in c_lower or "quetta" in c_lower:
            return "Balochistan High Court"
        if "islamabad" in c_lower:
            return "Islamabad High Court"

    return court_name.title()

# Metadata Extraction Helpers

def extract_statutes_and_sections(text: str) -> Tuple[List[str], List[str]]:

    if not text:

        return [], []

    acts_map = {

        "ppc": "PPC (Pakistan Penal Code)",

        "crpc": "CrPC (Code of Criminal Procedure)",

        "cnsa": "CNSA (Control of Narcotic Substances Act)",

        "constitution": "Constitution of Pakistan",

        "registration act": "Registration Act 1908",

        "specific relief": "Specific Relief Act 1877",

        "limitation act": "Limitation Act 1908",

        "family laws": "Muslim Family Laws Ordinance 1961",

        "companies act": "Companies Act 2017"

    }

    found_acts = set()

    text_lower = text.lower()

    for keyword, act_name in acts_map.items():

        if keyword in text_lower:

            found_acts.add(act_name)

    sections = re.findall(r'\b(?:section|sec\.|s\.)\s*(\d+[A-Za-z]?)\b', text, flags=re.IGNORECASE)

    unique_sections = list(set(sections))[:10]

    return list(found_acts), unique_sections



def extract_judges(text: str) -> List[str]:

    if not text:

        return []

    judges = []

    before_match = re.search(r'\bBefore\s+([A-Z][A-Za-z\s\.\,\&]+?)(?:\n|\b(?:JJ|J\.|Member|JJ\.)\b)', text)

    if before_match:

        raw_names = before_match.group(1)

        names = re.split(r'\s*(?:and|\,|\&)\s*', raw_names)

        for name in names:

            cleaned_name = name.strip()

            cleaned_name = re.sub(r'\b(?:Justice|Mr\.|Chief|Hon\'ble)\b', '', cleaned_name, flags=re.IGNORECASE)

            cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()

            if len(cleaned_name) > 3 and cleaned_name.count(' ') >= 1:

                judges.append(cleaned_name)

    j_matches = re.findall(r'\b([A-Z][A-Za-z\s\.]+)\,\s*(?:J\.|JJ\.|CJ\.)', text)

    for name in j_matches:

        cleaned_name = re.sub(r'\b(?:Justice|Mr\.|Chief|Hon\'ble)\b', '', name, flags=re.IGNORECASE)

        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()

        if len(cleaned_name) > 3 and cleaned_name not in judges:

            judges.append(cleaned_name)

    return list(set(judges))[:5]



def detect_bench(judges: List[str]) -> Tuple[str, int]:

    count = len(judges)

    if count == 1:

        return "Single Bench", 1

    elif count == 2:

        return "Division Bench", 2

    elif count >= 3:

        return "Full Bench", count

    return "Single Bench", 1



def extract_outcome(text: str) -> str:

    if not text:

        return "Undetermined"

    text_lower = text.lower()

    excerpt = text_lower[:200] + " " + text_lower[-400:]

    if any(x in excerpt for x in ("petition accepted", "appeal allowed", "suit decreed", "judgment set aside")):

        return "Allowed / Accepted"

    elif any(x in excerpt for x in ("acquitted", "acquittal")):

        return "Acquitted"

    elif any(x in excerpt for x in ("petition dismissed", "appeal dismissed", "suit dismissed", "dismissed")):

        return "Dismissed"

    elif any(x in excerpt for x in ("conviction maintained", "sentenced")):

        return "Conviction Upheld"

    elif any(x in excerpt for x in ("remanded", "case sent back")):

        return "Remanded"

    return "Undetermined"



# Ingestion State Tracker

def load_ingestion_state() -> Dict[str, Any]:

    if os.path.exists(STATE_FILE):

        try:

            with open(STATE_FILE, "r", encoding="utf-8") as f:

                return json.load(f)

        except Exception as e:

            logger.warning(f"Ingestion state ledger corrupted, constructing clean state map: {e}")

    return {"processed_files": {}, "processed_record_hashes": []}



def save_ingestion_state(state: Dict[str, Any]):

    try:

        with open(STATE_FILE, "w", encoding="utf-8") as f:

            json.dump(state, f, indent=2, ensure_ascii=False)

    except Exception as e:

        logger.error(f"Failed to record state tracking ledger: {e}")



# Text Chunking

def split_long_paragraph_by_sentence(paragraph: str, max_tokens: int) -> List[str]:

    sentences = paragraph.replace("\n", " ").split(". ")

    pieces = []

    current = []

    current_tokens = 0



    for i, sentence in enumerate(sentences):

        piece = sentence if sentence.endswith(".") or i == len(sentences) - 1 else sentence + "."

        piece_tokens = count_tokens(piece)



        if piece_tokens > max_tokens:

            if current:

                pieces.append(" ".join(current))

                current, current_tokens = [], 0

            tokens = text_to_tokens(piece)

            for start in range(0, len(tokens), max_tokens):

                pieces.append(tokens_to_text(tokens[start:start + max_tokens]))

            continue



        if current_tokens + piece_tokens > max_tokens:

            pieces.append(" ".join(current))

            current, current_tokens = [piece], piece_tokens

        else:

            current.append(piece)

            current_tokens += piece_tokens



    if current:

        pieces.append(" ".join(current))

    return pieces



def chunk_by_paragraph(text: str,

                       target_tokens: int = TARGET_CHUNK_TOKENS,

                       min_tokens: int = MIN_CHUNK_TOKENS,

                       max_tokens: int = MAX_CHUNK_TOKENS,

                       overlap_tokens: int = OVERLAP_TOKENS) -> List[str]:

    raw_paragraphs = [p.strip() for p in str(text).split("\n") if p.strip()]

    if not raw_paragraphs:

        return []



    paragraphs = []

    for para in raw_paragraphs:

        if count_tokens(para) > max_tokens:

            paragraphs.extend(split_long_paragraph_by_sentence(para, max_tokens))

        else:

            paragraphs.append(para)



    chunks = []

    current_paras = []

    current_tokens = 0



    def flush() -> Tuple[List[str], int]:

        nonlocal current_paras, current_tokens

        if not current_paras:

            return [], 0

        chunk_text = "\n".join(current_paras)

        chunks.append(chunk_text)



        overlap_paras = []

        overlap_tok = 0

        for para in reversed(current_paras):

            p_tok = count_tokens(para)

            if overlap_tok + p_tok > overlap_tokens and overlap_paras:

                break

            overlap_paras.append(para)

            overlap_tok += p_tok

        overlap_paras.reverse()

        return overlap_paras, overlap_tok



    for para in paragraphs:

        para_tokens = count_tokens(para)



        if current_tokens + para_tokens > max_tokens and current_paras:

            overlap_paras, _ = flush()

            current_paras = overlap_paras[:]

            current_tokens = sum(count_tokens(p) for p in current_paras)



        current_paras.append(para)

        current_tokens += para_tokens



        if current_tokens >= target_tokens:

            overlap_paras, _ = flush()

            current_paras = overlap_paras[:]

            current_tokens = sum(count_tokens(p) for p in current_paras)



    if current_paras:

        chunks.append("\n".join(current_paras))



    if len(chunks) > 1:

        chunks = [c for c in chunks if count_tokens(c) >= min_tokens]



    return chunks



# Pinecone Upserts

def upsert_vectors_with_retry(vectors: List[Dict[str, Any]],

                               index,

                               namespace: str,

                               retries: int = MAX_RETRIES,

                               base_delay: float = RETRY_BASE_DELAY) -> bool:

    try:

        async_results = []

        chunk_size = min(len(vectors), 50)

        for idx in range(0, len(vectors), chunk_size):

            sub_batch = vectors[idx:idx + chunk_size]

            res = index.upsert(vectors=sub_batch, namespace=namespace, async_req=True)

            async_results.append(res)

        

        for res in async_results:

            res.get()

        return True

    except Exception as e:

        err_msg = str(e)

        logger.warning(f"Async upsert fallback: {err_msg}. Running synchronous retry...")

        for attempt in range(retries):

            try:

                index.upsert(vectors=vectors, namespace=namespace)

                return True

            except Exception as ex:

                err_msg = str(ex)

                is_transient = any(code in err_msg for code in ["429", "5xx", "timeout", "connection", "unavailable"])

                if is_transient and attempt < retries - 1:

                    delay = base_delay * (2 ** attempt)

                    time.sleep(delay)

                    continue

                else:

                    logger.error(f"Pinecone vector insertion failed: {err_msg}")

                    return False

        return False



def log_failed_vector_batch(vectors: List[Dict[str, Any]], error_msg: str, log_path: str = FAILURE_LOG):

    with open(log_path, "a", encoding="utf-8") as f:

        for vec in vectors:

            f.write(json.dumps({"error": error_msg, "vector_data": vec}, ensure_ascii=False) + "\n")



# Metadata Utilities

def find_content_column(keys: List[str]) -> str:

    common_names = ["full_text", "content", "content_text", "judgment", "judgment_text", "statute_text",

                    "text", "body", "case_description", "headnotes", "section_content", 

                    "maxim", "words", "maxims", "case_summary"]

    for col in common_names:

        if col in keys:

            return col

    return keys[0] if keys else ""



def extract_mapped_column(record_keys: list, target_field: str) -> str:

    aliases = COLUMN_ALIASES.get(target_field, [])

    record_keys_lower = {k.lower().strip(): k for k in record_keys}

    for alias in aliases:

        if alias in record_keys_lower:

            return record_keys_lower[alias]

    return None



def safe_year(value: Any) -> int:

    if pd.isna(value) if hasattr(pd, "isna") else value is None:

        return 2026

    try:

        num = float(value)

        if 1800 <= num <= 2100:

            return int(num)

    except (ValueError, TypeError):

        pass

    match = re.search(r'\b(19\d{2}|20\d{2})\b', str(value))

    if match:

        return int(match.group(1))

    return 2026



# Load and Flatten CSV/JSON files

def load_and_flatten_file(file_path: str) -> List[Dict[str, Any]]:

    file_name = os.path.basename(file_path)

    ext = os.path.splitext(file_name)[1].lower()

    

    records = []

    if ext == ".csv":
        try:
            try:
                df = pd.read_csv(file_path, on_bad_lines="skip", engine="python", encoding="utf-8-sig").dropna(how="all")
                df = df.where(pd.notnull(df), None)
                records = df.to_dict(orient="records")
            except Exception:
                import csv
                csv.field_size_limit(10000000)
                with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    records = [dict(row) for row in reader if row]
        except Exception as e:
            logger.error(f"Could not load CSV file {file_path}: {e}")

    elif ext == ".json":

        try:

            with open(file_path, "r", encoding="utf-8") as f:

                data = json.load(f)

            

            items = data if isinstance(data, list) else [data]

            for item in items:

                if isinstance(item, dict):

                    if "cases" in item and isinstance(item["cases"], list):

                        # Merge group/topic meta with individual nested cases

                        group_meta = {k: v for k, v in item.items() if k != "cases"}

                        for c in item["cases"]:

                            if isinstance(c, dict):

                                records.append({**group_meta, **c})

                    else:

                        records.append(item)

        except Exception as e:

            logger.error(f"Could not load JSON file {file_path}: {e}")

    return records



# Core Ingestion Sequence

def run_ingestion(dry_run: bool = False, resume: bool = False, force_reingest: bool = False):

    pc = Pinecone(api_key=PINECONE_API_KEY)

    try:

        index = pc.Index(INDEX_NAME)

        stats = index.describe_index_stats()

        logger.info(f"Connected to Pinecone Index: '{INDEX_NAME}'. Namespace: '{NAMESPACE}'. Active vectors: {stats.total_vector_count}")

    except PineconeException as e:

        logger.error(f"Failed to access Pinecone index: {e}")

        sys.exit(1)



    state_ledger = load_ingestion_state()

    processed_hashes = set(state_ledger.get("processed_record_hashes", []))



    if resume:

        if not os.path.exists(FAILURE_LOG):

            logger.info(f"No failure track file found at {FAILURE_LOG}. Aborting resume.")

            return

        failed_entries = []

        with open(FAILURE_LOG, "r", encoding="utf-8") as f:

            for line in f:

                line = line.strip()

                if line:

                    try:

                        failed_entries.append(json.loads(line))

                    except json.JSONDecodeError:

                        continue

        if not failed_entries:

            logger.info("Failure tracking log is clean.")

            return

            

        logger.info(f"Resubmitting {len(failed_entries)} failed records from tracking log...")

        recovery_vectors = []

        for entry in failed_entries:

            if "vector_data" in entry and isinstance(entry["vector_data"], dict):

                vec = entry["vector_data"]

                if "id" not in vec:

                    continue

                if len(vec["id"]) > 510:

                    hash_suffix = hashlib.md5(vec["id"].encode("utf-8")).hexdigest()

                    vec["id"] = f"{vec['id'][:470]}_{hash_suffix}"

                recovery_vectors.append(vec)

        total_recovered = 0

        

        for i in range(0, len(recovery_vectors), BATCH_SIZE):

            batch = recovery_vectors[i:i+BATCH_SIZE]

            if not dry_run:

                success = upsert_vectors_with_retry(batch, index, NAMESPACE)

                if success:

                    total_recovered += len(batch)

                else:

                    log_failed_vector_batch(batch, "Terminal recovery line insertion failure.")

                time.sleep(BATCH_COOLDOWN_SECONDS)

        logger.info(f"Recovery complete. Pushed {total_recovered} recovery vectors successfully.")

        return



    # Find both CSV and JSON datasets, preferring _vector duplicates if they exist

    all_files = glob.glob(os.path.join(INPUT_DIR, "*.csv")) + glob.glob(os.path.join(INPUT_DIR, "*.json"))

    data_files = []

    

    # Filter: if both x.csv and x_vector.csv exist, only keep x_vector.csv

    for f in all_files:

        if f.endswith("_vector.csv") or f.endswith("_vector.json"):

            data_files.append(f)

        else:

            # Check if a vector version exists

            vector_version = f.replace(".csv", "_vector.csv").replace(".json", "_vector.json")

            if vector_version not in all_files:

                data_files.append(f)

                

    if not data_files:

        logger.warning(f"Target data folder '{INPUT_DIR}' contains zero valid files.")

        return



    total_chunks_created = 0

    total_records_pushed = 0



    for file_path in data_files:

        file_name = os.path.basename(file_path)

        category_name = os.path.splitext(file_name)[0]

        file_mtime = os.path.getmtime(file_path)

        

        if not force_reingest and file_name in state_ledger["processed_files"]:

            if state_ledger["processed_files"][file_name] == file_mtime:

                logger.info(f"⏩ [STATE MONITOR] File '{file_name}' has already been processed and remains unmodified. Skipping.")

                continue



        logger.info(f"\nProcessing active workspace file: {file_name}")

        records = load_and_flatten_file(file_path)

        if not records:

            logger.warning(f"Skipping empty or failed file: {file_path}")

            continue



        # Extract column names from the first record keys

        record_keys = list(records[0].keys())

        content_col = find_content_column(record_keys)

        logger.info(f"Selected primary text channel: '{content_col}'")



        id_col = extract_mapped_column(record_keys, "case_id")

        court_col = extract_mapped_column(record_keys, "court")

        year_col = extract_mapped_column(record_keys, "year")

        subject_col = extract_mapped_column(record_keys, "subject_matter")

        source_col = extract_mapped_column(record_keys, "source_url")

        title_col = extract_mapped_column(record_keys, "title")

        citation_col = extract_mapped_column(record_keys, "citation")



        candidates = []

        for idx, row in tqdm(enumerate(records), total=len(records), desc="Parsing rows", unit="row"):

            raw_main_text = str(row.get(content_col, "")).strip()

            # Apply PakistaniLegalTextCleaner OCR Pipeline
            clean_text = legal_cleaner.clean(raw_main_text)

            

            # 6. Long Document Hub Cases / Citation Appendices (Drop Bibliography)

            # Drop anything after extreme citation chains usually at the end of huge cases

            if len(clean_text) > 10000:

                match = re.search(r'(?i)((bibliography|references|counsel for the|list of citations|annexures?))', clean_text[-5000:])

                if match:

                    clean_text = clean_text[:match.start() - 5000] + clean_text[-5000:match.start()]

                    

            main_text = clean_text

            if not main_text or main_text.lower() in ("nan", "none", ""):

                continue



            # Deterministic fingerprint to prevent processing identical rows

            row_fingerprint = hashlib.md5(f"{category_name}_{idx}_{main_text[:500]}".encode("utf-8")).hexdigest()

            if not force_reingest and row_fingerprint in processed_hashes:

                continue



            raw_id = row.get(id_col)
            cit_title_val = str(row.get("Citation / Title") or row.get("citation / title") or row.get(title_col) or row.get(citation_col) or "").strip()
            
            if cit_title_val and " - " in cit_title_val:
                parts = cit_title_val.split(" - ", 1)
                citation = parts[0].strip()
                title = parts[1].strip()
            elif cit_title_val:
                citation = cit_title_val
                title = cit_title_val
            else:
                title = str(row.get(title_col, "Untitled Case")) if title_col and row.get(title_col) else "Untitled Case"
                citation = str(row.get(citation_col, "No Citation")) if citation_col and row.get(citation_col) else "No Citation"

            if raw_id and not pd.isna(raw_id) and str(raw_id).lower() not in ("nan", "none", ""):
                case_id = str(raw_id)
            else:
                case_id = generate_case_id(citation, title)

            safe_case_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', case_id)

            court = str(row.get(court_col, f"{category_name} Source")) if court_col else f"{category_name} Source"
            year = safe_year(row.get(year_col, 2026)) if year_col else 2026
            subject_matter = str(row.get(subject_col, category_name))[:400] if subject_col else category_name

            source_url = str(row.get(source_col, "")) if source_col else ""

            # Clean Metadata values on-the-fly

            title = clean_repeated_phrases(title)

            court = clean_court_name(court)



            # Advanced Metadata Enrichment Extractor Calls

            statutes, sections = extract_statutes_and_sections(main_text)

            judges = extract_judges(main_text)

            bench_type, bench_size = detect_bench(judges)

            outcome = extract_outcome(main_text)



            # Dynamic extra fields expansion

            extra_metadata = {}

            for col, val in row.items():

                if col in [content_col, id_col, court_col, year_col, subject_col, source_col, title_col, citation_col]:

                    continue

                if val is None or str(val).lower() in ("nan", "none", ""):

                    continue

                if isinstance(val, (bool, int, float)):

                    extra_metadata[col] = val

                elif isinstance(val, list) and all(isinstance(i, str) for i in val):

                    extra_metadata[col] = val

                else:

                    extra_metadata[col] = str(val)[:500]



            chunks = chunk_by_paragraph(main_text)

            total_chunks_created += len(chunks)



            for chunk_idx, chunk_text in enumerate(chunks):

                meta_block = {

                    "text_preview": chunk_text[:200],

                    "text": chunk_text,

                    "case_id": case_id,

                    "court": court,

                    "year": year,

                    "subject_matter": subject_matter,

                    "source_url": source_url,

                    "title": title,

                    "citation": citation,

                    "chunk_index": chunk_idx,

                    "dataset_category": category_name,

                    "statutes": statutes,

                    "sections": sections,

                    "author_judges": judges,

                    "bench_type": bench_type,

                    "bench_size": bench_size,

                    "outcome": outcome,

                    **extra_metadata

                }

                

                if len(safe_case_id) > 450:

                    hash_suffix = hashlib.md5(safe_case_id.encode("utf-8")).hexdigest()

                    vector_id = f"{safe_case_id[:410]}_{hash_suffix}_chunk_{chunk_idx}"

                else:

                    vector_id = f"{safe_case_id}_chunk_{chunk_idx}"

                candidates.append((vector_id, chunk_text, meta_block, row_fingerprint))



        # Perform batch checks and uploads

        logger.info(f"Built {len(candidates)} total candidate chunks for '{file_name}'")

        

        # 1. Fetch check against Pinecone in batches of 1000 (Pinecone's fetch ID cap)

        to_upload = []

        if not force_reingest and candidates:

            logger.info("Verifying existences in Pinecone index via batch fetches...")

            for start_idx in range(0, len(candidates), 250):

                batch_candidates = candidates[start_idx:start_idx + 250]

                ids_to_check = [c[0] for c in batch_candidates]

                try:

                    fetch_res = index.fetch(ids=ids_to_check, namespace=NAMESPACE)

                    existing_ids = set(fetch_res.vectors.keys())

                except Exception as e:

                    logger.warning(f"Pinecone fetch error (assuming not uploaded): {e}")

                    existing_ids = set()

                

                for cand in batch_candidates:

                    if cand[0] not in existing_ids:

                        to_upload.append(cand)

        else:

            to_upload = candidates



        logger.info(f"Need to embed and upload {len(to_upload)} / {len(candidates)} chunks.")



        # 2. Embed via Voyage AI (concurrent batches) and upsert to Pinecone

        embed_batches = [to_upload[i:i + EMBED_BATCH_SIZE] for i in range(0, len(to_upload), EMBED_BATCH_SIZE)]



        def _process_batch(batch_cand):

            batch_chunks = [c[1] for c in batch_cand]

            batch_meta = [(c[0], c[2]) for c in batch_cand]

            batch_fingerprints = [c[3] for c in batch_cand]



            embeddings = embed_batch_with_retry(batch_chunks)

            if embeddings is None:

                return batch_cand, None, None



            vectors_payload = [

                {"id": v_id, "values": embeddings[i], "metadata": meta}

                for i, (v_id, meta) in enumerate(batch_meta)

            ]

            return batch_cand, vectors_payload, batch_fingerprints



        if not dry_run and embed_batches:

            with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as executor:

                futures = {executor.submit(_process_batch, b): b for b in embed_batches}

                for future in tqdm(as_completed(futures), total=len(futures), desc="Embedding + upserting batches", unit="batch"):

                    batch_cand, vectors_payload, batch_fingerprints = future.result()



                    if vectors_payload is None:

                        failed_ids = [c[0] for c in batch_cand]

                        logger.error(f"Voyage embedding failed after retries for {len(failed_ids)} chunk(s); skipped (will retry on next ingestion run): {failed_ids[:5]}{'...' if len(failed_ids) > 5 else ''}")

                        continue



                    success = upsert_vectors_with_retry(vectors_payload, index, NAMESPACE)

                    if success:

                        total_records_pushed += len(vectors_payload)

                        processed_hashes.update(batch_fingerprints)

                        state_ledger["processed_record_hashes"] = list(processed_hashes)

                        save_ingestion_state(state_ledger)

                    else:

                        log_failed_vector_batch(vectors_payload, "Batch transmission lifecycle failed.")



                    if BATCH_COOLDOWN_SECONDS:

                        time.sleep(BATCH_COOLDOWN_SECONDS)

        else:

            total_records_pushed += len(to_upload)



        if not dry_run:

            state_ledger["processed_files"][file_name] = file_mtime

            state_ledger["processed_record_hashes"] = list(processed_hashes)

            save_ingestion_state(state_ledger)



    logger.info(f"\nProcessing Complete. {total_chunks_created} pieces built, {total_records_pushed} coordinates successfully saved in Pinecone.")



def main():

    parser = argparse.ArgumentParser(description="AMICUS AI - Local Ingestion Engine.")

    parser.add_argument("--dry-run", action="store_true", help="Preview calculations without writing records.")

    parser.add_argument("--resume", action="store_true", help="Restore records from failure tracking buffers.")

    parser.add_argument("--force-reingest", action="store_true", help="Bypass state tracking ledger checks and re-upload everything.")

    parser.add_argument("--debug", action="store_true", help="Activate system diagnostic traces.")

    args = parser.parse_args()



    if args.debug:

        logger.setLevel(logging.DEBUG)



    run_ingestion(dry_run=args.dry_run, resume=args.resume, force_reingest=args.force_reingest)



if __name__ == "__main__":

    main()