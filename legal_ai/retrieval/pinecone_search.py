"""
legal_ai/retrieval/pinecone_search.py

Dual-Mode Dense Semantic Vector Search Driver for Pakistani Court Judgments.
Leverages Voyage AI (voyage-law-2) 1024-dimension embeddings and Pinecone vector store.

Phase 4, Step 4 Implementation:
- Dual-Mode Retrieval Architecture:
  * Lane A (Enriched): Metadata-filtered search on v1.0 enriched vectors using query planner allowed domains.
  * Lane B (Legacy): Unfiltered semantic search across the 401,351 legacy vectors with post-retrieval
    deterministic classification and universal domain quarantine.
- Controlled Candidate Merging & Deduplication:
  * Resolves candidates across both lanes, deduplicating by canonical document/vector identifiers.
  * Preserves provenance ('Lane_A_Enriched' vs 'Lane_B_Legacy') and classification confidence.
  * Guarantees zero candidate budget reduction for legacy vectors.
- Production Isolation:
  * Controlled by feature flag ENABLE_DUAL_MODE_PINECONE_SEARCH (default: False).
  * 100% backward-compatible fallback to original search_pinecone_dense.
"""

import os
import sys
import re
import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple, Set, Union

from legal_ai.config import get_pinecone_index, PINECONE_NAMESPACE, get_voyage_embedding
from legal_ai.ranking.court_weighting import normalize_court_name
from core.metadata_enrichment import (
    classify_legal_text,
    canonicalize_domain_name,
    normalize_legacy_vector_metadata,
    is_enriched_vector,
    ALL_LEGAL_DOMAINS
)
from core.legal_query_planner import (
    create_deterministic_fallback_plan,
    StructuredLegalQueryPlan,
    LegalQueryPlan
)
from core.authority_ranking import is_irrelevant_subject

logger = logging.getLogger(__name__)

# Feature flag: disabled by default in production until explicit rollout
ENABLE_DUAL_MODE_PINECONE_SEARCH: bool = (
    os.getenv("ENABLE_DUAL_MODE_PINECONE_SEARCH", "false").lower() in ("true", "1", "yes")
)


def _format_pinecone_match(
    m: Any,
    min_similarity: float = 0.40
) -> Optional[Dict[str, Any]]:
    """
    Standardizes a raw Pinecone query match into a canonical Candidate Record.
    """
    m_dict = dict(m) if isinstance(m, dict) else {
        "id": getattr(m, "id", ""),
        "score": getattr(m, "score", 0.0),
        "metadata": getattr(m, "metadata", {})
    }
    score = float(m_dict.get("score", 0.0))
    if score < min_similarity:
        return None

    meta = m_dict.get("metadata") or {}
    cid = str(meta.get("case_id") or meta.get("id") or m_dict.get("id", "")).strip()
    text = str(meta.get("text") or meta.get("full_text") or meta.get("text_preview") or "").strip()
    title = str(meta.get("title") or meta.get("case_title") or "").strip()
    if not title or title.lower() in ("precedent on record", "reported precedent", "none", "unknown"):
        m_br = re.search(r'\[[^|\]]+\|\s*([^\]]+)\]', text)
        if m_br:
            title = m_br.group(1).strip()
        else:
            m_vs = re.search(r'([A-Z0-9\s,\.\(\)/\-\'&]+?\s+(?:VS|V\.|VERSUS)\s+[A-Z0-9\s,\.\(\)/\-\'&]+)', text)
            title = m_vs.group(1).strip() if m_vs else "Precedent on Record"
    cit = str(meta.get("citation") or meta.get("neutral_citation") or cid).strip()
    raw_court = str(meta.get("court") or meta.get("court_name") or "Supreme Court of Pakistan").strip()
    court = normalize_court_name(raw_court)
    content_type = str(meta.get("content_type") or "full_text").lower()

    # Extract year
    year = meta.get("year")
    if not year:
        m_year = re.search(r'\b(19\d{2}|20\d{2})\b', f"{cit} {title}")
        year = int(m_year.group(1)) if m_year else 2020
    else:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = 2020

    return {
        "id": cid,
        "score": score,
        "dense_score": score,
        "sparse_score": 0.0,
        "rrf_score": 0.0,
        "source_type": "Pinecone",
        "citation": cit,
        "title": title,
        "case_name": title,
        "court": court,
        "year": year,
        "content_type": content_type,
        "preview": text[:400],
        "text": text,
        "metadata": meta
    }


async def execute_pinecone_query_safe(
    index: Any,
    query_vector: List[float],
    namespace: str,
    top_k: int,
    filter_dict: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 10.0
) -> List[Any]:
    """
    Executes a Pinecone query safely with timeout catching and non-blocking degradation.
    """
    try:
        def _sync_query():
            if filter_dict:
                return index.query(
                    namespace=namespace,
                    vector=query_vector,
                    top_k=top_k,
                    filter=filter_dict,
                    include_metadata=True
                )
            else:
                return index.query(
                    namespace=namespace,
                    vector=query_vector,
                    top_k=top_k,
                    include_metadata=True
                )

        loop = asyncio.get_running_loop()
        res = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_query),
            timeout=timeout_seconds
        )
        return res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ [PineconeSearch] Query timed out after {timeout_seconds}s (filter={filter_dict is not None})")
        return []
    except Exception as err:
        logger.warning(f"⚠️ [PineconeSearch] Query error: {err} (filter={filter_dict is not None})")
        return []


async def search_pinecone_dual_mode(
    query_text: str,
    query_plan: Optional[Union[StructuredLegalQueryPlan, LegalQueryPlan, Dict[str, Any]]] = None,
    top_k: int = 40,
    min_similarity: float = 0.40,
    enable_lane_a: bool = True,
    enable_lane_b: bool = True,
    timeout_seconds: float = 10.0
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Dual-Mode Dense Vector Search Driver for Pakistani Legal Corpus.
    
    Lane A: Enriched Vector Retrieval (Server-side metadata filter on v1.0 vectors)
    Lane B: Legacy Vector Retrieval (Unfiltered semantic search on 401,351 legacy vectors + post-retrieval quarantine)
    
    Returns:
        (merged_candidates, execution_telemetry)
    """
    telemetry: Dict[str, Any] = {
        "lane_a_enabled": enable_lane_a,
        "lane_b_enabled": enable_lane_b,
        "lane_a_raw_count": 0,
        "lane_b_raw_count": 0,
        "lane_b_quarantined_count": 0,
        "merged_count": 0,
        "allowed_domains": [],
        "is_cross_domain_relevant": False
    }

    index = get_pinecone_index()
    if not index or not query_text:
        return [], telemetry

    # 1. Resolve structured query plan for domain boundaries
    if query_plan is None:
        resolved_plan = create_deterministic_fallback_plan(query_text)
    elif isinstance(query_plan, dict):
        try:
            resolved_plan = StructuredLegalQueryPlan(**query_plan)
        except Exception:
            resolved_plan = create_deterministic_fallback_plan(query_text)
    else:
        resolved_plan = query_plan

    # Extract allowed domains
    raw_allowed = getattr(resolved_plan, "allowed_domains_filter", []) or [getattr(resolved_plan, "primary_domain", "civil")]
    if not raw_allowed and hasattr(resolved_plan, "domains"):
        raw_allowed = getattr(resolved_plan, "domains") or ["civil"]
    
    canonical_allowed = list(set([canonicalize_domain_name(str(d)) for d in raw_allowed]))
    if "general_legal" not in canonical_allowed:
        canonical_allowed.append("general_legal")

    is_cross_domain = bool(getattr(resolved_plan, "is_cross_domain_relevant", False))
    telemetry["allowed_domains"] = canonical_allowed
    telemetry["is_cross_domain_relevant"] = is_cross_domain

    # 2. Compute query dense embedding via Voyage AI (voyage-law-2)
    try:
        query_vector = await get_voyage_embedding(query_text)
    except Exception as emb_err:
        print(f"⚠️ [PineconeDualMode] Voyage embedding error: {emb_err}", file=sys.stderr)
        return [], telemetry

    lane_a_candidates: List[Dict[str, Any]] = []
    lane_b_candidates: List[Dict[str, Any]] = []

    # --------------------------------------------------------------------------
    # 3. Lane A: Enriched Vector Retrieval (Server-side Filter)
    # --------------------------------------------------------------------------
    if enable_lane_a:
        lane_a_filter = {
            "metadata_schema_version": {"$eq": "1.0"},
            "legal_domain": {"$in": canonical_allowed}
        }
        raw_matches_a = await execute_pinecone_query_safe(
            index=index,
            query_vector=query_vector,
            namespace=PINECONE_NAMESPACE,
            top_k=top_k,
            filter_dict=lane_a_filter,
            timeout_seconds=timeout_seconds
        )
        telemetry["lane_a_raw_count"] = len(raw_matches_a)

        for m in raw_matches_a:
            cand = _format_pinecone_match(m, min_similarity=min_similarity)
            if not cand:
                continue
            meta = cand.get("metadata") or {}
            cand["lane_source"] = "Lane_A_Enriched"
            cand["is_enriched"] = True
            cand["legal_domain"] = meta.get("legal_domain", "general_legal")
            cand["subdomain"] = meta.get("subdomain", "unspecified")
            cand["statutory_provisions"] = meta.get("statutory_provisions", [])
            cand["classification_confidence"] = float(meta.get("classification_confidence", 0.90))
            cand["classification_source"] = meta.get("classification_source", "statutory_explicit")
            cand["is_quarantined"] = False
            lane_a_candidates.append(cand)

    # --------------------------------------------------------------------------
    # 4. Lane B: Legacy Vector Retrieval (Unfiltered + Post-Retrieval Quarantine)
    # --------------------------------------------------------------------------
    if enable_lane_b:
        raw_matches_b = await execute_pinecone_query_safe(
            index=index,
            query_vector=query_vector,
            namespace=PINECONE_NAMESPACE,
            top_k=top_k,
            filter_dict=None,  # Unfiltered: guarantees legacy vectors are never excluded by Pinecone
            timeout_seconds=timeout_seconds
        )
        telemetry["lane_b_raw_count"] = len(raw_matches_b)

        quarantined_count = 0
        for m in raw_matches_b:
            cand = _format_pinecone_match(m, min_similarity=min_similarity)
            if not cand:
                continue

            meta = cand.get("metadata") or {}
            # Normalize legacy format
            norm_meta = normalize_legacy_vector_metadata(meta)
            cand["metadata"] = norm_meta
            cand["lane_source"] = "Lane_B_Legacy"
            cand["is_enriched"] = is_enriched_vector(meta)

            # Deterministic Post-Retrieval Classification on candidate text
            chunk_text = cand.get("text") or cand.get("preview") or ""
            c_domain, c_subdomain, c_provisions, c_conf, c_src = classify_legal_text(
                text=chunk_text,
                title=cand.get("title", ""),
                citation=cand.get("citation", ""),
                court=cand.get("court", "")
            )
            cand["legal_domain"] = c_domain
            cand["subdomain"] = c_subdomain
            cand["statutory_provisions"] = c_provisions
            cand["classification_confidence"] = c_conf
            cand["classification_source"] = c_src

            # Universal Domain Quarantine Check
            # Check 1: Does authority_ranking.is_irrelevant_subject flag this candidate?
            is_irrelevant_legacy = is_irrelevant_subject(cand, resolved_plan)

            # Check 2: Confident cross-domain conflict without cross-domain justification
            is_confidently_conflicted = False
            if not is_cross_domain and c_conf >= 0.70 and c_domain != "general_legal":
                if c_domain not in canonical_allowed:
                    is_confidently_conflicted = True

            if is_irrelevant_legacy or is_confidently_conflicted:
                cand["is_quarantined"] = True
                cand["quarantine_reason"] = (
                    f"Irrelevant cross-domain: query allows {canonical_allowed}, "
                    f"candidate classified as {c_domain} ({c_src}, conf={c_conf})"
                )
                cand["score"] = 0.0
                cand["dense_score"] = 0.0
                quarantined_count += 1
            else:
                cand["is_quarantined"] = False

            lane_b_candidates.append(cand)

        telemetry["lane_b_quarantined_count"] = quarantined_count

    # --------------------------------------------------------------------------
    # 5. Controlled Merging, Deduplication & Preservation
    # --------------------------------------------------------------------------
    merged_candidates: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    # Step A: Add Lane A (Enriched) valid candidates first
    for cand in lane_a_candidates:
        cid = cand.get("id") or cand.get("citation")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_candidates.append(cand)

    # Step B: Add Lane B (Legacy) non-quarantined candidates
    for cand in lane_b_candidates:
        if cand.get("is_quarantined", False):
            continue
        cid = cand.get("id") or cand.get("citation")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            merged_candidates.append(cand)

    # Sort merged results by dense score descending
    merged_candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    telemetry["merged_count"] = len(merged_candidates)

    return merged_candidates, telemetry


async def search_pinecone_dense(
    query_text: str,
    top_k: int = 40,
    min_similarity: float = 0.40,
    query_plan: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Dense Semantic Vector Search driver for Pakistani Court Judgments.
    
    If ENABLE_DUAL_MODE_PINECONE_SEARCH is True:
        Executes search_pinecone_dual_mode with Lane A (metadata filter) + Lane B (legacy quarantine).
    Otherwise (Default Production Path):
        Executes unfiltered legacy semantic vector search to ensure zero regression.
    """
    if ENABLE_DUAL_MODE_PINECONE_SEARCH:
        candidates, _ = await search_pinecone_dual_mode(
            query_text=query_text,
            query_plan=query_plan,
            top_k=top_k,
            min_similarity=min_similarity
        )
        return candidates

    # Default Legacy Production Search (Identical to original implementation)
    index = get_pinecone_index()
    if not index or not query_text:
        return []

    try:
        query_vector = await get_voyage_embedding(query_text)
    except Exception as emb_err:
        print(f"⚠️ [PineconeSearch] Voyage embedding error: {emb_err}", file=sys.stderr)
        return []

    try:
        res = index.query(
            namespace=PINECONE_NAMESPACE,
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
    except Exception as q_err:
        print(f"⚠️ [PineconeSearch] Pinecone query error: {q_err}", file=sys.stderr)
        return []

    candidates: List[Dict[str, Any]] = []
    matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])

    for m in matches:
        cand = _format_pinecone_match(m, min_similarity=min_similarity)
        if cand:
            candidates.append(cand)

    return candidates
