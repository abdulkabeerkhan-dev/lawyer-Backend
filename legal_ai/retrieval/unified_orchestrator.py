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
from core.provider_ledger import (
    ProviderHealthLedger,
    ProviderStatus,
    record_provider_event,
    retrieval_lane_scope,
)
from legal_ai.retrieval.supabase_search import search_supabase_judgments
from legal_ai.retrieval.pinecone_search import search_pinecone_dense
from legal_ai.retrieval.bm25_search import search_bm25_sparse
from legal_ai.retrieval.external_search import search_external_judgments
from legal_ai.ranking.court_weighting import resolve_court_and_province
from core.authority_ranking import is_irrelevant_subject


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

            base_engine = engine_name.split("_")[0]
            if norm_cid not in merged_map:
                merged_map[norm_cid] = dict(c)
                merged_map[norm_cid]["retrieval_engines"] = [base_engine]
                merged_map[norm_cid]["retrieval_lanes"] = [engine_name]
                merged_map[norm_cid]["lane_ranks"] = {engine_name: rank + 1}
                rrf_scores[norm_cid] = 0.0
            else:
                existing = merged_map[norm_cid]
                if "source_issue_id" in c and "source_issue_id" not in existing:
                    existing["source_issue_id"] = c["source_issue_id"]
                    existing["source_lane_query"] = c.get("source_lane_query")
                if base_engine not in existing.get("retrieval_engines", []):
                    existing.setdefault("retrieval_engines", []).append(base_engine)
                if engine_name not in existing.get("retrieval_lanes", []):
                    existing.setdefault("retrieval_lanes", []).append(engine_name)
                existing.setdefault("lane_ranks", {})[engine_name] = rank + 1

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
        # Article 189: Supreme Court is apex binding precedent across Pakistan (1.35x)
        if "supreme court" in cand_court.lower() or "scmr" in c_cit.lower() or "pld sc" in c_cit.lower():
            weight_mult = 1.35
        elif binding_courts and any(bc in cand_court.lower() for bc in binding_courts):
            weight_mult = 1.15
        elif "high court" in cand_court.lower():
            # Article 201: High Court binding precedent within provincial jurisdiction (1.10x)
            weight_mult = 1.10
            if target_province in ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"]:
                # Cross-provincial leakage penalty if non-binding sister High Court
                if cand_prov in ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"] and cand_prov != target_province:
                    weight_mult = 0.65
        elif any(tk in cand_court.lower() for tk in ["tribunal", "fto", "ombudsman"]):
            weight_mult = 0.95

        final_score = base_score * weight_mult
        cand["court_weight"] = weight_mult
        cand["recency_weight"] = 1.0
        cand["rrf_score"] = round(final_score, 6)
        cand["score"] = round(final_score, 6)
        cand["final_rank_score"] = round(final_score, 6)
        final_list.append(cand)

    final_list.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    if query_plan:
        filtered_list = [c for c in final_list if not is_irrelevant_subject(c, query_plan)]
        return filtered_list
    return final_list


def anchor_provision_token(token: str, query_plan: Any = None) -> Optional[str]:
    """
    Anchors provision numbers to their parent statute name before use as a search token.
    Never returns bare section numbers (e.g. '138', 'Section 138').
    """
    t = str(token or "").strip()
    if not t or len(t) < 3:
        return None

    # Disallow bare digits (e.g. "138", "420")
    if t.isdigit():
        return None

    # If already anchored with parent statute, keep it
    if re.search(r'\b(ppc|crpc|cpc|qso|sra|prpa|srpo|limitation|constitution|penal|contract|negotiable|instruments|family)\b', t, re.I):
        return t

    # If bare "Section X" without statute:
    m_bare = re.match(r'^(?:sections?|secs?\.?|s\.)\s*([0-9]+(?:-[a-z])?)$', t, re.IGNORECASE)
    if m_bare:
        num = m_bare.group(1).upper()
        gov = getattr(query_plan, "governing_statutes", []) if query_plan else []
        if gov:
            return f"Section {num} {gov[0]}"
        # Infer parent statute from known numbers
        clean_d = re.sub(r'[^0-9]', '', num)
        val = int(clean_d) if clean_d else 0
        if val in [409, 420, 406, 489, 302, 376, 380, 468, 471]:
            return f"Section {num} Pakistan Penal Code, 1860"
        elif val in [497, 498, 561, 154, 161, 164, 173]:
            return f"Section {num} Code of Criminal Procedure, 1898"
        elif val in [115, 12, 151, 96, 100]:
            return f"Section {num} Code of Civil Procedure, 1908"
        elif val in [118, 138, 4, 13]:
            return f"Section {num} Negotiable Instruments Act, 1881"
        elif val in [28, 5, 14, 19]:
            return f"Section {num} Limitation Act, 1908"
        elif val in [9, 42, 8, 39, 54]:
            return f"Section {num} Specific Relief Act, 1877"
        return None

    return t


def collapse_chunks_per_case(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Spec Phase 4: Collapses multiple vector/search chunks of the same case into a single entry
    preserving the highest similarity score, richest text, and metadata before ranking.
    """
    if not candidates:
        return []
    seen_map: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        raw_cid = str(c.get("case_id") or meta.get("case_id") or c.get("id") or "").strip()
        if not raw_cid:
            continue
        norm_cid = re.sub(r'[\s_\-]+', '_', raw_cid).lower()
        norm_cid = re.sub(r'(_chk_\d+|_chunk_\d+|#c\d+)$', '', norm_cid, flags=re.IGNORECASE).strip()

        if norm_cid not in seen_map:
            seen_map[norm_cid] = dict(c)
        else:
            existing = seen_map[norm_cid]
            if "source_issue_id" in c and "source_issue_id" not in existing:
                existing["source_issue_id"] = c["source_issue_id"]
                existing["source_lane_query"] = c.get("source_lane_query")
            existing = seen_map[norm_cid]
            score_new = float(c.get("score") or c.get("similarity") or c.get("dense_score") or 0.0)
            score_old = float(existing.get("score") or existing.get("similarity") or existing.get("dense_score") or 0.0)
            if score_new > score_old:
                existing["score"] = score_new
                existing["similarity"] = score_new
                if "dense_score" in c:
                    existing["dense_score"] = c["dense_score"]
            if "metadata" not in existing or not isinstance(existing.get("metadata"), dict):
                existing["metadata"] = {}
            existing_meta = existing["metadata"]
            new_meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
            new_text_len = len(str(new_meta.get("full_text") or new_meta.get("text") or c.get("text") or c.get("preview") or ""))
            old_text_len = len(str(existing_meta.get("full_text") or existing_meta.get("text") or existing.get("text") or existing.get("preview") or ""))
            if new_text_len > old_text_len:
                if "preview" in c:
                    existing["preview"] = c["preview"]
                if "text" in c:
                    existing["text"] = c["text"]
                if new_meta:
                    existing["metadata"].update(new_meta)

    collapsed = list(seen_map.values())
    collapsed.sort(key=lambda x: float(x.get("score") or x.get("similarity") or 0.0), reverse=True)
    return collapsed


async def retrieve_candidates_parallel(
    query_text: str,
    query_plan: Any = None,
    include_external: bool = False,
    top_k_per_engine: int = 40
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Executes Phase 2 Multi-Lane Hybrid Retrieval across 5 distinct legal intent lanes:
    1. Dense Conceptual: Pinecone dense vector semantic retrieval (voyage-law-2)
    2. Sparse Lexical: Local inverted BM25 keyword matching for exact terms & citations
    3. Procedural: Targeted dual dense + sparse retrieval on relief, forum, limitation, maintainability
    4. Doctrinal: Targeted dual dense + sparse retrieval on substantive judicial ratios & legal tests
    5. Statutory: Exact statutory ID matching and provision-anchored precedent retrieval

    Candidates are fused via Reciprocal Rank Fusion (k=60), adjusted for Article 189/201 judicial authority
    and neutral recency, collapsed per case, and passed to downstream cross-encoder reranking.
    """
    import logging
    logger = logging.getLogger(__name__)
    provider_ledger = ProviderHealthLedger()
    provider_ledger.record(
        lane="turso_fts",
        provider="Turso",
        status=ProviderStatus.DISABLED,
        message="Turso FTS is not invoked by this query-retrieval path.",
    )

    if query_plan is None:
        from core.legal_query_planner import create_deterministic_fallback_plan
        query_plan = create_deterministic_fallback_plan(query_text)

    # 1. Deconstruct query plan into the 5 dimensional intent lanes
    multi_lane = getattr(query_plan, "multi_lane_queries", None)

    dense_conceptual_query = (
        getattr(multi_lane, "dense_conceptual_query", None)
        or getattr(query_plan, "primary_issue", None)
        or query_text
    )
    sparse_lexical_query = (
        getattr(multi_lane, "sparse_lexical_query", None)
        or query_text
    )
    procedural_query = (
        getattr(multi_lane, "procedural_query", None)
        or query_text
    )
    doctrinal_query = (
        getattr(multi_lane, "doctrinal_query", None)
        or getattr(query_plan, "primary_issue", None)
        or query_text
    )
    statutory_provisions = (
        getattr(multi_lane, "statutory_provisions", None)
        or getattr(query_plan, "statutory_provisions", None)
        or getattr(query_plan, "governing_statutes", None)
        or []
    )

    # 2. Build prioritized search terms for exact statute & keyword matching
    search_terms: List[str] = []
    from legal_ai.verification.doctrinal_rules import detect_topics, TOPICS_SPEC
    detected = detect_topics(query_text)
    for t in detected:
        if t in TOPICS_SPEC:
            for la in TOPICS_SPEC[t].get("landmark_authorities", []):
                if la not in search_terms:
                    search_terms.append(la)

    for p in statutory_provisions:
        anchored = anchor_provision_token(str(p), query_plan=query_plan)
        if anchored and anchored not in search_terms:
            search_terms.append(anchored)

    lanes = getattr(query_plan, "search_lanes", []) if hasattr(query_plan, "search_lanes") else []
    for lane in lanes:
        lq = str(getattr(lane, "query", None) or (lane.get("query") if isinstance(lane, dict) else "") or "")
        if lq and lq not in search_terms:
            search_terms.append(lq)

    if query_text not in search_terms:
        search_terms.append(query_text)

    search_terms = [
        st for st in search_terms
        if not re.match(r'^(?:sections?|secs?\.?|s\.)?\s*\d+$', st.strip(), re.IGNORECASE)
    ]

    import os
    enable_supabase_fts = os.getenv("ENABLE_SUPABASE_FTS", "false").lower() in ("true", "1")

    # 3. Define concurrent lane executors with strict timeouts & circuit breakers

    # Lane 1: Dense Conceptual
    async def _lane_dense_conceptual() -> List[Dict[str, Any]]:
        try:
            raw = await asyncio.wait_for(
                search_pinecone_dense(
                    dense_conceptual_query,
                    top_k=top_k_per_engine,
                    min_similarity=0.30,
                    query_plan=query_plan
                ),
                timeout=12.0
            )
            for c in raw:
                c["source_lane"] = "dense_conceptual"
                c["source_issue_id"] = "dense_conceptual"
                c["source_lane_query"] = dense_conceptual_query
            return collapse_chunks_per_case(raw)
        except Exception as e:
            logger.warning(f"[Lane 1: Dense Conceptual] query error: {e}")
            return []

    # Lane 2: Sparse Lexical (BM25)
    def _lane_sparse_lexical() -> List[Dict[str, Any]]:
        try:
            raw = search_bm25_sparse(sparse_lexical_query, top_k=top_k_per_engine)
            record_provider_event(
                "BM25",
                ProviderStatus.SUCCESS if raw else ProviderStatus.EMPTY,
                result_count=len(raw),
            )
            for c in raw:
                c["source_lane"] = "sparse_lexical"
                c["source_issue_id"] = "sparse_lexical"
                c["source_lane_query"] = sparse_lexical_query
            return collapse_chunks_per_case(raw)
        except Exception as e:
            logger.warning(f"[Lane 2: Sparse Lexical] query error: {e}")
            return []

    # Lane 3: Procedural Retrieval (Targeted dense + sparse)
    async def _lane_procedural() -> List[Dict[str, Any]]:
        async def _pc_proc():
            try:
                return await asyncio.wait_for(
                    search_pinecone_dense(
                        procedural_query,
                        top_k=top_k_per_engine,
                        min_similarity=0.30,
                        query_plan=query_plan
                    ),
                    timeout=10.0
                )
            except Exception:
                return []

        def _bm_proc():
            try:
                hits = search_bm25_sparse(procedural_query, top_k=top_k_per_engine)
                record_provider_event(
                    "BM25",
                    ProviderStatus.SUCCESS if hits else ProviderStatus.EMPTY,
                    result_count=len(hits),
                )
                return hits
            except Exception:
                record_provider_event("BM25", ProviderStatus.ERROR, message="Procedural BM25 search failed.")
                return []

        pc_hits, bm_hits = await asyncio.gather(
            _pc_proc(),
            asyncio.to_thread(_bm_proc)
        )
        combined = []
        for c in pc_hits:
            c["source_lane"] = "procedural"
            c["source_issue_id"] = "procedural_dense"
            c["source_lane_query"] = procedural_query
            combined.append(c)
        for c in bm_hits:
            c["source_lane"] = "procedural"
            c["source_issue_id"] = "procedural_sparse"
            c["source_lane_query"] = procedural_query
            combined.append(c)
        return collapse_chunks_per_case(combined)

    # Lane 4: Doctrinal Retrieval (Targeted dense + sparse)
    async def _lane_doctrinal() -> List[Dict[str, Any]]:
        async def _pc_doc():
            try:
                return await asyncio.wait_for(
                    search_pinecone_dense(
                        doctrinal_query,
                        top_k=top_k_per_engine,
                        min_similarity=0.30,
                        query_plan=query_plan
                    ),
                    timeout=10.0
                )
            except Exception:
                return []

        def _bm_doc():
            try:
                hits = search_bm25_sparse(doctrinal_query, top_k=top_k_per_engine)
                record_provider_event(
                    "BM25",
                    ProviderStatus.SUCCESS if hits else ProviderStatus.EMPTY,
                    result_count=len(hits),
                )
                return hits
            except Exception:
                record_provider_event("BM25", ProviderStatus.ERROR, message="Doctrinal BM25 search failed.")
                return []

        pc_hits, bm_hits = await asyncio.gather(
            _pc_doc(),
            asyncio.to_thread(_bm_doc)
        )
        combined = []
        for c in pc_hits:
            c["source_lane"] = "doctrinal"
            c["source_issue_id"] = "doctrinal_dense"
            c["source_lane_query"] = doctrinal_query
            combined.append(c)
        for c in bm_hits:
            c["source_lane"] = "doctrinal"
            c["source_issue_id"] = "doctrinal_sparse"
            c["source_lane_query"] = doctrinal_query
            combined.append(c)
        return collapse_chunks_per_case(combined)

    # Lane 5: Statutory Retrieval (Exact statutory tokens & precedents)
    def _lane_statutory() -> List[Dict[str, Any]]:
        statute_queries = []
        for p in statutory_provisions:
            anchored = anchor_provision_token(str(p), query_plan=query_plan)
            if anchored and anchored not in statute_queries:
                statute_queries.append(anchored)
        if not statute_queries:
            statute_queries = [str(p) for p in statutory_provisions if str(p)] or [sparse_lexical_query]

        statute_hits = []
        for sq in statute_queries[:4]:
            try:
                hits = search_bm25_sparse(sq, top_k=top_k_per_engine)
                record_provider_event(
                    "BM25",
                    ProviderStatus.SUCCESS if hits else ProviderStatus.EMPTY,
                    result_count=len(hits),
                )
                for h in hits:
                    h["source_lane"] = "statutory"
                    h["source_issue_id"] = "statutory"
                    h["source_lane_query"] = sq
                    statute_hits.append(h)
            except Exception as e:
                logger.warning(f"[Lane 5: Statutory] error querying '{sq}': {e}")
        return collapse_chunks_per_case(statute_hits)

    # Supplementary Tasks: Supabase FTS & External Judicial Search
    async def _guarded_supabase_search():
        if not enable_supabase_fts:
            record_provider_event("Supabase", ProviderStatus.DISABLED, message="Supabase FTS is disabled.")
            return []
        from legal_ai.config import is_supabase_circuit_open, trip_supabase_circuit
        if is_supabase_circuit_open():
            record_provider_event("Supabase", ProviderStatus.PROVIDER_DOWN, message="Supabase circuit breaker is open.")
            return []
        try:
            hits = await asyncio.wait_for(
                search_supabase_judgments(search_terms[:2], limit_per_term=5, query_plan=query_plan),
                timeout=5.0
            )
            if is_supabase_circuit_open():
                record_provider_event("Supabase", ProviderStatus.PROVIDER_DOWN, message="Supabase circuit breaker opened during retrieval.")
                return hits
            record_provider_event(
                "Supabase",
                ProviderStatus.SUCCESS if hits else ProviderStatus.EMPTY,
                result_count=len(hits),
            )
            return hits
        except asyncio.TimeoutError:
            record_provider_event("Supabase", ProviderStatus.TIMEOUT, message="Supabase FTS exceeded 5 seconds.")
            trip_supabase_circuit(60.0, "Supabase search timeout in orchestrator")
            return []
        except Exception as sb_err:
            trip_supabase_circuit(60.0, f"Supabase search timeout in orchestrator: {sb_err}")
            record_provider_event("Supabase", ProviderStatus.PROVIDER_DOWN, message=str(sb_err))
            return []

    async def _guarded_external_search() -> List[Dict[str, Any]]:
        try:
            hits = await asyncio.wait_for(search_external_judgments(query_text, max_results=5), timeout=5.0)
            if not any(event.provider == "External" for event in provider_ledger.events):
                record_provider_event("External", ProviderStatus.SUCCESS if hits else ProviderStatus.EMPTY, result_count=len(hits))
            return hits
        except asyncio.TimeoutError:
            record_provider_event("External", ProviderStatus.TIMEOUT, message="External search exceeded 5 seconds.")
            logger.warning("[ExternalSearch] Search exceeded the 5-second orchestrator limit.")
            return []
        except Exception as ext_err:
            logger.warning(f"External search timed out/failed: {ext_err}")
            record_provider_event("External", ProviderStatus.ERROR, message=str(ext_err))
            return []

    async def _run_lane(lane_name: str, lane_fn: Any) -> List[Dict[str, Any]]:
        with retrieval_lane_scope(provider_ledger, lane_name):
            try:
                if asyncio.iscoroutinefunction(lane_fn):
                    results = await lane_fn()
                else:
                    results = await asyncio.to_thread(lane_fn)
                normalized = results if isinstance(results, list) else []
                record_provider_event(
                    "lane",
                    ProviderStatus.SUCCESS if normalized else ProviderStatus.EMPTY,
                    result_count=len(normalized),
                )
                return normalized
            except asyncio.TimeoutError:
                record_provider_event("lane", ProviderStatus.TIMEOUT, message="Retrieval lane timed out.")
                logger.warning("[RetrievalLane:%s] timed out.", lane_name)
                return []
            except Exception as lane_err:
                record_provider_event("lane", ProviderStatus.ERROR, message=str(lane_err))
                logger.exception("[RetrievalLane:%s] failed.", lane_name)
                return []

    # 4. Fire all 5 lanes + supplementary tasks concurrently
    l1_task = asyncio.create_task(_run_lane("dense_conceptual", _lane_dense_conceptual))
    l2_task = asyncio.create_task(_run_lane("sparse_lexical", _lane_sparse_lexical))
    l3_task = asyncio.create_task(_run_lane("procedural", _lane_procedural))
    l4_task = asyncio.create_task(_run_lane("doctrinal", _lane_doctrinal))
    l5_task = asyncio.create_task(_run_lane("statutory", _lane_statutory))
    sb_task = asyncio.create_task(_run_lane("supabase_fts", _guarded_supabase_search))

    if include_external:
        ext_task = asyncio.create_task(_run_lane("external", _guarded_external_search))
        l1_res, l2_res, l3_res, l4_res, l5_res, sb_res, ext_res = await asyncio.gather(
            l1_task, l2_task, l3_task, l4_task, l5_task, sb_task, ext_task
        )
    else:
        l1_res, l2_res, l3_res, l4_res, l5_res, sb_res = await asyncio.gather(
            l1_task, l2_task, l3_task, l4_task, l5_task, sb_task
        )
        ext_res = []

    # 5. Populate Multi-Lane Engine Results for Reciprocal Rank Fusion
    per_lane_engine_results: Dict[str, List[Dict[str, Any]]] = {
        "dense_conceptual": l1_res,
        "sparse_lexical": l2_res,
        "procedural": l3_res,
        "doctrinal": l4_res,
        "statutory": l5_res,
    }
    if sb_res:
        per_lane_engine_results["supabase_fts"] = collapse_chunks_per_case(sb_res)
    if ext_res:
        per_lane_engine_results["external_leads"] = collapse_chunks_per_case(ext_res)

    total_dense_cases = len(l1_res) + len([c for c in l3_res if "dense" in c.get("source_issue_id", "")]) + len([c for c in l4_res if "dense" in c.get("source_issue_id", "")])
    total_sparse_cases = len(l2_res) + len([c for c in l3_res if "sparse" in c.get("source_issue_id", "")]) + len([c for c in l4_res if "sparse" in c.get("source_issue_id", "")]) + len(l5_res)

    engine_counts = {
        "count_dense_conceptual": len(l1_res),
        "count_sparse_lexical": len(l2_res),
        "count_procedural": len(l3_res),
        "count_doctrinal": len(l4_res),
        "count_statutory": len(l5_res),
        "count_supabase": len(sb_res),
        "count_pinecone": total_dense_cases,
        "count_bm25": total_sparse_cases,
        "count_external": len(ext_res)
    }
    engine_counts["provider_health"] = provider_ledger.to_dict()

    # 6. Reciprocal Rank Fusion & Judicial Authority Weighting
    merged = merge_candidates_with_rrf(per_lane_engine_results, query_plan=query_plan, rrf_k=60)
    return merged, engine_counts
