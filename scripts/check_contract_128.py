import json

with open("data/unified_statutes/CONTRACT_1872.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for r in data:
    if "128" in str(r.get("primary_num", "")) or "128" in str(r.get("canonical_id", "")):
        print("Found:", r)
