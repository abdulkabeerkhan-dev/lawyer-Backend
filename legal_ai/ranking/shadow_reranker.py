"""
legal_ai/ranking/shadow_reranker.py

Shadow Evaluation and Cross-Encoder Candidate Reranker.
Integrates Voyage AI rerank-2 and deterministic legal heuristics for evaluating
candidate relevance, ranking legal precedents, and computing issue abstention flags.
"""

import os
import sys
import re
import time
import logging
from typing import Dict, List, Any, Optional, Tuple

import voyageai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_RERANK_MODEL = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2")
MAX_CANDIDATE_TEXT_CHARS = 2000


def _extract_candidate_text(candidate: Dict[str, Any]) -> str:
    """Extracts sanitized candidate text for relevance evaluation."""
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


def _heuristic_relevance_score(
    query_text: str,
    candidate: Dict[str, Any],
    query_plan: Optional[Any] = None
) -> float:
    """Deterministic legal relevance scorer for Pakistani jurisprudence."""
    q_low = query_text.lower()
    text = _extract_candidate_text(candidate).lower()
    meta = candidate.get("metadata") or {}

    # Token overlap
    q_tokens = [w for w in re.sub(r'[^\w\s]', ' ', q_low).split() if len(w) >= 4]
    overlap_count = sum(1 for tok in q_tokens if tok in text)
    base_score = min(0.60, (overlap_count / len(q_tokens)) * 0.60) if q_tokens else 0.20

    # Statutory match
    statute_boost = 0.0
    if query_plan:
        provisions = getattr(query_plan, "statutory_provisions", []) or getattr(query_plan, "provisions", [])
        for p in provisions:
            p_clean = str(p).lower().replace("_", " ")
            if p_clean in text:
                statute_boost = 0.25
                break

    # Court weighting
    court = str(candidate.get("court") or meta.get("court") or "").lower()
    court_boost = 0.15 if ("supreme court" in court or "apex court" in court) else (0.08 if "high court" in court else 0.0)

    # Segment boost: Ratio Decidendi and Headnotes receive extra relevance
    seg_type = str(candidate.get("segment_type") or meta.get("segment_type") or "").lower()
    seg_boost = 0.10 if seg_type in ("ratio_decidendi", "headnote") else 0.0

    return round(min(0.99, base_score + statute_boost + court_boost + seg_boost), 4)


def evaluate_candidate_relevance_shadow(
    candidates: List[Dict[str, Any]],
    query_plan: Optional[Any] = None,
    query_text: str = ""
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Evaluates candidate relevance in shadow mode without terminating the pipeline.
    Applies Voyage AI rerank-2 if available or fallback heuristic scoring.
    Returns (evaluated_candidates, shadow_rerank_stats).
    """
    if not candidates:
        return [], {"total_evaluated": 0, "relevant_count": 0, "issue_abstention_flags": {}}

    t0 = time.time()
    model_name = "heuristic-legal-ranker"
    scores: Dict[int, float] = {}

    doc_texts = [_extract_candidate_text(c) for c in candidates]

    # Attempt Voyage API Cross-Encoder
    if VOYAGE_API_KEY and query_text and doc_texts:
        try:
            client = voyageai.Client(api_key=VOYAGE_API_KEY)
            # Re-rank top candidates (max 25 for fast response)
            docs_to_rerank = doc_texts[:25]
            res = client.rerank(
                query=query_text,
                documents=docs_to_rerank,
                model=VOYAGE_RERANK_MODEL,
                top_k=len(docs_to_rerank)
            )
            for item in getattr(res, "results", []):
                idx = getattr(item, "index", None)
                r_score = getattr(item, "relevance_score", 0.0)
                if idx is not None:
                    scores[idx] = float(r_score)
            model_name = f"voyage-{VOYAGE_RERANK_MODEL}"
        except Exception as err:
            logger.warning(f"⚠️ [ShadowReranker] Voyage rerank error ({err}); falling back to heuristic.")

    # Fill any remaining with deterministic heuristic
    for idx, c in enumerate(candidates):
        if idx not in scores:
            scores[idx] = _heuristic_relevance_score(query_text, c, query_plan)

    # Decorate candidates
    evaluated: List[Dict[str, Any]] = []
    issue_abstention_flags: Dict[str, bool] = {}
    relevant_count = 0

    for idx, c in enumerate(candidates):
        c_copy = dict(c)
        r_score = scores.get(idx, 0.0)
        is_rel = r_score >= 0.35
        if is_rel:
            relevant_count += 1

        c_copy["shadow_rerank_score"] = r_score
        c_copy["is_shadow_relevant"] = is_rel
        c_copy["rerank_model"] = model_name
        evaluated.append(c_copy)

    # Sort candidates by rerank score descending
    evaluated.sort(key=lambda x: x.get("shadow_rerank_score", 0.0), reverse=True)

    stats: Dict[str, Any] = {
        "total_evaluated": len(candidates),
        "relevant_count": relevant_count,
        "irrelevant_count": len(candidates) - relevant_count,
        "latency_seconds": round(time.time() - t0, 3),
        "rerank_model": model_name,
        "issue_abstention_flags": issue_abstention_flags
    }

    return evaluated, stats
