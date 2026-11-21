import asyncio
import sys
sys.path.insert(0, 'D:/lawyer-Backend')
from dotenv import load_dotenv
load_dotenv('D:/lawyer-Backend/.env')

from legal_ai.retrieval.unified_orchestrator import retrieve_candidates_parallel
from core.legal_query_planner import create_deterministic_fallback_plan

async def main():
    q = "eviction notice"
    print(f"Testing retrieve_candidates_parallel for '{q}'...")
    plan = create_deterministic_fallback_plan(q)
    candidates, counts = await retrieve_candidates_parallel(q, query_plan=plan, top_k_per_engine=5)
    print("Engine counts:", counts)
    print(f"Total merged candidates: {len(candidates)}")
    for i, c in enumerate(candidates[:10]):
        cit = c.get("citation") or c.get("case_id")
        court = c.get("court") or c.get("court_name")
        title = c.get("title") or c.get("case_name")
        engines = c.get("retrieval_engines", [])
        is_stat = c.get("metadata", {}).get("is_statute", False)
        print(f"[{i+1}] is_statute={is_stat} | Citation: {cit} | Court: {court} | Engines: {engines} | Title: {title[:50] if title else ''}")

if __name__ == "__main__":
    asyncio.run(main())
