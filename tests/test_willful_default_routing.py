import pytest
from core.legal_query_planner import create_deterministic_fallback_plan
from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern


def test_willful_default_classification():
    query = "What is willful default under Pakistani law?"
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "banking"
    assert "criminal" in plan.secondary_domains or "civil" in plan.secondary_domains
    assert any("Financial Institutions" in s for s in plan.governing_statutes)
    assert any("2" in p for p in plan.statutory_provisions)
    assert any("20" in p for p in plan.statutory_provisions)
    assert any("Section 20" in q or "willful default" in q.lower() for q in plan.core_legal_issues)
    assert any("willful" in l.lane.lower() for l in plan.search_lanes)


def test_willful_default_30_day_notice_inquiry():
    query = "Can a bank initiate criminal trial for willful default without 30 days demand notice?"
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "banking"
    assert "criminal" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "Section 20" in plan.procedural_remedy
    assert any("notice" in q.lower() or "30 days" in q.lower() for q in plan.core_legal_issues)


def test_willful_default_issue_decomposition():
    query = "The borrower was declared a willful defaulter by the bank and summoned under Section 20 of FIO 2001"
    decomp = extract_legal_issues_from_fact_pattern(query)

    assert decomp.primary_domain == "banking"
    willful_issues = [iss for iss in decomp.issues if iss.issue_id == "issue_banking_willful_default"]
    assert len(willful_issues) > 0
    issue = willful_issues[0]
    assert any("Financial Institutions" in s for s in issue.controlling_statutes)
    assert "FIO_2001_SEC_20" in issue.controlling_provisions
    assert "FIO_2001_SEC_2" in issue.controlling_provisions
