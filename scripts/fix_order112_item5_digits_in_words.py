"""
scripts/fix_order112_item5_digits_in_words.py

ORDER 1.12 - ITEM 5: Digits in Words (OCR Footnote Contamination)
Scans all stored text across unified statutes for:
  - Pattern 1: [A-Za-z]+\\d+[A-Za-z]+ (e.g. 'dishonest1y', mid-word digit)
  - Pattern 2: [A-Za-z]\\d\\b (e.g. 'minimum1', word-ending digit)

Fixes identified contaminations against official PDF page proofs:
  1. PPC_1860_SEC_415: Fix 'dishonest1y' in text_normalized -> 'dishonestly' (page proof: ppc_1860.pdf p. 145)
  2. BCO_1962_SEC_83: Fix 'minimum1[.]' in text/text_normalized -> 'minimum 1[.]' (page proof: banking_companies_ordinance_1962.pdf p. 96)
  3. NI_ACT_1881_SEC_131F: Fix 'l31G' in pending store -> '131G'
"""

import os
import sys
import glob
import json
import re

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)

p1 = re.compile(r'([A-Za-z]+\d+[A-Za-z]+)')
p2 = re.compile(r'([A-Za-z]\d\b)')

def scan_all_statutes():
    results = {}
    for fpath in sorted(glob.glob("data/unified_statutes/*.json")):
        fname = os.path.basename(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else list(data.values())
        file_matches = []
        for p in items:
            cid = p.get("canonical_id", "")
            for field in ["text", "text_normalized", "statutory_text"]:
                val = p.get(field)
                if isinstance(val, str) and val:
                    m1 = p1.findall(val)
                    m2 = p2.findall(val)
                    if m1 or m2:
                        file_matches.append({
                            "canonical_id": cid,
                            "field": field,
                            "mid_word": m1,
                            "end_word": m2
                        })
        results[fname] = file_matches
    return results

print("=" * 80)
print("ORDER 1.12 - ITEM 5: DIGITS IN WORDS AUDIT (BEFORE FIX)")
print("=" * 80)
before_scan = scan_all_statutes()
for fname, matches in before_scan.items():
    print(f"{fname:<26}: {len(matches)} contamination occurrences")
    for m in matches:
        print(f"   [{m['canonical_id']}] {m['field']}: mid={m['mid_word']} | end={m['end_word']}")

# Apply Fixes:
# 1. PPC_1860.json: SEC_415
ppc_path = "data/unified_statutes/PPC_1860.json"
with open(ppc_path, "r", encoding="utf-8") as f:
    ppc_data = json.load(f)

for p in ppc_data:
    if p.get("canonical_id") == "PPC_1860_SEC_415":
        if "dishonest1y" in (p.get("text_normalized") or ""):
            p["text_normalized"] = p["text_normalized"].replace("dishonest1y", "dishonestly")
            print("\n[FIX 1] Fixed 'dishonest1y' -> 'dishonestly' in PPC_1860_SEC_415 text_normalized (page proof: ppc_1860.pdf p. 145)")

with open(ppc_path, "w", encoding="utf-8") as f:
    json.dump(ppc_data, f, indent=2, ensure_ascii=False)

# 2. BCO_1962.json: SEC_83
bco_path = "data/unified_statutes/BCO_1962.json"
with open(bco_path, "r", encoding="utf-8") as f:
    bco_data = json.load(f)

for p in bco_data:
    if p.get("canonical_id") == "BCO_1962_SEC_83":
        for field in ["text", "text_normalized"]:
            val = p.get(field, "")
            if "minimum1[.]" in val:
                p[field] = val.replace("minimum1[.]", "minimum 1[.]")
                print(f"[FIX 2] Fixed 'minimum1[.]' -> 'minimum 1[.]' in BCO_1962_SEC_83 {field} (page proof: bco_1962.pdf p. 96)")

with open(bco_path, "w", encoding="utf-8") as f:
    json.dump(bco_data, f, indent=2, ensure_ascii=False)

# 3. Pending NI Act if present
ni_path = "data/pending/unified_statutes/NI_ACT_1881.json"
if os.path.exists(ni_path):
    with open(ni_path, "r", encoding="utf-8") as f:
        ni_data = json.load(f)
    for p in ni_data:
        if p.get("canonical_id") == "NI_ACT_1881_SEC_131F":
            for field in ["text", "text_normalized"]:
                val = p.get(field, "")
                if "l31G" in val:
                    p[field] = val.replace("l31G", "131G")
                    print(f"[FIX 3] Fixed 'l31G' -> '131G' in NI_ACT_1881_SEC_131F {field}")
    with open(ni_path, "w", encoding="utf-8") as f:
        json.dump(ni_data, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 80)
print("ORDER 1.12 - ITEM 5: DIGITS IN WORDS AUDIT (AFTER FIX)")
print("=" * 80)
after_scan = scan_all_statutes()
total_remaining = sum(len(m) for m in after_scan.values())
for fname, matches in after_scan.items():
    print(f"{fname:<26}: {len(matches)} contamination occurrences")
    for m in matches:
        print(f"   [{m['canonical_id']}] {m['field']}: mid={m['mid_word']} | end={m['end_word']}")

print(f"\nTotal remaining digit contamination across all unified statutes: {total_remaining}")
assert total_remaining == 0, f"Expected 0 remaining contaminations, got {total_remaining}"
print("VERIFICATION: Zero digit-in-word contaminations remain across all unified statutes!")
