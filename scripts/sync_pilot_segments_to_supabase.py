"""
scripts/sync_pilot_segments_to_supabase.py

Syncs enriched legal segment metadata (headnotes, ratio decidendi, domains, statutes)
from data/enriched_pilot_segments.jsonl into Supabase PostgreSQL table `full_judgments`.
"""

import os
import json
import time
from dotenv import load_dotenv
from supabase import create_client

def main():
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        return

    sb = create_client(url, key)
    segments_path = "data/enriched_pilot_segments.jsonl"
    if not os.path.exists(segments_path):
        print(f"ERROR: {segments_path} not found.")
        return

    records = []
    with open(segments_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"Loaded {len(records)} enriched pilot records from {segments_path}")
    updated_count = 0
    not_found_count = 0
    failed_count = 0

    start_time = time.time()
    for i, rec in enumerate(records, 1):
        case_id = rec.get("case_id")
        payload = {
            "domain": rec.get("domain"),
            "subdomain": rec.get("subdomain"),
            "headnote": rec.get("headnote"),
            "ratio_decidendi": rec.get("ratio_decidendi"),
            "statutes_cited": rec.get("statutes_cited", []),
            "provisions_cited": rec.get("provisions_cited", [])
        }
        try:
            res = sb.table("full_judgments").update(payload).eq("case_id", case_id).execute()
            if res.data and len(res.data) > 0:
                updated_count += 1
            else:
                not_found_count += 1
        except Exception as e:
            print(f"  [ERROR] {case_id}: {e}")
            failed_count += 1

        if i % 10 == 0 or i == len(records):
            print(f"  Progress: {i}/{len(records)} (Updated: {updated_count}, Not in DB: {not_found_count}, Failed: {failed_count})")

    elapsed = time.time() - start_time
    print(f"\n=== Sync Summary ===")
    print(f"Total processed: {len(records)} in {elapsed:.2f}s ({(len(records)/elapsed if elapsed else 0):.1f} rec/s)")
    print(f"Successfully enriched in Supabase: {updated_count}")
    print(f"Cases not present in full_judgments: {not_found_count}")
    print(f"Failed updates: {failed_count}")

if __name__ == "__main__":
    main()
