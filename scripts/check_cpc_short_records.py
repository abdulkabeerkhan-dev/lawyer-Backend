import json
import os

with open("data/unified_statutes/CPC_1908.json", "r", encoding="utf-8") as f:
    cpc = json.load(f)

print("=== CHECKING ORDER XXI RECORDS IN CPC_1908.json ===")
oxxi_recs = [r for r in cpc if "ORD_XXI" in str(r.get("canonical_id", "")) or "Order XXI" in str(r.get("title", "")) or "Order XXI" in str(r.get("heading", ""))]
print(f"Total Order XXI records: {len(oxxi_recs)}")
for r in oxxi_recs:
    cid = r.get("canonical_id")
    tier = r.get("tier")
    txt = r.get("text", "")
    words = len(txt.split())
    print(f"- {cid} | Tier: {tier} | Words: {words} | Text preview: {txt[:60]!r}")

print("\n=== CHECKING ALL CPC RECORDS WITH < 25 WORDS ===")
short_recs = [r for r in cpc if len(r.get("text", "").split()) < 25]
print(f"Total CPC records with < 25 words: {len(short_recs)}")
for r in short_recs[:15]:
    print(f"- {r.get('canonical_id')} | Tier: {r.get('tier')} | Words: {len(r.get('text', '').split())} | Text: {r.get('text', '')!r}")
