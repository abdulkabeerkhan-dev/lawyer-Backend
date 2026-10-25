"""
scripts/fix_widened_footnotes.py

ORDER 1.4 - ITEM 3:
Fix BCO s.83 ("1Renumberd" footnote in the body).
Widens the footnote detector (a digit followed by any capitalized word) to catch:
  - Typos like "1Renumberd"
  - Annotations like "5New sub-section (1B)", "6New sub-section(1C)", "1Rep.", "2The word", "1Explanation", etc.
Extracts them into the record's 'footnotes' array.
Removes them from 'text' and 'text_normalized'.
Re-runs and prints EVERY hit across all files.
"""

import os
import sys
import json
import re
import hashlib
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

# Widened footnote regex:
# Matches an asterisk OR a digit followed by optional whitespace and any capitalized word/abbreviation
WIDENED_FOOTNOTE_RE = re.compile(
    r'^\s*(?:\*+|\d+\s*(?:[A-Z][a-zA-Z\.\(\)\,\s\d\-]+))'
)

def is_footnote_line(line):
    l = line.strip()
    if not l:
        return False
    # If it is a normal section/rule heading like '83. Penalties.', '2B. Expiration...', '498A. No bail...', it's NOT a footnote
    if re.match(r'^\s*\d+[A-Za-z\-]*\.\s+[A-Z]', l):
        return False
    # If it is a normal subsection like '(1) Whoever' or '1[(1) Whoever', it's NOT a footnote
    if re.match(r'^\s*(?:\d+\[)?\([0-9a-zA-Z]+\)', l):
        return False

    # Check widened footnote regex
    if WIDENED_FOOTNOTE_RE.match(l):
        fn_keywords = [
            "subs", "ins", "omitted", "added", "renumber", "amend", "rep",
            "the word", "the words", "explanation", "for the purposes of",
            "for modifications", "act", "ordinance", "order", "sch", "w.e.f",
            "g. g. in c", "l. g.", "govt", "a. o.", "a.o."
        ]
        l_low = l.lower()
        if any(k in l_low for k in fn_keywords) or l.startswith("*"):
            return True
    return False

def main():
    print("=" * 110)
    print("ITEM 3: WIDENED FOOTNOTE EXTRACTION ACROSS ENTIRE CORPUS (INCLUDING BCO s.83 '1Renumberd')")
    print("=" * 110)
    print("Widened Pattern: r'^\\s*(?:\\*+|\\d+\\s*(?:[A-Z][a-zA-Z\\.\\(\\)\\,\\s\\d\\-]+))'")
    print("Includes non-standard spellings ('1Renumberd'), annotations ('5New sub-section'), etc.\n")

    total_cleaned_records = 0
    total_extracted_lines = 0

    # Load baseline from commit 8b0b7d7 to demonstrate every hit detected and repaired
    for fname in sorted(os.listdir(STATUTES_DIR)):
        if not fname.endswith(".json"):
            continue

        cmd = ["git", "show", f"8b0b7d7:data/unified_statutes/{fname}"]
        try:
            raw = subprocess.check_output(cmd, cwd=REPO_DIR, text=True, encoding="utf-8")
            base_data = json.loads(raw)
        except Exception:
            fpath = os.path.join(STATUTES_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                base_data = json.load(f)

        records = base_data if isinstance(base_data, list) else list(base_data.values()) if isinstance(base_data, dict) else []
        file_hits = []

        for r in records:
            if not isinstance(r, dict):
                continue
            txt = r.get("text", "")
            if not txt:
                continue

            lines = txt.splitlines()
            body_lines = []
            extracted_fns = []

            for l in lines:
                if is_footnote_line(l):
                    extracted_fns.append(l.strip())
                else:
                    body_lines.append(l)

            if extracted_fns:
                total_cleaned_records += 1
                total_extracted_lines += len(extracted_fns)
                file_hits.append((r.get("canonical_id", "UNKNOWN"), extracted_fns))

                # Also update current working tree file
                cleaned_text = "\n".join(body_lines).strip()
                cleaned_text = re.sub(r'\s*\d+\[\s*$', '', cleaned_text).strip()

                norm = cleaned_text.replace("\xad", "").replace("\u00ad", "")
                norm = norm.replace("\u037e", ";")
                norm = re.sub(r'_{2,}', '\u2014', norm)
                norm_lines = [" ".join(line.split()) for line in norm.splitlines() if line.strip()]
                text_normalized = "\n".join(norm_lines)

                # Update in memory
                cur_path = os.path.join(STATUTES_DIR, fname)
                with open(cur_path, "r", encoding="utf-8") as cur_f:
                    cur_data = json.load(cur_f)
                cur_records = cur_data if isinstance(cur_data, list) else list(cur_data.values()) if isinstance(cur_data, dict) else []
                for cr in cur_records:
                    if cr.get("canonical_id") == r.get("canonical_id"):
                        cr["text"] = cleaned_text
                        cr["text_normalized"] = text_normalized
                        existing_fns = cr.get("footnotes", [])
                        for ef in extracted_fns:
                            if ef not in existing_fns:
                                existing_fns.append(ef)
                        cr["footnotes"] = existing_fns
                        cr["content_hash"] = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
                with open(cur_path, "w", encoding="utf-8") as cur_f:
                    json.dump(cur_data, cur_f, indent=2, ensure_ascii=False)

        if file_hits:
            print(f"FILE: {fname} ({len(file_hits)} records containing newly detected footnotes):")
            for cid, fns in file_hits:
                print(f"  [{cid}] - {len(fns)} footnote line(s) extracted:")
                for fn in fns:
                    print(f"    * {repr(fn)}")
            print()

    print("-" * 110)
    print(f"SUMMARY: Extracted {total_extracted_lines} footnote lines across {total_cleaned_records} records.")
    print("=" * 110)

if __name__ == "__main__":
    main()
