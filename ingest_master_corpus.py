import os
import sys
import re
import glob
import time
import pandas as pd
from typing import List, Dict, Any
from supabase import create_client
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("[ERROR] SUPABASE_URL or SUPABASE_SERVICE_KEY missing from environment.")
    sys.exit(1)

# STANDING SAFETY GUARD: Prevent accidental direct mutations to production full_judgments
if os.environ.get("ALLOW_DIRECT_PROD_MUTATION") != "TRUE":
    raise RuntimeError(
        "SAFETY GUARD: Direct script writes to full_judgments are blocked to prevent accidental data contamination. "
        "Set ALLOW_DIRECT_PROD_MUTATION=TRUE explicitly if you genuinely intend to run this offline migration."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


JOURNAL_FILES = [
    "PCRLJ_cases.csv",
    "PTD_cases.csv"
]

DATA_DIR = os.environ.get("INPUT_DIR", "D:\\")
BATCH_SIZE = 500

def strip_copyright_and_branding(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r'Copyrights?\s*©?\s*\d*\s*by\s*Oratier\s*Technologies\s*\(Pvt\.\)?\s*Ltd\.?',
        r'This\s*site\s*is\s*developed\s*&\s*maintained\s*(by\s*)?Oratier\s*Technologies\s*\(Pvt\.\)?\s*Ltd\.?',
        r'Help\s*FAQ\'?s?\s*Sitemap',
        r'Page\s*\d+\s*of\s*\d+',
        r'Confidential\s*&\s*Official\s*Record\s*-\s*Pakistan\s*Legal\s*Corpus',
        r'Source:\s*pakistan\s*law\s*site',
        r'pakistan\s*law\s*site',
        r'pakistanlawsite(?:\.com)?',
        r'Oratier\s*Technologies\s*\(Pvt\.\)?\s*Ltd\.?',
        r'Bookmark\s*this\s*Case'
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*Source:\s*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

def clean_court_from_title(title: str, text: str) -> str:
    combined = (title + " " + text[:500]).lower()
    if "supreme court" in combined or "sc" in combined:
        return "Supreme Court of Pakistan"
    elif "sindh" in combined or "karachi" in combined:
        return "High Court of Sindh"
    elif "lahore" in combined or "lhc" in combined:
        return "Lahore High Court"
    elif "peshawar" in combined or "phc" in combined:
        return "Peshawar High Court"
    elif "balochistan" in combined or "quetta" in combined:
        return "High Court of Balochistan"
    elif "federal shariat" in combined or "fsc" in combined:
        return "Federal Shariat Court"
    return "Superior Courts of Pakistan"

def process_journal_csv(csv_path: str):
    filename = os.path.basename(csv_path)
    print(f"\n[INGESTION] Processing {filename}...")

    if not os.path.exists(csv_path):
        print(f"[WARNING] File {csv_path} does not exist. Skipping.")
        return

    total_ingested = 0
    batch_records: List[Dict[str, Any]] = []
    seen_ids_in_batch = set()

    try:
        # Stream read CSV in chunks of 2,000 for memory efficiency
        chunk_iterator = pd.read_csv(csv_path, chunksize=2000, low_memory=False)
        
        for chunk in chunk_iterator:
            for idx, row in chunk.iterrows():
                raw_title = str(row.get("Citation / Title") or "")
                raw_body = str(row.get("Full Judgment Body") or "")
                raw_headnotes = str(row.get("Headnotes / Case Description") or "")
                raw_content = str(row.get("Judgment Content") or "")
                journal = str(row.get("Journal") or filename.split("_")[0]).upper()
                year = str(row.get("Year") or "2024")
                case_idx = str(row.get("Case Index") or idx)

                # Extract neutral citation (e.g., 2024 PCRLJ 1)
                cit_match = re.search(r'\b(\d{4}\s+' + re.escape(journal) + r'\s+\d+)\b', raw_title, re.IGNORECASE)
                neutral_cit = cit_match.group(1).upper() if cit_match else f"{year} {journal} {case_idx}"
                case_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', neutral_cit).strip('_')

                if case_id in seen_ids_in_batch:
                    continue
                seen_ids_in_batch.add(case_id)

                # Extract party names / case title
                title_match = re.search(r'([A-Za-z0-9\s\.\,\'\-]+VS[A-Za-z0-9\s\.\,\'\-]+)', raw_title, re.IGNORECASE)
                case_title = title_match.group(1).strip() if title_match else (raw_title[:150] or f"Matter under {neutral_cit}")

                raw_text = raw_headnotes if len(raw_headnotes) > 150 else (raw_body if len(raw_body) > 150 else raw_content)
                if not raw_text or len(raw_text.strip()) < 20:
                    continue

                full_text = strip_copyright_and_branding(raw_text)
                case_title = strip_copyright_and_branding(case_title)
                court_name = clean_court_from_title(case_title, full_text)

                record = {
                    "case_id": case_id,
                    "case_title": case_title[:250],
                    "neutral_citation": neutral_cit,
                    "court_name": court_name,
                    "decision_date": f"{year}-01-01",
                    "full_text": full_text[:200000] # Safe upper cap per judgment
                }
                batch_records.append(record)

                if len(batch_records) >= BATCH_SIZE:
                    try:
                        supabase.table("full_judgments").upsert(batch_records, on_conflict="case_id").execute()
                        total_ingested += len(batch_records)
                        print(f"  [OK] Ingested {total_ingested:,} cases from {filename}...", flush=True)
                    except Exception as batch_err:
                        print(f"  [NOTICE] Batch upsert notice in {filename}: {batch_err}")
                    batch_records = []
                    seen_ids_in_batch = set()

        if batch_records:
            try:
                supabase.table("full_judgments").upsert(batch_records, on_conflict="case_id").execute()
                total_ingested += len(batch_records)
            except Exception as batch_err:
                print(f"  [NOTICE] Final batch upsert notice in {filename}: {batch_err}")

        print(f"[DONE] Finished {filename}: Total {total_ingested:,} cases stored in Supabase!")

    except Exception as e:
        print(f"[ERROR] Processing {filename}: {e}")

def main():
    print("==================================================")
    print("   INGESTING PCRLJ AND PTD JOURNALS TO SUPABASE   ")
    print("==================================================")
    
    start_time = time.time()
    for j_file in JOURNAL_FILES:
        full_csv_path = os.path.join(DATA_DIR, j_file)
        process_journal_csv(full_csv_path)

    elapsed = time.time() - start_time
    print(f"\n==================================================")
    print(f"PCRLJ & PTD JOURNALS PROCESSED IN {elapsed:.2f} SECONDS!")
    print("==================================================")

if __name__ == "__main__":
    main()
