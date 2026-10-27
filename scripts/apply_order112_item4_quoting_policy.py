"""
scripts/apply_order112_item4_quoting_policy.py

ORDER 1.12 - ITEM 4: Quoting Allowed Policy Refinement
Decouples into two explicit boolean fields:
- in_force: bool
- page_verified: bool

Enforces strict policy:
quoting_allowed = True requires page_verified AND in_force AND not disputed.
If a record is disputed, quoting_allowed is strictly False.
If a record is title_only or unverified, quoting_allowed is strictly False.

Prints counts per act and documents policy for disputed and unverified text.
"""

import os
import sys
import glob
import json

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)

UNIFIED_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
statute_files = sorted(glob.glob(os.path.join(UNIFIED_DIR, "*.json")))

# FIO authentic section page map from fio_2001.pdf
FIO_PAGE_MAP = {
    "1": "3", "2": "3-5", "3": "5", "4": "6", "5": "6", "6": "6",
    "7": "7-8", "8": "8", "9": "8", "10": "8-10", "11": "10",
    "12": "11", "13": "11", "14": "11", "15": "11-17", "16": "18",
    "17": "19", "18": "19", "19": "20-21", "20": "21", "21": "23",
    "22": "23-24", "23": "24", "24": "24", "25": "24", "26": "25",
    "27": "25", "28": "25", "29": "25"
}

summary_counts = {}

for s_path in statute_files:
    fname = os.path.basename(s_path)
    act_code = fname.replace(".json", "")
    with open(s_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    is_dict = isinstance(data, dict)
    provisions = list(data.values()) if is_dict else data

    tot = len(provisions)
    cnt_in_force = 0
    cnt_page_verified = 0
    cnt_disputed = 0
    cnt_qa_true = 0
    cnt_qa_false = 0

    for p in provisions:
        # 1. Backfill FIO source pages if missing
        p_num = str(p.get("primary_num", ""))
        if act_code == "FIO_2001" and p_num in FIO_PAGE_MAP:
            p["source_page"] = FIO_PAGE_MAP[p_num]

        # 2. Evaluate in_force
        status_val = p.get("status", "in_force")
        if isinstance(status_val, dict):
            status_val = status_val.get("federal", "in_force")
        status_str = str(status_val).lower()
        
        is_in_force = not any(w in status_str for w in ["repeal", "omit", "delete", "spent", "expired"])
        if p.get("in_force") is False or status_str == "unknown":
            is_in_force = False
        p["in_force"] = is_in_force
        if is_in_force:
            cnt_in_force += 1

        # 3. Evaluate page_verified
        tier_val = str(p.get("tier", "")).lower()
        txt = (p.get("text") or p.get("statutory_text") or "").strip()
        title = (p.get("title") or "").strip()
        sp = p.get("source_page")
        has_valid_page = sp not in [None, "", "unspecified", "None"]
        has_operative_text = (
            tier_val != "title_only" and
            len(txt) > 25 and
            txt != title and
            "[heading only]" not in txt.lower() and
            p.get("verification_status") != "stub"
        )

        is_page_verified = bool(has_operative_text and has_valid_page and act_code != "CRPC_SCHEDULE_II")
        p["page_verified"] = is_page_verified
        if is_page_verified:
            cnt_page_verified += 1

        # 4. Evaluate disputed
        is_disputed = (tier_val == "disputed")
        if is_disputed:
            cnt_disputed += 1

        # 5. Enforce strict quoting_allowed policy:
        # quoting_allowed = True requires page_verified AND in_force AND not disputed
        qa = bool(is_page_verified and is_in_force and not is_disputed)
        p["quoting_allowed"] = qa
        if qa:
            cnt_qa_true += 1
        else:
            cnt_qa_false += 1

    with open(s_path, "w", encoding="utf-8") as f:
        if is_dict:
            json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            json.dump(provisions, f, indent=2, ensure_ascii=False)

    summary_counts[fname] = {
        "total": tot,
        "in_force": cnt_in_force,
        "page_verified": cnt_page_verified,
        "disputed": cnt_disputed,
        "quoting_allowed_true": cnt_qa_true,
        "quoting_allowed_false": cnt_qa_false
    }

print("=" * 105)
print(f"{'Act File':<26} | {'Total':<6} | {'In-Force':<9} | {'Page-Ver':<9} | {'Disputed':<9} | {'QA Allowed':<11} | {'QA Blocked':<11}")
print("-" * 105)
for fname, c in summary_counts.items():
    print(f"{fname:<26} | {c['total']:<6} | {c['in_force']:<9} | {c['page_verified']:<9} | {c['disputed']:<9} | {c['quoting_allowed_true']:<11} | {c['quoting_allowed_false']:<11}")
print("=" * 105)
