"""
scripts/update_disputed_warning_text.py

ITEM 8: REPLACE DISPUTED WARNING
Replaces:
  'divergent gazette layers and unverified amendments'
With:
  'Text not yet checked against page images by a human.'
Across all scripts, statute files, and evaluation harnesses.
"""

import os
import sys
import json
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGET_FILES = [
    os.path.join(REPO_DIR, "scripts", "offline_model_eval.py"),
    os.path.join(REPO_DIR, "scripts", "print_order1_1_memos.py"),
    os.path.join(REPO_DIR, "data", "unified_statutes", "FIO_2001.json"),
    os.path.join(REPO_DIR, "legal_ai", "statutes", "statute_injector.py"),
    os.path.join(REPO_DIR, "data", "offline_model_eval_results.json")
]

def main():
    print("=" * 110)
    print("ITEM 8: UPDATING DISPUTED REASON ACROSS CODEBASE")
    print("=" * 110)

    for fp in TARGET_FILES:
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()

        updated = content
        updated = re.sub(
            r'due to divergent gazette layers and unverified amendments',
            'Text not yet checked against page images by a human.',
            updated
        )
        updated = re.sub(
            r'divergent gazette layers and unverified amendments',
            'Text not yet checked against page images by a human.',
            updated
        )
        updated = re.sub(
            r'conflicting official gazette layers and unverified amendments',
            'Text not yet checked against page images by a human.',
            updated
        )

        if updated != content:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"Updated disputed reason in: {os.path.relpath(fp, REPO_DIR)}")
        else:
            print(f"No stale phrasing found in: {os.path.relpath(fp, REPO_DIR)}")

    print("\nVerifying zero residual occurrences of 'divergent gazette'...")
    # Grep check
    cmd = ["git", "grep", "-n", "divergent gazette"]
    import subprocess
    res = subprocess.run(cmd, cwd=REPO_DIR, stdout=subprocess.PIPE, text=True)
    if res.stdout.strip():
        print("Residual matches found:")
        print(res.stdout)
    else:
        print("CONFIRMED: Zero residual occurrences of 'divergent gazette layers' across repository.")
    print("=" * 110)

if __name__ == "__main__":
    main()
