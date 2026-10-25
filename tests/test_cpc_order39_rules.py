"""
tests/test_cpc_order39_rules.py

Verifies that CPC Order XXXIX Rules 2A, 2B, and 4A are recognized as authentic
Pakistani statutory provisions in the Pakistan Code and are answered directly
from the store, distinguishing Rule 2A (15-day ex-parte injunction limit)
from Rule 2(3) (penalty for disobedience/breach of injunction).
"""

import pytest
from legal_ai.statutes.statute_store import get_statute_store, lookup
from core.legal_query_planner import create_deterministic_fallback_plan, check_query_premises


def test_order_xxxix_rule_2a_answered_from_store():
    """Rule 2A exists in Pakistan CPC (inserted by Act XIV of 1994, s. 11) for 15-day ex-parte duration."""
    res = lookup("CPC_1908", "Order XXXIX Rule 2A")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.canonical_id == "CPC_1908_ORD_XXXIX_R_2A"
    assert res.text is not None
    assert "fifteen days" in res.text.lower()
    assert "in the absence of defendant" in res.text.lower()


def test_order_xxxix_rule_2b_answered_from_store():
    """Rule 2B exists in Pakistan CPC (inserted by Act XIV of 1994, s. 11) for 6-month expiry after notice."""
    res = lookup("CPC_1908", "Order XXXIX Rule 2B")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.canonical_id == "CPC_1908_ORD_XXXIX_R_2B"
    assert res.text is not None
    assert "six months" in res.text.lower()
    assert "after notice to the defendant" in res.text.lower()


def test_order_xxxix_rule_4a_answered_from_store():
    """Rule 4A exists in Pakistan CPC (inserted by Act XV of 1976 / Ord XXV of 1977) for injunctions against public revenues."""
    res = lookup("CPC_1908", "Order XXXIX Rule 4A")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.canonical_id == "CPC_1908_ORD_XXXIX_R_4A"
    assert res.text is not None
    assert "public revenues" in res.text.lower()
    assert "six months" in res.text.lower()


def test_order_xxxix_rule_2_3_governs_breach_and_disobedience():
    """Disobedience or breach of injunction in Pakistan is governed by Rule 2(3), not Rule 2A."""
    res = lookup("CPC_1908", "Order XXXIX Rule 2(3)")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.text is not None
    assert "disobedience" in res.text.lower()
    assert "attached" in res.text.lower()
    assert "prison" in res.text.lower()

    # Rule 2A queried in breach context includes explanation distinguishing Rule 2A from Rule 2(3)
    res_breach = lookup("CPC_1908", "Order XXXIX Rule 2A for breach of stay order")
    assert res_breach.status == "EXISTS"
    assert res_breach.explanation is not None
    assert "Order XXXIX Rule 2(3) CPC" in res_breach.explanation


def test_planning_order_xxxix_rule_2a_query():
    """A user query on Order XXXIX Rule 2A plans correctly without marking Rule 2A absent."""
    q = "What is the maximum duration of an ex-parte interim injunction under Order XXXIX Rule 2A CPC in Pakistan?"
    checks = check_query_premises(q)
    assert len(checks) >= 1
    r2a_check = [c for c in checks if "2A" in c.get("queried_provision", "").upper()][0]
    assert r2a_check["status"] == "EXISTS"

    plan = create_deterministic_fallback_plan(q)
    assert any("2A" in p for p in plan.provisions)
