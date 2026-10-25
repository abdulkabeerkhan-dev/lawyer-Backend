"""
scripts/scan_statute_artifacts.py

Scans all statute records in data/unified_statutes/ for raw PDF/print artifacts:
  - '(Index'
  - 'Page N of'
  - '[Page'
  - 'http'
  - Running headers/footers
Prints every matching record with line numbers and matched string.
"""

import os
import sys
import json
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

PATTERNS = [
    (r'\(Index\s*\d*\)?', "(Index"),
    (r'Page\s+\d+\s+of\s+\d+', "Page N of M"),
    (r'\[Page\s*\d+\]', "[Page N]"),
    (r'https?://[^\s]+', "http(s) URL"),
    (r'THE\s+[A-Z\s]{4,}(?:ACT|ORDINANCE|CODE)', "All-caps Running Header"),
    (r'PAKISTAN\s+CODE', "PAKISTAN CODE Header")
]

def scan_statutes():
    print("=" * 110)
    print("ITEM 4: ARTIFACT SCAN ACROSS ALL UNIFIED STATUTE FILES")
    print("=" * 110)

    total_matches = 0
    matches_by_file = {}

    for fname in sorted(os.listdir(STATUTES_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(STATUTES_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"Error reading {fname}: {e}")
                continue

        records = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        file_matches = []

        for r in records:
            if not isinstance(r, dict):
                continue
            cid = r.get("canonical_id", "UNKNOWN")
            text = r.get("text") or r.get("statutory_text") or ""
            
            for pat, pat_name in PATTERNS:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    start = max(0, m.start() - 30)
                    end = min(len(text), m.end() + 30)
                    snippet = text[start:end].replace("\n", " ")
                    file_matches.append({
                        "canonical_id": cid,
                        "pattern": pat_name,
                        "match": m.group(0),
                        "snippet": snippet
                    })
                    total_matches += 1

        if file_matches:
            matches_by_file[fname] = file_matches

    print(f"Total matching artifacts found across all JSON files: {total_matches}\n")
    for fname, fmatches in matches_by_file.items():
        print(f"File: {fname} ({len(fmatches)} matches):")
        for m in fmatches:
            print(f"  [{m['canonical_id']}] Pattern: {m['pattern']} -> Match: '{m['match']}'")
            print(f"    Context: ...{m['snippet']}...\n")

    print("=" * 110)

if __name__ == "__main__":
    scan_statutes()
