import json

with open("data/unified_statutes/CPC_1908.json", "r", encoding="utf-8") as f:
    cpc = json.load(f)

o39_rules = [r for r in cpc if "ORD_XXXIX" in str(r.get("canonical_id", ""))]
print(f"Total Order XXXIX rules in CPC_1908.json: {len(o39_rules)}")
for r in o39_rules:
    print(f"- {r.get('canonical_id')} | Tier: {r.get('tier')} | Words: {len(r.get('text', '').split())}")
    print(f"  Title: {r.get('title')}")
    print(f"  Text preview: {r.get('text')[:120]!r}\n")
