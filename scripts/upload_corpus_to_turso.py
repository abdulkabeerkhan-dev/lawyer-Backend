#!/usr/bin/env python3
"""
Turso Master Corpus Uploader
Batches all authentic Pakistan law cases from I:\*.csv into Turso libSQL database.
Features:
- Resumable checkpointing (I:/turso_upload_checkpoint.json)
- Batch size 50 statements per HTTP pipeline call
- Exponential backoff and retry
- Clean citation, court name, and body extraction
"""

import csv
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

# Allow huge fields in judgment CSVs
csv.field_size_limit(2147483647)

TURSO_URL = os.environ.get("TURSO_DATABASE_URL_PIPELINE") or "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN") or "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"

CHECKPOINT_FILE = r"I:\turso_upload_checkpoint.json"
LOG_FILE = r"I:\turso_upload.log"

CSV_ORDER = [
    "SCMR_cases.csv",
    "CLD_cases.csv",
    "PTD_cases.csv",
    "GBLR_cases.csv",
    "PLC_cases.csv",
    "CLC_cases.csv",
    "PCRLJ_cases.csv",
    "YLR_cases.csv",
    "MLD_cases.csv",
    "pakistan_law_cases.csv",
    "PLD_cases.csv"
]

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Warning: could not read checkpoint: {e}")
    return {}

def save_checkpoint(cp: dict):
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(cp, f, indent=2)
    except Exception as e:
        log(f"Warning: could not save checkpoint: {e}")

def clean_title(raw_title_col: str) -> str:
    t = re.sub(r'^\d+\s+\d{4}\s+[A-Za-z]+\s+\d+\s+', '', raw_title_col.strip())
    parts = re.split(r'\s+-\s+Honorable|\s+-\s+Supreme|\s+SUPREME-COURT|\s+HIGH-COURT', t, flags=re.IGNORECASE)
    cleaned = parts[0].strip()
    return cleaned[:300] if len(cleaned) > 300 else cleaned

def derive_court(journal: str, title: str) -> str:
    j = journal.upper()
    t_up = title.upper()
    if j == "SCMR" or "SUPREME COURT" in t_up:
        return "Supreme Court of Pakistan"
    if "LAHORE HIGH COURT" in t_up or "LHC" in t_up:
        return "Lahore High Court"
    if "SINDH HIGH COURT" in t_up or "SHC" in t_up:
        return "High Court of Sindh"
    if "PESHAWAR HIGH COURT" in t_up or "PHC" in t_up:
        return "Peshawar High Court"
    if "BALOCHISTAN HIGH COURT" in t_up or "BHC" in t_up:
        return "High Court of Balochistan"
    if "ISLAMABAD HIGH COURT" in t_up or "IHC" in t_up:
        return "Islamabad High Court"
    if "FEDERAL SHARIAT COURT" in t_up or "FSC" in t_up:
        return "Federal Shariat Court"
    return "High Court / Appellate Tribunal"

def send_batch_to_turso(batch: list, max_retries: int = 5) -> bool:
    requests = []
    sql = """
    INSERT OR REPLACE INTO case_texts (
        case_id, neutral_citation, case_title, court_name, year, journal, page, content_level, full_text, headnote
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for r in batch:
        year_arg = {"type": "integer", "value": str(r["year"])} if r.get("year") is not None else {"type": "null"}
        page_arg = {"type": "integer", "value": str(r["page"])} if r.get("page") is not None else {"type": "null"}
        requests.append({
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [
                    {"type": "text", "value": str(r.get("case_id", ""))},
                    {"type": "text", "value": str(r.get("neutral_citation", ""))},
                    {"type": "text", "value": str(r.get("case_title", ""))},
                    {"type": "text", "value": str(r.get("court_name", ""))},
                    year_arg,
                    {"type": "text", "value": str(r.get("journal", ""))},
                    page_arg,
                    {"type": "text", "value": str(r.get("content_level", ""))},
                    {"type": "text", "value": str(r.get("full_text", ""))},
                    {"type": "text", "value": str(r.get("headnote", "")) if r.get("headnote") else ""}
                ]
            }
        })

    payload = json.dumps({"requests": requests}).encode("utf-8")

    backoff = 2
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                TURSO_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {TURSO_TOKEN}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if "results" in res_data:
                    return True
                else:
                    log(f"Turso response missing results: {res_data}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            log(f"HTTPError {e.code} on attempt {attempt}: {err_body[:200]}")
            if e.code == 429:
                time.sleep(backoff * 2)
            else:
                time.sleep(backoff)
        except Exception as e:
            log(f"Network error on attempt {attempt}: {e}")
            time.sleep(backoff)
        backoff = min(backoff * 2, 30)

    log(f"Failed to insert batch of {len(batch)} items after {max_retries} attempts.")
    return False

def upload_csv(csv_path: str, filename: str, start_index: int = 0) -> int:
    log(f"Starting upload for {filename} (resuming from index {start_index})...")
    batch = []
    BATCH_SIZE = 50
    total_processed = 0
    t_start = time.time()
    checkpoint = load_checkpoint()

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return 0

        has_full_judgment_col = len(header) >= 6 and "Full Judgment" in header[5]

        for i, row in enumerate(reader):
            if i < start_index:
                continue

            if len(row) < 5:
                continue

            journal = row[0].strip().upper()
            year = int(row[1].strip()) if row[1].strip().isdigit() else None
            title_col = row[3].strip()

            if has_full_judgment_col:
                headnote = row[4].strip()
                full_body = row[5].strip() if len(row) > 5 else ""
            else:
                full_body = row[4].strip()
                headnote = full_body[:1200] if len(full_body) > 1200 else full_body

            # Extract page from citation in title_col (e.g. 2021 SCMR 1463)
            m_cit = re.search(r'\b(\d{4})\s+([A-Za-z]+)\s+(\d+)\b', title_col)
            if m_cit:
                yr_val, jn_val, page_val = m_cit.groups()
                citation = f"{yr_val} {jn_val.upper()} {page_val}"
                case_id = f"{yr_val}_{jn_val.upper()}_{page_val}"
                page = int(page_val)
            else:
                citation = f"{year} {journal} {i}"
                case_id = f"{year}_{journal}_{i}"
                page = None

            title = clean_title(title_col)
            court = derive_court(journal, title_col)
            content_level = "full_judgment" if len(full_body) > 300 else "headnote_only"
            text_to_store = full_body if content_level == "full_judgment" else headnote

            batch.append({
                "case_id": case_id,
                "neutral_citation": citation,
                "case_title": title,
                "court_name": court,
                "year": year,
                "journal": journal,
                "page": page,
                "content_level": content_level,
                "full_text": text_to_store,
                "headnote": headnote
            })

            if len(batch) >= BATCH_SIZE:
                success = send_batch_to_turso(batch)
                if not success:
                    log(f"Batch failed in {filename} at row {i+1}. Attempting row-by-row fallback...")
                    for single_r in batch:
                        ok_single = send_batch_to_turso([single_r], max_retries=2)
                        if ok_single:
                            total_processed += 1
                    checkpoint[filename] = i + 1
                    save_checkpoint(checkpoint)
                    batch = []
                else:
                    total_processed += len(batch)
                    checkpoint[filename] = i + 1
                    save_checkpoint(checkpoint)
                    batch = []

                if total_processed % 500 == 0:
                    rate = total_processed / (time.time() - t_start)
                    log(f"[{filename}] Processed row {i+1} ({total_processed} uploaded, {rate:.1f} rows/s)")

        # Flush final remaining
        if batch:
            send_batch_to_turso(batch)
            total_processed += len(batch)
            checkpoint[filename] = i + 1
            save_checkpoint(checkpoint)

    log(f"Completed {filename}! Total uploaded: {total_processed} records.")
    return total_processed

def main():
    log("=== Turso Legal Master Corpus Uploader Initialized ===")
    checkpoint = load_checkpoint()

    grand_total = 0
    for fname in CSV_ORDER:
        csv_path = os.path.join("I:/", fname)
        if not os.path.exists(csv_path):
            log(f"File not found: {csv_path}, skipping.")
            continue

        start_idx = checkpoint.get(fname, 0)
        uploaded = upload_csv(csv_path, fname, start_index=start_idx)
        grand_total += uploaded

    log(f"=== ALL UPLOADS COMPLETED! Grand Total: {grand_total} cases uploaded to Turso! ===")

if __name__ == "__main__":
    main()
