import os
import json

UNIFIED_DIR = "data/unified_statutes"

print("=== CHECKING TIER / WORD COUNT MISMATCHES ACROSS ALL STATUTES ===")
mismatches = []

for fname in sorted(os.listdir(UNIFIED_DIR)):
    if not fname.endswith(".json"): continue
    fpath = os.path.join(UNIFIED_DIR, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        for k in ["sections", "provisions", "records"]:
            if k in data and isinstance(data[k], list):
                data = data[k]
                break
    if not isinstance(data, list):
        continue

    for r in data:
        cid = r.get("canonical_id", r.get("citation", r.get("section", "")))
        tier = r.get("tier", "")
        txt = r.get("text", "") or ""
        words = len(txt.split())
        
        # Check condition 1: tier says substantive/ingested_unreviewed/page_verified but words < 25
        if tier not in ["title_only", "disputed"] and words < 25:
            mismatches.append((fname, cid, tier, words, "non-title_only but words < 25", txt[:50]))
        # Check condition 2: tier says title_only but words >= 25
        if tier == "title_only" and words >= 25:
            mismatches.append((fname, cid, tier, words, "title_only but words >= 25", txt[:50]))

print(f"Total potential mismatches: {len(mismatches)}")
for m in mismatches[:40]:
    print(f"- {m[0]} | {m[1]} | Tier: {m[2]} | Words: {m[3]} | Issue: {m[4]} | Text: {m[5]!r}")
