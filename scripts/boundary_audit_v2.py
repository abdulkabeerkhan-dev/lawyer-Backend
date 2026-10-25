"""
scripts/boundary_audit_v2.py

Rigorous Boundary Audit for Substantive Statute Records:
Detects:
  (a) Trailing or leading "N[" fragments (e.g., '1[', '6[')
  (b) Text ending without terminal punctuation (full stop '.', closing bracket ']', ')', ':', or quote)
  (c) Footnote lines embedded in text (starting with digit + Ins./Subs./Omitted/Added/Renumbered/*)
Prints EVERY failure across the entire unified statute corpus.
"""

import os
import sys
import json
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

FOOTNOTE_LINE_RE = re.compile(
    r'^\s*(?:\*+|\d+\s*(?:Ins\.|Ins\b|Subs\.|Subs\b|Omitted\b|Added\b|Renumbered\b|Amended\b|Word\b|Words\b|Clause\b|Sub-section\b|Section\b))',
    re.IGNORECASE
)

LEADING_FRAGMENT_RE = re.compile(r'^\s*\d+\[')
TRAILING_FRAGMENT_RE = re.compile(r'\d+\[\s*$')

def audit_record(cid, text):
    issues = []
    if not text or len(text.strip()) == 0:
        return issues
    
    clean = text.strip()

    # (a) Leading or trailing N[ fragment
    if LEADING_FRAGMENT_RE.search(clean):
        m = LEADING_FRAGMENT_RE.search(clean).group(0)
        issues.append(f"Leading fragment '{m}'")
    if TRAILING_FRAGMENT_RE.search(clean):
        m = TRAILING_FRAGMENT_RE.search(clean).group(0)
        issues.append(f"Trailing fragment '{m}'")

    # (b) Terminal punctuation check
    if not re.search(r'[\.\]\)\:\'\"\*]\s*$', clean):
        last_char = clean[-1] if clean else ""
        issues.append(f"Text ends without full stop or closing bracket (ends with {repr(last_char)})")

    # (c) Embedded footnote lines
    fn_lines = []
    for l_idx, line in enumerate(clean.splitlines(), 1):
        if FOOTNOTE_LINE_RE.search(line):
            fn_lines.append((l_idx, line.strip()[:60]))
    if fn_lines:
        issues.append(f"Embedded footnote lines detected ({len(fn_lines)} lines, e.g. L{fn_lines[0][0]}: {repr(fn_lines[0][1])})")

    return issues

def main():
    print("=" * 110)
    print("ITEM 2: COMPREHENSIVE SUBSTANTIVE STATUTE BOUNDARY AUDIT")
    print("=" * 110)

    total_substantive = 0
    total_failures = 0
    failures_by_file = {}

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

        for r in records:
            if not isinstance(r, dict):
                continue
            tier = r.get("tier", "")
            if tier in ("title_only", "title_only_record"):
                continue
            text = r.get("text") or r.get("statutory_text") or ""
            if not text or len(text.split()) < 5:
                continue

            total_substantive += 1
            cid = r.get("canonical_id", "UNKNOWN")
            issues = audit_record(cid, text)
            if issues:
                total_failures += 1
                if fname not in failures_by_file:
                    failures_by_file[fname] = []
                failures_by_file[fname].append((cid, issues, text))

    print(f"Total substantive records audited: {total_substantive}")
    print(f"Total boundary failures detected:  {total_failures}\n")

    for fname, fails in failures_by_file.items():
        print(f"FILE: {fname} ({len(fails)} failing records):")
        for cid, issues, txt in fails:
            print(f"  [{cid}]")
            for iss in issues:
                print(f"    - FAIL: {iss}")
            # print last 100 chars
            clean_txt = txt.strip().replace("\n", " ")
            print(f"    - Ending context: ...{repr(clean_txt[-120:])}\n")

    print("=" * 110)

if __name__ == "__main__":
    main()
