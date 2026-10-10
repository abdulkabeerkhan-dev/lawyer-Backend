"""
legal_ai/retrieval/unified_orchestrator.py

Unified Parallel Multi-Source Retrieval Orchestrator for Pakistani Legal AI Pipeline.
Executes concurrent retrieval across all 4 independent engines:
1. Supabase Postgres: Exact terms, indexed case_id, sections, and full_text FTS
2. Pinecone Vector DB: Dense semantic legal meaning (voyage-law-2) per issue lane
3. BM25 Sparse Index: Keyword precision across 40,575 local chunks
4. External Judicial Portals: Fresh verification / leads-only web fallback

Merges candidates using Reciprocal Rank Fusion (RRF) with constitutional court hierarchy
and provincial jurisdiction weighting (Articles 189 & 201).
"""

import asyncio
import re
from typing import Dict, List, Any, Tuple, Optional
from legal_ai.retrieval.supabase_search import search_supabase_judgments
from legal_ai.retrieval.pinecone_search import search_pinecone_dense
from legal_ai.retrieval.bm25_search import search_bm25_sparse
from legal_ai.retrieval.external_search import search_external_judgments
from scripts.propose_court_metadata_repair import resolve_court_and_province


def merge_candidates_with_rrf(
    engine_results: Dict[str, List[Dict[str, Any]]],
    query_plan: Any = None,
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """
    Merges candidates across retrieval engines using Reciprocal Rank Fusion (RRF).
    RRF score = sum(1.0 / (rrf_k + rank)) across engines where candidate was retrieved.
    Applies constitutional priority (Article 189 Supreme Court, Article 201 High Court)
    and tags external results as leads_only unless corroborated by local primary stores.
    """
    merged_map: Dict[str, Dict[str, Any]] = {}
    rrf_scores: Dict[str, float] = {}

    target_province = ""
    binding_courts = []
    if query_plan:
        target_province = str(getattr(query_plan, "province", "") or "").strip().title()
        binding_courts = [str(bc).lower() for bc in getattr(query_plan, "binding_courts", [])]

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

    # Apply constitutional weighting and leads_only tagging
    final_list: List[Dict[str, Any]] = []
    for norm_cid, cand in merged_map.items():
        base_score = rrf_scores[norm_cid]
        engines = cand.get("retrieval_engines", [])

        # Tag web-only leads
        if "External" in engines and len(engines) == 1:
            cand["leads_only"] = True
        else:
            cand["leads_only"] = False

        # Resolve court and province
        meta = cand.get("metadata", {})
        c_court = str(cand.get("court_name") or cand.get("court") or meta.get("court_name") or "")
        c_cit = str(cand.get("neutral_citation") or cand.get("citation") or "")
        c_preview = str(cand.get("preview") or meta.get("full_text") or "")[:400]
        court_res = resolve_court_and_province(c_cit, c_court, c_preview)
        cand_court = str(court_res.get("canonical_court_name") or court_res.get("court_name") or c_court or "")
        cand_prov = str(court_res.get("province") or "Federal")

        # Sanitize metadata with authoritative canonical court name
        cand["court"] = cand_court
        cand["court_name"] = cand_court
        cand["canonical_court_name"] = cand_court
        if "metadata" in cand and isinstance(cand["metadata"], dict):
            cand["metadata"]["court_name"] = cand_court
            cand["metadata"]["court"] = cand_court
            cand["metadata"]["canonical_court_name"] = cand_court

        weight_mult = 1.0
        # Article 189: Supreme Court is apex binding
        if "supreme court" in cand_court.lower():
            weight_mult = 1.25
        elif binding_courts and any(bc in cand_court.lower() for bc in binding_courts):
            weight_mult = 1.15
        elif target_province in ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"]:
            # Cross-provincial leakage penalty if non-binding sister High Court
            if cand_prov in ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"] and cand_prov != target_province:
                weight_mult = 0.65

        final_score = base_score * weight_mult
        cand["rrf_score"] = round(final_score, 6)
        cand["score"] = round(final_score, 6)
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
    Executes parallel per-issue retrieval across Supabase, Pinecone, BM25, and optional External search.
    Returns:
        merged_candidates: Unified RRF-ranked candidate list
        engine_counts: Dict with {count_supabase, count_pinecone, count_bm25, count_external}
    """
    if query_plan is None:
        from core.legal_query_planner import create_deterministic_fallback_plan
        query_plan = create_deterministic_fallback_plan(query_text)

    # 1. Build prioritized search terms for Supabase exact & keyword search
    search_terms: List[str] = []

    # Priority 1: Landmark authorities from detected doctrinal topics
    from legal_ai.verification.doctrinal_rules import detect_topics, TOPICS_SPEC
    detected = detect_topics(query_text)
    for t in detected:
        if t in TOPICS_SPEC:
            for la in TOPICS_SPEC[t].get("landmark_authorities", []):
                if la not in search_terms:
                    search_terms.append(la)

    # Priority 2: Canonical statutory provisions from query plan
    provisions = getattr(query_plan, "provisions", []) if hasattr(query_plan, "provisions") else []
    for p in provisions:
        p_str = str(p).strip()
        if p_str and p_str not in search_terms:
            search_terms.append(p_str)

    # Priority 3: Doctrinal issue queries and search lanes
    lanes = getattr(query_plan, "search_lanes", []) if hasattr(query_plan, "search_lanes") else []
    issues = getattr(query_plan, "issues", []) if hasattr(query_plan, "issues") else (getattr(query_plan, "legal_questions", []) if hasattr(query_plan, "legal_questions") else [])
    for lane in lanes:
        if isinstance(lane, dict) and lane.get("query"):
            lq = str(lane["query"]).strip()
            if lq and lq not in search_terms:
                search_terms.append(lq)

    for t in detected:
        if t in TOPICS_SPEC:
            for eq in TOPICS_SPEC[t].get("extra_queries", [])[:2]:
                if eq not in search_terms:
                    search_terms.append(eq)

    # Priority 4: Raw user query
    if query_text not in search_terms:
        search_terms.append(query_text)

    # 2. Build multi-lane queries for Pinecone dense semantic search
    dense_queries = [query_text]
    if lanes:
        for l in lanes[:5]:
            if isinstance(l, dict) and l.get("query"):
                q_str = str(l["query"]).strip()
                if q_str and q_str not in dense_queries:
                    dense_queries.append(q_str)
    elif issues:
        for iss in issues[:3]:
            iss_str = str(iss).strip()
            if iss_str and iss_str not in dense_queries:
                dense_queries.append(iss_str)

    # 3. Build multi-query for BM25 sparse search across all search lanes
    bm_queries = [query_text]
    if lanes:
        for l in lanes[:5]:
            if isinstance(l, dict) and l.get("query"):
                q_str = str(l["query"]).strip()
                if q_str and q_str not in bm_queries:
                    bm_queries.append(q_str)
    elif issues:
        for iss in issues[:3]:
            iss_str = str(iss).strip()
            if iss_str and iss_str not in bm_queries:
                bm_queries.append(iss_str)

    def _execute_multi_bm25():
        bm_results: List[Dict[str, Any]] = []
        seen_bm = set()
        for bq in bm_queries:
            sub_res = search_bm25_sparse(bq, top_k=top_k_per_engine)
            for c in sub_res:
                cid = str(c.get("case_id") or c.get("id") or "")
                if cid not in seen_bm:
                    seen_bm.add(cid)
                    bm_results.append(c)
        return bm_results

    # 4. Fire concurrent search tasks
    supabase_task = asyncio.create_task(search_supabase_judgments(search_terms, limit_per_term=15))

    async def _execute_multi_pinecone():
        pc_tasks = [
            search_pinecone_dense(dq, top_k=top_k_per_engine, min_similarity=0.30)
            for dq in dense_queries
        ]
        pc_lists = await asyncio.gather(*pc_tasks)
        pc_results: List[Dict[str, Any]] = []
        seen_pc = set()
        for plist in pc_lists:
            for c in plist:
                cid = str(c.get("case_id") or c.get("id") or "")
                if cid not in seen_pc:
                    seen_pc.add(cid)
                    pc_results.append(c)
        return pc_results

    pinecone_task = asyncio.create_task(_execute_multi_pinecone())
    bm25_task = asyncio.create_task(asyncio.to_thread(_execute_multi_bm25))

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

    merged = merge_candidates_with_rrf(engine_results, query_plan=query_plan)
    return merged, engine_counts
