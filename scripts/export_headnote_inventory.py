#!/usr/bin/env python3
"""
Export Headnote Inventory Script
Scans Supabase `full_judgments` for records where full_text is an editorial headnote summary (< 300 words),
and exports a structured manifest CSV to serve as the scraping queue for full-text gap upgrades.
"""

import os
import sys
import csv
import argparse
from typing import Dict, Any, List
from collections import Counter
from dotenv import load_dotenv

# Reconfigure stdout for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in environment.", file=sys.stderr)
    sys.exit(1)

from supabase import create_client

def export_headnote_inventory(
    output_path: str = "headnote_citations_manifest.csv",
    batch_size: int = 1000,
    max_records: int = 0
) -> Dict[str, Any]:
    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    print("=" * 70, flush=True)
    print("AUDIT & MANIFEST EXPORT: HEADNOTE-ONLY PRECEDENT INVENTORY", flush=True)
    print(f"Supabase Endpoint: {SUPABASE_URL}", flush=True)
    print(f"Batch Size: {batch_size:,} | Output Manifest: {output_path}", flush=True)
    print("=" * 70, flush=True)

    total_db_rows = 191872
    print(f"Known total rows in full_judgments: ~{total_db_rows:,}", flush=True)
    if max_records > 0:
        print(f"Scan cap set to: {max_records:,} records.", flush=True)

    offset = 0
    scanned_total = 0
    headnote_records: List[Dict[str, Any]] = []
    court_counter = Counter()
    reporter_counter = Counter()

    # Open CSV writer
    csv_file = open(output_path, "w", newline="", encoding="utf-8")
    fieldnames = [
        "case_id",
        "neutral_citation",
        "court_name",
        "case_title",
        "decision_date",
        "word_count",
        "source_url"
    ]
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()

    try:
        while True:
            fetch_limit = batch_size
            if max_records > 0 and (scanned_total + batch_size) > max_records:
                fetch_limit = max_records - scanned_total
                if fetch_limit <= 0:
                    break

            try:
                res = sb.table("full_judgments") \
                    .select("case_id, neutral_citation, court_name, case_title, decision_date, full_text, source_url") \
                    .range(offset, offset + fetch_limit - 1) \
                    .execute()
            except Exception as fetch_err:
                print(f"⚠️ Fetch error at offset {offset:,}: {fetch_err}. Retrying once...", file=sys.stderr)
                try:
                    res = sb.table("full_judgments") \
                        .select("case_id, neutral_citation, court_name, case_title, decision_date, full_text, source_url") \
                        .range(offset, offset + fetch_limit - 1) \
                        .execute()
                except Exception as retry_err:
                    print(f"❌ Aborting page at offset {offset:,} due to: {retry_err}", file=sys.stderr)
                    break

            batch = res.data or []
            if not batch:
                break

            for r in batch:
                scanned_total += 1
                txt = r.get("full_text") or ""
                words = len(txt.split())

                # Classification floor: under 300 words is an editorial headnote summary / short order
                if words < 300:
                    cid = r.get("case_id") or ""
                    ncit = r.get("neutral_citation") or cid
                    court = r.get("court_name") or "Unknown"
                    raw_title = r.get("case_title") or ""
                    try:
                        from main import clean_or_extract_title, sanitize_case_title
                        title = sanitize_case_title(clean_or_extract_title(raw_title, txt[:2500]))
                    except Exception:
                        title = raw_title or "Reported Precedent"
                    date_val = str(r.get("decision_date") or "")
                    src_url = r.get("source_url") or ""

                    # Extract reporter prefix
                    rep = "OTHER"
                    for known_rep in ["PLD", "SCMR", "YLR", "CLC", "PCRLJ", "PCrLJ", "MLD", "PTD", "PLC", "CLD"]:
                        if known_rep.upper() in ncit.upper():
                            rep = known_rep.upper()
                            break

                    court_counter[court] += 1
                    reporter_counter[rep] += 1

                    row_data = {
                        "case_id": cid,
                        "neutral_citation": ncit,
                        "court_name": court,
                        "case_title": title,
                        "decision_date": date_val,
                        "word_count": words,
                        "source_url": src_url
                    }
                    writer.writerow(row_data)
                    headnote_records.append(row_data)

            offset += len(batch)
            if scanned_total % 1000 == 0 or len(batch) < fetch_limit:
                pct = (scanned_total / max(1, total_db_rows)) * 100
                print(f"  --> Scanned {scanned_total:,}/{total_db_rows:,} ({pct:.1f}%) | Found {len(headnote_records):,} headnote-only records...", flush=True)

            if len(batch) < fetch_limit:
                break
    finally:
        csv_file.close()

    print("=" * 70)
    print("AUDIT & MANIFEST EXPORT COMPLETED")
    print(f"Total Scanned: {scanned_total:,} rows")
    print(f"Total Headnote-Only Records: {len(headnote_records):,} ({(len(headnote_records)/max(1, scanned_total))*100:.1f}%)")
    print(f"Manifest Saved To: {os.path.abspath(output_path)}")
    print("-" * 70)
    print("BREAKDOWN BY REPORTER:")
    for rep, count in reporter_counter.most_common(10):
        print(f"  - {rep:10}: {count:,}")
    print("-" * 70)
    print("BREAKDOWN BY COURT:")
    for crt, count in court_counter.most_common(10):
        print(f"  - {crt:35}: {count:,}")
    print("=" * 70)

    return {
        "scanned_total": scanned_total,
        "headnote_total": len(headnote_records),
        "manifest_path": os.path.abspath(output_path),
        "by_reporter": dict(reporter_counter),
        "by_court": dict(court_counter)
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export headnote-only citations manifest from Supabase")
    parser.add_argument("--output", default="headnote_citations_manifest.csv", help="Output CSV path")
    parser.add_argument("--limit", type=int, default=0, help="Max rows to scan (0 = all)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch query page size")
    args = parser.parse_args()

    export_headnote_inventory(
        output_path=args.output,
        batch_size=args.batch_size,
        max_records=args.limit
    )
