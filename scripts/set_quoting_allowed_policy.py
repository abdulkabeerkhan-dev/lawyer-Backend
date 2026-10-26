"""
scripts/set_quoting_allowed_policy.py

ORDER 1.11 - ITEM 3: Quoting Allowed Policy
Explicitly sets quoting_allowed boolean flag on all records in data/unified_statutes/*.json.
- If in_force is False or status is repealed/omitted: quoting_allowed = False
- If sourced from official PDF and in force: quoting_allowed = True
"""

import os
import glob
import json

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)

unified_dir = os.path.join(REPO_DIR, "data", "unified_statutes")
statute_files = sorted(glob.glob(os.path.join(unified_dir, "*.json")))

total_provisions = 0
total_qa_true = 0
total_qa_false = 0

for s_path in statute_files:
    fname = os.path.basename(s_path)
    with open(s_path, "r", encoding="utf-8") as f:
        provisions = json.load(f)

    file_qa_true = 0
    file_qa_false = 0

    for p in provisions:
        total_provisions += 1
        status = str(p.get("status", "in_force")).lower()
        tier = str(p.get("tier", "tier_1")).lower()
        has_text = bool((p.get("text") or "").strip())
        
        is_repealed_or_omitted = (
            "repeal" in status or 
            "omit" in status or 
            p.get("in_force") is False or
            tier == "unsourced" or
            not has_text
        )

        if is_repealed_or_omitted:
            p["quoting_allowed"] = False
            file_qa_false += 1
            total_qa_false += 1
        else:
            p["quoting_allowed"] = True
            file_qa_true += 1
            total_qa_true += 1

    with open(s_path, "w", encoding="utf-8") as f:
        json.dump(provisions, f, indent=2, ensure_ascii=False)

    print(f"{fname:25}: Total={len(provisions):4} | Quoting Allowed={file_qa_true:4} | Quoting Blocked={file_qa_false:4}")

print("=" * 60)
print(f"TOTAL: {total_provisions} provisions | Allowed={total_qa_true} | Blocked={total_qa_false}")
