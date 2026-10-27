"""
scripts/count_worktrees_order115.py
Counts records, matched counts, and per-tier counts for 82f317a and 9ebe1a6.
"""

import os
import glob
import json

def count_worktree(wt_path):
    stat_dir = os.path.join(wt_path, "data", "unified_statutes")
    files = sorted(glob.glob(os.path.join(stat_dir, "*.json")))
    results = {}
    for f in files:
        act = os.path.basename(f).replace(".json", "")
        with open(f, "r", encoding="utf-8") as jf:
            d = json.load(jf)
        recs = d if isinstance(d, list) else list(d.values())
        
        tiers = {}
        matched_count = 0
        for r in recs:
            t = r.get("tier", "unknown")
            tiers[t] = tiers.get(t, 0) + 1
            if r.get("text_layer_matched") is True or r.get("page_verified") is True:
                matched_count += 1
                
        results[act] = {
            "total": len(recs),
            "matched": matched_count,
            "tiers": tiers
        }
    return results

r_old = count_worktree("../wt_82f317a")
r_new = count_worktree("../wt_9ebe1a6")

all_acts = sorted(list(set(list(r_old.keys()) + list(r_new.keys()))))

print("=== SIDE-BY-SIDE RECORD COUNTS ===")
header = f"{'Act':<20} | {'82f317a Total':<13} | {'9ebe1a6 Total':<13} | {'Diff':<6} | {'82f317a Match':<13} | {'9ebe1a6 Match':<13} | {'Diff Match':<10}"
print(header)
print("-" * len(header))
for act in all_acts:
    o_tot = r_old.get(act, {}).get("total", 0)
    n_tot = r_new.get(act, {}).get("total", 0)
    diff_tot = n_tot - o_tot
    o_mat = r_old.get(act, {}).get("matched", 0)
    n_mat = r_new.get(act, {}).get("matched", 0)
    diff_mat = n_mat - o_mat
    print(f"{act:<20} | {o_tot:<13} | {n_tot:<13} | {diff_tot:<6} | {o_mat:<13} | {n_mat:<13} | {diff_mat:<10}")

print("\n=== PER-TIER COUNTS: 82f317a ===")
for act in all_acts:
    print(f"{act:<20}: {r_old.get(act, {}).get('tiers', {})}")

print("\n=== PER-TIER COUNTS: 9ebe1a6 ===")
for act in all_acts:
    print(f"{act:<20}: {r_new.get(act, {}).get('tiers', {})}")
