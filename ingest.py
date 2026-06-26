#!/usr/bin/env python3
"""
AMICUS AI - Local Open-Source Production Ingestion Engine
Optimized for Idempotency State Tracking, Multi-Variant Schema Normalization, and Native JSON support.
Uses BAAI/bge-large-en-v1.5 for local, high-precision vector generation (1024 Dim).
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
from typing import List, Dict, Any, Tuple, Set, Optional
import pandas as pd
import tiktoken
from dotenv import load_dotenv
from pinecone import Pinecone, PineconeException
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Force stable, single-threaded sequential streaming down from Hugging Face
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "180"
os.environ["HF_HUB_ETAG_TIMEOUT"] = "60"

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

TARGET_CHUNK_TOKENS = int(os.getenv("TARGET_CHUNK_TOKENS", "500"))
MIN_CHUNK_TOKENS = int(os.getenv("MIN_CHUNK_TOKENS", "200"))
MAX_CHUNK_TOKENS = int(os.getenv("MAX_CHUNK_TOKENS", "600"))
OVERLAP_TOKENS = int(os.getenv("OVERLAP_TOKENS", "50"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))  
BATCH_COOLDOWN_SECONDS = float(os.getenv("BATCH_COOLDOWN_SECONDS", "0.5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "5.0"))

CONTENT_COLUMN = os.getenv("CONTENT_COLUMN")       
INPUT_DIR = os.getenv("INPUT_DIR", "datasets")
FAILURE_LOG = os.getenv("FAILURE_LOG", "failed_batches.jsonl")
STATE_FILE = os.getenv("INGESTION_STATE_FILE", "ingestion_state.json")

# Metadata Schema Column Mapping Aliases
COLUMN_ALIASES = {
    "case_id": ["unique_id", "case_id", "case_no", "statute_id", "section_id", "id", "serial_no", "reference_id"],
    "court": ["court", "category", "jurisdiction", "authority", "bench", "court_name", "tribunal"],
    "year": ["year", "passed_year", "date", "session_year", "judgment_year", "decision_date"],
    "subject_matter": ["subject_matter", "legal_domain", "topic", "tags", "subject", "summary", "headnotes", "keywords"],
    "source_url": ["source_url", "link", "url", "source_link", "website"],
    "title": ["case_title", "title", "subject_title", "topic_title"],
    "citation": ["citation", "citation_no", "volume"]
}

# Embedding Model Initialization (1024 Dim)
logger.info("Loading local embedding engine (BAAI/bge-large-en-v1.5)...")
try:
    embedding_model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    logger.info("Local embedding engine initialized successfully. Vector dimensions: 1024")
except Exception as error:
    logger.error(f"Failed to load the local sentence-transformers model: {error}")
    sys.exit(1)

_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))

def text_to_tokens(text: str) -> List[int]:
    return _encoder.encode(text)

def tokens_to_text(tokens: List[int]) -> str:
    return _encoder.decode(tokens)

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
    if "karachi high court sindh" in c_lower or "sindh high court" in c_lower or "high court sindh" in c_lower:
        return "Sindh High Court"
    if "lahore high court" in c_lower or "high court lahore" in c_lower:
        return "Lahore High Court"
    if "peshawar high court" in c_lower:
        return "Peshawar High Court"
    if "balochistan high court" in c_lower:
        return "Balochistan High Court"
    if "islamabad high court" in c_lower:
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
    common_names = ["content", "content_text", "judgment", "judgment_text", "statute_text",
                    "text", "body", "case_description", "headnotes", "section_content", 
                    "maxim", "words", "maxims", "case_summary"]
    for col in common_names:
        if col in keys:
            return col
    return keys[0] if keys else ""

def extract_mapped_column(keys: List[str], standard_key: str) -> Optional[str]:
    aliases = COLUMN_ALIASES.get(standard_key, [])
    for col in keys:
        if str(col).lower().strip() in aliases:
            return str(col)
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
            df = pd.read_csv(file_path).dropna(how="all")
            # Convert NaN to None
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")
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
        with open(FAILURE_LOG, "r", encoding="utf-8") as f:
            failed_entries = [json.loads(line) for line in f if line.strip()]
        if not failed_entries:
            logger.info("Failure tracking log is clean.")
            return
            
        logger.info(f"Resubmitting {len(failed_entries)} failed records from tracking log...")
        recovery_vectors = [entry["vector_data"] for entry in failed_entries]
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

    # Find both CSV and JSON datasets
    data_files = glob.glob(os.path.join(INPUT_DIR, "*.csv")) + glob.glob(os.path.join(INPUT_DIR, "*.json"))
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

        pending_batch_chunks = []
        pending_batch_metadata = []
        pending_batch_hashes = []

        for idx, row in tqdm(enumerate(records), total=len(records), desc="Parsing rows", unit="row"):
            main_text = str(row.get(content_col, "")).strip()
            if not main_text or main_text.lower() in ("nan", "none", ""):
                continue

            # Deterministic fingerprint to prevent processing identical rows
            row_fingerprint = hashlib.md5(f"{category_name}_{idx}_{main_text[:500]}".encode("utf-8")).hexdigest()
            if not force_reingest and row_fingerprint in processed_hashes:
                continue

            case_id = str(row.get(id_col, f"{category_name}-ROW-{idx}")) if id_col else f"{category_name}-ROW-{idx}"
            safe_case_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', case_id)
            court = str(row.get(court_col, f"{category_name} Source")) if court_col else f"{category_name} Source"
            year = safe_year(row.get(year_col, 2026)) if year_col else 2026
            subject_matter = str(row.get(subject_col, category_name))[:400] if subject_col else category_name
            source_url = str(row.get(source_col, "https://pakistanlawsite.com/")) if source_col else "https://pakistanlawsite.com/"
            title = str(row.get(title_col, "Untitled Case")) if title_col and row.get(title_col) else "Untitled Case"
            citation = str(row.get(citation_col, "No Citation")) if citation_col and row.get(citation_col) else "No Citation"

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
                
                vector_id = f"{safe_case_id}_chunk_{chunk_idx}"

                # Idempotency Check: check if already exists in Pinecone before generating embeddings
                if not force_reingest:
                    try:
                        res = index.query(
                            vector=[0.0] * 1024,
                            top_k=1,
                            filter={"case_id": {"$eq": case_id}, "chunk_index": {"$eq": chunk_idx}},
                            namespace=NAMESPACE
                        )
                        if res.matches:
                            # Already exists in Pinecone, skip generating embeddings and uploading
                            continue
                    except Exception:
                        pass
                
                pending_batch_chunks.append(chunk_text)
                pending_batch_metadata.append((vector_id, meta_block))
                pending_batch_hashes.append(row_fingerprint)

                if len(pending_batch_chunks) >= BATCH_SIZE:
                    if not dry_run:
                        embeddings = embedding_model.encode(pending_batch_chunks, convert_to_numpy=True).tolist()
                        vectors_payload = []
                        for i, (v_id, meta) in enumerate(pending_batch_metadata):
                            vectors_payload.append({
                                "id": v_id,
                                "values": embeddings[i],
                                "metadata": meta
                            })
                        
                        success = upsert_vectors_with_retry(vectors_payload, index, NAMESPACE)
                        if success:
                            total_records_pushed += len(vectors_payload)
                            processed_hashes.update(pending_batch_hashes)
                            state_ledger["processed_record_hashes"] = list(processed_hashes)
                            save_ingestion_state(state_ledger)
                        else:
                            log_failed_vector_batch(vectors_payload, "Batch transmission lifecycle failed.")
                    else:
                        total_records_pushed += len(pending_batch_chunks)

                    pending_batch_chunks = []
                    pending_batch_metadata = []
                    pending_batch_hashes = []

        if pending_batch_chunks:
            if not dry_run:
                embeddings = embedding_model.encode(pending_batch_chunks, convert_to_numpy=True).tolist()
                vectors_payload = []
                for i, (v_id, meta) in enumerate(pending_batch_metadata):
                    vectors_payload.append({
                        "id": v_id,
                        "values": embeddings[i],
                        "metadata": meta
                    })
                success = upsert_vectors_with_retry(vectors_payload, index, NAMESPACE)
                if success:
                    total_records_pushed += len(vectors_payload)
                    processed_hashes.update(pending_batch_hashes)
                else:
                    log_failed_vector_batch(vectors_payload, "Tail block transmission lifecycle failed.")
            else:
                total_records_pushed += len(pending_batch_chunks)

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