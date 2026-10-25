import os
import sys
import json
import hashlib
import re
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

def clean_extracted(txt: str) -> str:
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    return "\n".join(lines)

def load_or_create_store(fname: str) -> list:
    fpath = os.path.join(UNIFIED_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for k in ["provisions", "sections", "records", "data"]:
                if k in data and isinstance(data[k], list): return data[k]
    return []

def save_store(fname: str, records: list):
    fpath = os.path.join(UNIFIED_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"Saved {fname} ({len(records)} records).")

def upsert_provision(records: list, prov: dict):
    cid = prov["canonical_id"]
    for idx, r in enumerate(records):
        if r.get("canonical_id") == cid or (r.get("primary_num") == prov.get("primary_num") and r.get("secondary_num") == prov.get("secondary_num") and prov.get("primary_num")):
            records[idx] = prov
            return
    records.append(prov)

# Ingest Registration Act 49
reg_records = load_or_create_store("REGISTRATION_1908.json")
reg_reader = pypdf.PdfReader(os.path.join(PDF_DIR, "registration_act_1908.pdf"))
p21_txt = reg_reader.pages[20].extract_text()
reg49_raw = p21_txt[p21_txt.find("49. Effect of non") : p21_txt.find("50. Certain registered documents")]
reg49_clean = clean_extracted(reg49_raw)
upsert_provision(reg_records, {
    "canonical_id": "REGISTRATION_1908_SEC_49",
    "statute_code": "REGISTRATION_1908",
    "primary_num": "49",
    "secondary_num": None,
    "title": "Effect of non-registration of documents required to be registered",
    "text": reg49_clean,
    "tier": "ingested_unreviewed",
    "status": "in_force",
    "verification_status": "ingested_unreviewed",
    "source_page": 21,
    "content_hash": sha256_text(reg49_clean),
    "missing_reason": None
})
save_store("REGISTRATION_1908.json", reg_records)
print(f"Registration Act 49 ingested: {len(reg49_clean.split())} words, hash={sha256_text(reg49_clean)[:12]}...")

# Ingest CPC Order XXI Rule 24
cpc_records = load_or_create_store("CPC_1908.json")
cpc_reader = pypdf.PdfReader(os.path.join(PDF_DIR, "cpc_1908.pdf"))
p107_txt = cpc_reader.pages[106].extract_text()
r24_raw = p107_txt[p107_txt.find("24. Process for Execution") : p107_txt.find("25. Endorsement on process")]
r24_clean = clean_extracted(r24_raw)
upsert_provision(cpc_records, {
    "canonical_id": "CPC_1908_ORD_XXI_R_24",
    "statute_code": "CPC_1908",
    "primary_num": "O.XXI_R.24",
    "secondary_num": None,
    "title": "EXECUTION OF DECREES AND ORDERS: Process for execution",
    "text": r24_clean,
    "tier": "ingested_unreviewed",
    "status": "in_force",
    "verification_status": "ingested_unreviewed",
    "source_page": 107,
    "content_hash": sha256_text(r24_clean),
    "missing_reason": None
})
save_store("CPC_1908.json", cpc_records)
print(f"CPC O.XXI R.24 ingested: {len(r24_clean.split())} words, hash={sha256_text(r24_clean)[:12]}...")
