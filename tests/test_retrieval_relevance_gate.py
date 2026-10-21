"""
tests/test_retrieval_relevance_gate.py

Tests for Fix C: Anchoring provision tokens and relevance gating.
"""

import pytest
from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.retrieval.unified_orchestrator import anchor_provision_token
from legal_ai.ranking.relevance_filter import filter_candidate_quality_before_ranking


def test_anchor_provision_token():
    # Bare numbers must be rejected
    assert anchor_provision_token("138") is None
    assert anchor_provision_token("420") is None
    assert anchor_provision_token("2A") is None

    # Bare "Section X" must be anchored to parent statute
    anchored_138 = anchor_provision_token("Section 138")
    assert anchored_138 is not None
    assert "Negotiable Instruments Act" in anchored_138

    anchored_420 = anchor_provision_token("Section 420")
    assert anchored_420 is not None
    assert "Pakistan Penal Code" in anchored_420

    # Already anchored provisions must be preserved
    assert "Order XXXIX Rule 2A CPC" in anchor_provision_token("Order XXXIX Rule 2A CPC")
    assert "Section 489-F PPC" in anchor_provision_token("Section 489-F PPC")


def test_relevance_gate_drops_tax_and_land_acquisition_in_cheque_query():
    plan = create_deterministic_fallback_plan("Punishment under Section 138 NI Act for a bounced cheque in Pakistan?")

    raw_candidates = [
        {
            "case_id": "2026_scmr_227",
            "citation": "2026 SCMR 227",
            "title": "Commissioner Inland Revenue v. ABC Corporation",
            "preview": "Section 138 of the Income Tax Ordinance 2001 provides for recovery of tax through bank accounts. The High Court erred in setting aside the recovery notice.",
            "court": "Supreme Court of Pakistan"
        },
        {
            "case_id": "pld_2026_sc_17",
            "citation": "PLD 2026 SC 17",
            "title": "Government of AJK v. Land Owners",
            "preview": "Land Acquisition Act, 1894 Section 18. Reference to Court for enhancement of compensation awarded by Collector Land Acquisition.",
            "court": "Supreme Court of Pakistan"
        },
        {
            "case_id": "2024_scmr_1719",
            "citation": "2024 SCMR 1719",
            "title": "Muhammad Tariq v. The State",
            "preview": "Section 489-F PPC. Dishonour of cheque. Ingredients of offence require dishonest issuance towards repayment of loan or fulfilment of obligation. Bail granted.",
            "court": "Supreme Court of Pakistan"
        }
    ]

    clean, rejections = filter_candidate_quality_before_ranking(raw_candidates, plan)

    # Tax and land acquisition cases must be dropped
    assert rejections["mismatched_domain"] >= 2
    clean_cids = [c["case_id"] for c in clean]
    assert "2026_scmr_227" not in clean_cids
    assert "pld_2026_sc_17" not in clean_cids
    # Cheque candidate must be kept
    assert "2024_scmr_1719" in clean_cids
