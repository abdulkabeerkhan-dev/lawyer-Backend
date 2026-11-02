"""
scripts/batch_enrich_and_index_full.py

Scalable Batch Legal Judgment Segmentation, Embedding & Indexing Pipeline.
Processes Pakistani court judgments from Supabase in tranches:
1. Checkpoint resilience: Tracks indexed case_ids in data/batch_indexing_checkpoint.log.
2. Structural segmentation: Extracts Headnote, Ratio Decidendi, Facts, Domain, and Statutes.
3. Voyage AI Embeddings: Embeds segment texts using voyage-law-2 (1024-d).
4. Pinecone Upsert: Upserts segmented vectors to namespace 'segmented-v1' with rich filter metadata.
5. Staging: Appends structured updates to data/enriched_judgments_staged.jsonl.
"""

import os
import sys
import json
import time
import argparse
import requests
from typing import List, Dict, Any, Set
from dotenv import load_dotenv

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

load_dotenv(os.path.join(WORKSPACE_DIR, ".env"))

from legal_ai.config import get_supabase_client, get_pinecone_index
from core.structural_judgment_segmenter import StructuralJudgmentSegmenter

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-law-2")
TARGET_NAMESPACE = os.getenv("PINECONE_SEGMENTED_NAMESPACE", "segmented-v1")

DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
CHECKPOINT_PATH = os.path.join(DATA_DIR, "batch_indexing_checkpoint.log")
STAGED_JSONL_PATH = os.path.join(DATA_DIR, "enriched_judgments_staged.jsonl")


def load_checkpoint() -> Set[str]:
    """Loads set of already indexed case_ids."""
    if not os.path.exists(CHECKPOINT_PATH):
        return set()
    completed = set()
    with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            cid = line.strip()
            if cid:
                completed.add(cid)
    return completed


def append_checkpoint(case_ids: List[str]) -> None:
    """Appends newly completed case_ids to checkpoint with disk flush."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CHECKPOINT_PATH, "a", encoding="utf-8") as f:
        for cid in case_ids:
            f.write(f"{cid}\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


def embed_batch_voyage(texts: List[str], max_retries: int = 5) -> List[List[float]]:
    """Embeds a batch of texts using Voyage AI voyage-law-2 with exponential backoff."""
    if not VOYAGE_API_KEY:
        raise RuntimeError("VOYAGE_API_KEY is not set.")

    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }

    cleaned_texts = [t[:16000].strip() if t else "court judgment" for t in texts]

    payload = {
        "input": cleaned_texts,
        "model": VOYAGE_MODEL,
        "input_type": "document"
    }

    delay = 2.0
    for attempt in range(max_retries):
        try:
            resp = requests.post(VOYAGE_API_URL, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            elif resp.status_code in (429, 500, 502, 503, 504):
                print(f"  [Voyage HTTP {resp.status_code}] Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
                time.sleep(delay)
                delay = min(delay * 1.5, 60.0)
            else:
                raise RuntimeError(f"Voyage API Error {resp.status_code}: {resp.text}")
        except requests.exceptions.RequestException as e:
            print(f"  [Voyage Network Error] {e}. Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
            time.sleep(delay)
            delay = min(delay * 1.5, 60.0)

    raise RuntimeError(f"Failed to embed batch with Voyage API after {max_retries} attempts.")


def run_batch_enrichment(limit: int = 200, batch_size: int = 30, landmark_only: bool = False, dry_run: bool = False):
    print("=" * 70)
    print("LEGAL RAG RETRIEVAL - BATCH ENRICHMENT & SEGMENTED INDEXING")
    print("=" * 70)
    print(f"Target Namespace: '{TARGET_NAMESPACE}' | Limit: {limit} | Batch Size: {batch_size}")
    print(f"Landmark Only: {landmark_only} | Dry Run: {dry_run}")

    sb = get_supabase_client()
    pc_index = get_pinecone_index() if not dry_run else None
    if not sb:
        raise RuntimeError("Failed to connect to Supabase.")
    if not dry_run and not pc_index:
        raise RuntimeError("Failed to connect to Pinecone.")

    indexed_checkpoint = load_checkpoint()
    print(f"[*] Already indexed according to checkpoint: {len(indexed_checkpoint)} cases.")

    # Fetch candidate cases
    print("[*] Querying Supabase for unindexed candidate cases...")
    q = sb.table("full_judgments").select(
        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
    )
    if landmark_only:
        q = q.or_("neutral_citation.ilike.%SCMR%,neutral_citation.ilike.%PLD%")

    records_to_process = []
    page_size = min(limit * 2, 500)
    offset = 0

    while len(records_to_process) < limit:
        res = q.range(offset, offset + page_size - 1).execute()
        rows = res.data or []
        if not rows:
            break

        for r in rows:
            cid = r.get("case_id")
            ft = r.get("full_text") or ""
            if cid and cid not in indexed_checkpoint and len(ft.split()) >= 40:
                records_to_process.append(r)
                if len(records_to_process) >= limit:
                    break

        offset += page_size
        print(f"    Scanned {offset} rows; candidate queue: {len(records_to_process)}/{limit}", flush=True)

    print(f"[*] Total cases selected for this run: {len(records_to_process)}")
    if not records_to_process:
        print("[*] No new cases to process. Checkpoint is up to date!")
        return

    # Process in batches
    total_processed_cases = 0
    total_upserted_vectors = 0
    t0 = time.time()

    for i in range(0, len(records_to_process), batch_size):
        chunk = records_to_process[i:i + batch_size]
        batch_vectors = []
        batch_cids = []
        staged_rows = []

        for rec in chunk:
            cid = rec["case_id"]
            ft = rec.get("full_text") or ""
            segmented = StructuralJudgmentSegmenter.segment_judgment(ft, metadata=rec)

            staged_rows.append({
                "case_id": cid,
                "neutral_citation": rec.get("neutral_citation"),
                "case_title": rec.get("case_title"),
                "court_name": rec.get("court_name"),
                "decision_date": rec.get("decision_date"),
                "domain": segmented["domain"],
                "subdomain": segmented["subdomain"],
                "statutes_cited": segmented["statutes_cited"],
                "provisions_cited": segmented["provisions_cited"],
                "headnote": segmented["headnote_segment"],
                "ratio_decidendi": segmented["ratio_decidendi_segment"],
                "facts_and_order": segmented["facts_and_order_segment"]
            })

            for p_seg in segmented["pinecone_segments"]:
                meta = dict(p_seg["metadata"])
                meta["text"] = p_seg["text"][:1200]
                batch_vectors.append({
                    "id": p_seg["segment_id"],
                    "text_to_embed": p_seg["text"],
                    "metadata": meta
                })

            batch_cids.append(cid)

        # Stage to JSONL
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STAGED_JSONL_PATH, "a", encoding="utf-8") as f:
            for s_row in staged_rows:
                f.write(json.dumps(s_row, ensure_ascii=False) + "\n")

        # Embed & Upsert if not dry-run
        if not dry_run and batch_vectors:
            embed_texts = [v["text_to_embed"] for v in batch_vectors]
            embeddings = embed_batch_voyage(embed_texts)
            
            upsert_payloads = []
            for v, emb in zip(batch_vectors, embeddings):
                upsert_payloads.append({
                    "id": v["id"],
                    "values": emb,
                    "metadata": v["metadata"]
                })

            # Upsert to Pinecone
            pc_index.upsert(vectors=upsert_payloads, namespace=TARGET_NAMESPACE)
            total_upserted_vectors += len(upsert_payloads)

        append_checkpoint(batch_cids)
        total_processed_cases += len(chunk)

        elapsed = time.time() - t0
        cases_per_sec = total_processed_cases / elapsed if elapsed > 0 else 0
        print(f"  [Batch {i // batch_size + 1}] Processed {total_processed_cases}/{len(records_to_process)} cases | Vectors upserted: {total_upserted_vectors} | {cases_per_sec:.2f} cases/s", flush=True)

    print("\n" + "=" * 70)
    print(f"BATCH COMPLETE! Cases processed: {total_processed_cases} | Vectors upserted: {total_upserted_vectors}")
    print(f"Checkpoint saved to: {CHECKPOINT_PATH}")
    print(f"Staged records appended to: {STAGED_JSONL_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="Total cases to process in this run")
    parser.add_argument("--batch-size", type=int, default=25, help="Batch size for embedding and upserting")
    parser.add_argument("--landmark-only", action="store_true", help="Only process SCMR and PLD cases")
    parser.add_argument("--dry-run", action="store_true", help="Segment and stage without embedding/upserting")
    args = parser.parse_args()

    run_batch_enrichment(limit=args.limit, batch_size=args.batch_size, landmark_only=args.landmark_only, dry_run=args.dry_run)
