import os
import json
import hashlib

SCRATCH_DIR = os.path.abspath(r"C:\Users\AKK\.gemini\antigravity\brain\dac42a9b-42b9-4274-b78f-d69c94f06232\scratch")
REPO_DIR = os.path.abspath(".")
QUARANTINE_DIR = os.path.join(REPO_DIR, "data", "quarantine", "unified_statutes")
PENDING_DIR = os.path.join(REPO_DIR, "data", "pending", "unified_statutes")

os.makedirs(PENDING_DIR, exist_ok=True)

ACT_PDF_MAP = {
    "ARBITRATION_1940": os.path.join(SCRATCH_DIR, "arbitration_1940_real_official.pdf"),
    "MFLO_1961": os.path.join(SCRATCH_DIR, "mflo_1961_official.pdf"),
    "ITO_2001": os.path.join(SCRATCH_DIR, "ito_2001_fbr.pdf"),
    "LAND_REVENUE_1967": os.path.join(SCRATCH_DIR, "land_revenue_1967_official.pdf"),
}

for act_code, pdf_path in ACT_PDF_MAP.items():
    json_path = os.path.join(QUARANTINE_DIR, f"{act_code}.json")
    if not os.path.exists(json_path):
        print(f"Quarantined JSON missing for {act_code}: {json_path}")
        continue
    if not os.path.exists(pdf_path):
        print(f"PDF missing for {act_code}: {pdf_path}")
        continue

    with open(pdf_path, "rb") as pf:
        pdf_sha = hashlib.sha256(pf.read()).hexdigest()

    with open(json_path, "r", encoding="utf-8") as jf:
        records = json.load(jf)

    # Attach pending verification metadata
    for rec in records:
        rec["tier"] = "pending_verification"
        rec["verification_status"] = "pending_review"
        rec["staged_pdf_file"] = os.path.basename(pdf_path)
        rec["staged_pdf_sha256"] = pdf_sha
        rec["admin_review_status"] = "pending"

    dest_path = os.path.join(PENDING_DIR, f"{act_code}.json")
    with open(dest_path, "w", encoding="utf-8") as out:
        json.dump(records, out, indent=2, ensure_ascii=False)

    print(f"Re-ingested {act_code} ({len(records)} provisions) into data/pending/unified_statutes/ with PDF SHA256: {pdf_sha[:16]}...")
