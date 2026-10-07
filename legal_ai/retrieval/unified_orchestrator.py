"""
legal_ai/retrieval/unified_orchestrator.py

Unified Parallel Multi-Source Retrieval Orchestrator for Pakistani Legal AI Pipeline.
Executes concurrent retrieval across all 4 independent engines:
1. Supabase Postgres FTS: Exact terms, sections, and citations
2. Pinecone Vector DB: Dense semantic legal meaning (voyage-law-2)
3. BM25 Sparse Index: Keyword precision across 40,575 local chunks
4. External Judicial Portals: Fresh verification / recent court judgments

Merges candidates using Reciprocal Rank Fusion (RRF) and provides structured telemetry counts.
"""

import asyncio
import re
from typing import Dict, List, Any, Tuple, Optional
from legal_ai.retrieval.supabase_search import search_supabase_judgments
from legal_ai.retrieval.pinecone_search import search_pinecone_dense
from legal_ai.retrieval.bm25_search import search_bm25_sparse
from legal_ai.retrieval.external_search import search_external_judgments


def merge_candidates_with_rrf(
    engine_results: Dict[str, List[Dict[str, Any]]],
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """
    Merges candidates across retrieval engines using Reciprocal Rank Fusion (RRF).
    RRF score = sum(1.0 / (rrf_k + rank)) across engines where candidate was retrieved.
    """
    merged_map: Dict[str, Dict[str, Any]] = {}
    rrf_scores: Dict[str, float] = {}

    for engine_name, candidates in engine_results.items():
        for rank, c in enumerate(candidates):
            meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
            cid = str(c.get("case_id") or meta.get("case_id") or c.get("citation") or c.get("id") or "").strip()
            if not cid:
                continue

            norm_cid = re.sub(r'[\s_\-]+', '_', cid).lower()
            norm_cid = re.sub(r'(_chk_\d+|_chunk_\d+|#c\d+)$', '', norm_cid, flags=re.IGNORECASE).strip()

            if norm_cid not in merged_map:
                merged_map[norm_cid] = dict(c)
                merged_map[norm_cid]["retrieval_engines"] = [engine_name]
                rrf_scores[norm_cid] = 0.0
            else:
                existing = merged_map[norm_cid]
                if engine_name not in existing.get("retrieval_engines", []):
                    existing.setdefault("retrieval_engines", []).append(engine_name)

            rrf_scores[norm_cid] += 1.0 / (rrf_k + rank + 1)

            # Preserve best full text and source attributes
            existing = merged_map[norm_cid]
            if c.get("is_supabase_fts"):
                existing["is_supabase_fts"] = True
            if c.get("dense_score", 0.0) > existing.get("dense_score", 0.0):
                existing["dense_score"] = c["dense_score"]
            if c.get("sparse_score", 0.0) > existing.get("sparse_score", 0.0):
                existing["sparse_score"] = c["sparse_score"]
            if c.get("bm25_score"):
                existing["bm25_score"] = c["bm25_score"]

            meta_existing = existing.get("metadata", {})
            meta_new = c.get("metadata", {})
            if len(str(meta_new.get("full_text") or meta_new.get("text") or "")) > len(str(meta_existing.get("full_text") or meta_existing.get("text") or "")):
                meta_existing["full_text"] = meta_new.get("full_text") or meta_new.get("text")
                existing["preview"] = c.get("preview") or existing.get("preview")

    # Assign final RRF score to each candidate
    final_list: List[Dict[str, Any]] = []
    for norm_cid, cand in merged_map.items():
        cand["rrf_score"] = rrf_scores[norm_cid]
        cand["score"] = rrf_scores[norm_cid]
        final_list.append(cand)

    final_list.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return final_list


async def retrieve_candidates_parallel(
    query_text: str,
    query_plan: Any = None,
    include_external: bool = False,
    top_k_per_engine: int = 40
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Executes parallel retrieval across Supabase, Pinecone, BM25, and optional External search.
    Returns:
        merged_candidates: Unified RRF-ranked candidate list
        engine_counts: Dict with {count_supabase, count_pinecone, count_bm25, count_external}
    """
    # 1. Extract search terms for Supabase and BM25
    search_terms = [query_text]
    provisions = []
    if query_plan:
        if hasattr(query_plan, "provisions") and query_plan.provisions:
            provisions = query_plan.provisions
        elif isinstance(query_plan, dict) and query_plan.get("provisions"):
            provisions = query_plan["provisions"]

    for p in provisions:
        search_terms.append(str(p))

    if query_plan and hasattr(query_plan, "search_lanes") and query_plan.search_lanes:
        for lane in query_plan.search_lanes:
            if isinstance(lane, dict) and lane.get("query"):
                search_terms.append(lane["query"])

    # 2. Build enriched query for semantic vector search
    semantic_query = query_text
    if query_plan:
        q_list = []
        if hasattr(query_plan, "legal_questions") and query_plan.legal_questions:
            q_list = [str(q) for q in query_plan.legal_questions]
        elif isinstance(query_plan, dict) and query_plan.get("legal_questions"):
            q_list = [str(q) for q in query_plan["legal_questions"]]
        if q_list:
            semantic_query = f"{query_text} {' '.join(q_list[:2])}".strip()

    # 3. Fire concurrent search tasks
    supabase_task = asyncio.create_task(search_supabase_judgments(search_terms, limit_per_term=15))
    pinecone_task = asyncio.create_task(search_pinecone_dense(semantic_query, top_k=top_k_per_engine, min_similarity=0.30))
    bm25_task = asyncio.create_task(asyncio.to_thread(search_bm25_sparse, query_text, top_k=top_k_per_engine))

    if include_external:
        external_task = asyncio.create_task(search_external_judgments(query_text, max_results=5))
        sb_res, pc_res, bm_res, ext_res = await asyncio.gather(
            supabase_task, pinecone_task, bm25_task, external_task
        )
    else:
        sb_res, pc_res, bm_res = await asyncio.gather(
            supabase_task, pinecone_task, bm25_task
        )
        ext_res = []

    engine_results = {
        "Supabase": sb_res,
        "Pinecone": pc_res,
        "BM25": bm_res,
        "External": ext_res
    }

    engine_counts = {
        "count_supabase": len(sb_res),
        "count_pinecone": len(pc_res),
        "count_bm25": len(bm_res),
        "count_external": len(ext_res)
    }

    merged = merge_candidates_with_rrf(engine_results)
    return merged, engine_counts
