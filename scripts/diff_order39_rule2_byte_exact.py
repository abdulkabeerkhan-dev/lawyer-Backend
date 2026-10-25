"""
scripts/diff_order39_rule2_byte_exact.py

Diffs the Order 1.1 stored text of CPC Order XXXIX Rule 2 against the newly
re-extracted byte-exact text from official CPC PDF pages 162-163.
Highlights the restoration of '1[* * *] prison' (omission of 'civil').
"""

import os
import sys
import json
import subprocess
import difflib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPC_JSON = os.path.join(REPO_DIR, "data", "unified_statutes", "CPC_1908.json")

def main():
    print("=" * 100)
    print("ITEM 4: CPC ORDER XXXIX RULE 2 BYTE-EXACT RE-EXTRACTION & DIFF")
    print("=" * 100)

    # 1. Fetch text from commit a06db61 (Order 1.1)
    cmd = ["git", "show", "a06db61:data/unified_statutes/CPC_1908.json"]
    raw_old = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8").stdout
    old_data = json.loads(raw_old)
    old_r2 = [r for r in old_data if r.get("canonical_id") == "CPC_1908_ORD_XXXIX_R_2"][0]["text"]

    # 2. Fetch current newly re-extracted text
    with open(CPC_JSON, "r", encoding="utf-8") as f:
        curr_data = json.load(f)
    curr_rec = [r for r in curr_data if r.get("canonical_id") == "CPC_1908_ORD_XXXIX_R_2"][0]
    curr_r2 = curr_rec["text"]
    curr_fns = curr_rec.get("footnotes", [])

    print(f"Old Rule 2 Length: {len(old_r2)} chars")
    print(f"New Rule 2 Length: {len(curr_r2)} chars")
    print(f"Footnotes Extracted: {curr_fns}")
    print("\nUNIFIED DIFF (Commit a06db61 -> Byte-Exact Raw PDF):")
    print("-" * 100)

    diff = list(difflib.unified_diff(
        old_r2.splitlines(keepends=True),
        curr_r2.splitlines(keepends=True),
        fromfile="commit_a06db61:CPC_ORD_XXXIX_R_2",
        tofile="byte_exact_raw_pdf:CPC_ORD_XXXIX_R_2",
        n=3
    ))
    sys.stdout.write("".join(diff))
    print("-" * 100)
    print("=" * 100)

if __name__ == "__main__":
    main()
