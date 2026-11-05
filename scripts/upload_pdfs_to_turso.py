#!/usr/bin/env python3
"""
Turso Master Scanned PDF Uploader
Batches all 278,395 authentic court law report PDFs from
I:\Legal_Master_Corpus\04_Formatted_PDFs into Turso libSQL database (case_pdfs).

Features:
- Resumable checkpointing (I:/turso_pdf_checkpoint.json)
- Batch size 25 PDFs per HTTP pipeline call (~200KB payload)
- Exponential backoff and retry
- Clean parsing of journal, year, page, case_id
"""

import os
import re
import json
import time
import base64
import urllib.request
import urllib.error

TURSO_URL = os.environ.get(
    "TURSO_DATABASE_URL_PIPELINE",
    "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
)
TURSO_TOKEN = os.environ.get(
    "TURSO_AUTH_TOKEN",
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"
)

PDF_ROOT = "I:/Legal_Master_Corpus/04_Formatted_PDFs"
CHECKPOINT_FILE = "I:/turso_pdf_checkpoint.json"
LOG_FILE = "I:/turso_pdf_upload.log"

JOURNAL_ORDER = [
    "SCMR",
    "PLD",
    "CLC",
    "MLD",
    "PCRLJ",
    "YLR",
    "CLD",
    "PLC",
    "PTD",
    "GBLR"
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

def ensure_tables():
    create_sql = """
    CREATE TABLE IF NOT EXISTS case_pdfs (
        pdf_id TEXT PRIMARY KEY,
        journal TEXT,
        year INTEGER,
        page INTEGER,
        case_id TEXT,
        pdf_base64 TEXT,
        pdf_size INTEGER
    );
    """
    req = {
        "requests": [
            {"type": "execute", "stmt": {"sql": create_sql}},
            {"type": "execute", "stmt": {"sql": "CREATE INDEX IF NOT EXISTS idx_case_pdfs_jyp ON case_pdfs (journal, year, page);"}}
        ]
    }
    payload = json.dumps(req).encode("utf-8")
    r = urllib.request.Request(
        TURSO_URL,
        data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            pass
    except Exception as e:
        log(f"Warning during ensure_tables: {e}")

def send_pdf_batch(batch: list, max_retries: int = 5) -> bool:
    requests = []
    sql = """
    INSERT OR REPLACE INTO case_pdfs (pdf_id, journal, year, page, case_id, pdf_base64, pdf_size)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    for item in batch:
        requests.append({
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [
                    {"type": "text", "value": item["pdf_id"]},
                    {"type": "text", "value": item["journal"]},
                    {"type": "integer", "value": str(item["year"]) if item["year"] else None},
                    {"type": "integer", "value": str(item["page"]) if item["page"] else None},
                    {"type": "text", "value": item["case_id"]},
                    {"type": "text", "value": item["pdf_base64"]},
                    {"type": "integer", "value": str(item["pdf_size"])}
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
                headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if "results" in res_data:
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(backoff * 2)
            else:
                time.sleep(backoff)
        except Exception as e:
            time.sleep(backoff)
        backoff = min(backoff * 2, 30)

    log(f"Failed to insert PDF batch of {len(batch)} items after {max_retries} retries.")
    return False

def extract_page_from_fname(fname: str, journal: str) -> str:
    m = re.search(r'(?:' + journal + r')[_\s]+(\d+)', fname, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r'_(\d+)_', fname)
    if m2:
        return m2.group(1)
    return ""

def upload_journal_pdfs(journal: str) -> int:
    j_dir = os.path.join(PDF_ROOT, journal)
    if not os.path.isdir(j_dir):
        log(f"Directory {j_dir} not found, skipping.")
        return 0

    checkpoint = load_checkpoint()
    completed_years = set(checkpoint.get(f"{journal}_completed_years", []))

    year_dirs = sorted([d for d in os.listdir(j_dir) if os.path.isdir(os.path.join(j_dir, d))])
    total_uploaded = 0
    BATCH_SIZE = 25

    log(f"[{journal}] Found {len(year_dirs)} years. Already completed: {len(completed_years)}")

    for y_str in year_dirs:
        if y_str in completed_years:
            continue

        y_path = os.path.join(j_dir, y_str)
        files = [f for f in os.listdir(y_path) if f.lower().endswith(".pdf")]
        if not files:
            completed_years.add(y_str)
            checkpoint[f"{journal}_completed_years"] = list(completed_years)
            save_checkpoint(checkpoint)
            continue

        year_val = int(y_str) if y_str.isdigit() else None
        batch = []
        t0 = time.time()
        y_uploaded = 0

        for fname in files:
            fpath = os.path.join(y_path, fname)
            try:
                with open(fpath, "rb") as fp:
                    pdf_data = fp.read()
            except Exception:
                continue

            page_str = extract_page_from_fname(fname, journal)
            page_val = int(page_str) if page_str.isdigit() else None
            pdf_id = f"{journal}_{y_str}_{page_str}" if page_str else f"{journal}_{y_str}_{fname}"
            case_id = f"{y_str}_{journal}_{page_str}" if page_str else f"{y_str}_{journal}_{fname}"

            b64_str = base64.b64encode(pdf_data).decode("ascii")

            batch.append({
                "pdf_id": pdf_id,
                "journal": journal,
                "year": year_val,
                "page": page_val,
                "case_id": case_id,
                "pdf_base64": b64_str,
                "pdf_size": len(pdf_data)
            })

            if len(batch) >= BATCH_SIZE:
                ok = send_pdf_batch(batch)
                if ok:
                    y_uploaded += len(batch)
                    total_uploaded += len(batch)
                batch = []

        if batch:
            ok = send_pdf_batch(batch)
            if ok:
                y_uploaded += len(batch)
                total_uploaded += len(batch)

        completed_years.add(y_str)
        checkpoint[f"{journal}_completed_years"] = list(completed_years)
        checkpoint[f"{journal}_total_uploaded"] = checkpoint.get(f"{journal}_total_uploaded", 0) + y_uploaded
        save_checkpoint(checkpoint)

        dur = time.time() - t0
        rate = y_uploaded / dur if dur > 0 else 0
        log(f"[{journal} {y_str}] Uploaded {y_uploaded} PDFs in {dur:.1f}s ({rate:.1f} PDFs/s)")

    return total_uploaded

def main():
    log("=== Turso Master Court PDF Uploader Initialized ===")
    ensure_tables()

    grand_total = 0
    for journal in JOURNAL_ORDER:
        uploaded = upload_journal_pdfs(journal)
        grand_total += uploaded

    log(f"=== ALL PDF UPLOADS COMPLETED! Grand Total: {grand_total} PDFs uploaded to Turso! ===")

if __name__ == "__main__":
    main()
