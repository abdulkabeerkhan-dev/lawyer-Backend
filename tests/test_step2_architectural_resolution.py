"""
tests/test_step2_architectural_resolution.py

Phase 2 Step 2 Acceptance Gate Test Suite:
Validates the single pipeline resolution between LLM Planner and Deterministic Extractor.
Tests:
1. Family Law Query:
   - primary_domain == "family"
   - controlling_provisions contains Family Courts Act, MFLO, Guardians and Wards Act
   - ZERO Section 489-F PPC, CrPC 154, or Section 12 SRA
2. Rent & Eviction Query:
   - primary_domain == "rent"
   - controlling_provisions contains PRPA 2009 provisions (Section 15, 22, 4)
   - ZERO Section 12 SRA or criminal provisions
3. Banking Recovery Query:
   - primary_domain == "banking"
   - controlling_provisions contains FIO 2001 provisions (Section 9, 10, 14, 22)
   - ZERO Section 12 SRA or criminal provisions
4. Criminal Theft / Fraud Query:
   - primary_domain == "criminal"
   - controlling_provisions contains Sections 379, 406, and 420 PPC
   - controlling_provisions contains Section 498 CrPC (pre-arrest bail) and 561-A CrPC (quashment)
   - ZERO weapon of offence / murder questions in open questions
"""

import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.legal_query_planner import create_deterministic_fallback_plan
from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern


def test_gate_query1_family_law():
    query = (
        "My client wants to file for Khula from her husband who has deserted her for over 2 years. "
        "She also seeks recovery of her unpaid prompt dower of Rs. 500,000, past and future maintenance for "
        "herself and her two minor children (ages 3 and 7), and custody (Hizanat) of both children under the Guardians and Wards Act."
    )
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    # 1. Primary domain check
    assert plan.primary_domain == "family", f"Expected 'family', got '{plan.primary_domain}'"
    assert decomp.primary_domain == "family", f"Expected 'family', got '{decomp.primary_domain}'"

    # 2. Controlling provisions check
    all_controlling = []
    for iss in decomp.issues:
        all_controlling.extend(iss.controlling_provisions)

    # Must contain family statutes
    assert any("Family Courts Act" in p or "FAMILY_COURTS" in p for p in all_controlling), "Missing Family Courts Act provisions"
    assert any("Muslim Family Laws" in p or "MFLO" in p for p in all_controlling), "Missing MFLO provisions"
    assert any("Guardians and Wards" in p or "GWA" in p for p in all_controlling), "Missing GWA provisions"

    # MUST NOT contain Section 489-F PPC or CrPC or SRA
    for p in all_controlling + plan.statutory_provisions:
        p_low = p.lower()
        assert "489-f" not in p_low and "489f" not in p_low, f"Found contaminated cheque provision: {p}"
        assert "crpc" not in p_low, f"Found contaminated criminal procedure provision: {p}"
        assert "specific relief" not in p_low and "sra" not in p_low, f"Found contaminated SRA provision: {p}"

    # Open questions must not mention cheque of Rs 15 lakh
    for oq in decomp.open_questions:
        assert "15 lakh" not in oq.lower() and "cheque" not in oq.lower(), f"Found contaminated cheque question: {oq}"


def test_gate_query2_rent_eviction():
    query = (
        "The landlord has filed an ejectment application against my client under Section 15 of the Punjab Rented "
        "Premises Act, 2009 on grounds of default in payment of rent and personal bona fide need. My client has paid rent "
        "regularly via cash but the landlord refused to issue receipts. What are the legal grounds to defend the ejectment and obtain leave to contest?"
    )
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    assert plan.primary_domain == "rent", f"Expected 'rent', got '{plan.primary_domain}'"
    assert decomp.primary_domain == "rent", f"Expected 'rent', got '{decomp.primary_domain}'"

    all_controlling = []
    for iss in decomp.issues:
        all_controlling.extend(iss.controlling_provisions)

    # Must contain PRPA provisions
    assert any("15" in p and "PRPA" in p for p in all_controlling), "Missing Section 15 PRPA 2009"
    assert any("22" in p and "PRPA" in p for p in all_controlling), "Missing Section 22 PRPA 2009"

    # MUST NOT contain Section 12 SRA
    for p in all_controlling + plan.statutory_provisions:
        p_low = p.lower()
        assert "specific relief" not in p_low and "sra" not in p_low, f"Found contaminated SRA provision: {p}"


def test_gate_query3_banking_recovery():
    query = (
        "A scheduled commercial bank has filed a recovery suit against my corporate client under Section 9 of the "
        "Financial Institutions (Recovery of Finances) Ordinance, 2001 (FIO 2001) for Rs. 45 million. The bank has charged "
        "compound mark-up and penal interest beyond the agreed finance agreement. What is the mandatory procedure and timeline under "
        "Section 10 FIO 2001 to file an application for leave to defend?"
    )
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    assert plan.primary_domain == "banking", f"Expected 'banking', got '{plan.primary_domain}'"
    assert decomp.primary_domain == "banking", f"Expected 'banking', got '{decomp.primary_domain}'"

    all_controlling = []
    for iss in decomp.issues:
        all_controlling.extend(iss.controlling_provisions)

    # Must contain FIO provisions
    assert any(("Section 9" in p or "SEC_9" in p) and ("Financial Institutions" in p or "FIO" in p) for p in all_controlling), "Missing Section 9 FIO 2001"
    assert any(("Section 10" in p or "SEC_10" in p) and ("Financial Institutions" in p or "FIO" in p) for p in all_controlling), "Missing Section 10 FIO 2001"

    # MUST NOT contain Section 12 SRA
    for p in all_controlling + plan.statutory_provisions:
        p_low = p.lower()
        assert "specific relief" not in p_low and "sra" not in p_low, f"Found contaminated SRA provision: {p}"


def test_gate_query4_criminal_theft_fraud():
    query = (
        "My client is falsely implicated in an FIR registered under Sections 379, 420, and 406 PPC alleging theft of "
        "industrial machinery and dishonest misappropriation of funds worth Rs. 3 million. The dispute arises out of a cancelled "
        "commercial distributorship agreement. What are the remedies for pre-arrest bail under Section 498 CrPC and quashment of the FIR under Section 561-A CrPC?"
    )
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    assert plan.primary_domain == "criminal", f"Expected 'criminal', got '{plan.primary_domain}'"
    assert decomp.primary_domain == "criminal", f"Expected 'criminal', got '{decomp.primary_domain}'"

    all_controlling = []
    for iss in decomp.issues:
        all_controlling.extend(iss.controlling_provisions)

    # Must contain Sections 379, 406, 420 PPC
    assert any("379" in p for p in all_controlling), "Missing Section 379 PPC (Theft)"
    assert any("406" in p for p in all_controlling), "Missing Section 406 PPC (Criminal Breach of Trust)"
    assert any("420" in p for p in all_controlling), "Missing Section 420 PPC (Cheating)"

    # Must contain Section 498 CrPC and 561-A CrPC
    assert any("498" in p for p in all_controlling), "Missing Section 498 CrPC (Pre-arrest bail)"
    assert any("561" in p for p in all_controlling), "Missing Section 561-A CrPC (Quashment)"

    # Open questions must NOT contain murder weapon / ocular evidence questions
    for oq in decomp.open_questions:
        assert "weapon of offence" not in oq.lower() and "ocular evidence" not in oq.lower(), f"Found inappropriate violent crime question: {oq}"


if __name__ == "__main__":
    test_gate_query1_family_law()
    print("[PASS] Gate Query 1: Family Law")
    test_gate_query2_rent_eviction()
    print("[PASS] Gate Query 2: Rent & Eviction")
    test_gate_query3_banking_recovery()
    print("[PASS] Gate Query 3: Banking Recovery")
    test_gate_query4_criminal_theft_fraud()
    print("[PASS] Gate Query 4: Criminal Theft / Fraud")
    print("\nALL STEP 2 ACCEPTANCE GATE TESTS PASSED!")
