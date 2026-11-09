"""
tests/test_step3_planner_canonical_ids.py

Phase 2 Step 3 Acceptance Gate Test Suite:
Validates that the LLM Planner Prompt and parsing pipeline return Canonical IDs only,
every returned canonical ID exists in the local JSON statute store, and zero hallucinated
IDs reach the final query plan.

Gate Requirements:
1. The planner prompt requires canonical IDs and injects the canonical ID lookup list.
2. For each of the 4 test queries:
   - Returns Canonical IDs only (matching ^[A-Z0-9_]+_(?:SEC|ART|ORD|RULE)_[0-9A-Z_()]+$)
   - Every returned ID exists in UnifiedStatuteStore (data/statutes_v2/*.json)
   - Zero hallucinated IDs
   - Zero cross-domain contamination
"""

import os
import sys
import re
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.legal_query_planner import (
    PLANNER_SYSTEM_PROMPT,
    create_deterministic_fallback_plan,
    analyze_legal_query
)
from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern
from core.unified_statute_store import get_unified_statute_store

# Ensure Turso network checks are skipped for instantaneous test execution
os.environ["SKIP_TURSO_DRIFT_CHECK"] = "1"
CANONICAL_ID_REGEX = re.compile(r'^[A-Z0-9_]+_(?:SEC|ART|ORD|RULE)_[0-9A-Z_()]+$')


def test_planner_prompt_has_canonical_mandate_and_lookup():
    """Verify that PLANNER_SYSTEM_PROMPT and prompts/query_planner.md mandate canonical IDs."""
    # Check prompt variables in code
    assert "CANONICAL ID MANDATE" in PLANNER_SYSTEM_PROMPT, "PLANNER_SYSTEM_PROMPT lacks CANONICAL ID MANDATE"
    assert "CANONICAL ID LOOKUP REFERENCE TABLE" in PLANNER_SYSTEM_PROMPT, "PLANNER_SYSTEM_PROMPT lacks lookup table"
    assert "PPC_1860_SEC_489F" in PLANNER_SYSTEM_PROMPT
    assert "CRPC_1898_SEC_498" in PLANNER_SYSTEM_PROMPT
    assert "FAMILY_COURTS_1964_SEC_5" in PLANNER_SYSTEM_PROMPT
    assert "PRPA_2009_SEC_15" in PLANNER_SYSTEM_PROMPT
    assert "FIO_2001_SEC_9" in PLANNER_SYSTEM_PROMPT

    # Check documentation prompt file
    prompt_file = os.path.join(REPO_ROOT, "prompts", "query_planner.md")
    assert os.path.exists(prompt_file), f"Missing {prompt_file}"
    with open(prompt_file, "r", encoding="utf-8") as f:
        doc_prompt = f.read()
    assert "Canonical ID Mandate" in doc_prompt or "CANONICAL ID MANDATE" in doc_prompt
    assert "Canonical ID Lookup Reference Table" in doc_prompt or "CANONICAL ID LOOKUP REFERENCE TABLE" in doc_prompt


def test_gate_query1_family_canonical_ids():
    query = (
        "My client wants to file for Khula from her husband who has deserted her for over 2 years. "
        "She also seeks recovery of her unpaid prompt dower of Rs. 500,000, past and future maintenance for "
        "herself and her two minor children (ages 3 and 7), and custody (Hizanat) of both children under the Guardians and Wards Act."
    )
    store = get_unified_statute_store()
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    # 1. Domain check
    assert plan.primary_domain == "family"
    assert decomp.primary_domain == "family"

    # 2. Collect all controlling provisions and statutory provisions
    all_controlling = []
    for iss in decomp.issues:
        for prov in iss.controlling_provisions:
            all_controlling.append(prov)
    all_provisions = list(dict.fromkeys(all_controlling + plan.statutory_provisions))

    assert len(all_provisions) > 0, "No provisions returned for family query"

    # 3. Every returned provision must be a valid canonical ID
    for cid in all_provisions:
        assert CANONICAL_ID_REGEX.match(cid), f"Provision '{cid}' is NOT a valid canonical ID format"
        rec = store.get_by_canonical_id(cid)
        assert rec is not None, f"Canonical ID '{cid}' does not exist in statute store!"

    # 4. Mandatory family provisions present
    assert "FAMILY_COURTS_1964_SEC_5" in all_provisions
    assert "DMMA_1939_SEC_2" in all_provisions
    assert "MFLO_1961_SEC_9" in all_provisions
    assert "GWA_1890_SEC_17" in all_provisions

    # 5. Zero hallucinated or contaminated provisions
    for cid in all_provisions:
        assert "489F" not in cid, f"Contaminated cheque provision: {cid}"
        assert "CRPC" not in cid, f"Contaminated criminal procedure provision: {cid}"
        assert "SRA" not in cid, f"Contaminated SRA provision: {cid}"


def test_gate_query2_rent_canonical_ids():
    query = (
        "The landlord has filed an ejectment application against my client under Section 15 of the Punjab Rented "
        "Premises Act, 2009 on grounds of default in payment of rent and personal bona fide need. My client has paid rent "
        "regularly via cash but the landlord refused to issue receipts. What are the legal grounds to defend the ejectment and obtain leave to contest?"
    )
    store = get_unified_statute_store()
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    assert plan.primary_domain == "rent"
    assert decomp.primary_domain == "rent"

    all_controlling = []
    for iss in decomp.issues:
        for prov in iss.controlling_provisions:
            all_controlling.append(prov)
    all_provisions = list(dict.fromkeys(all_controlling + plan.statutory_provisions))

    assert len(all_provisions) > 0, "No provisions returned for rent query"

    for cid in all_provisions:
        assert CANONICAL_ID_REGEX.match(cid), f"Provision '{cid}' is NOT a valid canonical ID format"
        rec = store.get_by_canonical_id(cid)
        assert rec is not None, f"Canonical ID '{cid}' does not exist in statute store!"

    # Mandatory rent provisions present
    assert "PRPA_2009_SEC_15" in all_provisions
    assert "PRPA_2009_SEC_22" in all_provisions

    # Zero SRA or criminal contamination
    for cid in all_provisions:
        assert "SRA" not in cid, f"Contaminated SRA provision: {cid}"
        assert "PPC" not in cid and "CRPC" not in cid, f"Contaminated penal provision: {cid}"


def test_gate_query3_banking_canonical_ids():
    query = (
        "A scheduled commercial bank has filed a recovery suit against my corporate client under Section 9 of the "
        "Financial Institutions (Recovery of Finances) Ordinance, 2001 (FIO 2001) for Rs. 45 million. The bank has charged "
        "compound mark-up and penal interest beyond the agreed finance agreement. What is the mandatory procedure and timeline under "
        "Section 10 FIO 2001 to file an application for leave to defend?"
    )
    store = get_unified_statute_store()
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    assert plan.primary_domain == "banking"
    assert decomp.primary_domain == "banking"

    all_controlling = []
    for iss in decomp.issues:
        for prov in iss.controlling_provisions:
            all_controlling.append(prov)
    all_provisions = list(dict.fromkeys(all_controlling + plan.statutory_provisions))

    assert len(all_provisions) > 0, "No provisions returned for banking query"

    for cid in all_provisions:
        assert CANONICAL_ID_REGEX.match(cid), f"Provision '{cid}' is NOT a valid canonical ID format"
        rec = store.get_by_canonical_id(cid)
        assert rec is not None, f"Canonical ID '{cid}' does not exist in statute store!"

    # Mandatory banking provisions present
    assert "FIO_2001_SEC_9" in all_provisions
    assert "FIO_2001_SEC_10" in all_provisions

    # Zero SRA or criminal contamination
    for cid in all_provisions:
        assert "SRA" not in cid, f"Contaminated SRA provision: {cid}"
        assert "PPC" not in cid and "CRPC" not in cid, f"Contaminated penal provision: {cid}"


def test_gate_query4_criminal_canonical_ids():
    query = (
        "My client is falsely implicated in an FIR registered under Sections 379, 420, and 406 PPC alleging theft of "
        "industrial machinery and dishonest misappropriation of funds worth Rs. 3 million. The dispute arises out of a cancelled "
        "commercial distributorship agreement. What are the remedies for pre-arrest bail under Section 498 CrPC and quashment of the FIR under Section 561-A CrPC?"
    )
    store = get_unified_statute_store()
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    assert plan.primary_domain == "criminal"
    assert decomp.primary_domain == "criminal"

    all_controlling = []
    for iss in decomp.issues:
        for prov in iss.controlling_provisions:
            all_controlling.append(prov)
    all_provisions = list(dict.fromkeys(all_controlling + plan.statutory_provisions))

    assert len(all_provisions) > 0, "No provisions returned for criminal query"

    for cid in all_provisions:
        assert CANONICAL_ID_REGEX.match(cid), f"Provision '{cid}' is NOT a valid canonical ID format"
        rec = store.get_by_canonical_id(cid)
        assert rec is not None, f"Canonical ID '{cid}' does not exist in statute store!"

    # Mandatory criminal provisions present
    assert "PPC_1860_SEC_379" in all_provisions
    assert "PPC_1860_SEC_406" in all_provisions
    assert "PPC_1860_SEC_420" in all_provisions
    assert "CRPC_1898_SEC_498" in all_provisions
    assert "CRPC_1898_SEC_561A" in all_provisions


@pytest.mark.anyio
async def test_llm_planner_response_validation_and_hallucination_filter():
    """
    Simulates LLM response containing valid canonical IDs and a hallucinated provision (e.g. Section 138 NIA).
    Validates that analyze_legal_query extracts valid canonical IDs and discards hallucinated ones.
    """
    mock_llm_json = """
    {
      "primary_domain": "criminal",
      "secondary_domains": ["civil"],
      "subdomains": ["theft", "cheating", "quashment"],
      "issues": [
        {
          "issue_id": "issue_theft",
          "heading": "Theft and Misappropriation",
          "description": "Analysis of theft and breach of trust.",
          "controlling_statutes": ["Pakistan Penal Code, 1860"],
          "controlling_provisions": [
            "PPC_1860_SEC_379",
            "PPC_1860_SEC_406",
            "PPC_1860_SEC_420",
            "NIA_1881_SEC_138",
            "PPC_1860_SEC_999"
          ],
          "search_queries": ["theft of industrial machinery"],
          "factual_anchors": ["machinery", "cancelled distributorship"]
        }
      ],
      "statutory_provisions": [
        "PPC_1860_SEC_379",
        "CRPC_1898_SEC_498",
        "CRPC_1898_SEC_561A",
        "NONEXISTENT_ACT_1999_SEC_1"
      ],
      "open_questions": ["Is there an arbitration clause?"],
      "procedural_remedy": "Petition under Section 561-A CrPC",
      "competent_forum": "High Court",
      "target_province": "Federal"
    }
    """
    class MockResp:
        def __init__(self, text):
            self.content = [type("Block", (), {"type": "text", "text": text})()]

    async def mock_ai_client(**kwargs):
        return MockResp(mock_llm_json)

    query = (
        "My client is falsely implicated in an FIR registered under Sections 379, 420, and 406 PPC alleging theft of "
        "industrial machinery and dishonest misappropriation of funds. What are the remedies for pre-arrest bail under Section 498 CrPC and quashment of the FIR under Section 561-A CrPC?"
    )
    plan = await analyze_legal_query(query, ai_client_fn=mock_ai_client)
    store = get_unified_statute_store()

    # 1. Valid IDs must be retained
    assert "PPC_1860_SEC_379" in plan.statutory_provisions
    assert "PPC_1860_SEC_406" in plan.statutory_provisions
    assert "PPC_1860_SEC_420" in plan.statutory_provisions
    assert "CRPC_1898_SEC_498" in plan.statutory_provisions
    assert "CRPC_1898_SEC_561A" in plan.statutory_provisions

    # 2. Hallucinated / absent IDs must be completely eliminated
    assert "NIA_1881_SEC_138" not in plan.statutory_provisions
    assert "PPC_1860_SEC_999" not in plan.statutory_provisions
    assert "NONEXISTENT_ACT_1999_SEC_1" not in plan.statutory_provisions

    # 3. Every remaining ID in plan.statutory_provisions must exist in store
    for cid in plan.statutory_provisions:
        assert CANONICAL_ID_REGEX.match(cid), f"Invalid CID format: {cid}"
        assert store.get_by_canonical_id(cid) is not None, f"CID '{cid}' is missing from store"


if __name__ == "__main__":
    test_planner_prompt_has_canonical_mandate_and_lookup()
    print("[PASS] Planner Prompt Canonical ID Mandate & Lookup Table")
    test_gate_query1_family_canonical_ids()
    print("[PASS] Gate Query 1: Family Law Canonical IDs")
    test_gate_query2_rent_canonical_ids()
    print("[PASS] Gate Query 2: Rent Eviction Canonical IDs")
    test_gate_query3_banking_canonical_ids()
    print("[PASS] Gate Query 3: Banking Recovery Canonical IDs")
    test_gate_query4_criminal_canonical_ids()
    print("[PASS] Gate Query 4: Criminal Theft / Fraud Canonical IDs")
    import asyncio
    asyncio.run(test_llm_planner_response_validation_and_hallucination_filter())
    print("[PASS] LLM Planner Response Validation & Hallucination Filter")
    print("\nALL STEP 3 ACCEPTANCE GATE TESTS PASSED!")
