"""
legal_ai/ranking/cross_encoder_reranker.py

Cross-Encoder Reranker for Pakistani Legal Case Law.
Phase 4, Step 5 Implementation:
- Uses Voyage AI rerank-2 API for high-precision cross-encoding of (query, document) pairs.
- Graceful degradation to deterministic legal heuristic ranker on API timeout or error.
- Fully isolated and gated behind feature flag ENABLE_CROSS_ENCODER_RERANKER (default: False).
- Preserves all candidate IDs, citations, metadata, provenance, and original retrieval scores.
- Never allows reranking failures to terminate the retrieval pipeline.
"""

import os
import sys
import re
import time
import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple, Union

import voyageai
from dotenv import load_dotenv

from core.legal_query_planner import StructuredLegalQueryPlan, LegalQueryPlan

load_dotenv()
logger = logging.getLogger(__name__)

# Feature flag: disabled by default in production
ENABLE_CROSS_ENCODER_RERANKER: bool = (
    os.getenv("ENABLE_CROSS_ENCODER_RERANKER", "false").lower() in ("true", "1", "yes")
)

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_RERANK_MODEL = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2")
MAX_CANDIDATE_TEXT_CHARS = 2000  # Truncate long documents to ~400-500 tokens for reranking efficiency


def _get_candidate_text_for_reranking(candidate: Dict[str, Any]) -> str:
    """Extracts and sanitizes candidate text for cross-encoder scoring."""
    title = str(candidate.get("title") or candidate.get("case_title") or "").strip()
    citation = str(candidate.get("citation") or candidate.get("neutral_citation") or "").strip()
    court = str(candidate.get("court") or candidate.get("court_name") or "").strip()

    body = str(
        candidate.get("text") or
        candidate.get("preview") or
        candidate.get("full_text") or
        ""
    ).strip()

    header_parts = []
    if citation:
        header_parts.append(f"Citation: {citation}")
    if title:
        header_parts.append(f"Title: {title}")
    if court:
        header_parts.append(f"Court: {court}")

    header = " | ".join(header_parts)
    full_str = f"{header}\n{body}".strip()
    
    if len(full_str) > MAX_CANDIDATE_TEXT_CHARS:
        return full_str[:MAX_CANDIDATE_TEXT_CHARS] + "..."
    return full_str or "Legal precedent on record."


def _heuristic_legal_cross_score(
    query_text: str,
    candidate: Dict[str, Any],
    query_plan: Optional[Any] = None
) -> float:
    """
    Deterministic fallback cross-scorer for Pakistani legal texts.
    Used when the API reranker is unavailable or times out.
    Combines:
    - Token overlap with legal keywords
    - Court hierarchy boost (Supreme Court > High Courts)
    - Statutory match boost
    """
    q_low = query_text.lower()
    text = _get_candidate_text_for_reranking(candidate).lower()
    meta = candidate.get("metadata") or {}

    # 1. Base lexical/semantic overlap score
    q_tokens = [w for w in re.sub(r'[^\w\s]', ' ', q_low).split() if len(w) >= 4]
    overlap_count = sum(1 for tok in q_tokens if tok in text)
    base_score = min(0.60, (overlap_count / len(q_tokens)) * 0.60) if q_tokens else 0.20

    # 2. Statutory match boost
    statute_boost = 0.0
    if query_plan:
        provisions = getattr(query_plan, "statutory_provisions", []) or getattr(query_plan, "provisions", [])
        for p in provisions:
            p_clean = str(p).lower().replace("_", " ")
            if p_clean in text:
                statute_boost = 0.25
                break

    # 3. Court hierarchy weighting
    court = str(candidate.get("court") or meta.get("court") or "").lower()
    court_boost = 0.0
    if "supreme court" in court or "apex court" in court:
        court_boost = 0.15
    elif "high court" in court:
        court_boost = 0.08

    final_score = min(0.99, base_score + statute_boost + court_boost)
    return round(final_score, 4)


async def rerank_candidates_cross_encoder(
    query_text: str,
    candidates: List[Dict[str, Any]],
    query_plan: Optional[Any] = None,
    top_k: int = 10,
    model: str = VOYAGE_RERANK_MODEL,
    timeout_seconds: float = 6.0
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Reranks a list of candidate legal judgments using a cross-encoder.
    
    Args:
        query_text: Original user query string.
        candidates: List of candidate records from dense, dual-mode, or RRF retrieval.
        query_plan: Optional structured legal query plan.
        top_k: Number of reranked candidates to return.
        model: Cross-encoder model identifier (defaults to 'rerank-2').
        timeout_seconds: Maximum time in seconds before falling back.
        
    Returns:
        (reranked_candidates, telemetry)
    """
    telemetry: Dict[str, Any] = {
        "model_used": "none",
        "input_count": len(candidates),
        "output_count": 0,
        "rerank_latency_s": 0.0,
        "fallback_triggered": False,
        "fallback_reason": None
    }

    if not candidates:
        return [], telemetry
    if not query_text:
        return candidates[:top_k], telemetry

    t0 = time.time()

    # Step 1: Build per-issue query map from decomposition and query plan
    issue_query_map: Dict[str, str] = {}
    try:
        from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern
        decomp = extract_legal_issues_from_fact_pattern(query_text)
        for issue in getattr(decomp, "issues", []):
            iq = f"{issue.heading}. {issue.description}"
            issue_query_map[issue.issue_id] = iq
    except Exception:
        pass

    if query_plan and hasattr(query_plan, "search_lanes"):
        for l in query_plan.search_lanes:
            lid = getattr(l, "lane_id", None) or (l.get("lane_id") if isinstance(l, dict) else "") or (l.get("lane") if isinstance(l, dict) else "")
            lq = getattr(l, "query", None) or (l.get("query") if isinstance(l, dict) else "")
            if lid and lq and lid not in issue_query_map:
                issue_query_map[lid] = lq

    def _resolve_candidate_query(cand: Dict[str, Any]) -> str:
        sid = cand.get("source_issue_id")
        if sid and sid in issue_query_map:
            return issue_query_map[sid]
        slq = cand.get("source_lane_query")
        if slq:
            return slq
        return query_text

    doc_texts = [_get_candidate_text_for_reranking(c) for c in candidates]

    # Step 2: Attempt Voyage AI Cross-Encoder Rerank (grouped by targeted issue query)
    voyage_api_key = VOYAGE_API_KEY
    can_use_voyage = bool(voyage_api_key and len(doc_texts) > 0)

    rerank_scores: Dict[int, float] = {}
    model_name = "fallback-heuristic"

    if can_use_voyage:
        try:
            client = voyageai.Client(api_key=voyage_api_key)

            # Group candidates by targeted candidate query
            query_to_indices: Dict[str, List[int]] = {}
            for idx, c in enumerate(candidates):
                cq = _resolve_candidate_query(c)
                query_to_indices.setdefault(cq, []).append(idx)

            def _sync_rerank_all():
                for cq, indices in query_to_indices.items():
                    sub_docs = [doc_texts[i] for i in indices]
                    res = client.rerank(
                        query=cq,
                        documents=sub_docs,
                        model=model,
                        top_k=min(len(sub_docs), max(top_k * 2, 20))
                    )
                    for item in getattr(res, "results", []):
                        sub_i = getattr(item, "index", None)
                        score = getattr(item, "relevance_score", 0.0)
                        if sub_i is not None and sub_i < len(indices):
                            orig_idx = indices[sub_i]
                            rerank_scores[orig_idx] = float(score)

            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, _sync_rerank_all),
                timeout=timeout_seconds
            )

            model_name = f"voyage-{model}"
            telemetry["model_used"] = model_name

        except asyncio.TimeoutError:
            telemetry["fallback_triggered"] = True
            telemetry["fallback_reason"] = f"Reranker timed out after {timeout_seconds}s"
            logger.warning(f"⚠️ [CrossEncoderReranker] Voyage rerank timed out after {timeout_seconds}s; falling back to heuristic scorer.")
        except Exception as e:
            telemetry["fallback_triggered"] = True
            telemetry["fallback_reason"] = f"Reranker error: {str(e)}"
            logger.warning(f"⚠️ [CrossEncoderReranker] Voyage rerank error ({e}); falling back to heuristic scorer.")
    else:
        telemetry["fallback_triggered"] = True
        telemetry["fallback_reason"] = "Voyage API key missing or unavailable"

    # Step 3: Fill missing scores with deterministic per-issue heuristic cross-scorer
    if not rerank_scores or telemetry["fallback_triggered"]:
        model_name = "fallback-heuristic"
        telemetry["model_used"] = model_name
        for idx, c in enumerate(candidates):
            cand_q = _resolve_candidate_query(c)
            rerank_scores[idx] = _heuristic_legal_cross_score(cand_q, c, query_plan)

    # Step 4: Construct decorated, reranked candidate list
    decorated_candidates: List[Dict[str, Any]] = []
    for idx, c in enumerate(candidates):
        c_copy = dict(c)
        r_score = rerank_scores.get(idx, 0.0)

        # Preserve original scores
        c_copy["original_score"] = c.get("score", 0.0)
        c_copy["dense_score"] = c.get("dense_score", c.get("score", 0.0))
        c_copy["sparse_score"] = c.get("sparse_score", 0.0)
        c_copy["rrf_score"] = c.get("rrf_score", 0.0)
        
        # Assign cross-encoder score
        c_copy["rerank_score"] = round(r_score, 4)
        c_copy["score"] = round(r_score, 4)  # Update primary score to rerank score
        c_copy["rerank_model"] = model_name
        c_copy["rerank_scorer"] = model_name
        c_copy["scorer"] = model_name

        decorated_candidates.append(c_copy)

    # Sort by rerank_score descending
    decorated_candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

    # Assign 1-based rerank_rank
    for r_idx, c in enumerate(decorated_candidates):
        c["rerank_rank"] = r_idx + 1

    final_results = decorated_candidates[:top_k]

    telemetry["rerank_latency_s"] = round(time.time() - t0, 3)
    telemetry["output_count"] = len(final_results)

    return final_results, telemetry
