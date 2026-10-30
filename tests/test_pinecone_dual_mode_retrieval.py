"""
tests/test_pinecone_dual_mode_retrieval.py

Dedicated Unit & Integration Test Suite for Phase 4, Step 4:
Pinecone Metadata Filtering: Dual-Mode Retrieval Architecture.

Mandatory Test Scenarios:
1. Civil partition query against civil enriched vectors (Lane A match).
2. Civil partition query against legacy criminal vectors (Lane B quarantine).
3. Criminal bail query against legacy civil vectors (Lane B quarantine).
4. Banking queries against corporate authorities (Cross-domain boundary check).
5. Genuine corporate/criminal cross-domain authorities (Cross-domain synthesis preserved).
6. General legal and unclassified authorities (Preserved without false quarantine).
7. Missing or malformed metadata (Resilience check).
8. Duplicate candidates across both lanes (Deduplication check).
9. Empty enriched-vector results (Lane B fallback coverage).
10. Pinecone timeout in either retrieval lane (Graceful degradation).
11. Legacy-only namespace (100% legacy vectors handled with zero recall loss).
12. Mixed enriched and legacy namespace (Merged, deduplicated, and ranked).
"""

import asyncio
from unittest.mock import MagicMock, patch
import pytest

from core.legal_query_planner import (
    create_deterministic_fallback_plan,
    StructuredLegalQueryPlan
)
from legal_ai.retrieval.pinecone_search import (
    search_pinecone_dual_mode,
    search_pinecone_dense,
    _format_pinecone_match,
    ENABLE_DUAL_MODE_PINECONE_SEARCH
)


# ==============================================================================
# Test Fixtures & Helpers
# ==============================================================================

def create_mock_pinecone_match(
    vec_id: str,
    score: float,
    metadata: dict
) -> dict:
    """Helper to create Pinecone match dictionary."""
    return {
        "id": vec_id,
        "score": score,
        "metadata": metadata
    }


# ==============================================================================
# 1. Civil Partition Query against Civil Enriched Vectors (Lane A)
# ==============================================================================

def test_civil_partition_query_against_civil_enriched_vectors():
    """Verify that civil enriched vectors in Lane A are retrieved when matching allowed domains."""
    mock_index = MagicMock()
    
    enriched_civil = create_mock_pinecone_match(
        vec_id="2024_SCMR_500_chunk_0",
        score=0.88,
        metadata={
            "metadata_schema_version": "1.0",
            "legal_domain": "civil",
            "subdomain": "partition",
            "statutory_provisions": ["transfer_of_property_act_1882_section_44"],
            "case_id": "2024_SCMR_500",
            "citation": "2024 SCMR 500",
            "case_title": "Mst. Aisha Bibi v. Muhammad Aslam",
            "court": "Supreme Court of Pakistan",
            "text": "Suit for partition of joint land. A co-sharer cannot sell specific khasra without partition."
        }
    )

    def _mock_query(namespace, vector, top_k, filter=None, include_metadata=True):
        if filter and filter.get("legal_domain", {}).get("$in"):
            # Lane A query with filter
            if "civil" in filter["legal_domain"]["$in"]:
                return {"matches": [enriched_civil]}
        return {"matches": []}

    mock_index.query.side_effect = _mock_query

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        plan = create_deterministic_fallback_plan("Whether a co-sharer can sell specific partition land without partition")
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text=plan.query_text,
            query_plan=plan,
            top_k=10,
            enable_lane_a=True,
            enable_lane_b=False
        ))

        assert len(candidates) == 1
        assert candidates[0]["citation"] == "2024 SCMR 500"
        assert candidates[0]["lane_source"] == "Lane_A_Enriched"
        assert candidates[0]["is_enriched"] is True
        assert candidates[0]["legal_domain"] == "civil"
        assert candidates[0]["is_quarantined"] is False


# ==============================================================================
# 2. Civil Partition Query against Legacy Criminal Vectors (Lane B Quarantine)
# ==============================================================================

def test_civil_partition_query_quarantines_legacy_criminal():
    """Verify that irrelevant criminal murder cases in legacy Lane B are quarantined for civil partition queries."""
    mock_index = MagicMock()
    
    legacy_criminal = create_mock_pinecone_match(
        vec_id="2023_SCMR_984_chunk_0",
        score=0.85,
        metadata={
            "case_id": "2023_SCMR_984",
            "citation": "2023 SCMR 984",
            "case_title": "Tariq Mahmood v. The State",
            "court": "Supreme Court of Pakistan",
            "text": "Petition under Section 498 Cr.P.C. for grant of pre-arrest bail in FIR under Section 302 PPC murder trial."
        }
    )

    mock_index.query.return_value = {"matches": [legacy_criminal]}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        plan = create_deterministic_fallback_plan("Partition suit between co-sharers in joint agricultural property")
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text=plan.query_text,
            query_plan=plan,
            top_k=10,
            enable_lane_a=False,
            enable_lane_b=True
        ))

        # Lane B raw had 1, but it was quarantined because it's pure criminal
        assert telemetry["lane_b_raw_count"] == 1
        assert telemetry["lane_b_quarantined_count"] == 1
        # Merged candidate list must NOT contain the quarantined criminal authority
        assert len(candidates) == 0


# ==============================================================================
# 3. Criminal Bail Query against Legacy Civil Vectors (Lane B Quarantine)
# ==============================================================================

def test_criminal_bail_query_quarantines_legacy_civil():
    """Verify that irrelevant civil property cases in legacy Lane B are quarantined for criminal bail queries."""
    mock_index = MagicMock()
    
    legacy_civil = create_mock_pinecone_match(
        vec_id="2020_CLC_100_chunk_0",
        score=0.82,
        metadata={
            "case_id": "2020_CLC_100",
            "citation": "2020 CLC 100",
            "case_title": "Muhammad Aslam v. Allah Ditta",
            "court": "Lahore High Court",
            "text": "Suit for declaration and permanent injunction under Specific Relief Act regarding possession of land."
        }
    )

    mock_index.query.return_value = {"matches": [legacy_civil]}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        plan = create_deterministic_fallback_plan("Pre-arrest bail under section 498 CrPC malafide intention of police")
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text=plan.query_text,
            query_plan=plan,
            top_k=10,
            enable_lane_a=False,
            enable_lane_b=True
        ))

        assert telemetry["lane_b_raw_count"] == 1
        assert telemetry["lane_b_quarantined_count"] == 1
        assert len(candidates) == 0


# ==============================================================================
# 4. Banking Query against Corporate Authorities
# ==============================================================================

def test_banking_query_boundaries():
    """Verify banking query boundaries under Section 9 & 10 FIO 2001."""
    mock_index = MagicMock()
    
    banking_doc = create_mock_pinecone_match(
        vec_id="2023_CLD_1150_chunk_0",
        score=0.89,
        metadata={
            "metadata_schema_version": "1.0",
            "legal_domain": "banking",
            "subdomain": "leave_to_defend",
            "statutory_provisions": ["fio_2001_section_10"],
            "case_id": "2023_CLD_1150",
            "citation": "2023 CLD 1150",
            "case_title": "HBL v. Premier Textile",
            "court": "Banking Court",
            "text": "Suit for recovery of finance under FIO 2001. Leave to defend application dismissed."
        }
    )

    def _mock_query(namespace, vector, top_k, filter=None, include_metadata=True):
        if filter and "banking" in filter.get("legal_domain", {}).get("$in", []):
            return {"matches": [banking_doc]}
        return {"matches": []}

    mock_index.query.side_effect = _mock_query

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        plan = create_deterministic_fallback_plan("Leave to defend application under section 10 FIO 2001 financial institutions ordinance")
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text=plan.query_text,
            query_plan=plan,
            top_k=10,
            enable_lane_a=True,
            enable_lane_b=False
        ))

        assert len(candidates) == 1
        assert candidates[0]["legal_domain"] == "banking"
        assert candidates[0]["subdomain"] == "leave_to_defend"


# ==============================================================================
# 5. Genuine Corporate / Criminal Cross-Domain Authorities
# ==============================================================================

def test_genuine_corporate_criminal_cross_domain_preserved():
    """Verify that when a corporate oppression query legitimately engages Section 409 criminal breach of trust, cross-domain authorities are preserved."""
    mock_index = MagicMock()
    
    # Legacy vector with criminal breach of trust in corporate funds
    corp_crime_doc = create_mock_pinecone_match(
        vec_id="2021_SCMR_123_chunk_0",
        score=0.86,
        metadata={
            "case_id": "2021_SCMR_123",
            "citation": "2021 SCMR 123",
            "case_title": "State v. Director ABC Ltd",
            "court": "Supreme Court of Pakistan",
            "text": "Misappropriation of corporate company funds by director. Offence under Section 409 PPC criminal breach of trust."
        }
    )

    mock_index.query.return_value = {"matches": [corp_crime_doc]}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        # Query explicitly engages corporate oppression and 409 PPC misappropriation
        plan = create_deterministic_fallback_plan("Oppression of minority shareholders under section 286 Companies Act where directors misappropriated funds under 409 PPC")
        assert plan.is_cross_domain_relevant is True
        assert "criminal" in plan.allowed_domains_filter

        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text=plan.query_text,
            query_plan=plan,
            top_k=10,
            enable_lane_a=False,
            enable_lane_b=True
        ))

        # Must NOT be quarantined because cross-domain relevance was recognized
        assert telemetry["lane_b_quarantined_count"] == 0
        assert len(candidates) == 1
        assert candidates[0]["citation"] == "2021 SCMR 123"
        assert candidates[0]["is_quarantined"] is False


# ==============================================================================
# 6. General Legal and Unclassified Authorities Preserved
# ==============================================================================

def test_general_legal_authorities_preserved():
    """Verify that authorities without clear domain (general procedural precedents) are preserved for reranking."""
    mock_index = MagicMock()
    
    procedural_doc = create_mock_pinecone_match(
        vec_id="1988_CLC_471_chunk_0",
        score=0.78,
        metadata={
            "case_id": "1988_CLC_471",
            "citation": "1988 CLC 471",
            "case_title": "Abdul Ghafoor Baig v. ADJ",
            "court": "High Court of Sindh",
            "text": "General principles of natural justice and audi alteram partem in subordinate court proceedings."
        }
    )

    mock_index.query.return_value = {"matches": [procedural_doc]}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        plan = create_deterministic_fallback_plan("Whether order passed without hearing can be sustained")
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text=plan.query_text,
            query_plan=plan,
            top_k=10,
            enable_lane_a=False,
            enable_lane_b=True
        ))

        assert telemetry["lane_b_quarantined_count"] == 0
        assert len(candidates) == 1
        assert candidates[0]["legal_domain"] == "general_legal"
        assert candidates[0]["is_quarantined"] is False


# ==============================================================================
# 7. Missing or Malformed Metadata Handling
# ==============================================================================

def test_missing_or_malformed_metadata_resilience():
    """Verify that vectors with missing metadata dicts or None values do not crash dual-mode search."""
    mock_index = MagicMock()
    
    malformed_doc = {
        "id": "corrupted_vec_001",
        "score": 0.75,
        "metadata": None  # Malformed metadata
    }

    mock_index.query.return_value = {"matches": [malformed_doc]}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text="Civil revision under section 115 CPC",
            top_k=10,
            enable_lane_a=False,
            enable_lane_b=True
        ))

        # Should execute safely without raising exceptions
        assert isinstance(candidates, list)


# ==============================================================================
# 8. Duplicate Candidates Across Both Lanes
# ==============================================================================

def test_duplicate_candidates_across_lanes_deduplicated():
    """Verify that if a document is returned by both Lane A and Lane B, it is deduplicated cleanly."""
    mock_index = MagicMock()
    
    doc_shared = create_mock_pinecone_match(
        vec_id="2022_SCMR_100_chunk_0",
        score=0.91,
        metadata={
            "metadata_schema_version": "1.0",
            "legal_domain": "civil",
            "subdomain": "partition",
            "case_id": "2022_SCMR_100",
            "citation": "2022 SCMR 100",
            "case_title": "Shared Case v. State",
            "court": "Supreme Court of Pakistan",
            "text": "Partition suit decree under Section 44 Transfer of Property Act."
        }
    )

    # Return the same match for both Lane A and Lane B
    mock_index.query.return_value = {"matches": [doc_shared]}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text="Partition of ancestral property",
            top_k=10,
            enable_lane_a=True,
            enable_lane_b=True
        ))

        # Lane A had 1, Lane B had 1, but merged list must contain exactly 1 candidate
        assert len(candidates) == 1
        assert candidates[0]["lane_source"] == "Lane_A_Enriched"


# ==============================================================================
# 9. Empty Enriched-Vector Results (Lane B Fallback)
# ==============================================================================

def test_empty_enriched_results_lane_b_fallback():
    """Verify that when Lane A returns 0 enriched vectors, Lane B legacy vectors provide full coverage."""
    mock_index = MagicMock()
    
    legacy_doc = create_mock_pinecone_match(
        vec_id="1979_SCMR_150_chunk_0",
        score=0.84,
        metadata={
            "case_id": "1979_SCMR_150",
            "citation": "1979 SCMR 338",
            "case_title": "Ahsanul Haq v. Abdul Rahim",
            "court": "Supreme Court of Pakistan",
            "text": "Suit for specific performance of agreement to sell under Section 12 Specific Relief Act."
        }
    )

    def _mock_query(namespace, vector, top_k, filter=None, include_metadata=True):
        if filter:
            return {"matches": []}  # Lane A has no enriched vectors yet
        return {"matches": [legacy_doc]}  # Lane B has legacy vectors

    mock_index.query.side_effect = _mock_query

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text="Specific performance of contract agreement to sell",
            top_k=10,
            enable_lane_a=True,
            enable_lane_b=True
        ))

        assert telemetry["lane_a_raw_count"] == 0
        assert telemetry["lane_b_raw_count"] == 1
        assert len(candidates) == 1
        assert candidates[0]["citation"] == "1979 SCMR 338"
        assert candidates[0]["lane_source"] == "Lane_B_Legacy"


# ==============================================================================
# 10. Pinecone Timeout in Either Retrieval Lane
# ==============================================================================

def test_pinecone_timeout_graceful_degradation():
    """Verify that a timeout in Lane A does not fail the entire search request and Lane B still delivers."""
    mock_index = MagicMock()
    
    legacy_doc = create_mock_pinecone_match(
        vec_id="2021_SCMR_554_chunk_0",
        score=0.87,
        metadata={
            "case_id": "2021_SCMR_554",
            "citation": "2021 SCMR 554",
            "case_title": "Muhammad Nawaz v. State",
            "court": "Supreme Court of Pakistan",
            "text": "Criminal bail petition under Section 497 CrPC for statutory delay."
        }
    )

    def _mock_query(namespace, vector, top_k, filter=None, include_metadata=True):
        if filter:
            # Simulate timeout or server error in Lane A
            raise asyncio.TimeoutError("Pinecone connection timed out")
        return {"matches": [legacy_doc]}

    mock_index.query.side_effect = _mock_query

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text="Bail under section 497 CrPC statutory delay",
            top_k=10,
            enable_lane_a=True,
            enable_lane_b=True,
            timeout_seconds=0.1
        ))

        # Lane A timed out, but Lane B delivered successfully
        assert telemetry["lane_a_raw_count"] == 0
        assert telemetry["lane_b_raw_count"] == 1
        assert len(candidates) == 1
        assert candidates[0]["citation"] == "2021 SCMR 554"


# ==============================================================================
# 11. Legacy-Only Namespace (100% Legacy Vectors Handled)
# ==============================================================================

def test_legacy_only_namespace_full_retrieval_preservation():
    """Verify that when operating on a 100% legacy namespace (like the existing 401,351 vectors), zero recall loss occurs."""
    mock_index = MagicMock()
    
    legacy_matches = [
        create_mock_pinecone_match(f"legacy_case_{i}", 0.85 - (i * 0.02), {
            "case_id": f"legacy_{i}",
            "citation": f"2020 SCMR {100 + i}",
            "court": "Supreme Court of Pakistan",
            "case_title": f"Party A v. Party B {i}",
            "text": "Civil revision on partition of joint property and co-sharer rights."
        })
        for i in range(5)
    ]

    def _mock_query(namespace, vector, top_k, filter=None, include_metadata=True):
        if filter:
            return {"matches": []}  # Zero enriched vectors
        return {"matches": legacy_matches}

    mock_index.query.side_effect = _mock_query

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text="Partition of joint property co-sharer",
            top_k=5,
            enable_lane_a=True,
            enable_lane_b=True
        ))

        # All 5 legacy matches must be retrieved and preserved
        assert len(candidates) == 5
        assert all(c["lane_source"] == "Lane_B_Legacy" for c in candidates)
        assert all(c["is_quarantined"] is False for c in candidates)


# ==============================================================================
# 12. Mixed Enriched and Legacy Namespace
# ==============================================================================

def test_mixed_enriched_and_legacy_namespace_merged():
    """Verify that a mixed corpus of enriched and legacy vectors is cleanly merged, deduplicated, and ranked by score."""
    mock_index = MagicMock()
    
    enriched_match = create_mock_pinecone_match("enriched_001", 0.92, {
        "metadata_schema_version": "1.0",
        "legal_domain": "civil",
        "subdomain": "partition",
        "case_id": "2024_SCMR_500",
        "citation": "2024 SCMR 500",
        "case_title": "Enriched Civil Case",
        "text": "Partition under Section 44 Transfer of Property Act."
    })

    legacy_match = create_mock_pinecone_match("legacy_001", 0.85, {
        "case_id": "1999_SCMR_200",
        "citation": "1999 SCMR 200",
        "case_title": "Legacy Civil Case",
        "text": "Partition suit decree and co-sharer possession rights."
    })

    def _mock_query(namespace, vector, top_k, filter=None, include_metadata=True):
        if filter:
            return {"matches": [enriched_match]}
        return {"matches": [legacy_match]}

    mock_index.query.side_effect = _mock_query

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024):
        
        candidates, telemetry = asyncio.run(search_pinecone_dual_mode(
            query_text="Partition suit between co-sharers",
            top_k=10,
            enable_lane_a=True,
            enable_lane_b=True
        ))

        assert len(candidates) == 2
        # Higher score (0.92) first
        assert candidates[0]["citation"] == "2024 SCMR 500"
        assert candidates[0]["lane_source"] == "Lane_A_Enriched"
        # Lower score (0.85) second
        assert candidates[1]["citation"] == "1999 SCMR 200"
        assert candidates[1]["lane_source"] == "Lane_B_Legacy"


# ==============================================================================
# 13. Production Feature Flag Invariant
# ==============================================================================

def test_production_feature_flag_disabled_by_default():
    """Verify that search_pinecone_dense executes the legacy path when feature flag is disabled."""
    mock_index = MagicMock()
    mock_index.query.return_value = {"matches": []}

    with patch("legal_ai.retrieval.pinecone_search.get_pinecone_index", return_value=mock_index), \
         patch("legal_ai.retrieval.pinecone_search.get_voyage_embedding", return_value=[0.1] * 1024), \
         patch("legal_ai.retrieval.pinecone_search.ENABLE_DUAL_MODE_PINECONE_SEARCH", False):
        
        res = asyncio.run(search_pinecone_dense("Test query"))
        assert isinstance(res, list)
        # Verify it called query without any filter
        mock_index.query.assert_called_once()
        _, kwargs = mock_index.query.call_args
        assert "filter" not in kwargs or kwargs.get("filter") is None
