"""
scripts/check_art182.py
"""
import json

d = json.load(open("data/unified_statutes/LIMITATION_1908.json", encoding="utf-8"))
for r in d:
    if "182" in str(r.get("canonical_id")):
        print(r.get("canonical_id"), "Tier:", r.get("tier"))
        print("Text:", repr(r.get("text")))
        # Explicitly ensure title_only
        r["tier"] = "title_only"

with open("data/unified_statutes/LIMITATION_1908.json", "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("Saved Limitation Act with Art 182 as title_only.")
