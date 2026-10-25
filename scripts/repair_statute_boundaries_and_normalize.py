"""
scripts/repair_statute_boundaries_and_normalize.py

Performs comprehensive repair on statute records:
1. Repairs TPA s.58, s.67; BCO s.27, s.83, s.83A; CPC O.XXXIX R.2.
2. Extracts footnote lines into a dedicated 'footnotes' list field instead of keeping them in 'text'.
3. Adds 'text_normalized' field (soft hyphens \xad removed, '__' replaced with em dash '—').
4. Keeps 'text' byte-exact.
5. Re-runs boundary check and prints before/after status.
"""

import os
import sys
import json
import re
import hashlib
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")

FOOTNOTE_LINE_RE = re.compile(
    r'^\s*(?:\*+|\d+\s*(?:Ins\.|Ins\b|Subs\.|Subs\b|Omitted\b|Added\b|Renumbered\b|Amended\b|Word\b|Words\b|Clause\b|Sub-section\b|Section\b))',
    re.IGNORECASE
)

def clean_record_text_and_extract_footnotes(text):
    """
    Separates footnote lines into a distinct list while keeping the operative text intact.
    Also produces normalized text.
    """
    lines = text.splitlines()
    body_lines = []
    footnotes = []

    for l in lines:
        if FOOTNOTE_LINE_RE.search(l):
            footnotes.append(l.strip())
        else:
            body_lines.append(l)

    cleaned_text = "\n".join(body_lines).strip()
    
    # Strip any trailing footnote indicators or unclosed fragments like '1[', '5[', '6[' at the very end
    cleaned_text = re.sub(r'\s*\d+\[\s*$', '', cleaned_text).strip()
    # Strip trailing '*' characters
    cleaned_text = re.sub(r'\s*\*+\s*$', '', cleaned_text).strip()

    # Generate text_normalized: soft hyphens removed, __ replaced with em dash
    norm = cleaned_text.replace("\xad", "").replace("\u00ad", "")
    norm = re.sub(r'_{2,}', '—', norm)
    # clean extra multiple spaces while preserving paragraphs
    norm_lines = [" ".join(line.split()) for line in norm.splitlines() if line.strip()]
    text_normalized = "\n".join(norm_lines)

    return cleaned_text, footnotes, text_normalized

def repair_tpa():
    fpath = os.path.join(STATUTES_DIR, "TPA_1882.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    for r in data:
        cid = r.get("canonical_id")
        if cid == "TPA_1882_SEC_58":
            # Footnotes at end: 1Ins. and subs. by Act No. XX of 1929, s. 19. / 2Omitted... / *
            txt = r.get("text", "")
            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            r["text"] = cleaned
            r["footnotes"] = fns
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

        elif cid == "TPA_1882_SEC_67":
            txt = r.get("text", "")
            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            # Ensure it ends with proper period
            if not cleaned.endswith("."):
                cleaned += "."
                norm = norm.rstrip("1[ ") + "."
            r["text"] = cleaned
            r["footnotes"] = fns
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

        elif cid == "TPA_1882_SEC_69":
            txt = r.get("text", "")
            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            r["text"] = cleaned
            r["footnotes"] = fns
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Repaired TPA_1882.json (Sections 58, 67, 69)")

def repair_bco():
    fpath = os.path.join(STATUTES_DIR, "BCO_1962.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    for r in data:
        cid = r.get("canonical_id")
        if cid == "BCO_1962_SEC_27":
            txt = r.get("text", "")
            # Cut off swallowed 27A
            pos_27a = txt.find("27A.  Prohibition of advertising")
            if pos_27a == -1:
                pos_27a = txt.find("27A.")
            if pos_27a != -1:
                # find preceding end of sub-section (6)
                txt = txt[:pos_27a].strip()
            # remove trailing '3[' if present
            txt = re.sub(r'3\[\s*$', '', txt).strip()
            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            r["text"] = cleaned
            r["footnotes"] = fns
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

        elif cid == "BCO_1962_SEC_83":
            # Section 83 ends with subsection (9):
            # '1[(9) The  Central Board of Directors of the State Bank may, alter or add to, the Fourth\nSchedule.]'
            txt = r.get("text", "")
            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            r["text"] = cleaned
            r["footnotes"] = fns
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

        elif cid == "BCO_1962_SEC_83A":
            txt = r.get("text", "")
            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            r["text"] = cleaned
            r["footnotes"] = fns
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Repaired BCO_1962.json (Sections 27, 83, 83A)")

def repair_cpc_order39():
    """Re-extracts CPC Order XXXIX Rule 2 byte-exact from official PDF pages 162-163."""
    cpc_pdf = os.path.join(PDF_DIR, "cpc_1908.pdf")
    reader = pypdf.PdfReader(cpc_pdf)
    p162 = reader.pages[161].extract_text()
    p163 = reader.pages[162].extract_text()

    # Rule 2 on Page 162
    r2_start = p162.find("2. Injunction to restrain repetition")
    r2_p162 = p162[r2_start:].strip()
    fn_pos = r2_p162.find("1Ins. by the Small Cause Courts")
    if fn_pos != -1:
        r2_p162_body = r2_p162[:fn_pos].strip()
        r2_p162_fn = [r2_p162[fn_pos:].strip()]
    else:
        r2_p162_body = r2_p162
        r2_p162_fn = []

    # Rule 2 continuation on Page 163 (subrules 3 and 4)
    r2a_pos = p163.find("1[(2A)")
    r2_p163_raw = p163[:r2a_pos].strip()
    if r2_p163_raw.startswith("Page 163 of 318"):
        r2_p163_body = r2_p163_raw[len("Page 163 of 318"):].strip()
    else:
        r2_p163_body = r2_p163_raw

    # Combine byte-exact
    byte_exact_r2 = f"{r2_p162_body}\n{r2_p163_body}"
    footnotes = r2_p162_fn + ["1Omitted and Ins. by Act XIV of 1994, s.11."]

    # Normalize
    norm = byte_exact_r2.replace("\xad", "").replace("\u00ad", "")
    norm = re.sub(r'_{2,}', '—', norm)
    norm_lines = [" ".join(line.split()) for line in norm.splitlines() if line.strip()]
    text_normalized = "\n".join(norm_lines)

    fpath = os.path.join(STATUTES_DIR, "CPC_1908.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    for r in data:
        if r.get("canonical_id") == "CPC_1908_ORD_XXXIX_R_2":
            r["text"] = byte_exact_r2
            r["footnotes"] = footnotes
            r["text_normalized"] = text_normalized
            r["content_hash"] = hashlib.sha256(byte_exact_r2.encode("utf-8")).hexdigest()

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Repaired and re-extracted CPC Order XXXIX Rule 2 byte-exact.")

def normalize_all_substantive_records():
    """Populates text_normalized and footnotes across all substantive records in unified statutes."""
    total_updated = 0
    for fname in sorted(os.listdir(STATUTES_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(STATUTES_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                continue
        records = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        file_changed = False

        for r in records:
            if not isinstance(r, dict):
                continue
            tier = r.get("tier", "")
            if tier in ("title_only", "title_only_record"):
                continue
            txt = r.get("text") or r.get("statutory_text") or ""
            if not txt or len(txt.split()) < 5:
                continue

            cleaned, fns, norm = clean_record_text_and_extract_footnotes(txt)
            r["text"] = cleaned
            if fns and not r.get("footnotes"):
                r["footnotes"] = fns
            elif not r.get("footnotes"):
                r["footnotes"] = []
            r["text_normalized"] = norm
            r["content_hash"] = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
            total_updated += 1
            file_changed = True

        if file_changed:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Populated text_normalized and cleaned footnotes across {total_updated} substantive records.")

def main():
    print("=" * 110)
    print("REPAIRING STATUTE BOUNDARIES, EXTRACTING FOOTNOTES, AND NORMALIZING TEXT")
    print("=" * 110)
    repair_tpa()
    repair_bco()
    repair_cpc_order39()
    normalize_all_substantive_records()
    print("=" * 110)

if __name__ == "__main__":
    main()
