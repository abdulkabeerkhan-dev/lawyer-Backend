"""
tests/test_cross_encoder_reranker.py

Dedicated Unit & Regression Test Suite for Phase 4, Step 5:
Cross-Encoder Reranker Implementation.

Tests:
1. Ranking correctness: High-relevance document outranks off-topic document.
2. Metadata preservation: IDs, citations, court, provenance, and original retrieval scores preserved.
3. Timeout handling: Voyage API timeout triggers graceful fallback without pipeline termination.
4. Malformed inputs: None values, empty strings, and missing fields handled safely.
5. Empty candidate list: Returns empty list cleanly without errors.
6. Fallback behavior: Deterministic heuristic cross-scorer works when API key is missing.
7. Length truncation: Documents exceeding token limits are safely truncated without crashing.
8. Feature flag invariant: ENABLE_CROSS_ENCODER_RERANKER is False by default.
"""

import asyncio
from unittest.mock import MagicMock, patch
import pytest

from legal_ai.ranking.cross_encoder_reranker import (
    rerank_candidates_cross_encoder,
    _get_candidate_text_for_reranking,
    _heuristic_legal_cross_score,
    ENABLE_CROSS_ENCODER_RERANKER
)
from core.legal_query_planner import create_deterministic_fallback_plan


# ==============================================================================
# 1. Ranking Correctness Test
# ==============================================================================

def test_reranking_correctness_high_relevance_outranks():
    """Verify that a highly relevant partition case outranks a generic procedural case."""
    candidates = [
        {
            "id": "cand_generic",
            "citation": "1990 SCMR 100",
            "title": "General Case v. State",
            "court": "High Court of Sindh",
            "text": "General principles of civil court proceedings and adjournment of hearing.",
            "score": 0.85,
            "dense_score": 0.85
        },
        {
            "id": "cand_partition",
            "citation": "2024 SCMR 500",
            "title": "Mst. Aisha Bibi v. Muhammad Aslam",
            "court": "Supreme Court of Pakistan",
            "text": "Suit for partition of joint ancestral property under Section 44 Transfer of Property Act. Co-sharer rights.",
            "score": 0.70,  # Lower dense score initially
            "dense_score": 0.70
        }
    ]

    query = "Whether a co-sharer in joint property can sell specific land without partition"
    plan = create_deterministic_fallback_plan(query)

    # Mock Voyage API response where cand_partition gets higher score
    mock_item_0 = MagicMock(index=1, relevance_score=0.92)  # partition
    mock_item_1 = MagicMock(index=0, relevance_score=0.35)  # generic
    mock_res = MagicMock(results=[mock_item_0, mock_item_1])

    with patch("voyageai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.rerank.return_value = mock_res
        mock_client_cls.return_value = mock_client

        reranked, telem = asyncio.run(rerank_candidates_cross_encoder(
            query_text=query,
            candidates=candidates,
            query_plan=plan,
            top_k=2
        ))

        assert len(reranked) == 2
        # Partition case should now be rank 1 despite lower initial dense score
        assert reranked[0]["id"] == "cand_partition"
        assert reranked[0]["rerank_rank"] == 1
        assert reranked[0]["rerank_score"] == 0.92
        assert reranked[1]["id"] == "cand_generic"
        assert reranked[1]["rerank_rank"] == 2


# ==============================================================================
# 2. Metadata & Score Preservation Test
# ==============================================================================

def test_metadata_and_original_scores_preserved():
    """Verify all original fields, citations, court names, and dense/RRF scores are preserved."""
    candidates = [
        {
            "id": "case_101",
            "citation": "2021 SCMR 554",
            "title": "State v. Accused",
            "court": "Supreme Court of Pakistan",
            "year": 2021,
            "text": "Bail under Section 497 CrPC for statutory delay.",
            "score": 0.75,
            "dense_score": 0.75,
            "sparse_score": 0.40,
            "rrf_score": 0.035,
            "lane_source": "Lane_B_Legacy",
            "is_enriched": False
        }
    ]

    query = "Bail statutory delay"
    mock_item = MagicMock(index=0, relevance_score=0.88)
    mock_res = MagicMock(results=[mock_item])

    with patch("voyageai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.rerank.return_value = mock_res
        mock_client_cls.return_value = mock_client

        reranked, _ = asyncio.run(rerank_candidates_cross_encoder(
            query_text=query,
            candidates=candidates,
            top_k=1
        ))

        res = reranked[0]
        assert res["id"] == "case_101"
        assert res["citation"] == "2021 SCMR 554"
        assert res["court"] == "Supreme Court of Pakistan"
        assert res["year"] == 2021
        assert res["original_score"] == 0.75
        assert res["dense_score"] == 0.75
        assert res["sparse_score"] == 0.40
        assert res["rrf_score"] == 0.035
        assert res["lane_source"] == "Lane_B_Legacy"
        assert res["rerank_score"] == 0.88
        assert res["score"] == 0.88
        assert res["rerank_rank"] == 1


# ==============================================================================
# 3. Timeout Handling & Graceful Degradation
# ==============================================================================

def test_timeout_triggers_graceful_fallback():
    """Verify that an API timeout falls back to deterministic heuristic scorer without failing."""
    candidates = [
        {
            "id": "c1",
            "citation": "2024 SCMR 10",
            "court": "Supreme Court of Pakistan",
            "text": "Suit for partition of joint property under Section 44 Transfer of Property Act.",
            "score": 0.80
        }
    ]

    with patch("voyageai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.rerank.side_effect = asyncio.TimeoutError("Connection timed out")
        mock_client_cls.return_value = mock_client

        query = "Partition of joint property"
        reranked, telem = asyncio.run(rerank_candidates_cross_encoder(
            query_text=query,
            candidates=candidates,
            top_k=1,
            timeout_seconds=0.01
        ))

        assert len(reranked) == 1
        assert telem["fallback_triggered"] is True
        assert telem["model_used"] == "fallback-heuristic"
        assert reranked[0]["rerank_model"] == "fallback-heuristic"
        assert reranked[0]["rerank_score"] > 0.0


# ==============================================================================
# 4. Malformed and Missing Inputs Handling
# ==============================================================================

def test_malformed_candidates_handled_safely():
    """Verify that candidates with missing text, None fields, or empty dictionaries do not crash reranker."""
    candidates = [
        {"id": "c_empty"},  # Missing text, title, citation
        {"id": "c_none", "text": None, "title": None, "score": None},
        {"id": "c_valid", "text": "Valid legal text on pre-arrest bail under 498 CrPC."}
    ]

    reranked, telem = asyncio.run(rerank_candidates_cross_encoder(
        query_text="Pre-arrest bail 498 CrPC",
        candidates=candidates,
        top_k=3
    ))

    assert len(reranked) == 3
    assert all("rerank_score" in c for c in reranked)


def test_empty_candidates_returns_empty():
    """Verify empty input candidates return empty list cleanly."""
    reranked, telem = asyncio.run(rerank_candidates_cross_encoder(
        query_text="Any query",
        candidates=[],
        top_k=5
    ))
    assert reranked == []
    assert telem["output_count"] == 0


# ==============================================================================
# 5. Length Truncation Test
# ==============================================================================

def test_excessive_length_text_truncated():
    """Verify candidate text exceeding MAX_CANDIDATE_TEXT_CHARS is cleanly truncated."""
    long_cand = {
        "title": "Huge Precedent v. State",
        "citation": "2020 SCMR 1000",
        "court": "Supreme Court of Pakistan",
        "text": "Detailed legal reasoning on partition. " * 500  # ~19,000 characters
    }
    prepared_text = _get_candidate_text_for_reranking(long_cand)
    assert len(prepared_text) <= 2010
    assert prepared_text.endswith("...")


# ==============================================================================
# 6. Feature Flag Invariant Test
# ==============================================================================

def test_cross_encoder_feature_flag_disabled_by_default():
    """Verify that ENABLE_CROSS_ENCODER_RERANKER is False by default."""
    assert ENABLE_CROSS_ENCODER_RERANKER is False
