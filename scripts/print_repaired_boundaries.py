"""
scripts/print_repaired_boundaries.py

Prints first and last 200 characters of repaired provisions:
TPA s.58, s.67, s.69 and BCO s.27, s.83, s.83A.
Also prints extracted footnotes and word counts.
"""

import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

TARGETS = [
    ("TPA_1882.json", "TPA_1882_SEC_58"),
    ("TPA_1882.json", "TPA_1882_SEC_67"),
    ("TPA_1882.json", "TPA_1882_SEC_69"),
    ("BCO_1962.json", "BCO_1962_SEC_27"),
    ("BCO_1962.json", "BCO_1962_SEC_83"),
    ("BCO_1962.json", "BCO_1962_SEC_83A"),
]

def main():
    print("=" * 110)
    print("REPAIRED STATUTORY PROVISIONS BOUNDARY VERIFICATION (TPA 58/67/69 & BCO 27/83/83A)")
    print("=" * 110)

    for fname, cid in TARGETS:
        p = os.path.join(STATUTES_DIR, fname)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        rec = [r for r in data if r.get("canonical_id") == cid][0]
        txt = rec.get("text", "")
        norm = rec.get("text_normalized", "")
        fns = rec.get("footnotes", [])
        words = len(txt.split())

        print(f"\nPROVISION: [{cid}] (from {fname})")
        print(f"Word Count: {words} words | Characters: {len(txt)} | Footnotes separated: {len(fns)}")
        print("-" * 110)
        print("First 200 Characters of Operative Text:")
        print(repr(txt[:200]))
        print("\nLast 200 Characters of Operative Text:")
        print(repr(txt[-200:]))
        if fns:
            print("\nSeparated Footnotes Field:")
            for fn in fns[:4]:
                print(f"  * {fn}")
        print()

    print("=" * 110)

if __name__ == "__main__":
    main()
