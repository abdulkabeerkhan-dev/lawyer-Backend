"""
scripts/show_full_citations.py

Executes full multi-lane retrieval (Zilliz statutes_v3 + Zilliz judgments_v1 + BM25)
to extract and present complete citations:
1. Verbatim Statutory Citations (Act + Section + Canonical ID)
2. Authentic Judicial Precedent Citations (Court, Year, Citation, Title, Ratio/Holding)
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
from legal_ai.retrieval.statute_search import search_statutes_hybrid
from legal_ai.retrieval.unified_orchestrator import retrieve_candidates_parallel

TEST_QUERIES = [
    "eviction notice",
    "willful default",
    "director took a bank loan and did not repay"
]

async def run_full_citation_demonstration():
    results = {}
    for q in TEST_QUERIES:
        print(f"\n" + "="*80)
        print(f"QUERY: '{q}'")
        print("="*80)

        # 1. Query Plan
        plan = create_deterministic_fallback_plan(q)

        # 2. Verbatim Bare-Act Framework
        framework = inject_statutory_framework(plan, query_text=q)
        statute_hits = await search_statutes_hybrid(q, top_k=5)

        # 3. Judicial Precedent Candidates
        candidates, counts = await retrieve_candidates_parallel(q, query_plan=plan, top_k_per_engine=5)

        # Filter out pure statute entries to isolate authentic case citations
        case_candidates = [
            c for c in candidates 
            if not c.get("metadata", {}).get("is_statute", False) 
            and (c.get("citation") or c.get("case_id"))
        ]

        print("\n--- A. VERBATIM STATUTORY CITATIONS ---")
        stat_list = []
        for rank, sh in enumerate(statute_hits, 1):
            act = sh.get("act_name", "")
            sec = sh.get("section", "")
            cid = sh.get("canonical_id", "")
            heading = sh.get("heading", "")
            stat_cite = f"{act} s.{sec} [{cid}]"
            stat_list.append(stat_cite)
            print(f"[{rank}] {act} — Section {sec}")
            print(f"    Canonical Citation: {cid}")
            print(f"    Subject / Heading: {heading}")

        print("\n--- B. AUTHENTIC JUDICIAL CASE CITATIONS (Precedents) ---")
        case_list = []
        for rank, cc in enumerate(case_candidates[:8], 1):
            cit = cc.get("citation") or cc.get("case_id")
            court = cc.get("court") or cc.get("canonical_court_name") or cc.get("court_name") or "Superior Court"
            title = cc.get("title") or cc.get("case_name") or "Reported Decision"
            score = cc.get("rrf_score") or cc.get("score") or 0.0
            preview = (cc.get("preview") or cc.get("metadata", {}).get("full_text") or "")[:200].replace("\n", " ").strip()
            
            entry = {
                "citation": cit,
                "court": court,
                "title": title,
                "score": score,
                "preview": preview
            }
            case_list.append(entry)
            print(f"[{rank}] Citation: {cit}")
            print(f"    Court: {court}")
            print(f"    Case Title: {title}")
            print(f"    RRF Relevance Score: {score}")
            print(f"    Key Rule / Excerpt: {preview}...")

        results[q] = {
            "statutory_citations": stat_list,
            "case_citations": case_list
        }

    # Save to report
    out_file = Path("D:/lawyer-Backend/reports/full_citations_report.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved full citations report to {out_file}")

if __name__ == "__main__":
    asyncio.run(run_full_citation_demonstration())
