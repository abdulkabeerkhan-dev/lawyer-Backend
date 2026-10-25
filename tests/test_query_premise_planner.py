"""
tests/test_query_premise_planner.py

Tests for Fix B: Query premise checks and routing in legal_query_planner.
"""

import pytest
from core.legal_query_planner import create_deterministic_fallback_plan, check_query_premises


def test_ni_act_138_query_planning():
    q = "What is the punishment under Section 138 of the Negotiable Instruments Act for a bounced cheque in Pakistan?"
    checks = check_query_premises(q)
    assert len(checks) >= 1
    ni_check = [c for c in checks if "138" in c.get("queried_provision", "")][0]
    assert ni_check["status"] == "CONFIRMED_ABSENT"
    assert ni_check["is_foreign"] is True
    assert "489-F" in ni_check["pakistani_equivalent"]

    plan = create_deterministic_fallback_plan(q)
    assert len(plan.premise_corrections) >= 1
    # Provisions must route to Pakistani law
    assert any("489-F" in p for p in plan.provisions)
    assert not any("138" in p for p in plan.provisions)
    # Search lanes must route to 489-F
    assert any("489-F" in l.get("query", "") for l in plan.search_lanes)
    assert not any("138" in l.get("query", "") for l in plan.search_lanes)


def test_ipc_420_query_planning():
    q = "What is the punishment under Section 420 of the Indian Penal Code in Pakistan?"
    checks = check_query_premises(q)
    assert len(checks) >= 1
    ipc_check = [c for c in checks if "420" in c.get("queried_provision", "")][0]
    assert ipc_check["status"] == "CONFIRMED_ABSENT"
    assert ipc_check["is_foreign"] is True
    assert ipc_check["schedule_ii"]["bailable_status"] == "Non-bailable"
    assert ipc_check["schedule_ii"]["bailable"] is False

    plan = create_deterministic_fallback_plan(q)
    assert len(plan.premise_corrections) >= 1
    assert any("420 PPC" in p for p in plan.provisions)
    assert not any("Indian" in p or "IPC" in p for p in plan.provisions)


def test_cpc_order_xxxix_rule_2a_planning():
    q = "Can an interim injunction be enforced under Order XXXIX Rule 2A CPC for breach of a stay order in Pakistan?"
    checks = check_query_premises(q)
    assert len(checks) >= 1
    r2a_check = [c for c in checks if "2A" in c.get("queried_provision", "").upper()][0]
    assert r2a_check["status"] == "EXISTS"

    plan = create_deterministic_fallback_plan(q)
    assert any("Rule 2(3)" in p or "Rule 2" in p for p in plan.provisions)
    assert any("Rule 2A" in p for p in plan.provisions)
    assert any("injunction_breach_rule_2_3" in l.get("lane", "") for l in plan.search_lanes)
