"""
tests/test_domain_gate.py

Comprehensive Test Suite for Phase 4, Step 5:
Post-Rerank Legal Domain Validation Gate & Dynamic Context Assembly Engine.

Validates Acceptance Criteria:
- AC-01: Gate Interface Contract
- AC-02: Domain Classification Positive/Negative Fixtures
- AC-03: Statutory Fallback 5-Stage Order
- AC-04: Five Interdisciplinary Doctrine Contracts (Positive & Negative)
- AC-05: Quarantine Hard-Drop Boundary (Pre-RRF) & Reinsertion Prevention
- AC-06: Strict Mode Generation Safety Boundary (Bucket 3 Exclusion)
- AC-07: Constitutional Precedent Hierarchy (Amended Article 189, FCC, SC, FSC, HC)
- AC-08: Pure Semantic Relevance Floor Cutoff (S_rerank >= 0.35)
- AC-09: Canonical Appeal-Number Deduplication
- AC-10: Native Generation Tokenizer Three-Tier Contract
- AC-11: Token Budget Enforcement & Clean Paragraph Truncation
- AC-12: Benchmark Evaluator Doctrine Awareness
- AC-16: Traceable Candidate Audit Trail & Telemetry
- AC-17: Article 212(1)(a) Service Terms and Conditions Jurisdiction
- AC-18: Article 212(1)(b) State Torts, 16-Enactment Ledger & Section 80 CPC Notice
- AC-19: Article 212(1)(c) Enemy Property Custodian Jurisdiction
- AC-20: Article 212(2) Provincial Extension Proviso
- AC-21: Residuary Article 120 Inheritance Limitation & Accrual
- AC-22: Article 142 Dispossession & Ouster vs Revenue Mutation
- AC-23: Section 18 Statutory Fraud Requirements
- AC-24: Authentic Section 2(8) Benami Tree, Fiduciary Exclusion & 108 States
- AC-25: Section 489-F PPC Cheque Dishonor Mens Rea & Recovery Forum
- AC-26: Section 420 PPC Inception Intention & FIR Quashment
- AC-27: Section 406 PPC Entrustment vs Debtor-Creditor Relationship
- AC-28: 20 Adversarial Acceptance Tests for FSC/SAB Appeal Forums & Article 202A
- AC-29: Serialized Request Recount & Non-ASCII Overflow Boundary
"""

import math
from unittest.mock import MagicMock
import pytest

from core.legal_query_planner import StructuredLegalQueryPlan, create_deterministic_fallback_plan
from core.post_rerank_domain_gate import (
    count_context_tokens,
    evaluate_interdisciplinary_doctrine,
    partition_candidates_into_ranking_buckets,
    validate_and_partition_post_rerank,
    _compute_lexicographic_sort_key,
    _extract_canonical_appeal_key,
    _format_candidate_for_context,
    _truncate_on_paragraph_boundary,
    assemble_generation_context,
    evaluate_art212_service_conditions,
    evaluate_state_tort_action,
    evaluate_art212_enemy_property,
    evaluate_art212_provincial_proviso,
    evaluate_inheritance_limitation,
    evaluate_benami_transaction,
    evaluate_s489f_cheque_liability,
    evaluate_s420_inception_intention,
    evaluate_s406_entrustment_vs_debt,
    evaluate_art203f_appeal_forum,
    evaluate_art202a_constitutional_bench,
    evaluate_precedent_hierarchy_and_conflict,
    MAX_CANDIDATE_TOKENS,
    PURE_RELEVANCE_FLOOR
)


# ==============================================================================
# Helper Mock Objects
# ==============================================================================

class MockQueryPlan:
    def __init__(
        self,
        primary_domain="civil",
        statutory_provisions=None,
        governing_statutes=None,
        is_cross_domain_relevant=False,
        cross_domain_controlling_doctrines=None,
        binding_courts=None
    ):
        self.primary_domain = primary_domain
        self.statutory_provisions = statutory_provisions or []
        self.governing_statutes = governing_statutes or []
        self.is_cross_domain_relevant = is_cross_domain_relevant
        self.cross_domain_controlling_doctrines = cross_domain_controlling_doctrines or []
        self.binding_courts = binding_courts or ["Supreme Court of Pakistan"]
        self.provisions = self.statutory_provisions


# ==============================================================================
# 1. AC-01: Domain Gate Interface Contract
# ==============================================================================

def test_domain_gate_interface_contract():
    plan = MockQueryPlan(primary_domain="civil", statutory_provisions=["Section 44 Transfer of Property Act"])
    candidates = [
        {
            "id": "c1",
            "citation": "2024 SCMR 100",
            "title": "A v. B",
            "text": "Partition suit under Section 44 Transfer of Property Act",
            "semantic_relevance_score": 0.85,
            "domain": "civil",
            "domain_confidence": 0.90
        }
    ]
    res, telem = validate_and_partition_post_rerank(candidates, plan, strict_mode=True)
    assert len(res) == 1
    assert telem["input_count"] == 1
    assert telem["bucket_1a_count"] == 1
    assert telem["final_output_count"] == 1
    assert res[0]["ranking_bucket"] == 1
    assert res[0]["validation_status"] == "APPROVED_ON_DOMAIN"


# ==============================================================================
# 2. AC-02: Domain Classification Positive/Negative Fixtures
# ==============================================================================

def test_domain_classification_positive_negative():
    plan = MockQueryPlan(primary_domain="civil")
    candidates = [
        # On-domain civil partition case
        {
            "id": "civil_cand",
            "citation": "2024 SCMR 500",
            "title": "Ahmad v. Bashir",
            "text": "Suit for partition of joint ancestral property",
            "domain": "civil",
            "domain_confidence": 0.88,
            "semantic_relevance_score": 0.80
        },
        # Off-domain family dower case (2015 SCMR 869)
        {
            "id": "family_cand",
            "citation": "2015 SCMR 869",
            "title": "Mst. Rashida v. Muhammad Akram",
            "text": "Recovery of deferred dower and dowry articles under Family Courts Act 1964",
            "domain": "family",
            "domain_confidence": 0.95,
            "semantic_relevance_score": 0.40
        }
    ]
    # In strict_mode=False, Bucket 3 is returned in candidate list for inspection
    res, telem = partition_candidates_into_ranking_buckets(candidates, plan, strict_mode=False)
    assert telem["bucket_1a_count"] == 1
    assert telem["bucket_3_count"] == 1
    c_civil = next(c for c in res if c["id"] == "civil_cand")
    c_family = next(c for c in res if c["id"] == "family_cand")
    assert c_civil["ranking_bucket"] == 1
    assert c_family["ranking_bucket"] == 3
    assert c_family["validation_status"] == "DEMOTED_OFF_DOMAIN"


# ==============================================================================
# 3. AC-03: Statutory Fallback 5-Stage Order
# ==============================================================================

def test_statutory_fallback_five_stage_order():
    plan = MockQueryPlan(primary_domain="civil", statutory_provisions=["Section 9 CPC"])
    candidates = [
        # Direct query statute match -> 1A
        {"id": "direct", "citation": "2023 SCMR 10", "title": "A v. B", "text": "Civil suit under Section 9 CPC", "score": 0.80},
        # Foreign disallowed statute (Income Tax Ordinance in Civil suit) -> 3
        {"id": "foreign", "citation": "2020 PTD 40", "title": "C v. D", "text": "Tax assessment notice under Income Tax Ordinance 2001", "score": 0.75},
        # Neutral procedural authority with conf >= 0.60 -> 2
        {"id": "procedural", "citation": "2019 SCMR 80", "title": "E v. F", "text": "Condonation of delay under Section 5 Limitation Act", "domain": "general_legal", "confidence": 0.70, "score": 0.60},
        # Ambiguous low confidence (< 0.60) without statute -> dropped in strict mode
        {"id": "ambiguous", "citation": "2018 YLR 1", "title": "G v. H", "text": "General factual remarks without statutory reference", "domain": "unknown", "domain_confidence": 0.35, "score": 0.50}
    ]

    # In strict mode: ambiguous dropped
    res_strict, telem_strict = partition_candidates_into_ranking_buckets(candidates, plan, strict_mode=True)
    assert telem_strict["bucket_1a_count"] == 1
    assert telem_strict["bucket_2_count"] == 1
    assert telem_strict["bucket_3_count"] == 1
    assert telem_strict["ambiguous_dropped"] == 1
    # Result contains 1A + 2 (len=2)
    assert len(res_strict) == 2
    assert {c["id"] for c in res_strict} == {"direct", "procedural"}

    # In non-strict mode: ambiguous demoted to Bucket 3
    res_loose, telem_loose = partition_candidates_into_ranking_buckets(candidates, plan, strict_mode=False)
    assert telem_loose["ambiguous_dropped"] == 0
    assert telem_loose["bucket_3_count"] == 2  # foreign + ambiguous


# ==============================================================================
# 4. AC-04: Five Interdisciplinary Doctrine Contracts
# ==============================================================================

def test_doctrine_contracts_positive_negative():
    # 1. Art 212 Service Bar
    plan_const = MockQueryPlan(
        primary_domain="constitutional",
        is_cross_domain_relevant=True,
        cross_domain_controlling_doctrines=["DOCTRINE_ART_212_SERVICE_BAR"]
    )
    cand_art212_pos = {
        "title": "Muhammad Hassanullah v. Chief Secretary",
        "citation": "2025 SCMR 134",
        "text": "Article 212 constitutional ouster of High Court writ jurisdiction in service tribunal matters of civil servant",
        "semantic_relevance_score": 0.88
    }
    admitted, doc_id, reason = evaluate_interdisciplinary_doctrine(cand_art212_pos, plan_const)
    assert admitted is True
    assert doc_id == "DOCTRINE_ART_212_SERVICE_BAR"

    cand_art212_neg = {
        "title": "Employee v. Bank",
        "citation": "2018 PLC(CS) 394",
        "text": "Article 212 service tribunal civil servant master and servant relationship of private bank employee",
        "semantic_relevance_score": 0.45
    }
    admitted_neg, _, _ = evaluate_interdisciplinary_doctrine(cand_art212_neg, plan_const)
    assert admitted_neg is False

    # 2. Civil Dispute Criminal Quashment (S.561-A / S.420 PPC)
    plan_crim = MockQueryPlan(
        primary_domain="criminal",
        is_cross_domain_relevant=True,
        cross_domain_controlling_doctrines=["DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT"]
    )
    cand_quash_pos = {
        "title": "Hamid Ali Shah v. DG FIA",
        "citation": "PLD 2023 SC 265",
        "text": "Quash of criminal proceedings arising from commercial contract breach without dishonest intention at inception; Section 420 PPC",
        "semantic_relevance_score": 0.90
    }
    admitted, doc_id, _ = evaluate_interdisciplinary_doctrine(cand_quash_pos, plan_crim)
    assert admitted is True
    assert doc_id == "DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT"

    cand_quash_neg = {
        "title": "State v. Robber",
        "citation": "2008 YLR 2548",
        "text": "Quash of FIR concerning physical assault and robbery under contract pretext",
        "semantic_relevance_score": 0.35
    }
    admitted_neg, _, _ = evaluate_interdisciplinary_doctrine(cand_quash_neg, plan_crim)
    assert admitted_neg is False

    # 3. Female Inheritance Limitation
    plan_civil = MockQueryPlan(
        primary_domain="civil",
        is_cross_domain_relevant=True,
        cross_domain_controlling_doctrines=["DOCTRINE_FEMALE_INHERITANCE_LIMITATION"]
    )
    cand_inher_pos = {
        "title": "Ghulam Ali v. Mst. Ghulam Sarwar",
        "citation": "PLD 1990 SC 1",
        "text": "Female inheritance rights; brother holds land as constructive trustee for sister; mutation without notice",
        "semantic_relevance_score": 0.92
    }
    admitted, doc_id, _ = evaluate_interdisciplinary_doctrine(cand_inher_pos, plan_civil)
    assert admitted is True

    cand_inher_neg = {
        "title": "Wife v. Husband",
        "citation": "2015 SCMR 869",
        "text": "Female inheritance mutation of sister in suit for dissolution of marriage and dowry articles",
        "semantic_relevance_score": 0.30
    }
    admitted_neg, _, _ = evaluate_interdisciplinary_doctrine(cand_inher_neg, plan_civil)
    assert admitted_neg is False

    # 4. Benami Partition Bar
    plan_benami = MockQueryPlan(
        primary_domain="civil",
        is_cross_domain_relevant=True,
        cross_domain_controlling_doctrines=["DOCTRINE_BENAMI_PARTITION_BAR"]
    )
    cand_benami_pos = {
        "title": "Muhammad Yousaf v. Muhammad Ishaq",
        "citation": "2023 SCMR 572",
        "text": "Suit for partition where co-sharer raises benami purchase defense of ostensible owner",
        "semantic_relevance_score": 0.89
    }
    admitted, doc_id, _ = evaluate_interdisciplinary_doctrine(cand_benami_pos, plan_benami)
    assert admitted is True

    cand_benami_neg = {
        "title": "Taxpayer v. FBR",
        "citation": "2018 SCMR 120",
        "text": "Partition and ostensible benami ownership in tax evasion investigation and income tax assessment",
        "semantic_relevance_score": 0.40
    }
    admitted_neg, _, _ = evaluate_interdisciplinary_doctrine(cand_benami_neg, plan_benami)
    assert admitted_neg is False

    # 5. Banking Recovery vs 489-F PPC
    plan_bank = MockQueryPlan(
        primary_domain="banking",
        is_cross_domain_relevant=True,
        cross_domain_controlling_doctrines=["DOCTRINE_BANKING_RECOVERY_VS_489F_PPC"]
    )
    cand_bank_pos = {
        "title": "Muhammad Sultan v. Bank of Punjab",
        "citation": "PLD 2012 SC 179",
        "text": "Cheque dishonor under Section 489-F PPC in financial institution loan recovery",
        "semantic_relevance_score": 0.91
    }
    admitted, doc_id, _ = evaluate_interdisciplinary_doctrine(cand_bank_pos, plan_bank)
    assert admitted is True

    cand_bank_neg = {
        "title": "Gambler v. State",
        "citation": "2016 YLR 450",
        "text": "Section 489-F cheque dishonor given for gambling debt by financial institution recovery",
        "semantic_relevance_score": 0.30
    }
    admitted_neg, _, _ = evaluate_interdisciplinary_doctrine(cand_bank_neg, plan_bank)
    assert admitted_neg is False


# ==============================================================================
# 5. AC-05: Quarantine Hard-Drop Boundary & Reinsertion Prevention
# ==============================================================================

def test_quarantine_hard_drop_top_scoring():
    plan = MockQueryPlan(primary_domain="civil", statutory_provisions=["Section 9 CPC"])
    quarantined_cand = {
        "id": "cand_quarantine_top",
        "citation": "2025 SCMR 999",
        "title": "Toxic Landmark v. State",
        "court": "Supreme Court of Pakistan",
        "text": "Direct section 9 cpc civil suit landmark with highest score",
        "semantic_relevance_score": 0.99,
        "is_quarantined": True
    }
    clean_cand = {
        "id": "cand_clean",
        "citation": "2023 SCMR 100",
        "title": "Legitimate Landmark v. Other",
        "court": "Supreme Court of Pakistan",
        "text": "Section 9 cpc civil suit",
        "semantic_relevance_score": 0.85,
        "is_quarantined": False
    }

    # Test in both strict_mode=True and strict_mode=False
    for mode in [True, False]:
        res, telem = partition_candidates_into_ranking_buckets([quarantined_cand, clean_cand], plan, strict_mode=mode)
        assert telem["quarantined_dropped"] == 1
        assert len(res) == 1
        assert res[0]["id"] == "cand_clean"
        assert quarantined_cand not in res

    # Context assembly check: quarantined candidate is NEVER included
    context, included, asm_telem, audit = assemble_generation_context([quarantined_cand, clean_cand], plan)
    assert asm_telem["quarantined_dropped"] == 1
    assert len(included) == 1
    assert included[0]["id"] == "cand_clean"
    assert "cand_quarantine_top" not in context
    assert any(a["status"] == "EXCLUDED" and "QUARANTINE_VIOLATION" in a["reason"] for a in audit)


# ==============================================================================
# 6. AC-06: Strict Mode Generation Safety Boundary
# ==============================================================================

def test_strict_mode_generation_boundary():
    plan = MockQueryPlan(primary_domain="civil")
    off_domain_cand = {
        "id": "off_domain",
        "citation": "2022 PTD 50",
        "title": "Tax Co v. FBR",
        "text": "Customs Act and sales tax assessment",
        "semantic_relevance_score": 0.85,
        "domain": "taxation",
        "domain_confidence": 0.95
    }
    on_domain_cand = {
        "id": "on_domain",
        "citation": "2024 SCMR 110",
        "title": "Civil Co v. Person",
        "text": "Civil declaration of property title",
        "semantic_relevance_score": 0.80,
        "domain": "civil",
        "domain_confidence": 0.90
    }

    # Caller passes strict_mode=False to inspect diagnostic records
    context, included, telem, audit = assemble_generation_context(
        [off_domain_cand, on_domain_cand],
        plan,
        strict_mode=False
    )
    # Invariant: Bucket 3 is NEVER in LLM context regardless of strict_mode=False
    assert len(included) == 1
    assert included[0]["id"] == "on_domain"
    assert "Tax Co v. FBR" not in context
    assert any(a["status"] == "EXCLUDED" and "BUCKET_3_EXCLUDED" in a["reason"] for a in audit)


# ==============================================================================
# 7. AC-07: Constitutional Precedent Hierarchy & Subject-Matter Gating
# ==============================================================================

def test_constitutional_hierarchy_subject_matter():
    # 1. Constitutional Query: FCC (Tier 1) > Supreme Court (Tier 2)
    plan_const = MockQueryPlan(primary_domain="constitutional", statutory_provisions=["Article 199"])
    cand_fcc = {
        "id": "fcc_case",
        "court": "Federal Constitutional Court of Pakistan",
        "citation": "2026 FCC 1",
        "text": "Interpretation of fundamental rights under Article 199",
        "ranking_bucket": 1,
        "semantic_relevance_score": 0.80
    }
    cand_sc = {
        "id": "sc_case",
        "court": "Supreme Court of Pakistan",
        "citation": "2024 SCMR 10",
        "text": "Article 199 constitutional jurisdiction",
        "ranking_bucket": 1,
        "semantic_relevance_score": 0.90
    }
    key_fcc = _compute_lexicographic_sort_key(cand_fcc, plan_const)
    key_sc = _compute_lexicographic_sort_key(cand_sc, plan_const)
    # Tier_precedent: FCC is 1, SC is 2 for constitutional queries
    assert key_fcc[1] == 1
    assert key_sc[1] == 2
    assert key_fcc < key_sc  # FCC wins rank

    # 2. Civil General Law Query: Supreme Court (Tier 1) > FCC (Tier 2)
    plan_civil = MockQueryPlan(primary_domain="civil", statutory_provisions=["Section 9 CPC"])
    key_sc_civil = _compute_lexicographic_sort_key(cand_sc, plan_civil)
    key_fcc_civil = _compute_lexicographic_sort_key(cand_fcc, plan_civil)
    assert key_sc_civil[1] == 1
    assert key_fcc_civil[1] == 2
    assert key_sc_civil < key_fcc_civil  # Supreme Court wins general law rank

    # 3. Federal Shariat Court is recognized as Tier 3
    cand_fsc = {
        "id": "fsc_case",
        "court": "Federal Shariat Court",
        "citation": "2023 FSC 5",
        "text": "Repugnancy of law under Chapter 3A Article 203D",
        "ranking_bucket": 1,
        "semantic_relevance_score": 0.85
    }
    key_fsc = _compute_lexicographic_sort_key(cand_fsc, plan_const)
    assert key_fsc[1] == 3


# ==============================================================================
# 8. AC-08: Pure Semantic Relevance Floor Cutoff (S_rerank >= 0.35)
# ==============================================================================

def test_pure_relevance_floor_cutoff():
    plan = MockQueryPlan(primary_domain="civil")
    # Supreme Court case with low semantic score (0.31 < 0.35)
    weak_sc_cand = {
        "id": "weak_sc",
        "court": "Supreme Court of Pakistan",
        "citation": "2024 SCMR 1",
        "title": "Irrelevant Apex Case v. State",
        "text": "Completely off-topic discussion with weak semantic relevance",
        "semantic_relevance_score": 0.31,
        "domain": "civil",
        "domain_confidence": 0.90
    }
    # Moderate High Court case with score >= 0.35
    valid_hc_cand = {
        "id": "valid_hc",
        "court": "Lahore High Court",
        "citation": "2023 CLC 10",
        "title": "Relevant HC Case v. Other",
        "text": "Relevant legal proposition for the user query",
        "semantic_relevance_score": 0.65,
        "domain": "civil",
        "domain_confidence": 0.90
    }

    context, included, telem, audit = assemble_generation_context(
        [weak_sc_cand, valid_hc_cand],
        plan,
        relevance_floor=PURE_RELEVANCE_FLOOR
    )
    assert telem["below_relevance_floor_dropped"] == 1
    assert len(included) == 1
    assert included[0]["id"] == "valid_hc"
    assert "Irrelevant Apex Case" not in context
    assert any(a["status"] == "EXCLUDED" and "BELOW_RELEVANCE_FLOOR" in a["reason"] for a in audit)


# ==============================================================================
# 9. AC-09: Canonical Appeal-Number Deduplication
# ==============================================================================

def test_canonical_appeal_deduplication():
    cand1 = {"title": "Civil Appeal No. 801 of 2021", "citation": "2023 SCMR 572"}
    cand2 = {"title": "Muhammad Yousaf v. Muhammad Ishaq", "citation": "Civil Appeal 801/2021"}
    cand3 = {"title": "Criminal Appeal No. 120 of 2019", "citation": "2020 SCMR 50"}

    key1 = _extract_canonical_appeal_key(cand1)
    key2 = _extract_canonical_appeal_key(cand2)
    key3 = _extract_canonical_appeal_key(cand3)

    assert key1 == "2021-801"
    assert key2 == "2021-801"
    assert key3 == "2019-120"
    assert key1 == key2  # Same appeal deduplicated
    assert key1 != key3  # Distinct appeal preserved


# ==============================================================================
# 10. AC-10: Native Generation Tokenizer Three-Tier Contract
# ==============================================================================

def test_native_tokenizer_contract_and_abort():
    # Level 1: Native tokenizer with encode method
    mock_tok = MagicMock()
    mock_tok.encode.return_value = [101, 102, 103, 104, 105]
    count1 = count_context_tokens(["Sample legal text"], generation_tokenizer=mock_tok)
    assert count1 == 5

    # Level 2: Calibrated operational fallback (2.4 chars/token with math.ceil)
    text = "A" * 240
    count2 = count_context_tokens([text], generation_tokenizer=None)
    assert count2 == math.ceil(240 / 2.4) == 100

    # Level 3: Fail-closed boundary on uncalibrated non-ASCII input (> 15%)
    urdu_text = "یہ ایک پاکستانی عدالتی فیصلہ ہے جس میں قانون کی تشریح کی گئی ہے" * 5
    count3 = count_context_tokens([urdu_text], generation_tokenizer=None)
    # Returns limit + 1 (7001) to fail closed safely
    assert count3 == MAX_CANDIDATE_TOKENS + 1


# ==============================================================================
# 11. AC-11: Token Budget Enforcement & Clean Paragraph Truncation
# ==============================================================================

def test_context_budget_enforcement_and_atomic_truncation():
    plan = MockQueryPlan(primary_domain="civil")
    long_para1 = "Paragraph 1: " + ("Ratio decidendi of judgment. " * 30)
    long_para2 = "Paragraph 2: " + ("Further facts and reasons. " * 30)
    long_para3 = "Paragraph 3: " + ("Concluding disposition order. " * 30)
    full_text = f"{long_para1}\n\n{long_para2}\n\n{long_para3}"

    cand = {
        "id": "c_long",
        "citation": "2024 SCMR 999",
        "title": "Long Case",
        "court": "Supreme Court of Pakistan",
        "text": full_text,
        "semantic_relevance_score": 0.85,
        "domain": "civil",
        "domain_confidence": 0.90
    }

    # Restrict budget so only first paragraph fits and remainder is truncated
    context, included, telem, audit = assemble_generation_context(
        [cand],
        plan,
        max_tokens=500  # Cap forcing truncation of paras 2 & 3
    )
    assert len(included) == 1
    assert telem["final_token_count"] <= 500
    assert "[... Remaining judgment truncated to preserve token budget ...]" in context


# ==============================================================================
# 12. AC-16: Traceable Candidate Audit Trail & Telemetry
# ==============================================================================

def test_candidate_audit_trail_telemetry():
    plan = MockQueryPlan(primary_domain="civil")
    cands = [
        {"id": "c1", "citation": "2024 SCMR 1", "title": "C1", "text": "Valid text", "semantic_relevance_score": 0.80, "domain": "civil", "domain_confidence": 0.90},
        {"id": "c2", "citation": "2024 SCMR 2", "title": "C2", "text": "Low score", "semantic_relevance_score": 0.20, "domain": "civil", "domain_confidence": 0.90},
        {"id": "c3", "citation": "2024 SCMR 3", "title": "C3", "text": "Quarantine", "semantic_relevance_score": 0.90, "is_quarantined": True}
    ]
    context, included, telem, audit = assemble_generation_context(cands, plan)
    assert len(audit) == 3
    statuses = {a["citation"]: a["status"] for a in audit}
    assert statuses["2024 SCMR 1"] == "INCLUDED"
    assert statuses["2024 SCMR 2"] == "EXCLUDED"
    assert statuses["2024 SCMR 3"] == "EXCLUDED"


# ==============================================================================
# 13. AC-17: Article 212(1)(a) Service Terms and Conditions Jurisdiction
# ==============================================================================

def test_art212_service_conditions():
    # Civil servant challenging promotion order -> FST exclusive, Art 199 barred
    res1 = evaluate_art212_service_conditions(claimant_is_civil_servant=True, is_terms_and_conditions=True)
    assert res1["status"] == "SERVICE_JURISDICTION_EXCLUSIVE_OVER_CIVIL_SERVANT_CLAIM"
    assert res1["article_199_maintainable"] is False
    assert res1["ouster_applicable"] is True

    # Non-civil servant contractor -> Art 199 conditional
    res2 = evaluate_art212_service_conditions(claimant_is_civil_servant=False, is_terms_and_conditions=False)
    assert res2["status"] == "SERVICE_JURISDICTION_EXCLUDED_CLAIMANT_NOT_CIVIL_SERVANT"
    assert res2["article_199_maintainable"] is True
    assert res2["ouster_applicable"] is False


# ==============================================================================
# 14. AC-18: Article 212(1)(b) State Torts, 16-Enactment Ledger & S.80 CPC
# ==============================================================================

def test_art212_tort_and_section80_pathways():
    # (a) S.80(1)(a) Federal Secretary notice satisfied
    claim_fed = {
        "has_locus_standi": True,
        "damnum_absque_injuria": False,
        "proximate_cause_established": True,
        "defendant_category": "government",
        "notice_recipient": "federal_secretary",
        "notice_delivered_months_prior": 2
    }
    res_fed = evaluate_state_tort_action(claim_fed)
    assert res_fed["overall_maintainability"] is True
    assert res_fed["gate_3_tribunal_status"] == "NO_TRIBUNAL_ESTABLISHED_ON_SEARCHED_ENACTMENTS"
    assert res_fed["gate_5_section_80_result"]["notice_status"] == "VALID_SECTION_80_NOTICE_SERVED"

    # (b) S.80(2) Trigger 1: Suit without notice -> 3-month Government WS proviso & costs disallowance
    claim_trig1 = {
        "has_locus_standi": True,
        "defendant_category": "government",
        "suit_without_notice": True,
        "settled_within_two_months": True
    }
    res_trig1 = evaluate_state_tort_action(claim_trig1)
    assert res_trig1["gate_5_section_80_result"]["government_written_statement_min_months"] == 3
    assert res_trig1["gate_5_section_80_result"]["costs_disallowed_if_settled_or_conceded"] is True

    # (c) S.80(2) Trigger 2/3: Order VIII provincial timeline (Punjab)
    claim_trig2 = {
        "has_locus_standi": True,
        "defendant_category": "government",
        "section_80_trigger": 2,
        "province": "Punjab"
    }
    res_trig2 = evaluate_state_tort_action(claim_trig2)
    assert "Order VIII Rule 1 CPC" in res_trig2["gate_5_section_80_result"]["governing_rule"]
    assert "30 days extendable up to 15 days" in res_trig2["gate_5_section_80_result"]["written_statement_timeline"]

    # (d) Art 199 writ petition exempt from Section 80 CPC
    claim_writ = {
        "suit_type": "writ_petition",
        "is_article_199": True,
        "has_locus_standi": True,
        "defendant_category": "government"
    }
    res_writ = evaluate_state_tort_action(claim_writ)
    assert res_writ["gate_5_section_80_result"]["notice_status"] == "ARTICLE_199_EXEMPT_FROM_S80_CPC"

    # (e) Indian CPC urgency leave rejected as foreign law
    claim_indian = {"pleads_urgency_leave_under_indian_cpc": True}
    res_indian = evaluate_state_tort_action(claim_indian)
    assert res_indian["status"] == "REJECTED_FOREIGN_PROCEDURAL_RULE_INDIAN_CPC_S80_2"


# ==============================================================================
# 15. AC-19 & AC-20: Enemy Property & Provincial Extension Proviso
# ==============================================================================

def test_art212_enemy_property():
    res = evaluate_art212_enemy_property({})
    assert res["status"] == "TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES"
    assert res["custodian_nature"] == "ENEMY_PROPERTY_CUSTODIAN_EXECUTIVE_JURISDICTION"
    assert res["judicial_review_maintainable"] is True


def test_art212_provincial_proviso():
    res_enacted = evaluate_art212_provincial_proviso(extension_act_enacted=True)
    assert res_enacted["ouster_applicable"] is True
    assert res_enacted["status"] == "PROVINCIAL_OUSTER_CONFIRMED"

    res_absent = evaluate_art212_provincial_proviso(extension_act_enacted=False)
    assert res_absent["ouster_applicable"] is False
    assert res_absent["status"] == "EVALUATED_UNDER_PROVINCIAL_STATUTORY_LAW"


# ==============================================================================
# 16. AC-21, AC-22, AC-23: Inheritance Limitation Tests
# ==============================================================================

def test_inheritance_art120_denial():
    # Specific Article 91 for cancellation
    res_art91 = evaluate_inheritance_limitation({"relief_sought": "cancellation_of_instrument"})
    assert res_art91["applicable_article"] == "Article 91 Limitation Act 1908"

    # Underspecified relief
    res_unres = evaluate_inheritance_limitation({"facts_specified": False})
    assert res_unres["status"] == "LIMITATION_ARTICLE_UNRESOLVED"

    # Declaratory suit with unequivocal denial on Date D -> Residuary Art 120 from Date D
    res_art120 = evaluate_inheritance_limitation({
        "relief_sought": "declaration",
        "unequivocal_hostile_denial_date": "2020-05-10"
    })
    assert res_art120["applicable_article"] == "Article 120 Limitation Act 1908"
    assert res_art120["status"] == "ARTICLE_120_APPLIED_FROM_UNEQUIVOCAL_DENIAL"


def test_inheritance_art142_dispossession():
    # Co-heir never in sole possession challenging revenue mutation -> Art 142 rejected
    res_mut = evaluate_inheritance_limitation({
        "relies_on_article_142": True,
        "prior_sole_possession": False,
        "actual_physical_ouster_proved": False
    })
    assert res_mut["status"] == "ARTICLE_142_REJECTED_NO_DISPOSSESSION"

    # Actual physical ouster proved -> Art 142 applied
    res_ouster = evaluate_inheritance_limitation({
        "relies_on_article_142": True,
        "prior_sole_possession": True,
        "actual_physical_ouster_proved": True
    })
    assert res_ouster["status"] == "ARTICLE_142_APPLIED_FROM_ACTUAL_OUSTER"


def test_inheritance_section18_fraud():
    # Bare non-communication -> fails S.18
    res_bare = evaluate_inheritance_limitation({
        "pleads_section_18_fraud": True,
        "affirmative_fraudulent_concealment_proved": False
    })
    assert res_bare["status"] == "SECTION_18_FRAUD_NOT_ESTABLISHED"

    # Affirmative intentional concealment proved -> time runs from discovery
    res_fraud = evaluate_inheritance_limitation({
        "pleads_section_18_fraud": True,
        "affirmative_fraudulent_concealment_proved": True
    })
    assert res_fraud["status"] == "SECTION_18_FRAUD_ESTABLISHED_TIME_RUNS_FROM_DISCOVERY"


# ==============================================================================
# 17. AC-24: Authentic Benami Tree, Fiduciary Exclusion & 108 States
# ==============================================================================

def test_benami_property_specific_holding():
    # (a) Statutory citation validation for Act No. V of 2017
    res_inv = evaluate_benami_transaction({"governing_act": "Act VIII of 2017"})
    assert res_inv["status"] == "INVALID_STATUTORY_CITATION"

    # (b) Redesigned completed legatee distribution under Section 2(8)(A)(b)(i)
    # Ms. Zainab (P) receives completed legacy distribution, engages Mansoor (H) as agent
    res_legatee = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "evaluate_fiduciary_route_a": True,
        "title_holder": "Mansoor",
        "consideration_provider": "Ms. Zainab",
        "held_for_benefit_of_provider": True,
        "fiduciary_capacity_established": True,
        "recognized_fiduciary_role": True,
        "property_held_in_capacity": True,
        "held_for_benefit_of_principal": True,
        "is_legatee_distribution": True,
        "executor_assent_under_s332_336": True,
        "estate_debts_discharged": True,
        "funds_in_personal_account_prior_to_purchase": True,
        "route_b_state": "NOT_ESTABLISHED",
        "route_c_state": "NOT_ESTABLISHED",
        "route_d_state": "NOT_ESTABLISHED"
    })
    assert res_legatee["status"] == "STATUTORILY_EXCLUDED_NON_BENAMI"
    assert res_legatee["typed_disposition"] == "BENAMI_EXCEPTION_ESTABLISHED"

    # (c) Inchoate / unadministered estate funds -> UNRESOLVED
    res_inchoate = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "evaluate_fiduciary_route_a": True,
        "title_holder": "Mansoor",
        "consideration_provider": "Estate",
        "held_for_benefit_of_provider": True,
        "fiduciary_capacity_established": True,
        "recognized_fiduciary_role": True,
        "property_held_in_capacity": True,
        "held_for_benefit_of_principal": True,
        "is_legatee_distribution": True,
        "executor_assent_under_s332_336": False  # Assent missing
    })
    assert res_inchoate["status"] == "BENAMI_CLASSIFICATION_UNRESOLVED"

    # (d) Route B trade name indicators vs bogus persona
    res_bogus = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "evaluate_route_b_trade_name": True,
        "invented_bogus_persona": True
    })
    assert res_bogus["status"] == "POTENTIAL_BENAMI_TRANSACTION"
    assert "ROUTE_B" in res_bogus["engaged_routes"]

    # (e) Non-Masking Invariant: Route A exception CANNOT cure Route B violation!
    res_non_mask = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "route_a_state": "EXCEPTION_ESTABLISHED",
        "route_b_state": "ESTABLISHED",
        "route_c_state": "NOT_ESTABLISHED",
        "route_d_state": "NOT_ESTABLISHED"
    })
    assert res_non_mask["status"] == "POTENTIAL_BENAMI_TRANSACTION"
    assert res_non_mask["non_masking_enforced"] is True

    # (f) Adversarial Uncertainty Fixtures BENAMI-UNCERT-01 through 04
    # UNCERT-01: Route B established, Route A unresolved -> POTENTIAL_BENAMI
    res_u1 = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "route_a_state": "UNRESOLVED",
        "route_b_state": "ESTABLISHED",
        "route_c_state": "NOT_ESTABLISHED",
        "route_d_state": "NOT_ESTABLISHED"
    })
    assert res_u1["status"] == "POTENTIAL_BENAMI_TRANSACTION"

    # UNCERT-03: Route A exception established, Route B unresolved -> UNRESOLVED
    res_u3 = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "route_a_state": "EXCEPTION_ESTABLISHED",
        "route_b_state": "UNRESOLVED",
        "route_c_state": "NOT_ESTABLISHED",
        "route_d_state": "NOT_ESTABLISHED"
    })
    assert res_u3["status"] == "BENAMI_CLASSIFICATION_UNRESOLVED"

    # (g) Formal Section 24 Adjudication Order
    res_s24 = evaluate_benami_transaction({
        "governing_act": "Act No. V of 2017",
        "is_formal_section_24_adjudication": True,
        "adjudication_provenance": {"order_no": "S24-2024-01", "authority": "Adjudicating Authority"},
        "engaged_routes": ["ROUTE_A"]
    })
    assert res_s24["status"] == "BENAMI_TRANSACTION_ADJUDICATED"

    # (h) Combinatorial State Space Sweep across 108 valid states
    # Route A (4 states) x Route B (3 states) x Route C (3 states) x Route D (3 states) = 108 states
    states_a = ["ESTABLISHED_UNEXCEPTED", "EXCEPTION_ESTABLISHED", "NOT_ESTABLISHED", "UNRESOLVED"]
    states_bcd = ["ESTABLISHED", "NOT_ESTABLISHED", "UNRESOLVED"]

    potential_count = 0
    exception_count = 0
    unresolved_count = 0
    not_benami_count = 0

    for sa in states_a:
        for sb in states_bcd:
            for sc in states_bcd:
                for sd in states_bcd:
                    sweep_res = evaluate_benami_transaction({
                        "governing_act": "Act No. V of 2017",
                        "route_a_state": sa,
                        "route_b_state": sb,
                        "route_c_state": sc,
                        "route_d_state": sd
                    })
                    status = sweep_res["status"]
                    if status == "POTENTIAL_BENAMI_TRANSACTION":
                        potential_count += 1
                        # Verify Non-Masking Invariant
                        assert (sb == "ESTABLISHED" or sc == "ESTABLISHED" or sd == "ESTABLISHED" or sa == "ESTABLISHED_UNEXCEPTED")
                    elif status == "STATUTORILY_EXCLUDED_NON_BENAMI":
                        exception_count += 1
                        assert sa == "EXCEPTION_ESTABLISHED" and sb == "NOT_ESTABLISHED" and sc == "NOT_ESTABLISHED" and sd == "NOT_ESTABLISHED"
                    elif status == "BENAMI_CLASSIFICATION_UNRESOLVED":
                        unresolved_count += 1
                    elif status == "NOT_BENAMI_TRANSACTION":
                        not_benami_count += 1
                        assert sa == "NOT_ESTABLISHED" and sb == "NOT_ESTABLISHED" and sc == "NOT_ESTABLISHED" and sd == "NOT_ESTABLISHED"

    # Exact expected counts across 108 valid states:
    assert potential_count == 84
    assert exception_count == 1
    assert unresolved_count == 22
    assert not_benami_count == 1
    assert potential_count + exception_count + unresolved_count + not_benami_count == 108


# ==============================================================================
# 18. AC-25, AC-26, AC-27: Banking & Criminal Quashment Tests
# ==============================================================================

def test_s489f_cumulative_ingredients():
    # Existing debt labeled "security" -> S.489-F attracted
    res_debt = evaluate_s489f_cheque_liability({
        "cheque_dishonored": True,
        "dishonest_intention_at_issuance": True,
        "existing_crystallized_obligation": True,
        "payee_is_financial_institution": True
    })
    assert res_debt["status"] == "SECTION_489F_ATTRACTED"
    assert res_debt["liability"] is True
    assert "Banking Court" in res_debt["competent_recovery_forum"]

    # Pure advance contingent guarantee -> S.489-F not attracted
    res_guar = evaluate_s489f_cheque_liability({
        "cheque_dishonored": True,
        "dishonest_intention_at_issuance": False,
        "existing_crystallized_obligation": False
    })
    assert res_guar["status"] == "SECTION_489F_NOT_ATTRACTED"


def test_s420_inception_intention():
    # Commercial breach without inception fraud -> FIR quashable
    res_quash = evaluate_s420_inception_intention({
        "dispute_arises_from_commercial_contract": True,
        "fraudulent_intention_at_inception": False
    })
    assert res_quash["status"] == "CRIMINAL_FRAUD_NOT_ATTRACTED"
    assert res_quash["quashment_maintainable"] is True
    assert res_quash["admitted_to_bucket"] == "Bucket 1B (Approved Cross-Domain)"


def test_s406_debtor_creditor_entrustment():
    # Sale on credit creates debtor-creditor relationship, not breach of trust
    res_credit = evaluate_s406_entrustment_vs_debt({
        "sale_of_goods_on_credit": True,
        "fiduciary_entrustment_of_property": False
    })
    assert res_credit["status"] == "DEBTOR_CREDITOR_RELATIONSHIP"
    assert res_credit["section_406_applicable"] is False


# ==============================================================================
# 19. AC-28: Twenty Adversarial Acceptance Tests (FSC/SAB, Precedents & Art 202A)
# ==============================================================================

def test_amended_art189_precedent_binding():
    # 1. test_fsc_reversal_sentence_15_years
    res1 = evaluate_art203f_appeal_forum({
        "is_acquittal_reversal": True,
        "sentence_years": 15,
        "forum_authenticated_by_rules_or_precedent": True
    })
    assert res1["appeal_type"] == "APPEAL_AS_OF_RIGHT"

    # 2. test_fsc_reversal_sentence_exact_14_years (14 is NOT exceeding 14)
    res2 = evaluate_art203f_appeal_forum({
        "is_acquittal_reversal": True,
        "sentence_years": 14
    })
    assert res2["appeal_type"] == "LEAVE_TO_APPEAL_REQUIRED"

    # 3. test_fsc_reversal_life_imprisonment
    res3 = evaluate_art203f_appeal_forum({
        "is_acquittal_reversal": True,
        "sentence_type": "life_imprisonment",
        "forum_authenticated_by_rules_or_precedent": True
    })
    assert res3["appeal_type"] == "APPEAL_AS_OF_RIGHT"

    # 4. test_fsc_contempt_punishment
    res4 = evaluate_art203f_appeal_forum({
        "is_contempt_punishment": True,
        "forum_authenticated_by_rules_or_precedent": True
    })
    assert res4["appeal_type"] == "APPEAL_AS_OF_RIGHT"
    assert "Contempt of Court" in res4["category"]

    # 5. test_fsc_ordinary_sentence_outside_2a (5 years)
    res5 = evaluate_art203f_appeal_forum({"sentence_years": 5})
    assert res5["appeal_type"] == "LEAVE_TO_APPEAL_REQUIRED"

    # 6. test_art203d_final_repugnancy_limitations
    res6 = evaluate_art203f_appeal_forum({
        "decision_type": "art_203d_repugnancy",
        "appellant_type": "party_aggrieved"
    })
    assert res6["appeal_type"] == "APPEAL_AS_OF_RIGHT"
    assert res6["limitation_period_days"] == 60
    assert res6["repugnancy_operation_suspended"] is True

    # 7. test_fsc_revision_sentence_enhanced_15_years
    res7 = evaluate_art203f_appeal_forum({
        "is_revision_enhancement": True,
        "sentence_years": 15,
        "forum_authenticated_by_rules_or_precedent": True
    })
    assert res7["appeal_type"] == "APPEAL_AS_OF_RIGHT"
    assert "second limb" in res7["category"]

    # 8. test_fsc_revision_sentence_enhanced_exact_14_years
    res8 = evaluate_art203f_appeal_forum({
        "is_revision_enhancement": True,
        "sentence_years": 14
    })
    assert res8["appeal_type"] == "LEAVE_TO_APPEAL_REQUIRED"

    # 9. test_fsc_revision_sentence_enhanced_life_imprisonment
    res9 = evaluate_art203f_appeal_forum({
        "is_revision_enhancement": True,
        "sentence_type": "life_imprisonment",
        "forum_authenticated_by_rules_or_precedent": True
    })
    assert res9["appeal_type"] == "APPEAL_AS_OF_RIGHT"

    # 10. test_fsc_revision_sentence_enhanced_death
    res10 = evaluate_art203f_appeal_forum({
        "is_revision_enhancement": True,
        "sentence_type": "death",
        "forum_authenticated_by_rules_or_precedent": True
    })
    assert res10["appeal_type"] == "APPEAL_AS_OF_RIGHT"

    # 11. test_ihc_activation_resolution_verified
    res11 = evaluate_art202a_constitutional_bench({
        "target_court": "IHC",
        "resolution_passed": True,
        "majority_of_total_membership": True,
        "jcp_nominated": True,
        "committee_hearing_bench_constituted": True,
        "activating_province": "Federal",
        "target_province": "Federal"
    })
    assert res11["operationalized"] is True

    # 12. test_provincial_resolution_isolation
    res12 = evaluate_art202a_constitutional_bench({
        "target_court": "SHC",
        "resolution_passed": True,
        "majority_of_total_membership": True,
        "activating_province": "Punjab",  # Punjab resolution
        "target_province": "Sindh"        # Target court is Sindh
    })
    assert res12["status"] == "PROVINCIAL_ISOLATION_INVARIANT_PRESERVED"
    assert res12["operationalized"] is False

    # 13. test_ihc_resolution_passes_jcp_unverified
    res13 = evaluate_art202a_constitutional_bench({
        "target_court": "IHC",
        "resolution_passed": True,
        "majority_of_total_membership": True,
        "jcp_nominated": False,  # JCP unverified
        "activating_province": "Federal",
        "target_province": "Federal"
    })
    assert res13["status"] == "ARTICLE_202A_COMPETENCE_UNVERIFIED_ESCALATE_HUMAN_REVIEW"

    # 14. test_constitutional_bench_hearing_bench_improperly_constituted
    res14 = evaluate_art202a_constitutional_bench({
        "target_court": "LHC",
        "resolution_passed": True,
        "majority_of_total_membership": True,
        "jcp_nominated": True,
        "committee_hearing_bench_constituted": False,  # Defective committee
        "activating_province": "Punjab",
        "target_province": "Punjab"
    })
    assert res14["status"] == "HEARING_BENCH_CONSTITUTION_UNVERIFIED"

    # 15. test_provincial_resolution_fails_total_membership
    res15 = evaluate_art202a_constitutional_bench({
        "target_court": "LHC",
        "resolution_passed": True,
        "majority_of_total_membership": False,  # Fails total membership
        "activating_province": "Punjab",
        "target_province": "Punjab"
    })
    assert res15["status"] == "PROVINCIAL_ACTIVATION_FAILED_RESOLUTION_INVALID"

    # 16. test_art199_historical_clause5_transfer
    res16 = evaluate_art202a_constitutional_bench({
        "target_court": "LHC",
        "resolution_passed": True,
        "majority_of_total_membership": True,
        "jcp_nominated": True,
        "committee_hearing_bench_constituted": True,
        "is_historical_pre_oct_2024_petition": True,
        "petition_clause": "199_1_c"  # Fundamental rights under 199(1)(c)
    })
    assert res16["status"] == "TRANSFERRED_UNDER_ARTICLE_202A_5"
    assert res16["transferred_to_constitutional_bench"] is True

    # 17. test_art199_historical_petition_outside_clause5
    res17 = evaluate_art202a_constitutional_bench({
        "target_court": "LHC",
        "resolution_passed": True,
        "majority_of_total_membership": True,
        "jcp_nominated": True,
        "committee_hearing_bench_constituted": True,
        "is_historical_pre_oct_2024_petition": True,
        "petition_clause": "199_1_a_ii"  # Certiorari outside clause 5
    })
    assert res17["status"] == "NOT_TRANSFERRED_UNDER_NARROW_CLAUSE_5"
    assert res17["transferred_to_constitutional_bench"] is False

    # 18. test_fcc_vs_supreme_court_conflict
    res18 = evaluate_precedent_hierarchy_and_conflict({
        "court_a": "Federal Constitutional Court of Pakistan",
        "court_b": "Supreme Court of Pakistan",
        "is_constitutional_question": True
    })
    assert res18["status"] == "FCC_RATIO_CONTROLS_ACROSS_TIERS"

    # 19. test_sab_vs_fsc_conflict
    res19 = evaluate_precedent_hierarchy_and_conflict({
        "court_a": "Shariat Appellate Bench of Supreme Court",
        "court_b": "Federal Shariat Court"
    })
    assert res19["status"] == "SAB_DECISION_CONTROLS_OVER_FSC"

    # 20. test_art203f2a_appellate_forum_unresolved_escalate
    res20 = evaluate_art203f_appeal_forum({
        "is_acquittal_reversal": True,
        "sentence_years": 15,
        "forum_authenticated_by_rules_or_precedent": False  # Unverified
    })
    assert res20["appellate_forum"] == "APPELLATE_FORUM_UNRESOLVED_ESCALATE_HUMAN_REVIEW"


# ==============================================================================
# 20. AC-29: Serialized Request Recount & Non-ASCII Overflow Boundary
# ==============================================================================

def test_native_tokenizer_full_payload_boundary():
    # Verify recount across full payload with system XML overhead
    system_xml = "<system_instructions>You are a legal AI.</system_instructions>"
    cand_block = "### [CASE AUTHORITY] 2024 SCMR 100\nJudgment ratio text."
    tokens = count_context_tokens([cand_block], system_overhead_text=system_xml)
    assert tokens > 0
    assert tokens < 100

    # Non-ASCII ratio test: mixed English with some Urdu (< 15%) is accepted
    mixed_text = ("Standard English legal judgment with ratio decidendi. " * 20) + "مفاد عامہ"
    tokens_mixed = count_context_tokens([mixed_text])
    assert tokens_mixed < MAX_CANDIDATE_TOKENS  # Accepted


# ==============================================================================
# 21. AC-12: Benchmark Evaluator Doctrine Awareness
# ==============================================================================

def test_benchmark_evaluator_doctrine_awareness():
    """
    AC-12: Verifies that benchmark evaluation scores Bucket 1B cross-domain doctrine
    candidates as legitimate primary authorities without false contamination penalty.
    """
    plan = MockQueryPlan(
        primary_domain="criminal",
        is_cross_domain_relevant=True,
        cross_domain_controlling_doctrines=["DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT"]
    )
    cross_cand = {
        "id": "cand_hamid_ali",
        "citation": "PLD 2023 SC 265",
        "title": "Hamid Ali Shah v. State",
        "text": "Quash of criminal proceedings under Section 420 PPC arising from civil contract without fraud at inception",
        "semantic_relevance_score": 0.90,
        "domain": "criminal"
    }

    partitioned, telem = partition_candidates_into_ranking_buckets([cross_cand], plan, strict_mode=True)
    assert telem["bucket_1b_count"] == 1
    assert telem["bucket_3_count"] == 0
    assert partitioned[0]["ranking_bucket"] == 1
    assert partitioned[0]["bucket_subtier"] == "1B"
    assert partitioned[0]["validation_status"] == "APPROVED_CROSS_DOMAIN"
    # Admitted to LLM context
    context, included, _, _ = assemble_generation_context([cross_cand], plan)
    assert len(included) == 1
    assert included[0]["id"] == "cand_hamid_ali"
    assert "Hamid Ali Shah" in context

