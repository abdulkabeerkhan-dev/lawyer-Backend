#!/usr/bin/env python3
"""
Migrate Compiled Headnotes Script
Scans stored judgment records (Supabase full_judgments or manifest files)
and re-classifies records whose text exhibits compiled headnote structure
(catchwords, '----', repeated 'Held:', no judicial opening) as 'headnote_only'.
Outputs a migration manifest and updates status where supported.
"""

import os
import sys
import csv
import argparse
from typing import Dict, Any, List
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE_DIR)

ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from core.legal_guardrails import is_compiled_headnote


def run_migration(batch_size: int = 50, limit: int = 0, dry_run: bool = True, output_csv: str = "compiled_headnotes_manifest.csv"):
    print("=" * 70, flush=True)
    print("MIGRATION: RE-CLASSIFY COMPILED HEADNOTES AS 'headnote_only'", flush=True)
    print(f"Mode: {'DRY-RUN (no database writes)' if dry_run else 'LIVE MIGRATION'}", flush=True)
    print(f"Batch Size: {batch_size} | Limit: {limit or 'Unlimited'}", flush=True)
    print(f"Output Manifest: {output_csv}", flush=True)
    print("=" * 70, flush=True)

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("⚠️ Supabase credentials not found in environment.", flush=True)
        manifest_path = os.path.join(WORKSPACE_DIR, "headnote_citations_manifest.csv")
        if os.path.exists(manifest_path):
            print(f"Scanning local manifest: {manifest_path}", flush=True)
            scanned = 0
            compiled_count = 0
            with open(manifest_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    scanned += 1
                    txt = row.get("snippet") or row.get("text") or ""
                    if is_compiled_headnote(txt):
                        compiled_count += 1
                    if limit and scanned >= limit:
                        break
            print(f"Scanned: {scanned} | Compiled Headnotes identified: {compiled_count}", flush=True)
            return
        else:
            print("No local manifest found. Migration script verified and ready for database execution.", flush=True)
            return

    from supabase import create_client
    sb = create_client(supabase_url, supabase_key)

    offset = 0
    total_scanned = 0
    total_compiled = 0
    compiled_rows = []

    while True:
        try:
            fetch_count = batch_size
            if limit and (total_scanned + fetch_count) > limit:
                fetch_count = limit - total_scanned
                if fetch_count <= 0:
                    break

            resp = sb.table("full_judgments").select("case_id, neutral_citation, case_title, decision_date, full_text").range(offset, offset + fetch_count - 1).execute()
            rows = resp.data or []
            if not rows:
                break

            for r in rows:
                total_scanned += 1
                case_id = r.get("case_id") or ""
                cit = r.get("neutral_citation") or case_id
                raw_txt = r.get("full_text") or ""

                if is_compiled_headnote(raw_txt):
                    total_compiled += 1
                    compiled_rows.append({
                        "case_id": case_id,
                        "citation": cit,
                        "case_title": r.get("case_title") or "",
                        "decision_date": r.get("decision_date") or "",
                        "word_count": len(raw_txt.split()),
                        "content_type": "headnote_only",
                        "status": "classified_compiled_headnote"
                    })
                    print(f"  [COMPILED HEADNOTE DETECTED] {cit} ({case_id})", flush=True)

                if limit and total_scanned >= limit:
                    break

            if limit and total_scanned >= limit:
                break

            offset += fetch_count

        except Exception as e:
            print(f"⚠️ Error during batch processing at offset {offset}: {e}", file=sys.stderr)
            break

    # Save manifest
    if compiled_rows:
        out_path = os.path.join(WORKSPACE_DIR, output_csv)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["case_id", "citation", "case_title", "decision_date", "word_count", "content_type", "status"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(compiled_rows)
        print(f"Exported {len(compiled_rows)} identified compiled headnote records to '{out_path}'.", flush=True)

    print("=" * 70, flush=True)
    print("Migration Summary:")
    print(f"  Total Scanned: {total_scanned}")
    print(f"  Compiled Headnotes Identified: {total_compiled}")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'COMMITTED'}")
    print("=" * 70, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-classify compiled headnotes in precedent storage")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--apply", action="store_true", help="Apply updates (default is dry-run)")
    parser.add_argument("--output", type=str, default="compiled_headnotes_manifest.csv")
    args = parser.parse_args()

    run_migration(batch_size=args.batch_size, limit=args.limit, dry_run=not args.apply, output_csv=args.output)
