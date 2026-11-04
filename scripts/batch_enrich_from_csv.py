"""
scripts/batch_enrich_from_csv.py

Offline/Direct-CSV Batch Legal Judgment Segmentation, Embedding & Indexing Pipeline.
Streams Pakistani court judgments directly from raw CSV files on disk (e.g. I:\\rerun\\05_Raw_CSVs):
1. Checkpoint resilience: Checks and updates data/batch_indexing_checkpoint.log to prevent duplicate processing.
2. Structural segmentation: Extracts Headnote, Ratio Decidendi, Facts, Domain, and Statutes via StructuralJudgmentSegmenter.
3. Voyage AI Embeddings: Embeds segment texts using voyage-law-2 (1024-d) with exponential backoff.
4. Pinecone Upsert: Upserts segmented vectors to namespace 'segmented-v1' with rich filter metadata.
5. Local Staging: Appends structured updates to data/enriched_judgments_staged.jsonl.
6. Zero Supabase calls: Operates completely offline from Supabase, avoiding all database locks and disk usage.
"""

import os
import sys
import csv
import json
import time
import argparse
import hashlib
import requests
from typing import List, Dict, Any, Set, Optional, Tuple
from dotenv import load_dotenv

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

load_dotenv(os.path.join(WORKSPACE_DIR, ".env"))

from legal_ai.config import get_pinecone_index
from core.structural_judgment_segmenter import StructuralJudgmentSegmenter
from scripts.ingest_all_csvs import extract_citation_and_title, sanitize_judgment_content, clean_court_name

try:
    csv.field_size_limit(2147483647)
except OverflowError:
    csv.field_size_limit(sys.maxsize)

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-law-2")
TARGET_NAMESPACE = os.getenv("PINECONE_SEGMENTED_NAMESPACE", "segmented-v1")

DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
CHECKPOINT_PATH = os.path.join(DATA_DIR, "batch_indexing_checkpoint.log")
STAGED_JSONL_PATH = os.path.join(DATA_DIR, "enriched_judgments_staged.jsonl")
DEFAULT_CSV_DIR = r"I:\rerun\05_Raw_CSVs"


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


def stream_cases_from_csv(csv_path: str, checkpoint: Set[str]):
    """Generator streaming only un-indexed cases from a CSV file."""
    if not os.path.exists(csv_path):
        return

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = {str(k).strip().lstrip("\ufeff"): str(v or "").strip() for kk, v in row.items() if kk for k in [kk]}
            journal = r.get("Journal") or ""
            year = r.get("Year") or ""
            cit_title = r.get("Citation / Title") or ""
            raw_judgment = r.get("Full Judgment Body") or r.get("Judgment Content") or r.get("case_description") or ""
            headnotes_text = r.get("Headnotes / Case Description") or r.get("headnotes") or ""

            full_text = sanitize_judgment_content(raw_judgment or headnotes_text)
            if not full_text or len(full_text.split()) < 40:
                continue

            neutral_cit, case_title, case_id = extract_citation_and_title(cit_title, default_journal=journal, default_year=year)
            if not case_id or case_id in checkpoint:
                continue

            court = clean_court_name(r.get("court") or "", journal_raw=journal)
            dec_date = f"{year}-01-01" if (year and str(year).isdigit() and len(str(year)) == 4) else None

            yield {
                "case_id": case_id,
                "case_title": case_title,
                "neutral_citation": neutral_cit,
                "court_name": court,
                "decision_date": dec_date,
                "full_text": full_text
            }


def run_csv_batch_enrichment(
    csv_dir: str = DEFAULT_CSV_DIR,
    limit: int = 0,
    batch_size: int = 25,
    dry_run: bool = False
):
    print("=" * 75)
    print("DIRECT CSV BATCH SEGMENTATION & PINECONE INDEXING PIPELINE")
    print("=" * 75)
    print(f"Source CSV Directory: {csv_dir}")
    print(f"Target Pinecone Namespace: '{TARGET_NAMESPACE}'")
    print(f"Batch Size: {batch_size} | Limit: {'UNLIMITED' if limit <= 0 else limit} | Dry Run: {dry_run}")

    pc_index = get_pinecone_index() if not dry_run else None
    if not dry_run and not pc_index:
        raise RuntimeError("Failed to connect to Pinecone.")

    indexed_checkpoint = load_checkpoint()
    print(f"[*] Pre-existing checkpoint entries: {len(indexed_checkpoint):,} cases already indexed.")

    csv_files = [
        os.path.join(csv_dir, f)
        for f in sorted(os.listdir(csv_dir))
        if f.endswith(".csv")
    ]
    print(f"[*] Found {len(csv_files)} CSV files in {csv_dir}")

    t_start = time.time()
    cases_processed_run = 0
    vectors_upserted_run = 0
    batch_num = 0

    current_chunk = []

    for fpath in csv_files:
        fname = os.path.basename(fpath)
        print(f"\n---> Scanning file: {fname}...")
        cases_in_file = 0

        for case_rec in stream_cases_from_csv(fpath, indexed_checkpoint):
            cid = case_rec["case_id"]
            if cid in indexed_checkpoint:
                continue

            current_chunk.append(case_rec)
            # Add to local set to avoid duplicates across files in same run
            indexed_checkpoint.add(cid)

            if len(current_chunk) >= batch_size:
                batch_num += 1
                b_cids, b_vecs, b_staged = process_and_upsert_chunk(
                    current_chunk, pc_index, dry_run=dry_run
                )
                cases_processed_run += len(b_cids)
                vectors_upserted_run += b_vecs
                cases_in_file += len(b_cids)

                elapsed = time.time() - t_start
                rate = cases_processed_run / elapsed if elapsed > 0 else 0
                print(
                    f"  [Batch {batch_num}] Total Cases: {cases_processed_run} "
                    f"| Vectors: {b_vecs} (Run total: {vectors_upserted_run}) "
                    f"| Rate: {rate:.2f} cases/s ({fname})",
                    flush=True
                )
                current_chunk = []

                if limit > 0 and cases_processed_run >= limit:
                    break

        if limit > 0 and cases_processed_run >= limit:
            print(f"[*] Reached limit of {limit} cases.")
            break

        print(f"  Completed file {fname}: {cases_in_file} new cases indexed.")

    # Process final dangling chunk if any
    if current_chunk and (limit <= 0 or cases_processed_run < limit):
        batch_num += 1
        b_cids, b_vecs, b_staged = process_and_upsert_chunk(
            current_chunk, pc_index, dry_run=dry_run
        )
        cases_processed_run += len(b_cids)
        vectors_upserted_run += b_vecs

    total_elapsed = time.time() - t_start
    avg_rate = cases_processed_run / total_elapsed if total_elapsed > 0 else 0
    print("\n" + "=" * 75)
    print("CSV BATCH INGESTION COMPLETE!")
    print(f"Cases processed this run: {cases_processed_run}")
    print(f"Vectors upserted this run: {vectors_upserted_run}")
    print(f"Total time: {total_elapsed:.1f}s | Average speed: {avg_rate:.2f} cases/s")
    print(f"Final checkpoint count: {len(load_checkpoint()):,} cases")
    print(f"Staged JSONL: {STAGED_JSONL_PATH}")
    print("=" * 75)


def process_and_upsert_chunk(
    chunk: List[Dict[str, Any]],
    pc_index,
    dry_run: bool = False
) -> Tuple[List[str], int, List[Dict[str, Any]]]:
    """Segments, stages, embeds, and upserts a chunk of cases."""
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
    if not dry_run and staged_rows:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STAGED_JSONL_PATH, "a", encoding="utf-8") as f:
            for s_row in staged_rows:
                f.write(json.dumps(s_row, ensure_ascii=False) + "\n")

    # 2. Embed & Upsert to Pinecone
    upserted_count = 0
    if not dry_run and batch_vectors:
        sanitized_vectors = []
        for v in batch_vectors:
            v_id = str(v["id"])
            if len(v_id) > 400:
                v_id = f"{v_id[:200]}_{hashlib.sha256(v_id.encode('utf-8')).hexdigest()[:16]}"
            v["id"] = v_id
            sanitized_vectors.append(v)

        embed_texts = [v["text_to_embed"] for v in sanitized_vectors]
        try:
            embeddings = embed_batch_voyage(embed_texts)
        except Exception as embed_err:
            print(f"  [Voyage Batch Fallback] Error {embed_err}. Attempting sub-batches...", flush=True)
            embeddings = []
            for et in embed_texts:
                try:
                    embeddings.extend(embed_batch_voyage([et], max_retries=3))
                except Exception as sub_err:
                    print(f"    [Skip Text Embed] Failed single embed: {sub_err}", flush=True)
                    embeddings.append([0.0] * 1024)

        upsert_payloads = []
        for v, emb in zip(sanitized_vectors, embeddings):
            if any(emb):  # only upsert non-zero embeddings
                upsert_payloads.append({
                    "id": v["id"],
                    "values": emb,
                    "metadata": v["metadata"]
                })

        try:
            pc_index.upsert(vectors=upsert_payloads, namespace=TARGET_NAMESPACE)
            upserted_count = len(upsert_payloads)
        except Exception as e:
            print(f"  [Pinecone Upsert Warning] Batch failed: {e}. Attempting item-by-item upsert...", flush=True)
            for item in upsert_payloads:
                try:
                    pc_index.upsert(vectors=[item], namespace=TARGET_NAMESPACE)
                    upserted_count += 1
                except Exception as item_err:
                    print(f"    [Pinecone Skip Vector] {item.get('id')[:60]}: {item_err}", flush=True)

        # 3. Append to checkpoint
        append_checkpoint(batch_cids)

    return batch_cids, upserted_count, staged_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch index remaining judgments from local CSVs.")
    parser.add_argument("--csv-dir", default=DEFAULT_CSV_DIR, help="Path to directory containing raw CSVs")
    parser.add_argument("--limit", type=int, default=0, help="Cases to process (0 for unlimited)")
    parser.add_argument("--batch-size", type=int, default=25, help="Batch size for embedding & upserting")
    parser.add_argument("--dry-run", action="store_true", help="Segment and stage without embedding/upserting")
    args = parser.parse_args()

    run_csv_batch_enrichment(
        csv_dir=args.csv_dir,
        limit=args.limit,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )
