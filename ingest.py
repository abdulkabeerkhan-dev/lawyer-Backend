#!/usr/bin/env python3
"""
TO BE NAMED AI LAWYER - Local Open-Source Production Ingestion Engine
Uses BAAI/bge-large-en-v1.5 for local, high-precision vector generation (1024 Dim).
Completely free from external API token caps or monthly subscription blocks.
"""

import os
import sys
import glob
import json
import time
import logging
import argparse
import re
from typing import List, Dict, Any, Tuple
import pandas as pd
import tiktoken
from dotenv import load_dotenv
from pinecone import Pinecone, PineconeException
from sentence_transformers import SentenceTransformer
from tqdm import tqdm



# ----------------------------------------------------------------------
# Environment Configuration
# ----------------------------------------------------------------------
import os
import sys

# Force stable, single-threaded sequential streaming down from Hugging Face
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "180"
os.environ["HF_HUB_ETAG_TIMEOUT"] = "60"


# ----------------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Environment Configuration
# ----------------------------------------------------------------------
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY is missing from your environment configurations!")

# Targets the newly created standard 1024-dim index space
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

# ----------------------------------------------------------------------
# Local Embedding Model Initialization (BAAI/bge-large-en-v1.5)
# ----------------------------------------------------------------------
logger.info("Loading local embedding engine (BAAI/bge-large-en-v1.5)...")
try:
    # Automatically downloads on first run (~1.34 GB) and caches locally
    embedding_model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    logger.info("Local embedding engine initialized successfully. Vector dimensions: 1024")
except Exception as error:
    logger.error(f"Failed to load the local sentence-transformers model: {error}")
    sys.exit(1)

# ----------------------------------------------------------------------
# Tokenizer Engine
# ----------------------------------------------------------------------
_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))

def text_to_tokens(text: str) -> List[int]:
    return _encoder.encode(text)

def tokens_to_text(tokens: List[int]) -> str:
    return _encoder.decode(tokens)

# ----------------------------------------------------------------------
# Context-Preserving Structural Chunking
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# Pinecone Production Ingestion Handlers
# ----------------------------------------------------------------------
def upsert_vectors_with_retry(vectors: List[Dict[str, Any]],
                              index,
                              namespace: str,
                              retries: int = MAX_RETRIES,
                              base_delay: float = RETRY_BASE_DELAY) -> bool:
    """Upserts processed vector structures safely into the production Pinecone standard index."""
    for attempt in range(retries):
        try:
            index.upsert(vectors=vectors, namespace=namespace)
            return True
        except Exception as e:
            err_msg = str(e)
            is_transient = any(code in err_msg for code in ["429", "5xx", "timeout", "connection", "unavailable"])
            
            if is_transient and attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Pinecone API throttling hit: {err_msg}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue
            else:
                logger.error(f"Pinecone vector insertion transaction failed: {err_msg}")
                return False
    return False

def log_failed_vector_batch(vectors: List[Dict[str, Any]], error_msg: str, log_path: str = FAILURE_LOG):
    """Caches generated vectors to a local fail log to prevent re-computation if an upsert drop occurs."""
    with open(log_path, "a", encoding="utf-8") as f:
        for vec in vectors:
            f.write(json.dumps({"error": error_msg, "vector_data": vec}, ensure_ascii=False) + "\n")
    logger.info(f"Successfully cached {len(vectors)} records into local tracking ledger: {log_path}")

# ----------------------------------------------------------------------
# Metadata Parsing Helpers
# ----------------------------------------------------------------------
def find_content_column(df: pd.DataFrame) -> str:
    if CONTENT_COLUMN and CONTENT_COLUMN in df.columns:
        return CONTENT_COLUMN
    common_names = ["content", "content_text", "judgment", "judgment_text", "statute_text",
                    "text", "body", "case_description", "headnotes", "section_content", "maxim"]
    for col in common_names:
        if col in df.columns:
            return col
    str_df = df.astype(str)
    avg_lens = str_df.apply(lambda x: x.str.len().mean())
    return str(avg_lens.idxmax())

def safe_year(value: Any) -> int:
    if pd.isna(value):
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

# ----------------------------------------------------------------------
# Core Execution Engine
# ----------------------------------------------------------------------
def process_csv_files(dry_run: bool = False, resume: bool = False):
    pc = Pinecone(api_key=PINECONE_API_KEY)
    try:
        index = pc.Index(INDEX_NAME)
        stats = index.describe_index_stats()
        logger.info(f"Connected to Standard Pinecone Index: '{INDEX_NAME}'. Extracted active vectors: {stats.total_vector_count}")
    except PineconeException as e:
        logger.error(f"Failed to access the designated Pinecone index deployment: {e}")
        sys.exit(1)

    # Ingestion Recovery Track
    if resume:
        if not os.path.exists(FAILURE_LOG):
            logger.info(f"No failure tracking file found at {FAILURE_LOG}. Aborting resume sequence.")
            return
        with open(FAILURE_LOG, "r", encoding="utf-8") as f:
            failed_entries = [json.loads(line) for line in f if line.strip()]
        if not failed_entries:
            logger.info("Failure tracking log is clean.")
            return
            
        logger.info(f"Resubmitting {len(failed_entries)} records directly from failure trace buffers...")
        recovery_vectors = [entry["vector_data"] for entry in failed_entries]
        total_recovered = 0
        
        for i in range(0, len(recovery_vectors), BATCH_SIZE):
            batch = recovery_vectors[i:i+BATCH_SIZE]
            if not dry_run:
                success = upsert_vectors_with_retry(batch, index, NAMESPACE)
                if success:
                    total_recovered += len(batch)
                else:
                    log_failed_vector_batch(batch, "Terminal recovery lane insertion failure.")
                time.sleep(BATCH_COOLDOWN_SECONDS)
        logger.info(f"Recovery track complete. Pushed {total_recovered} local vector positions safely.")
        return

    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    if not csv_files:
        logger.warning(f"Target data folder '{INPUT_DIR}' contains zero valid spreadsheet schemas.")
        return

    total_chunks_created = 0
    total_records_pushed = 0

    for file_path in csv_files:
        category_name = os.path.basename(file_path).replace(".csv", "")
        logger.info(f"\nProcessing active spreadsheet workspace: {category_name}")

        try:
            df = pd.read_csv(file_path).dropna(how="all")
        except Exception as e:
            logger.error(f"Could not load data container from file {file_path}: {e}")
            continue

        if df.empty:
            logger.warning(f"Skipping empty sheet: {file_path}")
            continue

        content_col = find_content_column(df)
        logger.info(f"Selected primary text data extraction target channel: '{content_col}'")

        # Extract structural tracking tags across varied legal forms
        id_col = next((c for c in ["unique_id", "case_id", "case_no", "statute_id", "section_id"] if c in df.columns), None)
        court_col = next((c for c in ["court", "category", "jurisdiction", "authority"] if c in df.columns), None)
        year_col = next((c for c in ["year", "passed_year", "date", "session_year"] if c in df.columns), None)
        subject_col = next((c for c in ["subject_matter", "legal_domain", "topic", "tags"] if c in df.columns), None)
        source_col = next((c for c in ["source_url", "link", "url"] if c in df.columns), None)

        pending_batch_chunks = []
        pending_batch_metadata = []

        for idx, row in tqdm(df.iterrows(), total=len(df), desc=f"Parsing rows", unit="row"):
            main_text = str(row.get(content_col, "")).strip()
            if not main_text or main_text.lower() in ("nan", "none", ""):
                continue

            case_id = str(row.get(id_col, f"{category_name}-ROW-{idx}"))
            safe_case_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', case_id)
            court = str(row.get(court_col, f"{category_name} Source"))
            year = safe_year(row.get(year_col, 2026))
            subject_matter = str(row.get(subject_col, category_name))[:400]
            source_url = str(row.get(source_col, "https://pakistanlawsite.com/"))

            # --- DYNAMIC FIELD EXPANSION GENERATOR ---
            extra_metadata = {}
            for col in df.columns:
                if col in [content_col, id_col, court_col, year_col, subject_col, source_col]:
                    continue  # Secure critical core references from being overridden
                
                val = row[col]
                if pd.isna(val) or str(val).lower() in ("nan", "none", ""):
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
                    "text_preview": chunk_text[:200], # Mandated system citation snippet match layout
                    "case_id": case_id,
                    "court": court,
                    "year": year,
                    "subject_matter": subject_matter,
                    "source_url": source_url,
                    "chunk_index": chunk_idx,
                    "dataset_category": category_name,
                    **extra_metadata
                }
                
                pending_batch_chunks.append(chunk_text)
                pending_batch_metadata.append((f"{safe_case_id}_chunk_{chunk_idx}", meta_block))

                if len(pending_batch_chunks) >= BATCH_SIZE:
                    if not dry_run:
                        # Compute embeddings locally via sentence-transformers in one batch call
                        embeddings = embedding_model.encode(pending_batch_chunks, convert_to_numpy=True).tolist()
                        
                        vectors_payload = []
                        for i, (vector_id, meta) in enumerate(pending_batch_metadata):
                            vectors_payload.append({
                                "id": vector_id,
                                "values": embeddings[i],
                                "metadata": meta
                            })
                        
                        success = upsert_vectors_with_retry(vectors_payload, index, NAMESPACE)
                        if success:
                            total_records_pushed += len(vectors_payload)
                        else:
                            log_failed_vector_batch(vectors_payload, "Batch transmission lifecycle failed.")
                        time.sleep(BATCH_COOLDOWN_SECONDS)
                    else:
                        total_records_pushed += len(pending_batch_chunks)

                    pending_batch_chunks = []
                    pending_batch_metadata = []

        if pending_batch_chunks:
            if not dry_run:
                embeddings = embedding_model.encode(pending_batch_chunks, convert_to_numpy=True).tolist()
                vectors_payload = []
                for i, (vector_id, meta) in enumerate(pending_batch_metadata):
                    vectors_payload.append({
                        "id": vector_id,
                        "values": embeddings[i],
                        "metadata": meta
                    })
                success = upsert_vectors_with_retry(vectors_payload, index, NAMESPACE)
                if success:
                    total_records_pushed += len(vectors_payload)
                else:
                    log_failed_vector_batch(vectors_payload, "Tail block transmission lifecycle failed.")
            else:
                total_records_pushed += len(pending_batch_chunks)

    logger.info(f"\nProcessing Complete. {total_chunks_created} pieces built, {total_records_pushed} coordinates successfully saved in Pinecone.")

# ----------------------------------------------------------------------
# Driver Entry Verification
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="TO BE NAMED AI LAWYER - Local Open-Source Ingestion Engine Driver.")
    parser.add_argument("--dry-run", action="store_true", help="Preview calculations without writing records.")
    parser.add_argument("--resume", action="store_true", help="Restore records from failure tracking buffers.")
    parser.add_argument("--debug", action="store_true", help="Activate system diagnostic traces.")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    process_csv_files(dry_run=args.dry_run, resume=args.resume)

if __name__ == "__main__":
    main()