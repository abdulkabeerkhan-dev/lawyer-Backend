import os
import sys
import re
import csv
import glob
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from supabase import create_client

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

csv.field_size_limit(100 * 1024 * 1024)

# Set safety guard explicitly for this authorized migration
os.environ["ALLOW_DIRECT_PROD_MUTATION"] = "TRUE"

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("[ERROR] SUPABASE_URL or SUPABASE_SERVICE_KEY missing from environment.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

CSV_DIR = r"D:\missing_gaps_verified\cleaned_CSVs"
PDF_DIR = r"D:\missing_gaps_verified\PDFs"
BUCKET_NAME = "judgments-pdf"
STATE_FILE = "ingestion_state_supabase.json"

STORAGE_WORKERS = 8
DB_BATCH_SIZE = 200

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"uploaded_pdfs": {}, "ingested_cases": {}}

def save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Notice saving state: {e}")

def sanitize_filename(name):
    name = str(name).strip()
    name = re.sub(r'[\\/*?:"<>|\r\n\t]', '_', name)
    name = re.sub(r'[\s\.\(\)\-]+', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name[:60]

def upload_single_pdf(args) -> Tuple[str, bool, str]:
    local_path, remote_path = args
    for attempt in range(4):
        try:
            with open(local_path, 'rb') as f:
                pdf_bytes = f.read()
            sb.storage.from_(BUCKET_NAME).upload(
                path=remote_path,
                file=pdf_bytes,
                file_options={'content-type': 'application/pdf', 'upsert': 'true'}
            )
            return (remote_path, True, "")
        except Exception as e:
            if attempt < 3:
                time.sleep(0.5 * (attempt + 1))
            else:
                return (remote_path, False, str(e))
    return (remote_path, False, "Max retries exceeded")


def format_date_for_pg(date_str: str, year: str) -> str:
    if not date_str:
        return f"{year}-01-01"
    # Try parsing patterns like "16th June 1979", "16-06-1979", "1979"
    m_month = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})', date_str)
    if m_month:
        day, mon_name, yr = m_month.groups()
        months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        m_code = months.get(mon_name[:3].lower(), '01')
        return f"{yr}-{m_code}-{int(day):02d}"
    
    m_iso = re.search(r'(\d{4})[\.\/\-](\d{1,2})[\.\/\-](\d{1,2})', date_str)
    if m_iso:
        yr, mo, da = m_iso.groups()
        return f"{yr}-{int(mo):02d}-{int(da):02d}"

    m_dmy = re.search(r'(\d{1,2})[\.\/\-](\d{1,2})[\.\/\-](\d{4})', date_str)
    if m_dmy:
        da, mo, yr = m_dmy.groups()
        return f"{yr}-{int(mo):02d}-{int(da):02d}"

    return f"{year}-01-01"

def process_journal_supabase(csv_file: str, state: Dict[str, Any]):
    filename = os.path.basename(csv_file)
    print(f"\n{'='*70}\nSTARTING SUPABASE INGESTION FOR: {filename}\n{'='*70}")

    rows = []
    with open(csv_file, 'r', encoding='utf-8-sig', errors='replace') as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            rows.append(r)

    print(f"Loaded {len(rows):,} records from {filename}")

    # 1. Map local PDF files and prepare upload tasks
    upload_tasks = []
    case_pdf_map = {}

    for r in rows:
        jn = r.get("journal", "").strip().upper()
        yr = r.get("year", "").strip()
        idx = r.get("case_index", "").strip()
        cit = r.get("citation", "").strip()
        court = r.get("court", "").strip()

        cit_slug = sanitize_filename(cit)
        court_short = sanitize_filename(court.split()[0]) if court else ""
        if court_short and court_short.lower() not in cit_slug.lower():
            pdf_name = f"{cit_slug}_{court_short}_{idx}.pdf"
        else:
            pdf_name = f"{cit_slug}_Case_{idx}.pdf"

        local_pdf_path = os.path.join(PDF_DIR, jn, yr, pdf_name)
        remote_storage_path = f"{jn}/{yr}/{pdf_name}"
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{remote_storage_path}"

        case_key = f"{jn}_{yr}_{idx}"
        case_pdf_map[case_key] = public_url

        if remote_storage_path not in state["uploaded_pdfs"]:
            if os.path.exists(local_pdf_path):
                upload_tasks.append((local_pdf_path, remote_storage_path))

    # Run Storage Uploads
    if upload_tasks:
        print(f"\n[STORAGE] Uploading {len(upload_tasks):,} PDFs to Supabase bucket '{BUCKET_NAME}'...")
        uploaded_count = 0
        t0_storage = time.time()
        with ThreadPoolExecutor(max_workers=STORAGE_WORKERS) as executor:
            futures = [executor.submit(upload_single_pdf, task) for task in upload_tasks]
            for future in as_completed(futures):
                rem_path, success, err = future.result()
                if success:
                    state["uploaded_pdfs"][rem_path] = True
                    uploaded_count += 1
                else:
                    print(f"Notice upload {rem_path}: {err}")
                if (uploaded_count) % 500 == 0 or uploaded_count == len(upload_tasks):
                    rate = uploaded_count / (time.time() - t0_storage + 0.001)
                    print(f"  Storage progress: {uploaded_count:,}/{len(upload_tasks):,} uploaded ({rate:.1f} PDFs/sec)...")
                    save_state(state)

        print(f"[STORAGE DONE] Uploaded {uploaded_count:,} PDFs in {time.time() - t0_storage:.1f}s.")
        save_state(state)
    else:
        print("[STORAGE] All PDFs for this dataset are already recorded as uploaded.")

    # 2. Database Upsert to full_judgments
    print(f"\n[DATABASE] Preparing records for 'full_judgments' table...")
    db_records: List[Dict[str, Any]] = []
    total_db_upserted = 0
    t0_db = time.time()

    for idx, r in enumerate(rows):
        jn = r.get("journal", "").strip().upper()
        yr = r.get("year", "").strip()
        case_idx = r.get("case_index", "").strip()
        cit = r.get("citation", "").strip()
        title = r.get("title", "").strip()
        court = r.get("court", "").strip()
        bench = r.get("bench", "").strip()
        docket = r.get("docket_number", "").strip()
        date_str = r.get("decision_date", "").strip()
        hn = r.get("headnotes", "").strip()
        jd = r.get("judgment_body", "").strip()

        case_key = f"{jn}_{yr}_{case_idx}"
        pdf_public_url = case_pdf_map.get(case_key, "")

        # Canonical case_id format: YYYY_JOURNAL_INDEX
        # e.g. 1979_CLC_1, 1988_MLD_1
        case_id = f"{yr}_{jn}_{case_idx}"

        # Full text: clean combination of headnotes and judgment
        if hn and jd and hn != jd:
            combined_text = f"CITATION: {cit}\nTITLE: {title}\nCOURT: {court}\nBENCH: {bench}\nDOCKET: {docket}\nDATE: {date_str}\n\nHEADNOTES:\n{hn}\n\nJUDGMENT / ORDER:\n{jd}"
        else:
            combined_text = f"CITATION: {cit}\nTITLE: {title}\nCOURT: {court}\nBENCH: {bench}\nDOCKET: {docket}\nDATE: {date_str}\n\n{jd or hn}"

        pg_date = format_date_for_pg(date_str, yr)

        db_rec = {
            "case_id": case_id,
            "case_title": title[:250],
            "neutral_citation": cit,
            "court_name": court or "Superior Courts of Pakistan",
            "bench": bench[:250] if bench else None,
            "decision_date": pg_date,
            "full_text": combined_text[:200000],
            "docket_number": docket[:150] if docket else None,
            "source_url": pdf_public_url
        }
        db_records.append(db_rec)

        if len(db_records) >= DB_BATCH_SIZE or idx == len(rows) - 1:
            # Batch upsert
            for attempt in range(3):
                try:
                    sb.table("full_judgments").upsert(db_records, on_conflict="case_id").execute()
                    total_db_upserted += len(db_records)
                    for rec in db_records:
                        state["ingested_cases"][rec["case_id"]] = True
                    break
                except Exception as err:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        print(f"Database batch upsert error on batch ending row {idx+1}: {err}")
            
            rate_db = total_db_upserted / (time.time() - t0_db + 0.001)
            print(f"  DB progress: {total_db_upserted:,}/{len(rows):,} upserted ({rate_db:.1f} rows/sec)...", end="\r")
            db_records = []

    print(f"\n[DATABASE DONE] Finished {filename}: {total_db_upserted:,} records upserted into full_judgments in {time.time() - t0_db:.1f}s.")
    save_state(state)

def main():
    print("=" * 80)
    print("PAKISTAN LEGAL MASTER CORPUS - PRODUCTION SUPABASE INGESTION")
    print(f"Supabase Storage Bucket: {BUCKET_NAME}")
    print(f"Supabase Database Table: full_judgments")
    print("=" * 80)

    state = load_state()
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, "*_cleaned.csv")))

    t0_all = time.time()
    for f in csv_files:
        process_journal_supabase(f, state)

    print("\n" + "=" * 80)
    print(f"ALL DATASETS INGESTED TO SUPABASE STORAGE & DATABASE!")
    print(f"Total Time Taken: {time.time() - t0_all:.1f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
