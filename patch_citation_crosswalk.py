import os
import sys
import re
import dotenv
dotenv.load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

def run_crosswalk_patch():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("⚠️ Supabase credentials missing from environment.")
        return

    print("Connecting to Supabase...")
    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # 1. Look up target judgment in full_judgments
    res = sb.table("full_judgments").select("*").or_("case_id.eq.2021_SCMR_2092,neutral_citation.eq.2021 SCMR 2092,case_title.ilike.%Muhammad Nasir Shafique%").execute()
    
    records = res.data or []
    print(f"Found {len(records)} matching records in full_judgments.")
    
    for r in records:
        print(f"Target Record ID: {r.get('id')} | Case ID: {r.get('case_id')} | Title: {r.get('case_title')[:60]}")
        # Ensure neutral_citation is cleanly set
        if not r.get("neutral_citation") or r.get("neutral_citation") == "No Citation":
            sb.table("full_judgments").update({"neutral_citation": "2021 SCMR 2092"}).eq("id", r.get("id")).execute()
            print("Updated neutral_citation in full_judgments to '2021 SCMR 2092'.")

        # Try populating citation_crosswalk table if table exists
        try:
            crosswalk_entry = {
                "citation": "2021 SCMR 2092",
                "court": r.get("court_name") or "Supreme Court of Pakistan",
                "docket_number": "Crl.P. 408-L/2021",
                "case_title": "Muhammad Nasir Shafique v. The State",
                "judgment_id": r.get("id")
            }
            sb.table("citation_crosswalk").upsert(crosswalk_entry, on_conflict="citation").execute()
            print("Upserted citation_crosswalk record for '2021 SCMR 2092'.")
        except Exception as cw_err:
            print(f"Notice (citation_crosswalk table): {cw_err}")

if __name__ == "__main__":
    run_crosswalk_patch()
