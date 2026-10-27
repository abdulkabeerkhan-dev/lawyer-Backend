"""
scripts/fix_crpc_source_pages.py
Updates CRPC_1898.json with exact source_page for Section 497 (p. 167) and Section 498 (p. 168).
"""
import json

with open("data/unified_statutes/CRPC_1898.json", "r", encoding="utf-8") as f:
    crpc = json.load(f)

for p in crpc:
    cid = p.get("canonical_id", "")
    if cid == "CRPC_1898_SEC_497":
        p["source_page"] = 167
        p["page_verified"] = True
        p["in_force"] = True
        p["quoting_allowed"] = True
        p["tier"] = "page_verified"
        print("Updated CRPC 497 source_page to 167")
    elif cid == "CRPC_1898_SEC_498":
        p["source_page"] = 168
        p["page_verified"] = True
        p["in_force"] = True
        p["quoting_allowed"] = True
        p["tier"] = "page_verified"
        print("Updated CRPC 498 source_page to 168")

with open("data/unified_statutes/CRPC_1898.json", "w", encoding="utf-8") as f:
    json.dump(crpc, f, indent=2, ensure_ascii=False)
