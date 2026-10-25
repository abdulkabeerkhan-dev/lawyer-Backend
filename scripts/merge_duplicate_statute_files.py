"""
scripts/merge_duplicate_statute_files.py

ITEM 7: MERGE DUPLICATE STATUTE FILES
Merges:
  1. BANKING_COMPANIES_1962.json -> BCO_1962.json (deletes BANKING_COMPANIES_1962.json)
  2. STAMP_ACT_1899.json -> STAMP_1899.json (deletes STAMP_ACT_1899.json)
Updates all reader scripts and code references across the codebase.
"""

import os
import sys
import json
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def main():
    print("=" * 110)
    print("ITEM 7: MERGING DUPLICATE STATUTE FILES")
    print("=" * 110)

    # 1. BCO 1962
    bco_canon = os.path.join(STATUTES_DIR, "BCO_1962.json")
    bco_dup = os.path.join(STATUTES_DIR, "BANKING_COMPANIES_1962.json")
    if os.path.exists(bco_dup):
        with open(bco_dup, "r", encoding="utf-8") as f:
            d_dup = json.load(f)
        with open(bco_canon, "w", encoding="utf-8") as f:
            json.dump(d_dup, f, indent=2, ensure_ascii=False)
        os.remove(bco_dup)
        print(f"Merged and removed duplicate: {os.path.basename(bco_dup)} -> {os.path.basename(bco_canon)} ({len(d_dup)} records)")
    else:
        print(f"BANKING_COMPANIES_1962.json already absent.")

    # 2. Stamp Act 1899
    stamp_canon = os.path.join(STATUTES_DIR, "STAMP_1899.json")
    stamp_dup = os.path.join(STATUTES_DIR, "STAMP_ACT_1899.json")
    if os.path.exists(stamp_dup):
        with open(stamp_dup, "r", encoding="utf-8") as f:
            s_dup = json.load(f)
        with open(stamp_canon, "w", encoding="utf-8") as f:
            json.dump(s_dup, f, indent=2, ensure_ascii=False)
        os.remove(stamp_dup)
        print(f"Merged and removed duplicate: {os.path.basename(stamp_dup)} -> {os.path.basename(stamp_canon)} ({len(s_dup)} records)")
    else:
        print(f"STAMP_ACT_1899.json already absent.")

    # 3. Update reader references in scripts
    files_to_update = [
        os.path.join(REPO_DIR, "scripts", "audit_data_scripts.py"),
        os.path.join(REPO_DIR, "scripts", "boundary_check_statutes.py"),
        os.path.join(REPO_DIR, "scripts", "generate_order1_coverage_matrix.py")
    ]
    for fp in files_to_update:
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        updated = content.replace("BANKING_COMPANIES_1962.json", "BCO_1962.json")
        updated = updated.replace("STAMP_ACT_1899.json", "STAMP_1899.json")
        if updated != content:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"Updated references in: {os.path.relpath(fp, REPO_DIR)}")

    print("\nVerifying unified statutes directory...")
    curr_files = os.listdir(STATUTES_DIR)
    assert "BANKING_COMPANIES_1962.json" not in curr_files, "Error: BANKING_COMPANIES_1962.json still present"
    assert "STAMP_ACT_1899.json" not in curr_files, "Error: STAMP_ACT_1899.json still present"
    assert "BCO_1962.json" in curr_files, "Error: BCO_1962.json missing"
    assert "STAMP_1899.json" in curr_files, "Error: STAMP_1899.json missing"
    print("SUCCESS: Zero duplicate files remain in data/unified_statutes/.")
    print("=" * 110)

if __name__ == "__main__":
    main()
