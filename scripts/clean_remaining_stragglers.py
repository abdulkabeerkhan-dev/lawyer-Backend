"""
scripts/clean_remaining_stragglers.py

Cleans:
- CPC Order XXI Rule 2 (strips trailing 'Courts executing Decrees')
- FIO Section 15 (strips leading '1[')
- Limitation Article 182 (adds terminal period, marks in_force=False)
- NI Act 1881 (strips trailing '_____ CHAPTER ...' headers from section ends)
"""

import os
import sys
import json
import re
import hashlib

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def clean_file(fname, cleaner_fn):
    p = os.path.join(STATUTES_DIR, fname)
    if not os.path.exists(p):
        return
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    changed = False
    for r in data:
        if cleaner_fn(r):
            changed = True
            r["content_hash"] = hashlib.sha256(r["text"].encode("utf-8")).hexdigest()
    if changed:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Cleaned {fname}")

def clean_cpc(r):
    if r.get("canonical_id") == "CPC_1908_ORD_XXI_R_2":
        txt = r.get("text", "")
        if "Courts executing Decrees" in txt:
            txt = txt.replace("Courts executing Decrees", "").strip()
            r["text"] = txt
            r["text_normalized"] = r.get("text_normalized", "").replace("Courts executing Decrees", "").strip()
            return True
    return False

def clean_fio(r):
    if r.get("canonical_id") == "FIO_2001_SEC_15":
        txt = r.get("text", "")
        if txt.startswith("1["):
            txt = txt[2:].strip()
            r["text"] = txt
            norm = r.get("text_normalized", "")
            if norm.startswith("1["):
                r["text_normalized"] = norm[2:].strip()
            return True
    return False

def clean_limitation(r):
    if r.get("canonical_id") == "LIMITATION_1908_ART_182":
        txt = r.get("text", "")
        if not txt.endswith("."):
            txt += "."
            r["text"] = txt
            r["text_normalized"] = r.get("text_normalized", "") + "."
            r["in_force"] = False
            return True
    return False

def clean_ni(r):
    txt = r.get("text", "")
    orig = txt
    # strip trailing CHAPTER headers
    txt = re.sub(r'_{2,}\s*CHAPTER\s+[IVXLCDM\d]+.*$', '', txt, flags=re.IGNORECASE).strip()
    if not re.search(r'[\.\]\)\:\'\"\*]\s*$', txt) and len(txt) > 20:
        txt += "."
    if txt != orig:
        r["text"] = txt
        r["text_normalized"] = re.sub(r'_{2,}\s*CHAPTER\s+[IVXLCDM\d]+.*$', '', r.get("text_normalized", ""), flags=re.IGNORECASE).strip()
        if not re.search(r'[\.\]\)\:\'\"\*]\s*$', r["text_normalized"]) and len(r["text_normalized"]) > 20:
            r["text_normalized"] += "."
        return True
    return False

def main():
    clean_file("CPC_1908.json", clean_cpc)
    clean_file("FIO_2001.json", clean_fio)
    clean_file("LIMITATION_1908.json", clean_limitation)
    clean_file("NI_ACT_1881.json", clean_ni)

if __name__ == "__main__":
    main()
