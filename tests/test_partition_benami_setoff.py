import pytest
from core.legal_query_planner import create_deterministic_fallback_plan
from core.authority_ranking import is_irrelevant_subject, rank_and_filter_authorities, calculate_authority_score
from legal_ai.synthesis.memorandum_generator import filter_and_cap_authorities

def test_partition_benami_query_plan_lanes():
    q = "give me more judgments on partition and benami as a set off claim"
    plan = create_deterministic_fallback_plan(q)
    lane_names = [l["lane"] for l in plan.search_lanes]
    assert "partition_set_off_inapplicability" in lane_names
    assert "partition_counter_claim_cross_suit" in lane_names
    assert "partition_order20_rule18_partial_partition" in lane_names
    assert "benami_statutory_bar_section4" in lane_names

def test_partition_authority_filter_excludes_unrelated():
    q = "give me more judgments on partition and benami as a set off claim"
    plan = create_deterministic_fallback_plan(q)
    
    # 2001 YLR 2537 is a cooperative housing society internal membership dispute
    card_society = {
        "citation": "2001 YLR 2537",
        "title": "AMIR ALI HUSSAIN SHALWANI VS ISMAILI MASALWALA",
        "preview": "dispute between member and cooperative housing society officers regarding allotment of share in society and benami claim",
        "court": "Karachi High Court"
    }
    assert is_irrelevant_subject(card_society, plan) is True

    # 2026 CLD 292 is a banking recovery dispute regarding pawnor pledged shares
    card_banking = {
        "citation": "2026 CLD 292",
        "title": "SALMAN CAPITAL INVESTMENTS VS HBL",
        "preview": "financial institutions recovery of finances ordinance 2001 pawnor pledge of shares banking court",
        "court": "Lahore High Court"
    }
    assert is_irrelevant_subject(card_banking, plan) is True

    # 2026 SCMR 941 is a Supreme Court partition suit case
    card_sc = {
        "citation": "2026 SCMR 941",
        "title": "SHAHBAZ KHAN VS DOWLAT KHAN",
        "preview": "partition of ancestral estate family settlement preliminary decree Order XX Rule 18 CPC partial partition impermissible",
        "court": "Supreme Court of Pakistan",
        "year": 2026
    }
    assert is_irrelevant_subject(card_sc, plan) is False

    # 2006 YLR 2059 is partition suit co-sharer counter-claim precedent
    card_lhc = {
        "citation": "2006 YLR 2059",
        "title": "Khawaja NAYYAR QAYYUM VS ZUBAIR QAYYUM",
        "preview": "suit for partition co-sharers properties in name of other persons proper remedy independent suit counter claim",
        "court": "Lahore High Court",
        "year": 2006
    }
    assert is_irrelevant_subject(card_lhc, plan) is False

def test_filter_and_cap_retains_only_partition_precedents():
    q = "give me more judgments on partition and benami as a set off claim"
    plan = create_deterministic_fallback_plan(q)
    candidates = [
        {"citation": "2001 YLR 2537", "court": "Karachi High Court", "preview": "cooperative housing society membership dispute"},
        {"citation": "2026 CLD 292", "court": "Lahore High Court", "preview": "financial institutions recovery of finances ordinance 2001"},
        {"citation": "2026 SCMR 941", "court": "Supreme Court of Pakistan", "preview": "suit for partition ancestral estate Order XX Rule 18 CPC"},
        {"citation": "2006 YLR 2059", "court": "Lahore High Court", "preview": "suit for partition co-sharers proper remedy counter claim"},
        {"citation": "2006 YLR 2289", "court": "Lahore High Court", "preview": "partition suit partial partition impermissible"}
    ]
    retained = filter_and_cap_authorities(candidates, query_plan=plan, query_text=q)
    retained_cits = [c["citation"] for c in retained]
    assert "2001 YLR 2537" not in retained_cits
    assert "2026 CLD 292" not in retained_cits
    assert "2026 SCMR 941" in retained_cits
    assert "2006 YLR 2059" in retained_cits
    assert "2006 YLR 2289" in retained_cits
