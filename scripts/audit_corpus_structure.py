#!/usr/bin/env python3
"""
Corpus Structure and Metadata Integrity Audit Script (Read-Only / Dry-Run)
Audits precedent records across Pinecone/BM25 active index and Supabase full_judgments.
Categorizes every record into:
  - Bucket A: Mislabelled "full text" (headnote stored/treated as full text -> relabel)
  - Bucket B: Mislabelled headnote (real order text stored/treated as headnote -> relabel)
  - Bucket C: Mixed (headnote plus order -> split into two parts)
  - Bucket D: Headnote-only (no full text exists -> queue for scraping)
  - Bucket E: Metadata conflicts (outcome, statute, ID mismatch -> manual check)
"""

import os
import sys
import csv
import json
import re
import time
import pickle
import sqlite3
import argparse
from typing import Dict, Any, List, Set, Tuple, Optional
from collections import defaultdict, Counter
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE_DIR)

ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from core.legal_guardrails import (
    classify_judgment_structure,
    parse_outcome_from_tail,
    extract_statutes_from_text,
    is_compiled_headnote
)

SCRATCH_DIR = os.path.join(os.path.dirname(WORKSPACE_DIR), "..", ".gemini", "antigravity", "brain", "5ce49601-04d3-4264-9d73-e9af4be35593", "scratch")
SQLITE_CATALOG_PATH = os.path.abspath(os.path.join(SCRATCH_DIR, "supabase_catalog.db"))
BM25_PATH = os.path.join(WORKSPACE_DIR, "bm25_index.pkl")
KNOWN_COLLISIONS_PATH = os.path.join(WORKSPACE_DIR, "known_collisions.json")


def normalize_cit_key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def audit_corpus(
    sample_size_supabase: int = 10000,
    batch_size: int = 500,
    output_dir: str = WORKSPACE_DIR
):
    print("=" * 80)
    print("CORPUS STRUCTURE AND METADATA INTEGRITY AUDIT (READ-ONLY / DRY-RUN)")
    print("=" * 80)
    print(f"BM25 Index File: {BM25_PATH}")
    print(f"Supabase Catalog DB: {SQLITE_CATALOG_PATH} (exists: {os.path.exists(SQLITE_CATALOG_PATH)})")
    print(f"Output Directory: {output_dir}")
    print("=" * 80)

    supabase_lookup: Dict[str, Dict[str, Any]] = {}
    normalized_supa_map: Dict[str, str] = {}
    if os.path.exists(SQLITE_CATALOG_PATH):
        print("\n[Step 1] Loading local Supabase catalog SQLite index...")
        conn = sqlite3.connect(SQLITE_CATALOG_PATH)
        c = conn.cursor()
        c.execute("SELECT case_id, neutral_citation, case_title, court_name, decision_date FROM full_judgments_catalog")
        rows = c.fetchall()
        conn.close()
        for r in rows:
            cid, cit, title, court, dt = r
            entry = {
                "case_id": cid,
                "neutral_citation": cit,
                "case_title": title,
                "court_name": court,
                "decision_date": dt
            }
            if cid:
                supabase_lookup[cid.upper()] = entry
                normalized_supa_map[normalize_cit_key(cid)] = cid
            if cit:
                supabase_lookup[cit.upper()] = entry
                normalized_supa_map[normalize_cit_key(cit)] = cid
        print(f"Loaded {len(rows):,} catalog rows into lookup table.")
    else:
        print("\n[Step 1] Local SQLite catalog not found; will query Supabase directly where needed.")

    print("\n[Step 2] Loading active precedent corpus from BM25 index...")
    if not os.path.exists(BM25_PATH):
        print(f"Error: {BM25_PATH} does not exist!", file=sys.stderr)
        return

    with open(BM25_PATH, "rb") as f:
        bm25_data = pickle.load(f)

    doc_metadata: List[Dict[str, Any]] = bm25_data.get("doc_metadata", [])
    print(f"Loaded {len(doc_metadata):,} active chunks from BM25 index.")

    cases_chunks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in doc_metadata:
        cid = m.get("case_id") or m.get("citation") or "UNKNOWN"
        cases_chunks[cid].append(m)

    print(f"Aggregated into {len(cases_chunks):,} distinct cases.")

    bucket_A: List[Dict[str, Any]] = []
    bucket_B: List[Dict[str, Any]] = []
    bucket_C: List[Dict[str, Any]] = []
    bucket_D: List[Dict[str, Any]] = []
    bucket_E: List[Dict[str, Any]] = []

    print("\n[Step 3] Auditing active cases in BM25 / Pinecone...")
    t0 = time.time()

    for cid, chunks in cases_chunks.items():
        chunks_sorted = sorted(chunks, key=lambda x: x.get("chunk_index", 0))
        full_text = " ".join(c.get("text", "") for c in chunks_sorted)
        meta0 = chunks_sorted[0]

        citation = meta0.get("citation") or meta0.get("neutral_citation") or cid
        case_title = meta0.get("case_title") or meta0.get("title") or meta0.get("case_name") or ""
        court_name = meta0.get("court") or meta0.get("court_name") or ""
        decision_date = str(meta0.get("decision_date") or meta0.get("year") or "")
        stored_content_type = meta0.get("content_type")

        word_count = len(full_text.split())
        legacy_type = "headnote_only" if word_count < 300 else "full_judgment"
        effective_stored_type = stored_content_type or legacy_type

        struct = classify_judgment_structure(full_text)
        detected_type = struct["detected_type"]
        split_offset = struct["split_offset"]
        signals = struct["signals"]
        parsed_outcome = struct["parsed_outcome"]

        meta_statutes = meta0.get("statutes") or meta0.get("sections") or []
        if isinstance(meta_statutes, str):
            meta_statutes = [meta_statutes]

        phantom_statutes = []
        for st in meta_statutes:
            st_str = str(st).strip()
            if len(st_str) > 2 and st_str.lower() not in full_text.lower():
                phantom_statutes.append(st_str)

        supa_entry = supabase_lookup.get(cid.upper())
        id_conflict = False
        supa_cid = None
        if not supa_entry:
            norm_key = normalize_cit_key(citation)
            supa_cid = normalized_supa_map.get(norm_key)
            if supa_cid and supa_cid.upper() != cid.upper():
                id_conflict = True
        else:
            supa_cid = supa_entry.get("case_id")

        record_info = {
            "case_id": cid,
            "citation": citation,
            "case_title": case_title,
            "court_name": court_name,
            "decision_date": decision_date,
            "word_count": word_count,
            "effective_stored_type": effective_stored_type,
            "detected_type": detected_type,
            "split_offset": split_offset,
            "parsed_outcome": parsed_outcome or "unknown",
            "phantom_statutes": "; ".join(phantom_statutes) if phantom_statutes else "none",
            "supabase_case_id": supa_cid or "not_found",
            "signals": signals
        }

        if detected_type == "mixed":
            bucket_C.append(record_info)
        elif detected_type == "headnote_only" and effective_stored_type in ("full_judgment", "full_text"):
            bucket_A.append(record_info)
        elif detected_type in ("order_text", "full_judgment") and effective_stored_type == "headnote_only":
            bucket_B.append(record_info)
        elif detected_type == "headnote_only":
            bucket_D.append(record_info)

        conflict_reasons = []
        if id_conflict:
            conflict_reasons.append(f"ID Mismatch (BM25={cid} vs Supabase={supa_cid})")
        if phantom_statutes:
            conflict_reasons.append(f"Statutes in metadata missing from text: {', '.join(phantom_statutes[:3])}")
        
        if conflict_reasons:
            rec_e = dict(record_info)
            rec_e["conflict_reasons"] = " | ".join(conflict_reasons)
            bucket_E.append(rec_e)

    print(f"BM25 audit completed in {time.time()-t0:.2f}s.")
    print(f"Active Index Breakdown:")
    print(f"  - Bucket A (Mislabelled Full Text): {len(bucket_A):,}")
    print(f"  - Bucket B (Mislabelled Headnote) : {len(bucket_B):,}")
    print(f"  - Bucket C (Mixed Headnote+Order) : {len(bucket_C):,}")
    print(f"  - Bucket D (Headnote-Only)        : {len(bucket_D):,}")
    print(f"  - Bucket E (Metadata Conflicts)   : {len(bucket_E):,}")

    print(f"\n[Step 4] Scanning Supabase full_judgments records (sample cap: {sample_size_supabase:,})...")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    supa_scanned = 0

    if supabase_url and supabase_key and sample_size_supabase > 0:
        from supabase import create_client
        sb = create_client(supabase_url, supabase_key)
        
        offset = 0
        supa_t0 = time.time()
        
        while supa_scanned < sample_size_supabase:
            fetch_cnt = min(batch_size, sample_size_supabase - supa_scanned)
            try:
                res = sb.table("full_judgments") \
                    .select("case_id, neutral_citation, case_title, court_name, decision_date, full_text") \
                    .range(offset, offset + fetch_cnt - 1) \
                    .execute()
                batch_rows = res.data or []
                if not batch_rows:
                    break

                for r in batch_rows:
                    supa_scanned += 1
                    s_cid = r.get("case_id") or ""
                    s_cit = r.get("neutral_citation") or s_cid
                    s_txt = r.get("full_text") or ""
                    s_words = len(s_txt.split())
                    s_legacy_type = "headnote_only" if s_words < 300 else "full_judgment"

                    s_struct = classify_judgment_structure(s_txt)
                    s_detected_type = s_struct["detected_type"]
                    s_outcome = s_struct["parsed_outcome"] or "unknown"

                    s_info = {
                        "case_id": s_cid,
                        "citation": s_cit,
                        "case_title": r.get("case_title") or "",
                        "court_name": r.get("court_name") or "",
                        "decision_date": str(r.get("decision_date") or ""),
                        "word_count": s_words,
                        "effective_stored_type": s_legacy_type,
                        "detected_type": s_detected_type,
                        "split_offset": s_struct["split_offset"],
                        "parsed_outcome": s_outcome,
                        "phantom_statutes": "none",
                        "supabase_case_id": s_cid,
                        "signals": s_struct["signals"]
                    }

                    if s_cid not in cases_chunks:
                        if s_detected_type == "mixed":
                            bucket_C.append(s_info)
                        elif s_detected_type == "headnote_only" and s_legacy_type == "full_judgment":
                            bucket_A.append(s_info)
                        elif s_detected_type in ("order_text", "full_judgment") and s_legacy_type == "headnote_only":
                            bucket_B.append(s_info)
                        elif s_detected_type == "headnote_only":
                            bucket_D.append(s_info)

                offset += len(batch_rows)
                if supa_scanned % 1000 == 0:
                    print(f"  Scanned {supa_scanned:,}/{sample_size_supabase:,} Supabase records ({time.time()-supa_t0:.1f}s)...", flush=True)

                if len(batch_rows) < fetch_cnt:
                    break
            except Exception as batch_err:
                print(f"Supabase scan batch error at offset {offset}: {batch_err}", file=sys.stderr)
                break
        print(f"Supabase scan completed: {supa_scanned:,} records scanned.")

    print("\n[Step 5] Exporting audit manifests and sample reviews...")

    def write_bucket_csv(filename: str, records: List[Dict[str, Any]], extra_fields: List[str] = None):
        path = os.path.join(output_dir, filename)
        fields = ["case_id", "citation", "case_title", "court_name", "decision_date", "word_count", "effective_stored_type", "detected_type", "parsed_outcome"]
        if extra_fields:
            fields.extend(extra_fields)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for r in records:
                writer.writerow(r)
        print(f"  -> Exported {len(records):,} records to '{filename}'")

    write_bucket_csv("audit_bucket_A_mislabelled_fulltext.csv", bucket_A)
    write_bucket_csv("audit_bucket_B_mislabelled_headnote.csv", bucket_B)
    write_bucket_csv("audit_bucket_C_mixed.csv", bucket_C, extra_fields=["split_offset"])
    write_bucket_csv("audit_bucket_D_headnote_only.csv", bucket_D)
    write_bucket_csv("audit_bucket_E_metadata_conflicts.csv", bucket_E, extra_fields=["conflict_reasons", "phantom_statutes"])

    def rank_headnote_priority(rec: Dict[str, Any]) -> int:
        cit = (rec.get("citation") or "").upper()
        cid = (rec.get("case_id") or "").upper()
        title = (rec.get("case_title") or "").upper()
        if "NOOR HAYAT" in title or "2026_CLD_68" in cid or "2026 CLD 68" in cit:
            return 1000
        if "VITAL CHEMICAL" in title or "2026_CLD_96" in cid or "2026 CLD 96" in cit:
            return 999
        if "TARIQ ZUBAIR" in title or "2024 SCMR 1218" in cit:
            return 998
        score = 0
        if "CLD" in cit or "BANK" in title:
            score += 100
        if "SCMR" in cit:
            score += 50
        if "PLD" in cit:
            score += 30
        if "2026" in cit or "2025" in cit or "2024" in cit:
            score += 20
        return score

    all_headnotes_queue = list(bucket_D) + list(bucket_A)
    seen_cids = set()
    deduped_headnotes_queue = []
    for h in all_headnotes_queue:
        if h["case_id"] not in seen_cids:
            seen_cids.add(h["case_id"])
            deduped_headnotes_queue.append(h)

    deduped_headnotes_queue.sort(key=rank_headnote_priority, reverse=True)

    write_bucket_csv("ranked_headnotes_bucket_D.csv", deduped_headnotes_queue)

    samples = {
        "bucket_A_sample_20": bucket_A[:20],
        "bucket_B_sample_20": bucket_B[:20],
        "bucket_C_sample_20": bucket_C[:20],
        "bucket_E_sample_20": bucket_E[:20],
        "top_20_headnote_upgrade_queue": deduped_headnotes_queue[:20]
    }
    sample_path = os.path.join(output_dir, "audit_samples_hand_review.json")
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)
    print(f"  -> Exported hand-review samples to '{sample_path}'")

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_active_cases_audited": len(cases_chunks),
        "total_supabase_records_scanned": supa_scanned,
        "bucket_counts": {
            "bucket_A_mislabelled_full_text": len(bucket_A),
            "bucket_B_mislabelled_headnote": len(bucket_B),
            "bucket_C_mixed_headnote_and_order": len(bucket_C),
            "bucket_D_headnote_only": len(bucket_D),
            "bucket_E_metadata_conflicts": len(bucket_E),
            "total_headnote_upgrade_queue": len(deduped_headnotes_queue)
        },
        "top_priority_headnotes_for_scraping": [
            f"{h['citation']} - {h['case_title'][:60]}" for h in deduped_headnotes_queue[:10]
        ]
    }
    summary_path = os.path.join(output_dir, "audit_summary_report.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  -> Exported high-level summary to '{summary_path}'")

    print("\n" + "=" * 80)
    print("CORPUS AUDIT COMPLETE")
    print(f"Total Unique Cases in Manifest: {len(cases_chunks) + supa_scanned:,}")
    print(f"Bucket A (Mislabelled Full Text)   : {len(bucket_A):,}")
    print(f"Bucket B (Mislabelled Headnote)    : {len(bucket_B):,}")
    print(f"Bucket C (Mixed Headnote + Order)  : {len(bucket_C):,}")
    print(f"Bucket D (Headnote-Only Queue)     : {len(bucket_D):,}")
    print(f"Bucket E (Metadata Conflicts)      : {len(bucket_E):,}")
    print("=" * 80)

    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corpus Structure & Integrity Audit")
    parser.add_argument("--supabase-sample", type=int, default=10000, help="Number of Supabase full_judgments records to scan")
    parser.add_argument("--batch-size", type=int, default=500, help="Supabase batch query size")
    parser.add_argument("--output-dir", type=str, default=WORKSPACE_DIR, help="Output directory")
    args = parser.parse_args()

    audit_corpus(
        sample_size_supabase=args.supabase_sample,
        batch_size=args.batch_size,
        output_dir=args.output_dir
    )
