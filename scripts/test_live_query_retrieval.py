"""
scripts/test_live_query_retrieval.py

Tests the live retrieval pipeline for:
- "eviction notice"
- "willful default"
- "director took a bank loan and did not repay"

Verifies that the entire pipeline operates with USE_ZILLIZ_STATUTES=true.
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('D:/lawyer-Backend/.env')
sys.path.insert(0, 'D:/lawyer-Backend')

from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.statutes.statute_injector import inject_statutory_framework
from legal_ai.retrieval.statute_search import search_statutes_hybrid, get_section

async def test_live_pipeline():
    test_queries = [
        "eviction notice",
        "willful default",
        "director took a bank loan and did not repay"
    ]

    for q in test_queries:
        print(f"\n" + "="*70)
        print(f"PROCESSING LIVE QUERY: '{q}'")
        print("="*70)

        # 1. Query Planning
        plan = create_deterministic_fallback_plan(q)
        print(f"1. Query Plan:")
        print(f"   Domain: {plan.primary_domain}")
        print(f"   Forum: {plan.competent_forum}")
        print(f"   Governing Statutes: {plan.governing_statutes}")
        print(f"   Statutory Provisions: {plan.statutory_provisions}")

        # 2. Ground-Truth Bare Act Verbatim Injection
        framework = inject_statutory_framework(plan, query_text=q)
        injected = framework.get("injected_provisions", [])
        with_text = framework.get("provisions_with_text", [])
        print(f"\n2. Injected Verbatim Bare-Act Framework:")
        print(f"   Total Provisions Injected: {len(injected)}")
        print(f"   Provisions with Verified Text: {with_text}")

        # 3. Live Zilliz statutes_v3 Hybrid Search
        print(f"\n3. Live Hybrid Search on statutes_v3:")
        hits = await search_statutes_hybrid(q, top_k=5)
        for rank, h in enumerate(hits, 1):
            print(f"   [{rank}] {h.get('canonical_id')} | Score: {h.get('score'):.4f}")
            print(f"       Act: {h.get('act_name')} | Section: {h.get('section')}")
            print(f"       Heading: {h.get('heading')}")
            print(f"       Snippet: {(h.get('text') or '')[:140].replace(chr(10), ' ')}...")

if __name__ == "__main__":
    asyncio.run(test_live_pipeline())
