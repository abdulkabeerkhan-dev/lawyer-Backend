"""
tests/test_authority_constitutional_fusion.py

Unit Test Suite for Phase 4, Step 7:
Authority & Constitutional Precedent Multiplier Fusion.
Formula:
    Final Score = S_cross_encoder * (1.0 + Constitutional Multiplier)
    Clamped to 0.0 if S_cross_encoder < 0.35.

Test Gates:
1. Irrelevant Supreme Court cases (S < 0.35) clamped to 0.0.
2. Direct High Court precedents outrank tangentially related Supreme Court cases.
3. On-point Supreme Court precedents outrank on-point High Court precedents (Art. 189).
4. FCC Tier 1 precedence on constitutional issues post-27th Amendment.
5. FSC Tier 3 precedence under Article 203-GG.
6. Step 6 integration: ratio_decidendi chunks receive holding multiplier boost.
7. Step 6 integration: counsel_arguments chunks receive penalty.
8. Backward compatibility: traditional calculate_authority_score preserves legacy behavior.
"""

import pytest
from core.legal_query_planner import create_deterministic_fallback_plan
from core.authority_ranking import (
    compute_constitutional_multiplier,
    compute_fused_authority_score,
    calculate_authority_score,
    rank_and_filter_authorities,
    is_irrelevant_subject
)


def test_relevance_floor_clamping():
    """Candidates with S_cross_encoder < 0.35 must be clamped to 0.0 regardless of court tier."""
    # Supreme Court case with low semantic relevance
    s_sc = 0.28
    mult_sc = 1.0  # Supreme Court multiplier
    score_sc = compute_fused_authority_score(s_sc, mult_sc, relevance_floor=0.35)
    assert score_sc == 0.0, f"Expected 0.0 for S < 0.35, got {score_sc}"

    # High Court case with low semantic relevance
    s_hc = 0.349
    mult_hc = 0.35
    score_hc = compute_fused_authority_score(s_hc, mult_hc, relevance_floor=0.35)
    assert score_hc == 0.0, f"Expected 0.0 for S < 0.35, got {score_hc}"


def test_direct_high_court_beats_tangential_supreme_court():
    """Direct High Court precedent (high S) must outrank tangential Supreme Court precedent (marginal S)."""
    # Direct on-point Lahore High Court ruling on partition preliminary decree
    s_hc = 0.88
    mult_hc = 0.40  # HC + recent + PLD
    score_hc = compute_fused_authority_score(s_hc, mult_hc)

    # Tangentially related Supreme Court case with marginal relevance
    s_sc = 0.38
    mult_sc = 0.95  # SC + recent + SCMR
    score_sc = compute_fused_authority_score(s_sc, mult_sc)

    # hc: 0.88 * 1.40 = 1.232
    # sc: 0.38 * 1.95 = 0.741
    assert score_hc > score_sc, f"Expected direct HC ({score_hc}) to outrank tangential SC ({score_sc})"


def test_on_point_supreme_court_beats_on_point_high_court():
    """When both precedents are on-point (high S), Supreme Court outranks High Court under Article 189."""
    s = 0.85
    mult_sc = compute_constitutional_multiplier({
        "court": "Supreme Court of Pakistan",
        "citation": "2024 SCMR 500",
        "year": 2024
    })
    mult_hc = compute_constitutional_multiplier({
        "court": "Lahore High Court",
        "citation": "2024 CLC 200",
        "year": 2024
    })

    score_sc = compute_fused_authority_score(s, mult_sc)
    score_hc = compute_fused_authority_score(s, mult_hc)

    assert mult_sc > mult_hc
    assert score_sc > score_hc, f"Expected SC ({score_sc}) > HC ({score_hc}) under Art 189"


def test_fcc_constitutional_question_precedence():
    """Federal Constitutional Court receives top multiplier on constitutional questions."""
    plan_const = create_deterministic_fallback_plan("vires of constitutional amendment under Article 239")
    mult_fcc = compute_constitutional_multiplier({
        "court": "Federal Constitutional Court",
        "citation": "2026 FCCR 1",
        "year": 2026
    }, query_plan=plan_const)

    mult_hc = compute_constitutional_multiplier({
        "court": "Lahore High Court",
        "citation": "2026 CLC 1",
        "year": 2026
    }, query_plan=plan_const)

    assert mult_fcc >= 0.90
    assert mult_fcc > mult_hc


def test_fsc_shariat_injunction_precedence():
    """Federal Shariat Court receives specialized multiplier under Article 203-GG."""
    plan_fsc = create_deterministic_fallback_plan("riba prohibition Islamic banking injunction under Article 203D")
    mult_fsc = compute_constitutional_multiplier({
        "court": "Federal Shariat Court",
        "citation": "2024 PCrLJ 100",
        "year": 2024
    }, query_plan=plan_fsc)

    assert mult_fsc >= 0.35


def test_hierarchical_chunk_holding_boost():
    """Step 6 integration: Chunks tagged with is_holding=True receive holding multiplier boost."""
    base_candidate = {
        "court": "Lahore High Court",
        "citation": "2024 CLC 100",
        "year": 2024
    }

    holding_candidate = dict(base_candidate)
    holding_candidate["is_holding"] = True
    holding_candidate["section_type"] = "ratio_decidendi"

    argument_candidate = dict(base_candidate)
    argument_candidate["is_argument"] = True
    argument_candidate["section_type"] = "counsel_arguments"

    mult_holding = compute_constitutional_multiplier(holding_candidate)
    mult_base = compute_constitutional_multiplier(base_candidate)
    mult_arg = compute_constitutional_multiplier(argument_candidate)

    assert mult_holding > mult_base, f"Holding ({mult_holding}) must exceed base ({mult_base})"
    assert mult_arg < mult_base, f"Argument ({mult_arg}) must be penalized below base ({mult_base})"


def test_rank_and_filter_with_cross_encoder_scores():
    """Verifies that rank_and_filter_authorities sorts candidates by fused score and clamps S < 0.35."""
    plan = create_deterministic_fallback_plan("suit for partition of joint ancestral property")

    candidates = [
        {
            "case_id": "CAND_OFFTOPIC_SC",
            "citation": "2025 SCMR 999",
            "court": "Supreme Court of Pakistan",
            "year": 2025,
            "preview": "conviction under customs act smuggling duty evasion",
            "full_text": "conviction under customs act smuggling duty evasion " * 20,
            "rerank_score": 0.20  # Below 0.35 floor
        },
        {
            "case_id": "CAND_TANGENTIAL_SC",
            "citation": "2024 SCMR 888",
            "court": "Supreme Court of Pakistan",
            "year": 2024,
            "preview": "civil dispute general observations on property valuation",
            "full_text": "civil dispute general observations on property valuation " * 20,
            "rerank_score": 0.40  # Marginal above floor
        },
        {
            "case_id": "CAND_DIRECT_HC",
            "citation": "2024 CLC 123",
            "court": "Lahore High Court",
            "year": 2024,
            "preview": "partition suit co-sharers preliminary decree Order XX Rule 18 CPC",
            "full_text": "partition suit co-sharers preliminary decree Order XX Rule 18 CPC " * 20,
            "rerank_score": 0.85,  # High relevance
            "is_holding": True,
            "section_type": "ratio_decidendi"
        }
    ]

    ranked = rank_and_filter_authorities(candidates, plan, top_k=5)

    # CAND_OFFTOPIC_SC must be excluded (S < 0.35 -> 0.0)
    ranked_ids = [c["case_id"] for c in ranked]
    assert "CAND_OFFTOPIC_SC" not in ranked_ids

    # CAND_DIRECT_HC must be ranked #1
    assert ranked[0]["case_id"] == "CAND_DIRECT_HC"
    assert ranked[0]["authority_score"] > ranked[1]["authority_score"]


def test_legacy_calculate_authority_score_backward_compatibility():
    """Verifies that calculate_authority_score without cross-encoder scores preserves legacy test behavior."""
    plan = create_deterministic_fallback_plan("partition of family land among legal heirs")
    unrelated_sc_case = {
        "citation": "2026 SCMR 100",
        "court": "Supreme Court of Pakistan",
        "year": 2026,
        "preview": "The appellant was convicted under customs act for evasion of duty on imported consignment. Appeal dismissed.",
        "full_text": "The appellant was convicted under customs act for evasion of duty on imported consignment. " * 50
    }
    relevant_hc_case = {
        "citation": "2006 YLR 2059",
        "court": "Lahore High Court",
        "year": 2006,
        "preview": "suit for partition co-sharers properties preliminary decree Order XX Rule 18 CPC",
        "full_text": "suit for partition co-sharers properties preliminary decree Order XX Rule 18 CPC " * 50
    }

    sc_score, _ = calculate_authority_score(unrelated_sc_case, plan)
    hc_score, _ = calculate_authority_score(relevant_hc_case, plan)

    # Legacy invariants from test_universal_domain_quarantine.py must hold identically
    assert sc_score == 0.0
    assert hc_score > 50.0
