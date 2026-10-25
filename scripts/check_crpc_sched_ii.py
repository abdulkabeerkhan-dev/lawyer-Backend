"""
scripts/check_crpc_sched_ii.py
"""
import json

d = json.load(open("data/unified_statutes/CRPC_1898.json", encoding="utf-8"))
for r in d:
    if "SCHED" in str(r.get("canonical_id")):
        print(r.get("canonical_id"), "Tier:", r.get("tier"))
        print("Text:", repr(r.get("text")))
        # Explicitly ensure title_only because it has no operative text
        r["tier"] = "title_only"

with open("data/unified_statutes/CRPC_1898.json", "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("Saved CRPC with Schedule II as title_only.")
