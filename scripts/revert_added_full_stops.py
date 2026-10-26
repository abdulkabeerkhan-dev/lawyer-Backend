"""
scripts/revert_added_full_stops.py

ORDER 1.5 - ITEM 2:
1. Reverts the artificially added full stop on NI Act Section 15:
   Restores ending: 'called the “indorser.”' (ends with closing curly quote U+201D, not .).
2. Reverts the artificially added full stop on Limitation Article 182:
   Restores ending: 'Time from which period begins to run: Omitted' (ends with 'Omitted', not .).
3. Hardens boundary detector (boundary_audit_v2.py) to accept closing quotes (", ”, ’, ')
   and 'Omitted' as valid terminal boundaries.
"""

import os
import sys
import json
import re
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def revert_ni_s15():
    fpath = os.path.join(STATUTES_DIR, "NI_ACT_1881.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    for r in data:
        if r.get("canonical_id") == "NI_ACT_1881_SEC_15":
            txt = r.get("text", "")
            # If it ends with . after quote, strip it
            if txt.endswith('.”.') or txt.endswith('.".') or txt.endswith('.” .'):
                txt = txt[:-1].strip()
                r["text"] = txt
                norm = r.get("text_normalized", "")
                if norm.endswith('.”.') or norm.endswith('.".'):
                    r["text_normalized"] = norm[:-1].strip()
                r["content_hash"] = hashlib.sha256(txt.encode("utf-8")).hexdigest()
                changed = True
                print("Reverted NI s.15 added period. Ending is now:")
                print(" ", repr(txt[-60:]))

    if changed:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def revert_limitation_art182():
    fpath = os.path.join(STATUTES_DIR, "LIMITATION_1908.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    for r in data:
        if r.get("canonical_id") == "LIMITATION_1908_ART_182":
            txt = r.get("text", "")
            if txt.endswith("Omitted."):
                txt = txt[:-1]
                r["text"] = txt
                norm = r.get("text_normalized", "")
                if norm.endswith("Omitted."):
                    r["text_normalized"] = norm[:-1]
                r["content_hash"] = hashlib.sha256(txt.encode("utf-8")).hexdigest()
                changed = True
                print("Reverted Limitation Art 182 added period. Ending is now:")
                print(" ", repr(txt[-60:]))

    if changed:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def update_detector():
    det_path = os.path.join(REPO_DIR, "scripts", "boundary_audit_v2.py")
    with open(det_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Old regex: r'[\.\]\)\:\'\"\*]\s*$'
    # New regex: r'(?:[\.\]\)\:\'\"”’\*]|Omitted)\s*$'
    old_target = r"if not re.search(r'[\.\]\)\:\'\"\*]\s*$', clean):"
    new_replacement = r"if not re.search(r'(?:[\.\]\)\:\'\"”’\*]|Omitted)\s*$', clean):"

    if old_target in content:
        content = content.replace(old_target, new_replacement)
        with open(det_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Updated scripts/boundary_audit_v2.py to accept closing quotes and 'Omitted' as terminal.")

def main():
    print("=" * 110)
    print("ITEM 2: REVERTING ARTIFICIAL TERMINAL PERIODS & HARDENING DETECTOR")
    print("=" * 110)
    revert_ni_s15()
    revert_limitation_art182()
    update_detector()
    print("=" * 110)

if __name__ == "__main__":
    main()
