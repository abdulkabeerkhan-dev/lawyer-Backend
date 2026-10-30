"""
scripts/run_cross_encoder_benchmark.py

Three-Way Comparative Benchmark Suite for Phase 4, Step 5:
1. Baseline Legacy Pinecone Retrieval
2. Dual-Mode Pinecone Retrieval (Step 4)
3. Dual-Mode + Cross-Encoder Reranking (Step 5)

Evaluates all 30 standardized legal queries from legal_retrieval_test_cases.json.
Measures:
- Recall@5, Recall@10
- Precision@5, Precision@10
- MRR (Mean Reciprocal Rank)
- Cross-Domain Contamination Rate (%)
- Latency (seconds)
- Category-specific performance breakdown
- Identification of any queries where reranking affected recall
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, List, Any, Tuple
from collections import defaultdict

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.retrieval.pinecone_search import search_pinecone_dense, search_pinecone_dual_mode
from legal_ai.ranking.cross_encoder_reranker import rerank_candidates_cross_encoder
from core.metadata_enrichment import classify_legal_text

TEST_CASES_PATH = os.path.join(WORKSPACE_DIR, "legal_retrieval_test_cases.json")


def is_candidate_relevant(cand: Dict[str, Any], test_case: Dict[str, Any]) -> Tuple[bool, bool]:
    text = (cand.get("text") or cand.get("preview") or "").lower()
    title = (cand.get("title") or cand.get("case_title") or "").lower()
    citation = (cand.get("citation") or "").upper()
    haystack = f"{title} {citation} {text}"

    expected_domain = test_case.get("expected_domain", "civil")
    
    cand_domain, _, provisions, _, _ = classify_legal_text(
        text=text,
        title=title,
        citation=citation
    )

    domain_match = (cand_domain == expected_domain) or (cand_domain == "general_legal")

    expected_statutes = [s.lower() for s in test_case.get("expected_statutes", [])]
    expected_topics = [t.lower() for t in test_case.get("expected_topics", [])]

    statute_match = any(st in haystack for st in expected_statutes) if expected_statutes else False
    topic_match = any(tp in haystack for tp in expected_topics) if expected_topics else False

    substantive_match = domain_match and (statute_match or topic_match or len(expected_statutes) == 0)
    return domain_match, substantive_match


async def run_three_way_benchmark():
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    print(f"Loaded {len(test_cases)} test cases.")
    print("=" * 80)
    print("STARTING THREE-WAY COMPARATIVE BENCHMARK: BASELINE vs DUAL-MODE vs CROSS-ENCODER")
    print("=" * 80)

    # Accumulators
    def _create_metric_tracker():
        return {
            "rel_at_5": 0, "rel_at_10": 0,
            "prec_5_sum": 0.0, "prec_10_sum": 0.0,
            "mrr_sum": 0.0, "dom_err_count": 0, "latency_sum": 0.0,
            "category_stats": defaultdict(lambda: {"total": 0, "rel5": 0, "rel10": 0, "dom_err": 0})
        }

    m_base = _create_metric_tracker()
    m_dual = _create_metric_tracker()
    m_rerank = _create_metric_tracker()

    query_details = []
    regressions_detected = []

    for idx, tc in enumerate(test_cases):
        q_id = tc.get("query_id") or tc.get("id") or f"Q_{idx+1}"
        q_text = tc["query"]
        category = tc.get("category", "General")
        plan = create_deterministic_fallback_plan(q_text)

        # ----------------------------------------------------------------------
        # Pipeline 1: Baseline Legacy Pinecone
        # ----------------------------------------------------------------------
        t0 = time.time()
        cands_base = await search_pinecone_dense(q_text, top_k=40)
        t_base = time.time() - t0
        m_base["latency_sum"] += t_base

        # ----------------------------------------------------------------------
        # Pipeline 2: Dual-Mode Pinecone (Step 4)
        # ----------------------------------------------------------------------
        t0 = time.time()
        cands_dual, telem_dual = await search_pinecone_dual_mode(
            query_text=q_text,
            query_plan=plan,
            top_k=40,
            enable_lane_a=True,
            enable_lane_b=True
        )
        t_dual = time.time() - t0
        m_dual["latency_sum"] += t_dual

        # ----------------------------------------------------------------------
        # Pipeline 3: Dual-Mode + Cross-Encoder Reranker (Step 5)
        # ----------------------------------------------------------------------
        t0 = time.time()
        cands_rerank, telem_rerank = await rerank_candidates_cross_encoder(
            query_text=q_text,
            candidates=cands_dual,
            query_plan=plan,
            top_k=10,
            timeout_seconds=5.0
        )
        t_rerank = t_dual + (time.time() - t0)
        m_rerank["latency_sum"] += t_rerank

        # Evaluate Pipeline 1
        b_top5, b_top10 = cands_base[:5], cands_base[:10]
        b_rel5 = any(is_candidate_relevant(c, tc)[1] for c in b_top5)
        b_rel10 = any(is_candidate_relevant(c, tc)[1] for c in b_top10)
        b_prec5 = sum(1 for c in b_top5 if is_candidate_relevant(c, tc)[1]) / 5.0 if b_top5 else 0.0
        b_prec10 = sum(1 for c in b_top10 if is_candidate_relevant(c, tc)[1]) / 10.0 if b_top10 else 0.0
        b_rank = next((r+1 for r, c in enumerate(cands_base) if is_candidate_relevant(c, tc)[1]), 0)
        b_mrr = (1.0 / b_rank) if b_rank > 0 else 0.0
        b_dom_err = any(not is_candidate_relevant(c, tc)[0] for c in b_top5) if b_top5 else False

        if b_rel5: m_base["rel_at_5"] += 1
        if b_rel10: m_base["rel_at_10"] += 1
        m_base["prec_5_sum"] += b_prec5
        m_base["prec_10_sum"] += b_prec10
        m_base["mrr_sum"] += b_mrr
        if b_dom_err: m_base["dom_err_count"] += 1
        m_base["category_stats"][category]["total"] += 1
        if b_rel5: m_base["category_stats"][category]["rel5"] += 1
        if b_dom_err: m_base["category_stats"][category]["dom_err"] += 1

        # Evaluate Pipeline 2
        d_top5, d_top10 = cands_dual[:5], cands_dual[:10]
        d_rel5 = any(is_candidate_relevant(c, tc)[1] for c in d_top5)
        d_rel10 = any(is_candidate_relevant(c, tc)[1] for c in d_top10)
        d_prec5 = sum(1 for c in d_top5 if is_candidate_relevant(c, tc)[1]) / 5.0 if d_top5 else 0.0
        d_prec10 = sum(1 for c in d_top10 if is_candidate_relevant(c, tc)[1]) / 10.0 if d_top10 else 0.0
        d_rank = next((r+1 for r, c in enumerate(cands_dual) if is_candidate_relevant(c, tc)[1]), 0)
        d_mrr = (1.0 / d_rank) if d_rank > 0 else 0.0
        d_dom_err = any(not is_candidate_relevant(c, tc)[0] for c in d_top5) if d_top5 else False

        if d_rel5: m_dual["rel_at_5"] += 1
        if d_rel10: m_dual["rel_at_10"] += 1
        m_dual["prec_5_sum"] += d_prec5
        m_dual["prec_10_sum"] += d_prec10
        m_dual["mrr_sum"] += d_mrr
        if d_dom_err: m_dual["dom_err_count"] += 1
        m_dual["category_stats"][category]["total"] += 1
        if d_rel5: m_dual["category_stats"][category]["rel5"] += 1
        if d_dom_err: m_dual["category_stats"][category]["dom_err"] += 1

        # Evaluate Pipeline 3 (Cross-Encoder)
        r_top5, r_top10 = cands_rerank[:5], cands_rerank[:10]
        r_rel5 = any(is_candidate_relevant(c, tc)[1] for c in r_top5)
        r_rel10 = any(is_candidate_relevant(c, tc)[1] for c in r_top10)
        r_prec5 = sum(1 for c in r_top5 if is_candidate_relevant(c, tc)[1]) / 5.0 if r_top5 else 0.0
        r_prec10 = sum(1 for c in r_top10 if is_candidate_relevant(c, tc)[1]) / 10.0 if r_top10 else 0.0
        r_rank = next((r+1 for r, c in enumerate(cands_rerank) if is_candidate_relevant(c, tc)[1]), 0)
        r_mrr = (1.0 / r_rank) if r_rank > 0 else 0.0
        r_dom_err = any(not is_candidate_relevant(c, tc)[0] for c in r_top5) if r_top5 else False

        if r_rel5: m_rerank["rel_at_5"] += 1
        if r_rel10: m_rerank["rel_at_10"] += 1
        m_rerank["prec_5_sum"] += r_prec5
        m_rerank["prec_10_sum"] += r_prec10
        m_rerank["mrr_sum"] += r_mrr
        if r_dom_err: m_rerank["dom_err_count"] += 1
        m_rerank["category_stats"][category]["total"] += 1
        if r_rel5: m_rerank["category_stats"][category]["rel5"] += 1
        if r_dom_err: m_rerank["category_stats"][category]["dom_err"] += 1

        # Regression detection: did reranking push relevant authority OUT of top-5?
        if d_rel5 and not r_rel5:
            regressions_detected.append({
                "query_id": q_id,
                "query": q_text,
                "issue": "Reranker pushed relevant candidate out of top-5"
            })

        print(f"[{idx+1:02d}/30] {q_id} ({category[:15]}): Base Rel@5={b_rel5} | Dual Rel@5={d_rel5} | Rerank Rel@5={r_rel5} (MRR: {r_mrr:.2f})")

        query_details.append({
            "id": q_id,
            "category": category,
            "base": {"rel5": b_rel5, "rel10": b_rel10, "mrr": round(b_mrr, 3), "dom_err": b_dom_err},
            "dual": {"rel5": d_rel5, "rel10": d_rel10, "mrr": round(d_mrr, 3), "dom_err": d_dom_err},
            "rerank": {"rel5": r_rel5, "rel10": r_rel10, "mrr": round(r_mrr, 3), "dom_err": r_dom_err, "model": telem_rerank.get("model_used")},
            "latencies_s": {"base": round(t_base, 3), "dual": round(t_dual, 3), "rerank": round(t_rerank, 3)}
        })

    total = len(test_cases)
    
    def _calc_summary(m):
        return {
            "Recall@5": round((m["rel_at_5"] / total) * 100, 1),
            "Recall@10": round((m["rel_at_10"] / total) * 100, 1),
            "Precision@5": round(m["prec_5_sum"] / total, 3),
            "Precision@10": round(m["prec_10_sum"] / total, 3),
            "MRR": round(m["mrr_sum"] / total, 3),
            "Domain_Contamination_Rate": round((m["dom_err_count"] / total) * 100, 1),
            "Avg_Latency_s": round(m["latency_sum"] / total, 3),
            "Category_Breakdown": {k: dict(v) for k, v in m["category_stats"].items()}
        }

    summary = {
        "total_queries": total,
        "baseline": _calc_summary(m_base),
        "dual_mode": _calc_summary(m_dual),
        "cross_encoder_rerank": _calc_summary(m_rerank),
        "regressions_detected": regressions_detected,
        "query_details": query_details
    }

    out_path = os.path.join(WORKSPACE_DIR, "cross_encoder_benchmark_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("FINAL THREE-WAY BENCHMARK RESULTS:")
    print("=" * 80)
    print(f"Metric                      Baseline        Dual-Mode       Dual+CrossEncoder")
    print(f"Recall@5:                   {summary['baseline']['Recall@5']}%          {summary['dual_mode']['Recall@5']}%          {summary['cross_encoder_rerank']['Recall@5']}%")
    print(f"Recall@10:                  {summary['baseline']['Recall@10']}%          {summary['dual_mode']['Recall@10']}%          {summary['cross_encoder_rerank']['Recall@10']}%")
    print(f"Precision@5:                {summary['baseline']['Precision@5']}           {summary['dual_mode']['Precision@5']}           {summary['cross_encoder_rerank']['Precision@5']}")
    print(f"MRR:                        {summary['baseline']['MRR']}           {summary['dual_mode']['MRR']}           {summary['cross_encoder_rerank']['MRR']}")
    print(f"Contamination Rate:         {summary['baseline']['Domain_Contamination_Rate']}%          {summary['dual_mode']['Domain_Contamination_Rate']}%           {summary['cross_encoder_rerank']['Domain_Contamination_Rate']}%")
    print(f"Avg Latency:                {summary['baseline']['Avg_Latency_s']}s          {summary['dual_mode']['Avg_Latency_s']}s          {summary['cross_encoder_rerank']['Avg_Latency_s']}s")
    print(f"Regressions Detected:       None            None            {len(regressions_detected)}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_three_way_benchmark())
