import json
import hashlib
import pypdf

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

reader = pypdf.PdfReader("data/official_pdfs/contract_act_1872.pdf")
p43_txt = reader.pages[42].extract_text() # 0-indexed 42 is page 43
s128_raw = p43_txt[p43_txt.find("128. Surety") : p43_txt.find("129.")]
lines = [l.strip() for l in s128_raw.split("\n") if l.strip()]
s128_clean = "\n".join(lines)

with open("data/unified_statutes/CONTRACT_1872.json", "r", encoding="utf-8") as f:
    records = json.load(f)

entry = {
    "canonical_id": "CONTRACT_1872_SEC_128",
    "statute_code": "CONTRACT_1872",
    "primary_num": "128",
    "secondary_num": None,
    "title": "Surety's liability co-extensive with principal debtor",
    "text": s128_clean,
    "tier": "ingested_unreviewed",
    "status": "in_force",
    "verification_status": "ingested_unreviewed",
    "source_page": 43,
    "content_hash": sha256_text(s128_clean),
    "missing_reason": None
}

found = False
for i, r in enumerate(records):
    if r.get("canonical_id") == "CONTRACT_1872_SEC_128" or r.get("primary_num") == "128":
        records[i] = entry
        found = True
        break
if not found:
    records.append(entry)

with open("data/unified_statutes/CONTRACT_1872.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2, ensure_ascii=False)

print(f"Contract Act 128 ingested: {len(s128_clean.split())} words, hash={sha256_text(s128_clean)[:12]}...")
