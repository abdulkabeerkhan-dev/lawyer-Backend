"""
scripts/batch_enrich_and_index_full.py

Scalable Batch Legal Judgment Segmentation, Embedding & Indexing Pipeline.
Streams Pakistani court judgments from Supabase in keyset-paginated tranches:
1. Checkpoint resilience: Tracks indexed case_ids in data/batch_indexing_checkpoint.log
   and keyset UUID cursor in data/batch_cursor.json.
2. Structural segmentation: Extracts Headnote, Ratio Decidendi, Facts, Domain, and Statutes.
3. Voyage AI Embeddings: Embeds segment texts using voyage-law-2 (1024-d) with exponential backoff.
4. Pinecone Upsert: Upserts segmented vectors to namespace 'segmented-v1' with rich filter metadata.
5. Supabase Dual-Lane Sync: Enriches full_judgments (domain, subdomain, headnote, ratio, statutes)
   which triggers automatic PostgreSQL GIN FTS updates.
6. Staging: Appends structured updates to data/enriched_judgments_staged.jsonl.
"""

import os
import sys
import json
import time
import argparse
import requests
from typing import List, Dict, Any, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
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
CURSOR_PATH = os.path.join(DATA_DIR, "batch_cursor.json")
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


def load_cursor() -> Optional[Dict[str, Any]]:
    """Loads cursor metadata from disk if present."""
    if not os.path.exists(CURSOR_PATH):
        return None
    try:
        with open(CURSOR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cursor(cursor_data: Dict[str, Any]) -> None:
    """Saves cursor metadata to disk with flush."""
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_path = CURSOR_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(cursor_data, f, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    try:
        os.replace(temp_path, CURSOR_PATH)
    except Exception:
        pass


def embed_batch_voyage(texts: List[str], max_retries: int = 5) -> List[List[float]]:
    """Embeds a batch of texts using Voyage AI voyage-law-2 with exponential backoff."""
    if not VOYAGE_API_KEY:
        raise RuntimeError("VOYAGE_API_KEY is not set in environment.")

    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }

    # voyage-law-2 context window is 16k tokens; safety clip to 16,000 chars (~4,000 tokens)
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


def sync_supabase_single_row(sb_client, row_data: Dict[str, Any]) -> bool:
    """Updates a single judgment row in Supabase with structured segment fields."""
    cid = row_data.get("case_id")
    if not cid:
        return False
    payload = {
        "domain": row_data.get("domain"),
        "subdomain": row_data.get("subdomain"),
        "headnote": row_data.get("headnote"),
        "ratio_decidendi": row_data.get("ratio_decidendi"),
        "statutes_cited": row_data.get("statutes_cited", []),
        "provisions_cited": row_data.get("provisions_cited", [])
    }
    try:
        sb_client.table("full_judgments").update(payload).eq("case_id", cid).execute()
        return True
    except Exception as e:
        print(f"  [Supabase Update Warning] {cid}: {e}", flush=True)
        return False


def sync_supabase_batch(sb_client, staged_rows: List[Dict[str, Any]], max_workers: int = 8) -> int:
    """Updates a batch of rows in Supabase in parallel using thread pool."""
    if not staged_rows:
        return 0
    success_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(sync_supabase_single_row, sb_client, r) for r in staged_rows]
        for f in as_completed(futures):
            if f.result():
                success_count += 1
    return success_count


def run_batch_enrichment(
    limit: int = 52636,
    batch_size: int = 25,
    fetch_page_size: int = 100,
    landmark_only: bool = True,
    sync_supabase: bool = True,
    dry_run: bool = False,
    reset_cursor: bool = False
):
    print("=" * 75)
    print("LEGAL RAG RETRIEVAL - STREAMING BATCH ENRICHMENT & SEGMENTED INDEXING")
    print("=" * 75)
    effective_limit = "UNLIMITED" if limit <= 0 else str(limit)
    print(f"Target Pinecone Namespace: '{TARGET_NAMESPACE}'")
    print(f"Limit: {effective_limit} | Batch Size: {batch_size} | Page Size: {fetch_page_size}")
    print(f"Landmark Only (SCMR/PLD): {landmark_only} | Sync Supabase: {sync_supabase} | Dry Run: {dry_run}")

    sb = get_supabase_client()
    pc_index = get_pinecone_index() if not dry_run else None
    if not sb:
        raise RuntimeError("Failed to connect to Supabase.")
    if not dry_run and not pc_index:
        raise RuntimeError("Failed to connect to Pinecone.")

    indexed_checkpoint = load_checkpoint()
    cursor_info = None if reset_cursor else load_cursor()
    last_id = cursor_info.get("last_id") if cursor_info else None
    total_processed_cases = cursor_info.get("total_cases_processed", 0) if (cursor_info and not reset_cursor) else 0
    total_upserted_vectors = cursor_info.get("total_vectors_upserted", 0) if (cursor_info and not reset_cursor) else 0

    print(f"[*] Pre-existing checkpoint entries: {len(indexed_checkpoint)} cases.")
    if last_id:
        print(f"[*] Resuming from keyset cursor: id > '{last_id}' (cumulative cases: {total_processed_cases})")
    else:
        print("[*] Starting keyset scan from beginning of table.")

    t_start = time.time()
    cases_in_this_run = 0
    vectors_in_this_run = 0
    batch_num = 0

    while True:
        if limit > 0 and cases_in_this_run >= limit:
            print(f"[*] Reached target limit of {limit} cases for this run.")
            break

        # Build keyset query
        q = sb.table("full_judgments").select(
            "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
        ).order("id", desc=False)

        if landmark_only:
            q = q.or_("neutral_citation.ilike.%SCMR%,neutral_citation.ilike.%PLD%")

        if last_id:
            q = q.gt("id", last_id)

        try:
            res = q.limit(fetch_page_size).execute()
        except Exception as e:
            print(f"[Supabase Query Error] {e}. Retrying in 5s...", flush=True)
            time.sleep(5)
            continue

        rows = res.data or []
        if not rows:
            print("[*] No more rows found matching criteria. Ingestion complete!")
            break

        # Update last_id from end of current page
        last_id = rows[-1]["id"]

        # Filter out already indexed or trivial cases
        valid_rows = []
        for r in rows:
            cid = r.get("case_id")
            ft = r.get("full_text") or ""
            if not cid:
                continue
            if cid in indexed_checkpoint:
                continue
            if len(ft.split()) < 40:
                # Still mark trivial cases in checkpoint to avoid re-evaluating
                append_checkpoint([cid])
                indexed_checkpoint.add(cid)
                continue
            valid_rows.append(r)

        if not valid_rows:
            # Advance cursor even if all rows in this page were skipped
            save_cursor({
                "last_id": last_id,
                "total_cases_processed": total_processed_cases,
                "total_vectors_upserted": total_upserted_vectors,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            continue

        # Process valid rows in chunks of batch_size
        for chunk_start in range(0, len(valid_rows), batch_size):
            chunk = valid_rows[chunk_start:chunk_start + batch_size]
            batch_num += 1

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

            # 1. Append staged records to JSONL
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(STAGED_JSONL_PATH, "a", encoding="utf-8") as f:
                for s_row in staged_rows:
                    f.write(json.dumps(s_row, ensure_ascii=False) + "\n")

            # 2. Embed & Upsert to Pinecone
            upserted_this_batch = 0
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

                pc_index.upsert(vectors=upsert_payloads, namespace=TARGET_NAMESPACE)
                upserted_this_batch = len(upsert_payloads)

            # 3. Synchronize Supabase full_judgments structured columns
            supabase_synced = 0
            if sync_supabase and not dry_run:
                supabase_synced = sync_supabase_batch(sb, staged_rows, max_workers=8)

            # 4. Record Checkpoint & Keyset Cursor
            append_checkpoint(batch_cids)
            for cid in batch_cids:
                indexed_checkpoint.add(cid)

            cases_in_this_run += len(chunk)
            vectors_in_this_run += upserted_this_batch
            total_processed_cases += len(chunk)
            total_upserted_vectors += upserted_this_batch

            save_cursor({
                "last_id": last_id,
                "total_cases_processed": total_processed_cases,
                "total_vectors_upserted": total_upserted_vectors,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            elapsed = time.time() - t_start
            rate = cases_in_this_run / elapsed if elapsed > 0 else 0
            supa_info = f" | Supa synced: {supabase_synced}" if sync_supabase and not dry_run else ""
            print(
                f"  [Batch {batch_num}] Processed {cases_in_this_run}/{effective_limit} cases "
                f"| Vectors: {upserted_this_batch} (Run total: {vectors_in_this_run}){supa_info} "
                f"| Rate: {rate:.2f} cases/s",
                flush=True
            )

            if limit > 0 and cases_in_this_run >= limit:
                break

    total_elapsed = time.time() - t_start
    avg_rate = cases_in_this_run / total_elapsed if total_elapsed > 0 else 0
    print("\n" + "=" * 75)
    print("RUN COMPLETE!")
    print(f"Cases processed this run: {cases_in_this_run} (Cumulative total: {total_processed_cases})")
    print(f"Vectors upserted this run: {vectors_in_this_run} (Cumulative total: {total_upserted_vectors})")
    print(f"Elapsed time: {total_elapsed:.1f}s | Average speed: {avg_rate:.2f} cases/s")
    print(f"Checkpoint saved to: {CHECKPOINT_PATH}")
    print(f"Cursor saved to: {CURSOR_PATH}")
    print(f"Staged JSONL: {STAGED_JSONL_PATH}")
    print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch enrich, embed, and index Pakistani legal judgments.")
    parser.add_argument("--limit", type=int, default=52636, help="Cases to process in this run (0 for unlimited)")
    parser.add_argument("--batch-size", type=int, default=25, help="Batch size for embedding and upserting")
    parser.add_argument("--page-size", type=int, default=100, help="Supabase fetch page size")
    parser.add_argument("--landmark-only", action="store_true", default=True, help="Only process SCMR and PLD cases")
    parser.add_argument("--all-cases", action="store_true", help="Process entire corpus regardless of citation")
    parser.add_argument("--skip-supabase-sync", action="store_true", help="Skip updating Supabase structured columns")
    parser.add_argument("--dry-run", action="store_true", help="Segment and stage without embedding/upserting")
    parser.add_argument("--reset-cursor", action="store_true", help="Reset cursor to start from the beginning")
    args = parser.parse_args()

    is_landmark = not args.all_cases

    run_batch_enrichment(
        limit=args.limit,
        batch_size=args.batch_size,
        fetch_page_size=args.page_size,
        landmark_only=is_landmark,
        sync_supabase=not args.skip_supabase_sync,
        dry_run=args.dry_run,
        reset_cursor=args.reset_cursor
    )
