import os
import sys
from dotenv import load_dotenv

load_dotenv('D:/lawyer-Backend/.env')
sys.path.insert(0, 'D:/lawyer-Backend')

from legal_ai.retrieval.statute_search import resolve_statute_id, get_section, search_statutes_hybrid

print("Testing resolve_statute_id:")
for s in ["CPC_1908_O_VII_R_11", "CPC_O_7_R_11", "CPC_ORDER_7_RULE_11", "Order VII Rule 11"]:
    print(f"  {s} -> {resolve_statute_id(s)}")

print("\nTesting get_section:")
for act, sec in [
    ("PPC", "302"),
    ("CrPC", "497"),
    ("FIO", "2(g)"),
    ("NAO", "5(u)"),
    ("Constitution", "199"),
    ("CPC", "11"),
    ("CPC", "Order VII Rule 11"),
    ("CPC", "O_VII_R_11"),
]:
    res = get_section(act, sec)
    cid = res.get("canonical_id") if res else None
    print(f"  {act} {sec} -> {cid}")
