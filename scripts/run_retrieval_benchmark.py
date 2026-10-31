"""
scripts/run_retrieval_benchmark.py

Reproducible Pakistani Legal RAG Benchmark Suite.
Runs 30 structured natural-language queries across:
1. BM25 Sparse Lexical Retrieval (40,575 local chunks)
2. Pinecone Dense Vector Retrieval (Voyage-law-2 1024-d)
3. Supabase Postgres Full-Text Search
4. Reciprocal Rank Fusion (RRF)
5. Authority Ranker & Relevance Gating

Outputs:
- retrieval_benchmark_results.csv
- Detailed metrics calculation for LEGAL_RAG_EVALUATION_REPORT.md
"""

import os
import sys
import json
import csv
import asyncio
import time
import re
from typing import Dict, List, Any, Set, Tuple

from dotenv import load_dotenv
load_dotenv()

# Add workspace root to sys.path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.retrieval.bm25_search import search_bm25_sparse
from legal_ai.retrieval.pinecone_search import search_pinecone_dense
from legal_ai.retrieval.supabase_search import search_supabase_judgments
from legal_ai.retrieval.unified_orchestrator import merge_candidates_with_rrf
from core.authority_ranking import rank_and_filter_authorities, is_irrelevant_subject

TEST_CASES_PATH = os.path.join(WORKSPACE_DIR, "legal_retrieval_test_cases.json")
RESULTS_CSV_PATH = os.path.join(WORKSPACE_DIR, "retrieval_benchmark_results.csv")


def determine_candidate_domain(cand: Dict[str, Any]) -> str:
    """Classifies candidate's legal domain from text, title, citation."""
    meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else cand
    title = str(cand.get("title") or cand.get("case_name") or meta.get("title") or "").lower()
    text = str(cand.get("preview") or cand.get("full_text") or meta.get("text") or meta.get("full_text") or "").lower()
    cit = str(cand.get("citation") or meta.get("citation") or "").upper()
    haystack = f"{title} {cit} {text}"

    if any(k in haystack for k in ["pcrlj", "bail petition", "fir", "quashment", "cr.p.c", "crpc", "section 302", "ppc", "cnsa", "narcotic", "criminal revision"]):
        if not any(k in haystack for k in ["partition", "khula", "rent tribunal"]):
            return "criminal"
    if any(k in haystack for k in ["khula", "dower", "nikahnama", "talaq", "family court", "custody of minor", "guardians and wards", "mflo"]):
        return "family"
    if any(k in haystack for k in ["rent tribunal", "tenant", "landlord", "prpa", "srpo", "ejectment", "fair rent"]):
        return "rent"
    if any(k in haystack for k in ["financial institutions", "fio 2001", "recovery of finances", "banking court", "pawnor", "pledge of shares", "cld"]):
        return "banking"
    if any(k in haystack for k in ["companies act", "secp", "oppression", "mismanagement", "shareholder", "company bench"]):
        return "corporate"
    if any(k in haystack for k in ["article 199", "article 184(3)", "service tribunal", "civil servant", "writ petition", "constitution of pakistan"]):
        return "constitutional"
    if any(k in haystack for k in ["partition", "benami", "co-sharer", "preliminary decree", "order xx rule 18", "specific relief", "order xxxix", "execution"]):
        return "civil"
    return "civil"


def is_candidate_relevant(cand: Dict[str, Any], test_case: Dict[str, Any]) -> Tuple[bool, bool]:
    """
    Evaluates if candidate is:
    1. Domain-relevant (matches expected legal domain)
    2. Substantively relevant (matches expected topics/statutes)
    """
    cand_domain = determine_candidate_domain(cand)
    expected_domain = test_case["expected_domain"]

    domain_match = (cand_domain == expected_domain)
    # Special compatibility: rent, banking, and family often overlap with civil procedure
    if not domain_match:
        if expected_domain in ("civil", "rent", "banking") and cand_domain in ("civil", "rent", "banking"):
            domain_match = True

    meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else cand
    title = str(cand.get("title") or cand.get("case_name") or meta.get("title") or "").lower()
    text = str(cand.get("preview") or cand.get("full_text") or meta.get("text") or meta.get("full_text") or "").lower()
    haystack = f"{title} {text}"

    # Check topic overlap
    topics = test_case.get("expected_topics", [])
    topic_hits = sum(1 for t in topics if t.lower() in haystack)

    # Check statute / provision overlap
    statutes = test_case.get("expected_statutes", [])
    provisions = test_case.get("expected_provisions", [])
    statute_hit = any(s.lower() in haystack for s in statutes) or any(p.lower() in haystack for p in provisions)

    substantive_relevant = (topic_hits >= 1 or statute_hit) and domain_match
    return domain_match, substantive_relevant


async def run_benchmark():
    print("=" * 80)
    print("PAKISTANI LEGAL RAG RETRIEVAL BENCHMARK SUITE")
    print("=" * 80)

    if not os.path.exists(TEST_CASES_PATH):
        raise FileNotFoundError(f"Test cases missing at {TEST_CASES_PATH}")

    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    print(f"Loaded {len(test_cases)} structured test cases.\n")

    csv_rows = []
    engine_stats = {
        "BM25": {"total": 0, "rel@5": 0, "rel@10": 0, "dom_correct": 0, "mrr_sum": 0.0},
        "Pinecone": {"total": 0, "rel@5": 0, "rel@10": 0, "dom_correct": 0, "mrr_sum": 0.0},
        "Supabase": {"total": 0, "rel@5": 0, "rel@10": 0, "dom_correct": 0, "mrr_sum": 0.0},
        "RRF_Merged": {"total": 0, "rel@5": 0, "rel@10": 0, "dom_correct": 0, "mrr_sum": 0.0},
        "Final_Reranked": {"total": 0, "rel@5": 0, "rel@10": 0, "dom_correct": 0, "mrr_sum": 0.0}
    }

    category_stats = {}

    for idx, tc in enumerate(test_cases):
        qid = tc["query_id"]
        q_text = tc["query"]
        cat = tc["category"]
        print(f"[{idx+1}/{len(test_cases)}] Running {qid}: '{q_text[:70]}...'")

        # 1. Query Planning
        plan = create_deterministic_fallback_plan(q_text)

        # 2. Concurrent Engine Retrievals
        def _exec_supabase_benchmark():
            try:
                from legal_ai.config import get_supabase_client
                from legal_ai.retrieval.supabase_search import _format_supabase_record
                sb = get_supabase_client()
                if not sb:
                    return []
                candidates = []
                seen_ids = set()

                # Check exact citations / numbers
                m_cit = re.search(r'\b(?:19|20)\d{2}\s+(?:SCMR|PLD|PCrLJ|CLC|MLD|YLR|CLD|PTD)\s+\d+\b', q_text, re.I)
                if m_cit:
                    t_cit = m_cit.group(0).strip().replace(' ', '_')
                    r = sb.table("full_judgments").select("id, case_id, case_title, neutral_citation, court_name, decision_date, full_text").eq("case_id", t_cit).limit(3).execute()
                    for item in (r.data or []):
                        cid = str(item.get("case_id") or item.get("id"))
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            candidates.append(_format_supabase_record(item, score=0.95))

                # Check indexed key terms from plan
                key_terms = []
                for p in getattr(plan, "provisions", [])[:2]:
                    nums = re.findall(r'\b\d+\b', p)
                    if nums:
                        key_terms.append(f"{p}")
                for q_word in re.findall(r'\b[A-Za-z]{5,}\b', q_text):
                    if q_word.lower() not in ("whether", "which", "court", "pakistan", "under", "without", "regarding", "between", "against", "appeal", "petition"):
                        key_terms.append(q_word)

                if len(key_terms) >= 2:
                    w1, w2 = key_terms[0], key_terms[1]
                    r = sb.table("full_judgments").select("id, case_id, case_title, neutral_citation, court_name, decision_date, full_text").ilike("case_title", f"%{w1}%{w2}%").limit(3).execute()
                    for item in (r.data or []):
                        cid = str(item.get("case_id") or item.get("id"))
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            candidates.append(_format_supabase_record(item, score=0.75))

                return candidates
            except Exception as s_err:
                return []

        async def _safe_pinecone():
            try:
                return await asyncio.wait_for(search_pinecone_dense(q_text, top_k=15, min_similarity=0.30), timeout=8.0)
            except Exception as pe:
                return []

        def _safe_bm25():
            try:
                return search_bm25_sparse(q_text, top_k=15)
            except Exception:
                return []

        bm25_hits, pinecone_hits, supabase_hits = await asyncio.gather(
            asyncio.to_thread(_safe_bm25),
            _safe_pinecone(),
            asyncio.to_thread(_exec_supabase_benchmark)
        )

        # 3. RRF Fusion
        engine_dict = {
            "BM25": bm25_hits,
            "Pinecone": pinecone_hits,
            "Supabase": supabase_hits
        }
        rrf_fused = merge_candidates_with_rrf(engine_dict, query_plan=plan, rrf_k=60)

        # 4. Final Authority Ranking & Gating
        final_reranked = rank_and_filter_authorities(list(rrf_fused), query_plan=plan, top_k=10)

        # Evaluate Each Engine
        eval_targets = [
            ("BM25", bm25_hits),
            ("Pinecone", pinecone_hits),
            ("Supabase", supabase_hits),
            ("RRF_Merged", rrf_fused),
            ("Final_Reranked", final_reranked)
        ]

        cat_entry = category_stats.setdefault(cat, {"queries": 0, "final_rel@5": 0, "final_dom_err": 0})
        cat_entry["queries"] += 1

        for eng_name, hits in eval_targets:
            engine_stats[eng_name]["total"] += 1
            first_rel_rank = 0
            hits_5 = hits[:5]
            hits_10 = hits[:10]

            rel_in_5 = 0
            dom_in_5 = 0
            for rank_i, h in enumerate(hits_10):
                dom_ok, rel_ok = is_candidate_relevant(h, tc)
                if rel_ok:
                    if first_rel_rank == 0:
                        first_rel_rank = rank_i + 1
                    if rank_i < 5:
                        rel_in_5 += 1
                if dom_ok and rank_i < 5:
                    dom_in_5 += 1

                # Log top-3 individual candidates to CSV
                if rank_i < 3:
                    cand_cit = str(h.get("citation") or h.get("case_id") or "Unknown")
                    cand_title = str(h.get("title") or h.get("case_name") or "Precedent")[:60]
                    cand_court = str(h.get("court") or "Superior Court")
                    cand_score = float(h.get("score") or h.get("authority_score") or 0.0)
                    cand_dom = determine_candidate_domain(h)
                    csv_rows.append({
                        "query_id": qid,
                        "category": cat,
                        "query": q_text,
                        "engine": eng_name,
                        "rank": rank_i + 1,
                        "citation": cand_cit,
                        "title": cand_title,
                        "court": cand_court,
                        "detected_domain": cand_dom,
                        "score": round(cand_score, 4),
                        "domain_match": dom_ok,
                        "substantive_relevant": rel_ok
                    })

            if rel_in_5 > 0:
                engine_stats[eng_name]["rel@5"] += 1
            if first_rel_rank > 0:
                engine_stats[eng_name]["rel@10"] += 1
                engine_stats[eng_name]["mrr_sum"] += (1.0 / first_rel_rank)
            if dom_in_5 >= 3:
                engine_stats[eng_name]["dom_correct"] += 1

            if eng_name == "Final_Reranked":
                if rel_in_5 > 0:
                    cat_entry["final_rel@5"] += 1
                if dom_in_5 < 3:
                    cat_entry["final_dom_err"] += 1

    # Write CSV
    with open(RESULTS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "query_id", "category", "query", "engine", "rank", "citation",
            "title", "court", "detected_domain", "score", "domain_match", "substantive_relevant"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n[OK] Benchmark results written to {RESULTS_CSV_PATH}")

    # Output Summary Table
    total_q = len(test_cases)
    print("\n" + "=" * 80)
    print("BENCHMARK METRICS SUMMARY (N=30 Queries)")
    print("=" * 80)
    print(f"{'Engine':<16} | {'Recall@5':<10} | {'Recall@10':<10} | {'MRR':<8} | {'Domain Error %':<15}")
    print("-" * 80)

    summary_metrics = {}
    for eng_name, s in engine_stats.items():
        r5 = (s["rel@5"] / total_q) * 100.0
        r10 = (s["rel@10"] / total_q) * 100.0
        mrr = s["mrr_sum"] / total_q
        dom_err = ((total_q - s["dom_correct"]) / total_q) * 100.0
        summary_metrics[eng_name] = {
            "Recall@5": round(r5, 1),
            "Recall@10": round(r10, 1),
            "MRR": round(mrr, 3),
            "Domain_Error_Rate": round(dom_err, 1)
        }
        print(f"{eng_name:<16} | {r5:>8.1f}% | {r10:>8.1f}% | {mrr:>8.3f} | {dom_err:>13.1f}%")

    print("\n" + "=" * 80)
    print("CATEGORY BREAKDOWN (Final Reranked Engine)")
    print("=" * 80)
    for cat, cs in category_stats.items():
        q_cnt = cs["queries"]
        rel_pct = (cs["final_rel@5"] / q_cnt) * 100.0
        err_pct = (cs["final_dom_err"] / q_cnt) * 100.0
        print(f"{cat:<32} | Queries: {q_cnt} | Rel@5: {rel_pct:>5.1f}% | Domain Mismatch: {err_pct:>5.1f}%")

    # Save summary json for evaluation report
    with open(os.path.join(WORKSPACE_DIR, "benchmark_metrics_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"summary_metrics": summary_metrics, "category_stats": category_stats}, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
