"""
tests/test_multi_lane_hybrid_retrieval.py

Phase 2 Multi-Lane Hybrid Retrieval Verification Suite:
1. Multi-Lane Reciprocal Rank Fusion across all 5 independent lanes
   (dense_conceptual, sparse_lexical, procedural, doctrinal, statutory)
2. Constitutional Precedence Weighting (Article 189 Supreme Court 1.35x, Article 201 High Court 1.10x)
3. MultiLaneRetrievalEngine interface & lane attribution
4. BM25 atomic serialization and index versioning (v2.0.0)
5. Orchestrator 5-lane parallel dispatch and candidate deduplication
6. Legacy 2-lane reciprocal_rank_fusion backward compatibility
"""

import os
import sys
import tempfile
import asyncio
from unittest.mock import patch, AsyncMock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hybrid_search import (
    BM25Index,
    INDEX_VERSION,
    multi_lane_reciprocal_rank_fusion,
    reciprocal_rank_fusion,
    MultiLaneRetrievalEngine,
    get_court_authority_weight,
    get_recency_weight
)
from core.legal_query_planner import (
    create_deterministic_fallback_plan
)
from legal_ai.retrieval.unified_orchestrator import (
    retrieve_candidates_parallel,
    merge_candidates_with_rrf,
    collapse_chunks_per_case
)


def test_5_lane_rrf_scoring_and_attribution():
    """
    Verifies that multi-lane RRF combines candidates across all 5 lanes
    with formula RRF(d) = sum(1 / (60 + rank)) and tracks lane provenance.
    """
    lane_1_dense = [
        ("case_sc_landmark", 0.92, {"citation": "2024 SCMR 101", "court": "Supreme Court of Pakistan"}),
        ("case_hc_appeal", 0.85, {"citation": "2023 CLD 500", "court": "Lahore High Court"}),
    ]
    lane_2_sparse = [
        ("case_statute_match", 14.5, {"citation": "2022 CLD 300", "court": "High Court of Sindh"}),
        ("case_sc_landmark", 12.0, {"citation": "2024 SCMR 101", "court": "Supreme Court of Pakistan"}),
    ]
    lane_3_procedural = [
        ("case_sc_landmark", 0.88, {"citation": "2024 SCMR 101", "court": "Supreme Court of Pakistan"}),
        ("case_hc_limitation", 0.80, {"citation": "2021 MLD 400", "court": "Lahore High Court"}),
    ]
    lane_4_doctrinal = [
        ("case_sc_landmark", 0.95, {"citation": "2024 SCMR 101", "court": "Supreme Court of Pakistan"}),
    ]
    lane_5_statutory = [
        ("case_sc_landmark", 15.0, {"citation": "2024 SCMR 101", "court": "Supreme Court of Pakistan"}),
        ("case_statute_match", 11.2, {"citation": "2022 CLD 300", "court": "High Court of Sindh"}),
    ]

    engine = MultiLaneRetrievalEngine(rrf_k=60)
    fused = engine.fuse_5_lanes(
        dense_conceptual=lane_1_dense,
        sparse_lexical=lane_2_sparse,
        procedural=lane_3_procedural,
        doctrinal=lane_4_doctrinal,
        statutory=lane_5_statutory
    )

    assert len(fused) > 0
    top = fused[0]

    # Supreme Court landmark appeared in ALL 5 lanes: rank 1, rank 2, rank 1, rank 1, rank 1
    # Expected base RRF: 1/61 + 1/62 + 1/61 + 1/61 + 1/61
    expected_base_rrf = (1.0 / 61.0) * 4 + (1.0 / 62.0)
    assert top["id"] == "case_sc_landmark"
    assert abs(top["rrf_score"] - expected_base_rrf) < 1e-4

    # Supreme Court gets 1.35x constitutional authority multiplier
    assert top["court_weight"] == 1.35
    assert abs(top["final_rank_score"] - (expected_base_rrf * 1.35)) < 1e-4

    # Verify all 5 retrieval lanes are recorded in provenance
    assert set(top["retrieval_lanes"]) == {
        "dense_conceptual",
        "sparse_lexical",
        "procedural",
        "doctrinal",
        "statutory"
    }

    # Verify lane_ranks recorded accurately
    assert top["lane_ranks"]["dense_conceptual"] == 1
    assert top["lane_ranks"]["sparse_lexical"] == 2
    assert top["lane_ranks"]["procedural"] == 1
    assert top["lane_ranks"]["doctrinal"] == 1
    assert top["lane_ranks"]["statutory"] == 1


def test_constitutional_court_weighting():
    """
    Verifies Article 189 Supreme Court (1.35x) and Article 201 High Court (1.10x)
    weighting hierarchy across identical base ranks.
    """
    sc_weight = get_court_authority_weight("2024 SCMR 1", "Supreme Court of Pakistan")
    hc_weight = get_court_authority_weight("2024 CLD 1", "Lahore High Court")
    tribunal_weight = get_court_authority_weight("2024 PTD 1", "Service Tribunal")
    neutral_weight = get_court_authority_weight("1945 PC 1", "Privy Council")

    assert sc_weight == 1.35
    assert hc_weight == 1.10
    assert tribunal_weight == 0.95
    assert neutral_weight == 1.0


def test_bm25_atomic_replacement_and_versioning():
    """
    Verifies that BM25Index enforces version 2.0.0 and saves atomically
    via temporary file replacement with zero corruption risk.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        idx_path = os.path.join(tmp_dir, "test_bm25.pkl")
        idx = BM25Index(version=INDEX_VERSION)
        assert idx.version == "2.0.0"

        docs = [
            {
                "id": "doc_1",
                "text": "appeal from banking court under section 22 financial institutions ordinance 2001",
                "metadata": {"citation": "2024 CLD 100", "court": "Lahore High Court"}
            },
            {
                "id": "doc_2",
                "text": "limitation period condonation under section 5 limitation act 1908",
                "metadata": {"citation": "2023 SCMR 500", "court": "Supreme Court of Pakistan"}
            },
            {
                "id": "doc_3",
                "text": "suit for partition of joint ancestral property preliminary decree under order 20 cpc",
                "metadata": {"citation": "2022 SCMR 900", "court": "Supreme Court of Pakistan"}
            },
            {
                "id": "doc_4",
                "text": "dishonour of cheque commercial transaction liability under section 489-f ppc",
                "metadata": {"citation": "2021 SCMR 200", "court": "Supreme Court of Pakistan"}
            },
            {
                "id": "doc_5",
                "text": "bail post arrest principles and guidelines under section 497 crpc",
                "metadata": {"citation": "2020 SCMR 100", "court": "Supreme Court of Pakistan"}
            }
        ]
        idx.fit(docs)
        assert idx.corpus_size == 5

        # Atomic save
        idx.save(idx_path, compact=True)
        assert os.path.exists(idx_path)
        assert not os.path.exists(f"{idx_path}.tmp")

        # Load back
        loaded = BM25Index.load(idx_path)
        assert loaded.version == "2.0.0"
        assert loaded.corpus_size == 5

        # Search verification
        hits = loaded.search("appeal banking court", top_k=2)
        assert len(hits) > 0
        assert hits[0][0] == "doc_1"


def test_backward_compatibility_2_lane_rrf():
    """
    Verifies that reciprocal_rank_fusion(dense, sparse) maintains 100%
    backward compatibility for existing callers.
    """
    dense = [("c1", 0.9, {"citation": "2024 SCMR 1"}), ("c2", 0.7, {"citation": "2023 LHC 2"})]
    sparse = [("c2", 8.0, {"citation": "2023 LHC 2"}), ("c3", 6.0, {"citation": "2022 SHC 3"})]

    results = reciprocal_rank_fusion(dense, sparse, k=60)
    assert len(results) == 3
    # c2 appeared in both ranks (rank 2 in dense, rank 1 in sparse)
    ids = [r["id"] for r in results]
    assert "c1" in ids and "c2" in ids and "c3" in ids


def test_retrieve_candidates_parallel_5_lanes():
    """
    Verifies that retrieve_candidates_parallel dispatches across all 5 legal intent lanes,
    records lane metrics in engine_counts, and merges candidates cleanly.
    """
    async def _run():
        query = "What is the procedure for an appeal from a Banking Court and is there a limitation period?"
        plan = create_deterministic_fallback_plan(query)

        # Mock search functions to return synthetic candidates
        mock_dense_results = [
            {"case_id": "2024_SCMR_100", "citation": "2024 SCMR 100", "score": 0.88, "court": "Supreme Court of Pakistan", "metadata": {"full_text": "Section 22 FIO appeal lies to High Court."}}
        ]
        mock_sparse_results = [
            {"case_id": "2023_CLD_200", "citation": "2023 CLD 200", "score": 12.5, "court": "Lahore High Court", "metadata": {"full_text": "Appeal against judgment and decree of Banking Court."}}
        ]

        with patch("legal_ai.retrieval.unified_orchestrator.search_pinecone_dense", new=AsyncMock(return_value=mock_dense_results)), \
             patch("legal_ai.retrieval.unified_orchestrator.search_bm25_sparse", return_value=mock_sparse_results):

            merged, counts = await retrieve_candidates_parallel(
                query_text=query,
                query_plan=plan,
                include_external=False,
                top_k_per_engine=10
            )

            assert len(merged) > 0
            # Check all 5 lane count metrics are present
            assert "count_dense_conceptual" in counts
            assert "count_sparse_lexical" in counts
            assert "count_procedural" in counts
            assert "count_doctrinal" in counts
            assert "count_statutory" in counts

            # Check legacy keys exist
            assert "count_pinecone" in counts
            assert "count_bm25" in counts

            # Verify candidate attributes
            for c in merged:
                assert "rrf_score" in c
                assert "court_weight" in c
                assert "retrieval_lanes" in c
                assert len(c["retrieval_lanes"]) > 0

    asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
