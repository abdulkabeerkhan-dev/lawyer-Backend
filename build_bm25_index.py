#!/usr/bin/env python3
"""
Build Global BM25 Index across all 29,547 vectors in Pinecone namespace 'judgments'.
Serializes the fitted BM25 index and metadata into bm25_index.pkl for instantaneous startup.
"""

import os
import sys
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("build_bm25")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.getenv("PINECONE_NAMESPACE", "judgments")

if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY is missing from environment.")
    sys.exit(1)

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bm25_index.pkl")
CACHE_IDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "judgments_ids_cache.json")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)


def get_all_vector_ids() -> List[str]:
    """Retrieve all vector IDs in namespace 'judgments', caching them locally."""
    if os.path.exists(CACHE_IDS_FILE):
        try:
            with open(CACHE_IDS_FILE, "r", encoding="utf-8") as f:
                cached_ids = json.load(f)
            if len(cached_ids) >= 29000:
                logger.info(f"Loaded {len(cached_ids):,} vector IDs from cache ({CACHE_IDS_FILE})")
                return cached_ids
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

    logger.info(f"Listing all vectors from Pinecone namespace '{NAMESPACE}'...")
    all_ids = []
    max_retries = 3

    for retry in range(max_retries):
        try:
            all_ids = []
            for page in index.list(namespace=NAMESPACE):
                for item in page:
                    vid = item if isinstance(item, str) else getattr(item, 'id', str(item))
                    all_ids.append(vid)
            break
        except Exception as e:
            logger.warning(f"Error listing vectors (attempt {retry+1}/{max_retries}): {e}")
            time.sleep(2)

    logger.info(f"Enumerated {len(all_ids):,} vector IDs in namespace '{NAMESPACE}'")
    if all_ids:
        try:
            with open(CACHE_IDS_FILE, "w", encoding="utf-8") as f:
                json.dump(all_ids, f)
        except Exception as e:
            logger.warning(f"Could not write cache: {e}")

    return all_ids


def fetch_batch_metadata(batch_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch vector text and metadata for a batch of IDs with retries."""
    for attempt in range(4):
        try:
            res = index.fetch(ids=batch_ids, namespace=NAMESPACE)
            vectors_map = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {}) or {}
            docs = []
            for vid, vdata in vectors_map.items():
                meta = vdata.get("metadata", {}) if isinstance(vdata, dict) else getattr(vdata, "metadata", {}) or {}
                text = meta.get("text") or meta.get("text_content") or meta.get("preview") or ""
                if text:
                    docs.append({
                        "id": str(vid),
                        "text": text,
                        "metadata": {
                            "case_id": meta.get("case_id") or meta.get("canonical_id") or vid,
                            "citation": meta.get("citation") or meta.get("neutral_citation") or "",
                            "case_title": meta.get("case_title") or meta.get("title") or "",
                            "court": meta.get("court") or meta.get("court_name") or "",
                            "decision_date": meta.get("decision_date") or meta.get("year") or "",
                            "sections": meta.get("sections") or [],
                            "statutes": meta.get("statutes") or [],
                            "chunk_index": meta.get("chunk_index", 0),
                            "text": text[:3500]
                        }
                    })
            return docs
        except Exception as e:
            time.sleep(1 + attempt * 1.5)
            if attempt == 3:
                logger.error(f"Failed fetching batch ({len(batch_ids)} IDs) after retries: {e}")
                return []
    return []


def main():
    start_time = time.time()
    logger.info("==================================================")
    logger.info("  GLOBAL BM25 INDEX BUILDER - PINECONE JUDGMENTS  ")
    logger.info("==================================================")

    all_ids = get_all_vector_ids()
    if not all_ids:
        logger.error("No vector IDs found! Aborting.")
        sys.exit(1)

    batch_size = 100
    batches = [all_ids[i:i + batch_size] for i in range(0, len(all_ids), batch_size)]
    total_batches = len(batches)
    logger.info(f"Fetching metadata for {len(all_ids):,} vectors across {total_batches} batches (16 workers)...")

    all_docs = []
    completed_batches = 0
    max_workers = 16

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_batch_metadata, b): i for i, b in enumerate(batches)}
        for future in as_completed(futures):
            batch_docs = future.result()
            all_docs.extend(batch_docs)
            completed_batches += 1
            if completed_batches % 30 == 0 or completed_batches == total_batches:
                pct = (completed_batches / total_batches) * 100
                logger.info(f"Progress: {completed_batches}/{total_batches} batches ({pct:.1f}%) — {len(all_docs):,} valid documents fetched")

    logger.info(f"Metadata fetch complete in {time.time() - start_time:.1f}s. Total documents with text: {len(all_docs):,}")

    from hybrid_search import BM25Index

    logger.info("Tokenizing legal corpus and fitting BM25 index...")
    fit_start = time.time()
    bm25_idx = BM25Index()
    bm25_idx.fit(all_docs)
    logger.info(f"BM25 fitting finished in {time.time() - fit_start:.1f}s")

    logger.info(f"Saving BM25 index to {OUTPUT_FILE}...")
    bm25_idx.save(OUTPUT_FILE)

    total_time = time.time() - start_time
    logger.info(f"SUCCESS: Global BM25 index successfully generated in {total_time:.1f}s! ({len(all_docs):,} docs)")


if __name__ == "__main__":
    main()
