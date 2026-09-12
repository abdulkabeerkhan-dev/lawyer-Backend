#!/usr/bin/env python3
"""
AMICUS AI - Phase 2 Blue-Green Pinecone Re-indexing Engine & Namespace Purger

1. Connects to PostgreSQL Master Ledger (public.judgments / public.full_judgments).
2. Deterministically chunks judgment text (1,000 chars, 150 char overlap).
3. Generates deterministic vector IDs: {canonical_id}_chk_{i}.
4. Embeds chunks via Voyage AI (voyage-law-2, 1024 Dim) in concurrent batches.
5. Upserts clean vectors into isolated namespace 'clean-v1'.
6. Option --purge-old wipes legacy dirty vector namespaces ('judgments', 'production').
"""

import os
import sys
import time
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pinecone import Pinecone
import voyageai
from supabase import create_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("clean_reindex")

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
TARGET_NAMESPACE = os.environ.get("TARGET_NAMESPACE", "clean-v1")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-law-2")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY missing from environment.")
    sys.exit(1)

if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY missing from environment.")
    sys.exit(1)

if not VOYAGE_API_KEY:
    logger.error("VOYAGE_API_KEY missing from environment.")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
EMBED_BATCH_SIZE = 128
EMBED_CONCURRENCY = 10
PINECONE_BATCH_SIZE = 100

def chunk_text_deterministically(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Chunks text into slices of chunk_size characters with specified overlap."""
    if not text:
        return []
    clean_text = str(text).strip()
    if len(clean_text) <= chunk_size:
        return [clean_text]

    chunks = []
    start = 0
    stride = chunk_size - overlap

    while start < len(clean_text):
        end = start + chunk_size
        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += stride
        if end >= len(clean_text):
            break

    return chunks

def embed_texts_with_retry(texts: List[str], retries: int = 3, base_delay: float = 3.0) -> Optional[List[List[float]]]:
    """Generates 1024-dim Voyage embeddings for document chunks with exponential backoff."""
    for attempt in range(retries):
        try:
            res = voyage_client.embed(texts, model=VOYAGE_MODEL, input_type="document")
            return res.embeddings
        except Exception as e:
            err_msg = str(e)
            is_transient = any(c in err_msg for c in ["429", "500", "502", "503", "504", "timeout", "connection"])
            if is_transient and attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Voyage API transient error (attempt {attempt + 1}/{retries}): {err_msg}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue
            logger.error(f"Voyage embedding request failed permanently: {err_msg}")
            return None
    return None

def upsert_vectors_to_pinecone(vectors: List[Dict[str, Any]], namespace: str = TARGET_NAMESPACE) -> bool:
    """Upserts vector payloads to specified Pinecone namespace in batches."""
    try:
        for idx in range(0, len(vectors), PINECONE_BATCH_SIZE):
            batch = vectors[idx:idx + PINECONE_BATCH_SIZE]
            pinecone_index.upsert(vectors=batch, namespace=namespace)
        return True
    except Exception as e:
        logger.error(f"Pinecone upsert error into namespace '{namespace}': {e}")
        return False

def purge_legacy_namespaces(namespaces_to_purge: List[str]):
    """Purges old contaminated namespaces from Pinecone."""
    logger.info("==================================================================")
    logger.info("   PURGING LEGACY DIRTY PINECONE NAMESPACES                     ")
    logger.info("==================================================================")
    
    stats = pinecone_index.describe_index_stats()
    existing_ns = stats.namespaces if hasattr(stats, 'namespaces') else {}

    for ns in namespaces_to_purge:
        if ns in existing_ns:
            logger.info(f"🔥 Purging namespace '{ns}' ({existing_ns[ns].vector_count:,} vectors)...")
            try:
                pinecone_index.delete(delete_all=True, namespace=ns)
                logger.info(f"✅ Successfully purged namespace '{ns}'.")
            except Exception as e:
                logger.error(f"❌ Failed to purge namespace '{ns}': {e}")
        else:
            logger.info(f"ℹ️ Namespace '{ns}' not found or already empty.")

def run_reindex_pipeline(target_namespace: str = TARGET_NAMESPACE):
    logger.info("==================================================================")
    logger.info(f"   BLUE-GREEN RE-INDEXING MASTER LEDGER TO PINECONE ('{target_namespace}') ")
    logger.info("==================================================================")
    
    start_time = time.time()

    # 1. Fetch records from PostgreSQL Master Ledger (full_judgments / judgments)
    try:
        res = supabase.table("full_judgments").select("*").execute()
        records = res.data or []
        logger.info(f"✅ Retrieved {len(records)} records from PostgreSQL Master Ledger.")
    except Exception as e:
        logger.error(f"Failed to query master database: {e}")
        return

    all_chunks_to_embed = []
    
    for rec in records:
        rec_id = str(rec.get("id") or "")
        case_id = str(rec.get("case_id") or rec.get("canonical_id") or "SC_GEN_0_2026")
        title = str(rec.get("case_title") or "Untitled Case")
        court = str(rec.get("court_name") or rec.get("court") or "Supreme Court of Pakistan")
        citation = str(rec.get("neutral_citation") or rec.get("reported_citation") or "")
        decision_date = str(rec.get("decision_date") or "")
        full_text = str(rec.get("full_text") or rec.get("raw_text") or "")
        docket_num = str(rec.get("docket_number") or case_id)

        if not full_text or len(full_text.strip()) < 30:
            continue

        text_chunks = chunk_text_deterministically(full_text, CHUNK_SIZE, CHUNK_OVERLAP)

        for i, chunk in enumerate(text_chunks):
            vector_id = f"{case_id}_chk_{i}"
            meta = {
                "judgment_id": rec_id,
                "canonical_id": case_id,
                "case_id": case_id,
                "citation": citation,
                "case_title": title,
                "court": court,
                "docket_number": docket_num,
                "decision_date": decision_date,
                "chunk_index": i,
                "text": chunk[:2000]
            }
            all_chunks_to_embed.append({
                "id": vector_id,
                "text": chunk,
                "metadata": meta
            })

    total_chunks = len(all_chunks_to_embed)
    logger.info(f"📊 Total deterministic chunks generated for embedding: {total_chunks:,}")

    if total_chunks == 0:
        logger.warning("No chunks available for embedding. Exiting.")
        return

    # 2. Parallel Embedding & Upsert Loop
    embedded_vectors_count = 0

    batch_groups = []
    for i in range(0, total_chunks, EMBED_BATCH_SIZE):
        batch_groups.append(all_chunks_to_embed[i:i + EMBED_BATCH_SIZE])

    logger.info(f"⚡ Processing {len(batch_groups)} embedding batches (concurrency: {EMBED_CONCURRENCY})...")

    def process_single_batch(batch_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        texts = [item["text"] for item in batch_items]
        embeddings = embed_texts_with_retry(texts)
        if not embeddings or len(embeddings) != len(batch_items):
            logger.error(f"Failed to generate embeddings for batch of {len(batch_items)} items.")
            return []

        vectors = []
        for item, emb in zip(batch_items, embeddings):
            vectors.append({
                "id": item["id"],
                "values": emb,
                "metadata": item["metadata"]
            })
        return vectors

    with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as executor:
        futures = {executor.submit(process_single_batch, b): b for b in batch_groups}
        for future in as_completed(futures):
            vectors = future.result()
            if vectors:
                success = upsert_vectors_to_pinecone(vectors, namespace=target_namespace)
                if success:
                    embedded_vectors_count += len(vectors)
                    logger.info(f"  [PROGRESS] Upserted {embedded_vectors_count:,} / {total_chunks:,} vectors into '{target_namespace}'...")

    elapsed = time.time() - start_time
    logger.info(f"==================================================================")
    logger.info(f"✅ BLUE-GREEN RE-INDEX COMPLETE: {embedded_vectors_count:,} vectors in '{target_namespace}' ({elapsed:.2f}s)!")
    logger.info(f"==================================================================")

def main():
    parser = argparse.ArgumentParser(description="Blue-Green Pinecone Re-index to clean-v1 & Namespace Purger")
    parser.add_argument("--namespace", type=str, default=TARGET_NAMESPACE, help="Target Pinecone namespace (default: clean-v1)")
    parser.add_argument("--purge-old", action="store_true", help="Purge legacy dirty namespaces ('judgments', 'production')")
    args = parser.parse_args()

    if args.purge_old:
        purge_legacy_namespaces(["judgments", "production"])

    run_reindex_pipeline(target_namespace=args.namespace)

if __name__ == "__main__":
    main()
