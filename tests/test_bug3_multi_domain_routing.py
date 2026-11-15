"""
tests/test_bug3_multi_domain_routing.py
Verification test for Bug 3: Multi-domain routing opening corporate, criminal, and banking lanes.
"""

from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern, extract_named_statute_canonical_ids
from core.legal_query_planner import create_deterministic_fallback_plan


def test_complex_corporate_multi_domain_decomposition():
    query = (
        "Minority shareholder alleging oppression and mismanagement by majority directors under "
        "Section 286 Companies Act 2017 for siphoning corporate assets and illegal share allotment, "
        "falsification of accounts under Section 477-A PPC, criminal breach of trust under Section 406 PPC, "
        "and bank enforcing personal guarantee against director under FIO 2001 and Section 128 Contract Act."
    )

    # 1. Test Fact Pattern Decomposition directly
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain="corporate")

    assert decomp.primary_domain == "corporate", f"Expected primary domain corporate, got {decomp.primary_domain}"
    assert "criminal" in decomp.secondary_domains, f"Expected criminal in secondary domains: {decomp.secondary_domains}"
    assert "banking" in decomp.secondary_domains, f"Expected banking in secondary domains: {decomp.secondary_domains}"

    issue_ids = [iss.issue_id for iss in decomp.issues]
    print("Extracted issue IDs:", issue_ids)

    # Verify corporate lane opened
    assert "issue_corporate_oppression_mismanagement" in issue_ids, f"Corporate lane missing: {issue_ids}"

    # Verify criminal lane opened (both CBT 406 and Falsification 477-A)
    assert "issue_cbt_406_ppc" in issue_ids, f"Criminal CBT lane missing: {issue_ids}"
    assert "issue_falsification_accounts_477a_ppc" in issue_ids, f"Criminal falsification lane missing: {issue_ids}"

    # Verify banking lane opened (both personal guarantee under Sec 128 and FIO recovery suit)
    assert "issue_banking_personal_guarantee_liability" in issue_ids, f"Banking guarantee lane missing: {issue_ids}"
    assert "issue_banking_recovery_suit" in issue_ids, f"Banking recovery lane missing: {issue_ids}"

    # 2. Test Full Query Planner Integration
    plan = create_deterministic_fallback_plan(query)
    assert plan.primary_domain == "corporate"
    assert "criminal" in plan.secondary_domains
    assert "banking" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True

    plan_lane_names = [l.lane_id if hasattr(l, "lane_id") else l.get("lane") for l in plan.search_lanes]
    print("Plan search lanes:", plan_lane_names)
    assert "issue_corporate_oppression_mismanagement" in plan_lane_names
    assert any("cbt" in name or "falsification" in name for name in plan_lane_names)
    assert any("guarantee" in name or "banking" in name for name in plan_lane_names)

    # Verify all 3 domains' statutes are retained
    statute_names = " ".join(plan.governing_statutes)
    assert "Companies" in statute_names
    assert "Penal Code" in statute_names
    assert "Financial Institutions" in statute_names or "Contract" in statute_names

    # 3. Test Named Statute Canonical IDs direct lookup
    cids = extract_named_statute_canonical_ids(query)
    print("Named CIDs:", cids)
    assert any("COMPANIES_2017" in c for c in cids), f"Companies canonical ID missing in {cids}"
    assert any("PPC_1860_SEC_477A" in c or "PPC_1860" in c for c in cids), f"PPC canonical ID missing in {cids}"
    assert any("CONTRACT_1872_SEC_128" in c or "CONTRACT_1872" in c for c in cids), f"Contract canonical ID missing in {cids}"


def test_isolated_domains_not_cross_contaminated():
    """Verify single-domain queries stay isolated and don't trigger false multi-domain lanes."""
    # Murder bail query
    bail_query = "Pre-arrest bail under Section 498 CrPC in FIR under Section 302 PPC murder allegation."
    decomp_bail = extract_legal_issues_from_fact_pattern(bail_query, planner_domain="criminal")
    assert decomp_bail.primary_domain == "criminal"
    assert "corporate" not in decomp_bail.secondary_domains
    assert "banking" not in decomp_bail.secondary_domains
    bail_issue_ids = [iss.issue_id for iss in decomp_bail.issues]
    assert "issue_corporate_oppression_mismanagement" not in bail_issue_ids
    assert "issue_banking_recovery_suit" not in bail_issue_ids

    # Rent eviction query
    rent_query = "Ejectment application under Section 15 Punjab Rented Premises Act 2009 for default in rent payment."
    decomp_rent = extract_legal_issues_from_fact_pattern(rent_query, planner_domain="rent")
    assert decomp_rent.primary_domain == "rent"
    assert "corporate" not in decomp_rent.secondary_domains
    assert "criminal" not in decomp_rent.secondary_domains
    rent_issue_ids = [iss.issue_id for iss in decomp_rent.issues]
    assert "issue_corporate_oppression_mismanagement" not in rent_issue_ids
    assert "issue_cbt_406_ppc" not in rent_issue_ids


if __name__ == "__main__":
    test_complex_corporate_multi_domain_decomposition()
    test_isolated_domains_not_cross_contaminated()
    print("All tests passed successfully!")
