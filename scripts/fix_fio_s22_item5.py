"""
scripts/fix_fio_s22_item5.py

Deletes proposed correction #3 on s.22.
Normalizes U+037E to ';' in text_normalized only.
Keeps 'text' byte-exact with Unicode U+037E.
Prints the updated record, proposed corrections, and hash.
"""

import os
import sys
import json
import hashlib
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIO_PATH = os.path.join(REPO_DIR, "data", "unified_statutes", "FIO_2001.json")

def main():
    print("=" * 100)
    print("ITEM 5: DELETING PROPOSED CORRECTION #3 ON FIO S.22 & NORMALIZING U+037E TO ';'")
    print("=" * 100)

    with open(FIO_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for r in data:
        if r.get("canonical_id") == "FIO_2001_SEC_22":
            # Remove correction #3 (about amount / U+037E)
            old_corrs = r.get("proposed_corrections", [])
            new_corrs = [c for c in old_corrs if "amount" not in c.get("provision_subpart", "").lower() and "amount" not in c.get("printed_in_gazette", "").lower()]
            r["proposed_corrections"] = new_corrs

            # Keep text byte-exact with U+037E
            txt = r["text"]
            r["content_hash"] = hashlib.sha256(txt.encode("utf-8")).hexdigest()

            # Ensure text_normalized converts U+037E to ';'
            norm = txt.replace("\xad", "").replace("\u00ad", "")
            norm = norm.replace("\u037e", ";")
            norm = re.sub(r'_{2,}', '—', norm)
            r["text_normalized"] = norm

            print(f"Content Hash: {r['content_hash']}")
            print(f"Total Proposed Corrections Remaining: {len(new_corrs)}")
            for c in new_corrs:
                print(f"  [{c['provision_subpart']}]")
                print(f"    Printed:  {repr(c['printed_in_gazette'])}")
                print(f"    Proposed: {repr(c['proposed_correction'])}")
                print(f"    Reason:   {c['reason']}")

            # Verify U+037E in text and ';' in text_normalized
            has_u037e_txt = '\u037e' in txt
            has_u037e_norm = '\u037e' in norm
            has_semi_norm = ';' in norm
            print("\nVerification:")
            print(f"  U+037E in text:            {has_u037e_txt}")
            print(f"  U+037E in text_normalized: {has_u037e_norm}")
            print(f"  ';' in text_normalized:       {has_semi_norm}")

    with open(FIO_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("=" * 100)

if __name__ == "__main__":
    main()
