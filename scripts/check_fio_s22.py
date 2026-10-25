import json

with open("data/unified_statutes/FIO_2001.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for r in data:
    if r.get("canonical_id") == "FIO_2001_SEC_22":
        print(f"ID: {r.get('canonical_id')}")
        print(f"Tier: {r.get('tier')}")
        print(f"Status: {r.get('status')}")
        print(f"Verification status: {r.get('verification_status')}")
        print(f"Source page: {r.get('source_page')}")
        print(f"Missing reason: {r.get('missing_reason')}")
        print(f"Text length: {len(r.get('text', ''))}")
