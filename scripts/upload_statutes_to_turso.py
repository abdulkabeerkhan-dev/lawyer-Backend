#!/usr/bin/env python3
"""
scripts/upload_statutes_to_turso.py

Ingests all 4,410 authentic Pakistani statutory provisions from data/statutes_v2/*.json
into the Turso libSQL database (table: statute_provisions).
"""

import os
import glob
import json
import time
import urllib.request
import urllib.error

TURSO_URL = os.environ.get("TURSO_DATABASE_URL_PIPELINE") or "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN") or "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")

DOMAIN_MAP = {
    "PPC": "criminal",
    "CRPC": "criminal",
    "ATA": "criminal",
    "CNSA": "criminal",
    "ANTI_RAPE": "criminal",
    "ARMS": "criminal",
    "PECA": "criminal",
    "CPC": "civil",
    "CONTRACT": "civil",
    "SPECIFIC_RELIEF": "civil",
    "TPA": "civil",
    "REGISTRATION": "civil",
    "LIMITATION": "civil",
    "COURT_FEES": "civil",
    "SUITS_VALUATION": "civil",
    "STAMP": "civil",
    "QSO": "evidence",
    "CONST": "constitutional",
    "COMPANIES": "corporate",
    "SECURITIES": "corporate",
    "PARTNERSHIP": "corporate",
    "FIO": "banking",
    "BCO": "banking",
    "NI_ACT": "banking",
    "BANKERS_BOOKS": "banking",
    "CANTONMENT_RENT": "rent",
    "PRPA": "rent",
    "FAMILY": "family",
    "GUARDIAN": "family",
    "CHILD_MARRIAGE": "family",
    "MUSLIM_FAMILY": "family",
    "CHRISTIAN_MARRIAGE": "family",
    "CUSTOMS": "tax",
    "SALES_TAX": "tax",
    "INCOME_TAX": "tax",
    "FEDERAL_EXCISE": "tax"
}

def infer_domain(act_code: str) -> str:
    up = act_code.upper()
    for prefix, dom in DOMAIN_MAP.items():
        if up.startswith(prefix) or f"_{prefix}_" in up:
            return dom
    return "general_legal"

def send_batch(batch: list, max_retries: int = 5) -> bool:
    sql = """
    INSERT OR REPLACE INTO statute_provisions (
        canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    requests = []
    for r in batch:
        requests.append({
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [
                    {"type": "text", "value": str(r["canonical_id"])},
                    {"type": "text", "value": str(r["act_code"])},
                    {"type": "text", "value": str(r["act_name"])},
                    {"type": "text", "value": str(r["section_num"])},
                    {"type": "text", "value": str(r["title"])},
                    {"type": "text", "value": str(r["verbatim_text"])},
                    {"type": "text", "value": str(r["domain"])},
                    {"type": "text", "value": str(r["tier"])},
                    {"type": "integer", "value": str(r["in_force"])}
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
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return "results" in data
        except Exception as e:
            if attempt == max_retries:
                print(f"Error on attempt {attempt}: {e}")
                return False
            time.sleep(1.0 * attempt)
    return False

def main():
    print(f"Loading statute files from {STATUTES_DIR}...")
    files = sorted(glob.glob(os.path.join(STATUTES_DIR, "*.json")))
    print(f"Found {len(files)} statute files.")

    all_provisions = []
    for f in files:
        act_code = os.path.splitext(os.path.basename(f))[0]
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            records = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            act_title = data.get("act_name") or data.get("title") or act_code.replace("_", " ") if isinstance(data, dict) else act_code.replace("_", " ")

            for rec in records:
                sec_num = str(rec.get("section") or rec.get("primary_num") or "").strip()
                cid = str(rec.get("canonical_id") or f"{act_code}_SEC_{sec_num}").strip()
                title = str(rec.get("title") or rec.get("heading") or f"Section {sec_num}").strip()
                v_text = str(rec.get("text") or rec.get("text_raw") or "").strip()
                tier = str(rec.get("tier") or "reviewed")
                in_force = 1 if rec.get("in_force", True) else 0
                domain = infer_domain(act_code)

                if cid and (v_text or title):
                    all_provisions.append({
                        "canonical_id": cid,
                        "act_code": act_code,
                        "act_name": act_title,
                        "section_num": sec_num,
                        "title": title,
                        "verbatim_text": v_text,
                        "domain": domain,
                        "tier": tier,
                        "in_force": in_force
                    })
        except Exception as err:
            print(f"Error reading {f}: {err}")

    print(f"Total valid provisions to ingest: {len(all_provisions)}")

    batch_size = 50
    total_uploaded = 0
    t0 = time.time()

    for i in range(0, len(all_provisions), batch_size):
        chunk = all_provisions[i:i + batch_size]
        ok = send_batch(chunk)
        if ok:
            total_uploaded += len(chunk)
            if total_uploaded % 500 == 0 or total_uploaded == len(all_provisions):
                print(f"Uploaded {total_uploaded}/{len(all_provisions)} provisions ({total_uploaded * 100 // len(all_provisions)}%) in {time.time() - t0:.1f}s")
        else:
            print(f"Failed to upload batch at index {i}")

    print(f"Finished ingesting {total_uploaded} provisions into Turso statute_provisions table in {time.time() - t0:.1f}s.")

if __name__ == "__main__":
    main()
