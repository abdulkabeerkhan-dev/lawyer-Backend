"""
scripts/inspect_tier_sample.py
"""
import os
import json

d = json.load(open("data/unified_statutes/CNSA_1997.json", encoding="utf-8"))
print("Record 0:", d[0])
print("Record 1:", d[1])

crpc = json.load(open("data/unified_statutes/CRPC_1898.json", encoding="utf-8"))
for r in crpc:
    if r.get("canonical_id") in ["CRPC_1898_SEC_249A", "CRPC_1898_SEC_265K", "CRPC_1898_SEC_498A", "CRPC_1898_SCHED_II"]:
        print("\n", r.get("canonical_id"), "Tier:", r.get("tier"), "Text:", repr(r.get("text")))
