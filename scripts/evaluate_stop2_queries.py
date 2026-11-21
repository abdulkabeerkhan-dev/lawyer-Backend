"""
scripts/evaluate_stop2_queries.py

Executes hybrid search (dense Voyage-4-large + sparse BM25 with RRF) against Zilliz statutes_v3
with USE_ZILLIZ_STATUTES=True for:
1. 'willful default'
2. 'wilful default'
3. 'director took a bank loan and did not repay'

Prints Top 10 results with scores, canonical IDs, headings, and text snippets.
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('D:/lawyer-Backend/.env')
sys.path.insert(0, 'D:/lawyer-Backend')

# Set flag ON
os.environ["USE_ZILLIZ_STATUTES"] = "true"

from legal_ai.retrieval.statute_search import search_statutes_hybrid, get_section
from legal_ai.retrieval.query_planner import plan_statute_query

TARGET_QUERIES = [
    "willful default",
    "wilful default",
    "director took a bank loan and did not repay"
]

async def run_stop2():
    results = {}
    for q in TARGET_QUERIES:
        print(f"\n========================================================")
        print(f"QUERY: '{q}'")
        print(f"========================================================")

        # Plan the query
        plan = await plan_statute_query(q)
        print(f"Plan: area={plan.get('area_of_law')}, forum={plan.get('forum')}, likely_acts={plan.get('likely_acts')}, defined_terms={plan.get('defined_terms')}, explicit_refs={plan.get('explicit_refs')}")

        # Search statutes hybrid
        hits = await search_statutes_hybrid(
            query=q,
            top_k=10,
            include_historical=False,
            in_force_only=True
        )

        results[q] = []
        for rank, h in enumerate(hits, 1):
            cid = h.get("canonical_id", "")
            act = h.get("act_name", "")
            sec = h.get("section", "")
            heading = h.get("heading", "")
            score = h.get("score", 0.0)
            text_snippet = (h.get("text") or "")[:200].replace("\n", " ")
            
            entry = {
                "rank": rank,
                "canonical_id": cid,
                "act_code": h.get("act_code", ""),
                "act_name": act,
                "section": sec,
                "heading": heading,
                "score": round(score, 6),
                "snippet": text_snippet
            }
            results[q].append(entry)
            print(f"\n[{rank}] Score: {score:.4f} | {cid}")
            print(f"    Act: {act} | Section: {sec}")
            print(f"    Heading: {heading}")
            print(f"    Snippet: {text_snippet}...")

    # Save to report
    out_path = Path("D:/lawyer-Backend/reports/stop2_retrieval_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved STOP 2 report to {out_path}")

if __name__ == "__main__":
    asyncio.run(run_stop2())
