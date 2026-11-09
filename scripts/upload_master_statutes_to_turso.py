#!/usr/bin/env python3
"""
scripts/upload_master_statutes_to_turso.py

Streams clean, deduplicated statutory provisions from the local SQLite master database
(I:\Statutes\pakistan_statutes_master.db) into the Turso cloud database (table: statute_provisions).
Includes automatic checkpointing, batching, domain tagging, and retry logic.
"""

import os
import sys
import json
import time
import sqlite3
import urllib.request
import urllib.error

DB_PATH = r"I:\Statutes\pakistan_statutes_master.db"
CHECKPOINT_PATH = r"I:\Statutes\turso_upload_checkpoint.json"

TURSO_URL = os.environ.get("TURSO_DATABASE_URL_PIPELINE") or "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN") or "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"

BATCH_SIZE = 100

DOMAIN_KEYWORDS = [
    ("CRIMINAL", ["PENAL", "CRIMINAL", "CRPC", "PPC", "NAB", "ANTI-TERRORISM", "NARCOTIC", "ARMS", "CORRUPTION", "CYBER"]),
    ("CIVIL", ["SPECIFIC RELIEF", "CONTRACT", "CIVIL PROCEDURE", "CPC", "LIMITATION", "PROPERTY", "REGISTRATION", "EASEMENT", "TRANSFER OF PROPERTY", "COURT FEES", "SUITS VALUATION", "STAMP"]),
    ("RENT", ["RENT", "RENTED", "TENANCY", "PREMISES", "CANTONMENT"]),
    ("FAMILY", ["FAMILY", "MARRIAGE", "DIVORCE", "GUARDIAN", "CHILD", "DOWRY", "SUCCESSION", "INHERITANCE"]),
    ("CORPORATE", ["COMPANIES", "CORPORATION", "SECURITIES", "PARTNERSHIP", "BANKING", "FINANCIAL", "INSURANCE", "NEGOTIABLE", "ARBITRATION"]),
    ("CONSTITUTIONAL", ["CONSTITUTION", "HIGH COURT", "SUPREME COURT", "JUDICIAL", "WRIT", "CIVIL SERVANT"]),
    ("TAX", ["INCOME TAX", "SALES TAX", "CUSTOMS", "EXCISE", "REVENUE", "FINANCE ACT"])
]

def infer_domain(title: str) -> str:
    up = title.upper()
    for dom, kws in DOMAIN_KEYWORDS:
        if any(kw in up for kw in kws):
            return dom.lower()
    return "general_legal"

def send_batch(batch: list, max_retries: int = 5) -> bool:
    sql = """
    INSERT OR REPLACE INTO statute_provisions (
        canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force, jurisdiction
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    requests = []
    for r in batch:
        requests.append({
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [
                    {"type": "text", "value": str(r["canonical_id"])},
                    {"type": "text", "value": str(r["act_code"])[:60]},
                    {"type": "text", "value": str(r["act_name"])},
                    {"type": "text", "value": str(r["section_num"])},
                    {"type": "text", "value": str(r["title"])},
                    {"type": "text", "value": str(r["verbatim_text"])},
                    {"type": "text", "value": str(r["domain"])},
                    {"type": "text", "value": str(r["tier"])},
                    {"type": "integer", "value": str(r["in_force"])},
                    {"type": "text", "value": str(r["jurisdiction"])}
                ]
            }
        })

    payload = json.dumps({"requests": requests}).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                TURSO_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {TURSO_TOKEN}",
                    "Content-Type": "application/json",
                    "User-Agent": "SectionLegal/2.0"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return "results" in data
        except Exception as e:
            if attempt == max_retries:
                print(f"Error on attempt {attempt}: {e}", flush=True)
                return False
            time.sleep(1.0 * attempt)
    return False

def main():
    print("=" * 70, flush=True)
    print("TURSO STATUTE INGESTION WORKER", flush=True)
    print("=" * 70, flush=True)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: SQLite database not found at {DB_PATH}", flush=True)
        sys.exit(1)

    # Checkpoint
    checkpoint = 0
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r") as fp:
                chk = json.load(fp)
                checkpoint = chk.get("last_offset", 0)
                print(f"Resuming from checkpoint offset: {checkpoint:,}", flush=True)
        except Exception as e:
            print(f"Notice: Failed to load checkpoint: {e}", flush=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM statutes")
    total_statutes = cur.fetchone()[0]
    print(f"Total provisions available to upload: {total_statutes:,}", flush=True)

    # Order by length of text desc to get high-content substantive laws first, or by priority
    cur.execute("""
    SELECT canonical_id, jurisdiction, statute_title, section_number, section_title, full_text, rowid
    FROM statutes
    WHERE rowid > ?
    ORDER BY rowid ASC
    """, (checkpoint,))

    batch = []
    processed = checkpoint
    batch_count = 0
    start_time = time.time()

    while True:
        rows = cur.fetchmany(1000)
        if not rows:
            break

        for row in rows:
            cid, jur, title, sec_num, sec_title, full_txt, r_id = row
            dom = infer_domain(title)
            tier = "tier_1" if dom in ["civil", "criminal", "rent", "family", "constitutional"] else "tier_2"

            batch.append({
                "canonical_id": cid,
                "act_code": title,
                "act_name": title,
                "section_num": sec_num,
                "title": sec_title or "",
                "verbatim_text": full_txt,
                "domain": dom,
                "tier": tier,
                "in_force": 1,
                "jurisdiction": jur
            })

            if len(batch) >= BATCH_SIZE:
                ok = send_batch(batch)
                if ok:
                    processed += len(batch)
                    batch_count += 1
                    batch = []

                    # Save checkpoint every 10 batches (1,000 provisions)
                    if batch_count % 10 == 0:
                        with open(CHECKPOINT_PATH, "w") as fp:
                            json.dump({"last_offset": r_id, "uploaded_provisions": processed}, fp)
                        elapsed = time.time() - start_time
                        rate = (processed - checkpoint) / max(elapsed, 1.0)
                        print(f"  Uploaded: {processed:,} / {total_statutes:,} provisions ({rate:.1f} rec/s)", flush=True)
                else:
                    print(f"FAILED to upload batch ending at rowid {r_id}. Retrying in 5s...", flush=True)
                    time.sleep(5)

    if batch:
        ok = send_batch(batch)
        if ok:
            processed += len(batch)

    conn.close()
    print("=" * 70, flush=True)
    print(f"Upload complete! Total in Turso: {processed:,} provisions", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    main()
