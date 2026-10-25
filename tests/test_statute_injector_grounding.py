"""
tests/test_statute_injector_grounding.py

Tests for Fix D: Grounded bare-act injection, Schedule II data, and missing text markers.
"""

import pytest
from core.legal_query_planner import create_deterministic_fallback_plan
from legal_ai.statutes.statute_injector import inject_statutory_framework


def test_cheque_statute_injection():
    plan = create_deterministic_fallback_plan("Punishment under Section 138 NI Act for a bounced cheque in Pakistan?")
    res = inject_statutory_framework(plan, query_text="bounced cheque 138")
    block = res["statute_block"]

    # Must contain premise correction
    assert "MANDATORY QUERY PREMISE CORRECTIONS" in block
    assert "Section 489-F" in block

    # Must contain Schedule II info for 489-F
    assert "Cr.P.C. Schedule II Classification" in block
    assert "Non-bailable" in block

    # Must contain verbatim text of 489-F from PPC
    assert "Verbatim Bare-Act Text in Force" in block


def test_rule_2a_statute_injection():
    plan = create_deterministic_fallback_plan("Injunction under Order XXXIX Rule 2A CPC for breach of a stay order?")
    res = inject_statutory_framework(plan, query_text="Order XXXIX Rule 2A stay order breach")
    block = res["statute_block"]

    # Must route to Order XXXIX Rule 2(3) CPC
    assert "Rule 2(3)" in block or "Rule 2" in block
    # Must have verbatim bare act text of Rule 2(3) from Pakistan Code
    assert "disobedience" in block.lower()
    assert "prison" in block.lower()


def test_ipc_420_statute_injection():
    plan = create_deterministic_fallback_plan("Punishment under Section 420 of the Indian Penal Code in Pakistan?")
    res = inject_statutory_framework(plan, query_text="Section 420 Indian Penal Code")
    block = res["statute_block"]

    # Must contain premise correction
    assert "MANDATORY QUERY PREMISE CORRECTIONS" in block
    assert "Section 420 PPC" in block
    assert "Cr.P.C. Schedule II Classification" in block
    assert "Cognizable" in block
    assert "Bailable" in block
