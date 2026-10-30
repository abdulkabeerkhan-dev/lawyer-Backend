import pytest
from core.legal_query_planner import create_deterministic_fallback_plan
from core.authority_ranking import is_irrelevant_subject, calculate_authority_score, rank_and_filter_authorities
from legal_ai.synthesis.memorandum_generator import filter_and_cap_authorities

def test_partition_relevance_gates_authority():
    q = "partition of family land among legal heirs"
    plan = create_deterministic_fallback_plan(q)
    assert "partition & property" in plan.legal_domain
    assert any("order xx rule 18" in p.lower() for p in plan.provisions)

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

    # Invariant: An irrelevant Supreme Court case must be gated to 0.0,
    # while the relevant High Court authority outranks it.
    assert sc_score == 0.0, f"Expected 0.0 for unrelated SC case, got {sc_score}"
    assert hc_score > 50.0, f"Expected > 50.0 for relevant HC case, got {hc_score}"

def test_family_khula_cross_domain_isolation():
    q = "khula and return of dower without husband consent"
    plan = create_deterministic_fallback_plan(q)
    assert "family law" in plan.legal_domain
    assert any("family courts act" in p.lower() for p in plan.provisions)
    lane_names = [l["lane"] for l in plan.search_lanes]
    assert "khula_without_consent" in lane_names

    # Candidate leaks that must be rejected
    banking_leak = {
        "citation": "2026 CLD 292",
        "title": "SALMAN CAPITAL VS HBL",
        "preview": "financial institutions recovery of finances ordinance 2001 loan default banking court",
        "court": "Lahore High Court"
    }
    corporate_leak = {
        "citation": "2024 CLD 500",
        "title": "ABC TEXTILE VS XYZ",
        "preview": "companies act 2017 shareholder oppression and mismanagement secp board of directors",
        "court": "Lahore High Court"
    }
    khula_landmark = {
        "citation": "PLD 1967 SC 97",
        "title": "KHURSHID BIBI VS MUHAMMAD AMIN",
        "preview": "dissolution of marriage khula wife right without husband consent zar-i-khula dower",
        "court": "Supreme Court of Pakistan"
    }

    assert is_irrelevant_subject(banking_leak, plan) is True
    assert is_irrelevant_subject(corporate_leak, plan) is True
    assert is_irrelevant_subject(khula_landmark, plan) is False

def test_rent_eviction_cross_domain_isolation():
    q = "eviction of commercial tenant for non-payment of rent in lahore"
    plan = create_deterministic_fallback_plan(q)
    assert "rent restriction" in plan.legal_domain
    lane_names = [l["lane"] for l in plan.search_lanes]
    assert "rent_tribunal_exclusive_jurisdiction" in lane_names
    assert "rent_default_eviction_s15" in lane_names

    criminal_bail_leak = {
        "citation": "2025 PCrLJ 100",
        "title": "STATE VS ACCUSED",
        "preview": "bail petition section 497 crpc post-arrest bail non-bailable offence",
        "court": "Lahore High Court"
    }
    rent_precedent = {
        "citation": "2023 SCMR 500",
        "title": "TENANT VS LANDLORD",
        "preview": "punjab rented premises act 2009 section 15 eviction for default in payment of rent",
        "court": "Supreme Court of Pakistan"
    }

    assert is_irrelevant_subject(criminal_bail_leak, plan) is True
    assert is_irrelevant_subject(rent_precedent, plan) is False

def test_banking_recovery_cross_domain_isolation():
    q = "banking court leave to defend application delay condonation under FIO 2001"
    plan = create_deterministic_fallback_plan(q)
    assert "banking recovery" in plan.legal_domain
    assert any("fio" in p.lower() or "financial institutions" in p.lower() for p in plan.provisions)
    lane_names = [l["lane"] for l in plan.search_lanes]
    assert "fio_leave_to_defend_s10" in lane_names

    family_leak = {
        "citation": "2022 SCMR 300",
        "title": "WIFE VS HUSBAND",
        "preview": "family court custody of minor children guardians and wards act hizanat",
        "court": "Supreme Court of Pakistan"
    }
    banking_precedent = {
        "citation": "2026 CLD 100",
        "title": "BANK VS BORROWER",
        "preview": "section 10 financial institutions recovery of finances ordinance 2001 leave to defend 30 days mandatory",
        "court": "Lahore High Court"
    }

    assert is_irrelevant_subject(family_leak, plan) is True
    assert is_irrelevant_subject(banking_precedent, plan) is False

def test_filter_and_cap_universal_sanitization():
    q = "khula and dissolution of marriage without husband consent"
    plan = create_deterministic_fallback_plan(q)
    candidates = [
        {"citation": "2026 CLD 292", "court": "Lahore High Court", "preview": "financial institutions recovery of finances ordinance 2001 loan default"},
        {"citation": "2025 PCrLJ 50", "court": "Karachi High Court", "preview": "section 302 ppc murder trial firearm injury"},
        {"citation": "PLD 1967 SC 97", "court": "Supreme Court of Pakistan", "preview": "khula wife right without husband consent dissolution of marriage"},
        {"citation": "2024 SCMR 800", "court": "Supreme Court of Pakistan", "preview": "family courts act 1964 section 10 reconciliation failure decree for khula"}
    ]
    retained = filter_and_cap_authorities(candidates, query_plan=plan, query_text=q)
    retained_cits = [c["citation"] for c in retained]
    assert "2026 CLD 292" not in retained_cits
    assert "2025 PCrLJ 50" not in retained_cits
    assert "PLD 1967 SC 97" in retained_cits
    assert "2024 SCMR 800" in retained_cits
