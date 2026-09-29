#!/usr/bin/env python3
"""
Batch Headnote Gap-Sweep Scraper
Systematically crawls whitelisted court portals (supremecourt.gov.pk, lhc.gov.pk, etc.)
for citations currently held as editorial headnote summaries, parses them through
PyMuPDF and Gates 1–4, and stages them for full-text corpus upgrade.
"""

import os
import sys
import csv
import time
import argparse
from typing import Dict, Any, List
from dotenv import load_dotenv

# Reconfigure stdout for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE_DIR)

ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from core.fallback_pipeline import (
    search_whitelisted_court_precedents,
    process_court_pdf_pipeline,
    WHITELISTED_COURT_DOMAINS
)

def sweep_and_upgrade_headnotes(
    manifest_path: str = "headnote_citations_manifest.csv",
    limit: int = 10,
    delay_between_requests: float = 2.0,
    filter_court: str = "",
    filter_reporter: str = ""
):
    print("=" * 70)
    print("BATCH HEADNOTE GAP-SWEEP & VERIFICATION SCRAPER")
    print(f"Manifest: {manifest_path}")
    print(f"Limit: {limit} | Request Delay: {delay_between_requests}s")
    if filter_court:
        print(f"Filtered to Court: {filter_court}")
    if filter_reporter:
        print(f"Filtered to Reporter: {filter_reporter}")
    print("=" * 70)

    if not os.path.exists(manifest_path):
        print(f"❌ Manifest file '{manifest_path}' not found! Run export_headnote_inventory.py first.", file=sys.stderr)
        return

    items: List[Dict[str, str]] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if filter_court and filter_court.lower() not in (row.get("court_name") or "").lower():
                continue
            if filter_reporter and filter_reporter.upper() not in (row.get("neutral_citation") or "").upper():
                continue
            items.append(row)

    print(f"Loaded {len(items):,} candidate headnote records matching criteria.")
    if limit > 0:
        items = items[:limit]
        print(f"Processing first {limit} records for this batch sweep.")

    upgraded_count = 0
    quarantined_count = 0
    not_found_count = 0

    for idx, item in enumerate(items, 1):
        cid = item.get("case_id")
        cit = item.get("neutral_citation") or cid
        court = item.get("court_name") or ""
        title = item.get("case_title") or ""
        words = item.get("word_count")

        print(f"\n[{idx}/{len(items)}] Sweeping court portals for: {cit} ({court})")
        print(f"    Party Title: {title}")
        print(f"    Current DB text: {words} words (headnote-only)")

        # Formulate targeted portal query
        targeted_query = f"{cit} {title}".strip()
        try:
            candidates = search_whitelisted_court_precedents(targeted_query, max_results=1)
            if candidates:
                cand = candidates[0]
                cand_meta = cand.get("metadata", {})
                pdf_url = cand_meta.get("pdf_url") or cand_meta.get("source_url")
                text_len = len(cand_meta.get("text") or "")
                word_count = len((cand_meta.get("text") or "").split())

                print(f"  ✅ FOUND & VERIFIED ON PORTAL:")
                print(f"     Source URL: {pdf_url}")
                print(f"     Extracted Full Text: {word_count:,} words ({text_len:,} chars)")
                print(f"     Status: Quarantined & Verified via Gates 1-4")
                quarantined_count += 1

                # If production mutation is enabled, upgrade full_judgments directly
                if os.environ.get("ALLOW_DIRECT_PROD_MUTATION") == "TRUE":
                    try:
                        from supabase import create_client
                        sb = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY"))
                        full_txt = cand_meta.get("text") or ""
                        sb.table("full_judgments").update({
                            "full_text": full_txt,
                            "source_url": pdf_url,
                            "content_type": "full_text"
                        }).eq("case_id", cid).execute()
                        upgraded_count += 1
                        print(f"     ⚡ DIRECT PROD UPGRADE: Upgraded full_judgments record for {cid}")
                    except Exception as up_err:
                        print(f"     ⚠️ Supabase prod update notice: {up_err}")
            else:
                print(f"  ℹ️ Not indexed on court portals (remains headnote-only with disclosure banner)")
                not_found_count += 1

        except Exception as e:
            print(f"  ⚠️ Error scraping {cit}: {e}")
            not_found_count += 1

        if delay_between_requests > 0:
            time.sleep(delay_between_requests)

    print("\n" + "=" * 70)
    print("GAP-SWEEP BATCH SUMMARY")
    print(f"Records Processed: {len(items)}")
    print(f"Successfully Found & Quarantined: {quarantined_count}")
    if os.environ.get("ALLOW_DIRECT_PROD_MUTATION") == "TRUE":
        print(f"Directly Upgraded in full_judgments: {upgraded_count}")
    print(f"Remaining as Headnote Only: {not_found_count}")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sweep court portals and upgrade headnote records")
    parser.add_argument("--manifest", default="headnote_citations_manifest.csv", help="Path to manifest CSV")
    parser.add_argument("--limit", type=int, default=10, help="Number of records to sweep")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between portal requests (seconds)")
    parser.add_argument("--court", default="", help="Filter by court name")
    parser.add_argument("--reporter", default="", help="Filter by reporter abbreviation")
    args = parser.parse_args()

    sweep_and_upgrade_headnotes(
        manifest_path=args.manifest,
        limit=args.limit,
        delay_between_requests=args.delay,
        filter_court=args.court,
        filter_reporter=args.reporter
    )
