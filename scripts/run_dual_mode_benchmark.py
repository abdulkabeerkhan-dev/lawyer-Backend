"""
scripts/run_dual_mode_benchmark.py

Controlled Comparative Benchmark: Baseline Legacy Pinecone vs. Dual-Mode Pinecone Retrieval.
Evaluates all 30 benchmark test cases from legal_retrieval_test_cases.json.

Measures:
- Recall@5, Recall@10
- Precision@5, Precision@10
- MRR (Mean Reciprocal Rank)
- Cross-Domain Contamination Rate (% of retrieved results from irrelevant domains)
- Retrieval Latency (seconds)
- Candidate Counts per Retrieval Lane (Lane A vs Lane B vs Quarantined)
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, List, Any, Tuple

# Workspace root
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.retrieval.pinecone_search import search_pinecone_dense, search_pinecone_dual_mode
from core.metadata_enrichment import classify_legal_text

TEST_CASES_PATH = os.path.join(WORKSPACE_DIR, "legal_retrieval_test_cases.json")


def is_candidate_relevant(cand: Dict[str, Any], test_case: Dict[str, Any]) -> Tuple[bool, bool]:
    """
    Evaluates:
    1. Domain match (matches expected domain)
    2. Substantive relevance (matches topics, statutes, or keywords)
    """
    text = (cand.get("text") or cand.get("preview") or "").lower()
    title = (cand.get("title") or cand.get("case_title") or "").lower()
    citation = (cand.get("citation") or "").upper()
    haystack = f"{title} {citation} {text}"

    expected_domain = test_case.get("expected_domain", "civil")
    
    # Classify candidate domain
    cand_domain, _, provisions, _, _ = classify_legal_text(
        text=text,
        title=title,
        citation=citation
    )

    domain_match = (cand_domain == expected_domain) or (cand_domain == "general_legal")

    # Substantive check against expected keywords and statutes
    expected_statutes = [s.lower() for s in test_case.get("expected_statutes", [])]
    expected_topics = [t.lower() for t in test_case.get("expected_topics", [])]

    statute_match = any(st in haystack for st in expected_statutes) if expected_statutes else False
    topic_match = any(tp in haystack for tp in expected_topics) if expected_topics else False

    # Substantive match requires domain match plus either statute or topic presence
    substantive_match = domain_match and (statute_match or topic_match or len(expected_statutes) == 0)

    return domain_match, substantive_match


async def run_comparison_benchmark():
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    print(f"Loaded {len(test_cases)} benchmark test cases.")
    print("=" * 80)
    print("STARTING CONTROLLED BENCHMARK: BASELINE vs. DUAL-MODE PINECONE RETRIEVAL")
    print("=" * 80)

    # Metrics collectors
    baseline_metrics = {
        "rel_at_5": 0, "rel_at_10": 0,
        "prec_5_sum": 0.0, "prec_10_sum": 0.0,
        "mrr_sum": 0.0, "dom_err_count": 0, "total_eval": 0,
        "latency_sum": 0.0
    }

    dual_mode_metrics = {
        "rel_at_5": 0, "rel_at_10": 0,
        "prec_5_sum": 0.0, "prec_10_sum": 0.0,
        "mrr_sum": 0.0, "dom_err_count": 0, "total_eval": 0,
        "latency_sum": 0.0,
        "lane_a_total": 0, "lane_b_raw_total": 0,
        "lane_b_quarantined_total": 0, "merged_total": 0
    }

    results_table = []

    for idx, tc in enumerate(test_cases):
        q_id = tc.get("query_id") or tc.get("id") or f"Q_{idx+1}"
        q_text = tc["query"]
        exp_dom = tc["expected_domain"]
        plan = create_deterministic_fallback_plan(q_text)

        # ----------------------------------------------------------------------
        # 1. Baseline: Legacy Pinecone Dense Search (Unfiltered)
        # ----------------------------------------------------------------------
        t0_base = time.time()
        base_cands = await search_pinecone_dense(q_text, top_k=40)
        t_base = time.time() - t0_base
        baseline_metrics["latency_sum"] += t_base

        # Evaluate Baseline Top-10
        base_top5 = base_cands[:5]
        base_top10 = base_cands[:10]

        base_rel_5 = any(is_candidate_relevant(c, tc)[1] for c in base_top5)
        base_rel_10 = any(is_candidate_relevant(c, tc)[1] for c in base_top10)
        if base_rel_5: baseline_metrics["rel_at_5"] += 1
        if base_rel_10: baseline_metrics["rel_at_10"] += 1

        base_prec_5 = sum(1 for c in base_top5 if is_candidate_relevant(c, tc)[1]) / 5.0 if base_top5 else 0.0
        base_prec_10 = sum(1 for c in base_top10 if is_candidate_relevant(c, tc)[1]) / 10.0 if base_top10 else 0.0
        baseline_metrics["prec_5_sum"] += base_prec_5
        baseline_metrics["prec_10_sum"] += base_prec_10

        # Baseline MRR
        base_rank = 0
        for r_idx, c in enumerate(base_cands):
            if is_candidate_relevant(c, tc)[1]:
                base_rank = r_idx + 1
                break
        base_mrr = (1.0 / base_rank) if base_rank > 0 else 0.0
        baseline_metrics["mrr_sum"] += base_mrr

        # Baseline Domain Error in Top-5
        base_dom_err = any(not is_candidate_relevant(c, tc)[0] for c in base_top5) if base_top5 else False
        if base_dom_err: baseline_metrics["dom_err_count"] += 1

        # ----------------------------------------------------------------------
        # 2. Dual-Mode Pinecone Search (Lane A + Lane B + Post-Retrieval Quarantine)
        # ----------------------------------------------------------------------
        t0_dual = time.time()
        dual_cands, telem = await search_pinecone_dual_mode(
            query_text=q_text,
            query_plan=plan,
            top_k=40,
            enable_lane_a=True,
            enable_lane_b=True
        )
        t_dual = time.time() - t0_dual
        dual_mode_metrics["latency_sum"] += t_dual

        # Track telemetry
        dual_mode_metrics["lane_a_total"] += telem["lane_a_raw_count"]
        dual_mode_metrics["lane_b_raw_total"] += telem["lane_b_raw_count"]
        dual_mode_metrics["lane_b_quarantined_total"] += telem["lane_b_quarantined_count"]
        dual_mode_metrics["merged_total"] += telem["merged_count"]

        # Evaluate Dual-Mode Top-10
        dual_top5 = dual_cands[:5]
        dual_top10 = dual_cands[:10]

        dual_rel_5 = any(is_candidate_relevant(c, tc)[1] for c in dual_top5)
        dual_rel_10 = any(is_candidate_relevant(c, tc)[1] for c in dual_top10)
        if dual_rel_5: dual_mode_metrics["rel_at_5"] += 1
        if dual_rel_10: dual_mode_metrics["rel_at_10"] += 1

        dual_prec_5 = sum(1 for c in dual_top5 if is_candidate_relevant(c, tc)[1]) / 5.0 if dual_top5 else 0.0
        dual_prec_10 = sum(1 for c in dual_top10 if is_candidate_relevant(c, tc)[1]) / 10.0 if dual_top10 else 0.0
        dual_mode_metrics["prec_5_sum"] += dual_prec_5
        dual_mode_metrics["prec_10_sum"] += dual_prec_10

        # Dual-Mode MRR
        dual_rank = 0
        for r_idx, c in enumerate(dual_cands):
            if is_candidate_relevant(c, tc)[1]:
                dual_rank = r_idx + 1
                break
        dual_mrr = (1.0 / dual_rank) if dual_rank > 0 else 0.0
        dual_mode_metrics["mrr_sum"] += dual_mrr

        # Dual-Mode Domain Error in Top-5
        dual_dom_err = any(not is_candidate_relevant(c, tc)[0] for c in dual_top5) if dual_top5 else False
        if dual_dom_err: dual_mode_metrics["dom_err_count"] += 1

        baseline_metrics["total_eval"] += 1
        dual_mode_metrics["total_eval"] += 1

        print(f"[{idx+1:02d}/30] {q_id} ({exp_dom}): Baseline Hits={len(base_cands)} (Rel@5={base_rel_5}, DomErr={base_dom_err}) | "
              f"Dual-Mode Hits={len(dual_cands)} (Rel@5={dual_rel_5}, DomErr={dual_dom_err}, Quarantined={telem['lane_b_quarantined_count']})")

        results_table.append({
            "id": q_id,
            "domain": exp_dom,
            "baseline_rel5": base_rel_5,
            "dual_rel5": dual_rel_5,
            "baseline_dom_err": base_dom_err,
            "dual_dom_err": dual_dom_err,
            "quarantined": telem["lane_b_quarantined_count"],
            "base_latency": round(t_base, 3),
            "dual_latency": round(t_dual, 3)
        })

    total = len(test_cases)
    summary = {
        "total_queries": total,
        "baseline": {
            "Recall@5": round((baseline_metrics["rel_at_5"] / total) * 100, 1),
            "Recall@10": round((baseline_metrics["rel_at_10"] / total) * 100, 1),
            "Precision@5": round(baseline_metrics["prec_5_sum"] / total, 3),
            "Precision@10": round(baseline_metrics["prec_10_sum"] / total, 3),
            "MRR": round(baseline_metrics["mrr_sum"] / total, 3),
            "Domain_Contamination_Rate": round((baseline_metrics["dom_err_count"] / total) * 100, 1),
            "Avg_Latency_s": round(baseline_metrics["latency_sum"] / total, 3)
        },
        "dual_mode": {
            "Recall@5": round((dual_mode_metrics["rel_at_5"] / total) * 100, 1),
            "Recall@10": round((dual_mode_metrics["rel_at_10"] / total) * 100, 1),
            "Precision@5": round(dual_mode_metrics["prec_5_sum"] / total, 3),
            "Precision@10": round(dual_mode_metrics["prec_10_sum"] / total, 3),
            "MRR": round(dual_mode_metrics["mrr_sum"] / total, 3),
            "Domain_Contamination_Rate": round((dual_mode_metrics["dom_err_count"] / total) * 100, 1),
            "Avg_Latency_s": round(dual_mode_metrics["latency_sum"] / total, 3),
            "Avg_Lane_A_Raw_Hits": round(dual_mode_metrics["lane_a_total"] / total, 1),
            "Avg_Lane_B_Raw_Hits": round(dual_mode_metrics["lane_b_raw_total"] / total, 1),
            "Avg_Lane_B_Quarantined": round(dual_mode_metrics["lane_b_quarantined_total"] / total, 1),
            "Avg_Merged_Hits": round(dual_mode_metrics["merged_total"] / total, 1)
        },
        "per_query_details": results_table
    }

    out_file = os.path.join(WORKSPACE_DIR, "dual_mode_benchmark_summary.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("BENCHMARK COMPARISON SUMMARY:")
    print("=" * 80)
    print(f"Metric                          Baseline (Legacy)       Dual-Mode (Step 4)      Improvement")
    print(f"Recall@5:                       {summary['baseline']['Recall@5']}%                  {summary['dual_mode']['Recall@5']}%                  {summary['dual_mode']['Recall@5'] - summary['baseline']['Recall@5']:+.1f}%")
    print(f"Recall@10:                      {summary['baseline']['Recall@10']}%                  {summary['dual_mode']['Recall@10']}%                  {summary['dual_mode']['Recall@10'] - summary['baseline']['Recall@10']:+.1f}%")
    print(f"Precision@5:                    {summary['baseline']['Precision@5']}                  {summary['dual_mode']['Precision@5']}                  {summary['dual_mode']['Precision@5'] - summary['baseline']['Precision@5']:+.3f}")
    print(f"MRR:                            {summary['baseline']['MRR']}                  {summary['dual_mode']['MRR']}                  {summary['dual_mode']['MRR'] - summary['baseline']['MRR']:+.3f}")
    print(f"Domain Contamination Rate:      {summary['baseline']['Domain_Contamination_Rate']}%                  {summary['dual_mode']['Domain_Contamination_Rate']}%                  {summary['dual_mode']['Domain_Contamination_Rate'] - summary['baseline']['Domain_Contamination_Rate']:+.1f}%")
    print(f"Avg Latency:                    {summary['baseline']['Avg_Latency_s']}s                 {summary['dual_mode']['Avg_Latency_s']}s                 {summary['dual_mode']['Avg_Latency_s'] - summary['baseline']['Avg_Latency_s']:+.3f}s")
    print(f"Avg Quarantined per query:      0.0                    {summary['dual_mode']['Avg_Lane_B_Quarantined']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_comparison_benchmark())
