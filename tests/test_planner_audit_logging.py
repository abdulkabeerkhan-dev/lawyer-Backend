"""
tests/test_planner_audit_logging.py

Tests planner path audit logging in core/legal_query_planner.py:analyze_legal_query.
Verifies all 5 execution branches:
1. Short query -> deterministic_fallback, reason='query_too_short'
2. No AI client provided -> deterministic_fallback, reason='no_ai_client_provided'
3. AI client timeout -> deterministic_fallback, reason='ai_client_timeout'
4. AI client error -> deterministic_fallback, reason='ai_client_exception: ...'
5. Successful AI client response -> llm_planner
"""

import os
import sys
import json
import pytest
import asyncio
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.legal_query_planner import analyze_legal_query
LOG_FILE = os.path.join(REPO_ROOT, "logs", "planner_query_audit.jsonl")


@pytest.mark.asyncio
async def test_planner_audit_logging():
    # Clear log file before test
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    # 1. Short query (<10 chars)
    plan1 = await analyze_legal_query("short")
    assert plan1 is not None

    # 2. No AI client provided
    plan2 = await analyze_legal_query(
        "My client was arrested under Section 302 PPC and seeks bail under Section 497 CrPC."
    )
    assert plan2 is not None

    # 3. AI client timeout
    async def mock_timeout(**kwargs):
        raise asyncio.TimeoutError()

    plan3 = await analyze_legal_query(
        "Landlord filed ejectment application under Section 15 PRPA 2009 for default.",
        ai_client_fn=mock_timeout
    )
    assert plan3 is not None

    # 4. AI client exception
    async def mock_exc(**kwargs):
        raise ValueError("Anthropic gateway connection closed unexpectedly")

    plan4 = await analyze_legal_query(
        "Suit for recovery under Section 9 FIO 2001 and leave to defend under Section 10.",
        ai_client_fn=mock_exc
    )
    assert plan4 is not None

    # 5. Successful AI client response
    async def mock_success(**kwargs):
        mock_resp = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = json.dumps({
            "primary_domain": "family",
            "statutory_provisions": ["Section 10 Family Courts Act, 1964", "Section 9 Muslim Family Laws Ordinance, 1961"],
            "core_legal_issues": ["Dissolution of marriage by Khula", "Maintenance of minor children"],
            "governing_statutes": ["Family Courts Act, 1964", "Muslim Family Laws Ordinance, 1961"]
        })
        mock_resp.content = [mock_block]
        return mock_resp

    plan5 = await analyze_legal_query(
        "Wife filed for Khula and recovery of prompt dower and maintenance.",
        ai_client_fn=mock_success
    )
    assert plan5 is not None

    # Verify log output file
    assert os.path.exists(LOG_FILE), "Log file was not created"
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    assert len(records) >= 5, f"Expected at least 5 audit records, found {len(records)}"

    rec1, rec2, rec3, rec4, rec5 = records[-5:]

    # Check Record 1: Short query
    assert rec1["path_taken"] == "deterministic_fallback"
    assert rec1["fallback_reason"] == "query_too_short"

    # Check Record 2: No AI client
    assert rec2["path_taken"] == "deterministic_fallback"
    assert rec2["fallback_reason"] == "no_ai_client_provided"
    assert rec2["primary_domain"] == "criminal"

    # Check Record 3: Timeout
    assert rec3["path_taken"] == "deterministic_fallback"
    assert rec3["fallback_reason"] == "ai_client_timeout"

    # Check Record 4: Exception
    assert rec4["path_taken"] == "deterministic_fallback"
    assert "ai_client_exception" in rec4["fallback_reason"]

    # Check Record 5: Success
    assert rec5["path_taken"] == "llm_planner"
    assert rec5["fallback_reason"] is None
    assert rec5["primary_domain"] == "family"
    assert "Section 10 Family Courts Act, 1964" in rec5["controlling_provisions"]
    assert "Section 10 Family Courts Act, 1964" in rec5["provisions_in_unified_store"]
    assert rec5["provisions_in_unified_store"]["Section 10 Family Courts Act, 1964"] is True


if __name__ == "__main__":
    asyncio.run(test_planner_audit_logging())
    print("ALL PLANNER AUDIT LOGGING TESTS PASSED.")
