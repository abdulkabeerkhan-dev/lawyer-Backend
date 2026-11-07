"""
tests/test_statute_regression_suite.py

Comprehensive Regression Suite for the 8 Standard Doctrinal Queries:
1. Money Lent Limitation (Article 57 Limitation Act 1908 + Punjab Loans Limitation Act 1904)
2. Dishonestly Issuing Cheque (Section 489-F PPC 1860)
3. Post-Arrest Bail in Non-Bailable Offences (Section 497 CrPC 1898)
4. Auction Sale Challenge (Order XXI Rule 90 CPC 1908)
5. Benami Prohibition (Section 4 Benami Act 2017)
6. Specific Performance of Agreement to Sell (Section 12 SRA 1877 + Article 113 Limitation Act 1908)
7. Quashment of FIR (Section 561-A CrPC 1898)
8. Temporary Injunction (Order XXXIX Rules 1 & 2 CPC 1908)
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from legal_ai.query_engine.statute_router import (
    analyze_statute_query_intent,
    retrieve_statute_provisions,
    build_evidence_pack_for_query
)
from legal_ai.verification.statute_evidence_verifier import StatuteEvidenceVerifier
from legal_ai.synthesis.structured_memo_engine import execute_structured_memo_pipeline


# --- Query 1: Money Lent Limitation Query ---
def test_query_1_money_lent_limitation():
    query = "What is the limitation period for filing a suit for recovery of money lent?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "civil"
    # Admitted pack must contain Article 57 and Punjab caveat
    e1 = pack.items["E1"]
    assert e1.statute_id == "limitation-act-1908"
    assert e1.unit_type == "article"
    assert e1.number == "57"
    assert e1.period == "Three years"
    assert e1.trigger == "When the loan is made"

    # Punjab override must be admitted as linked caveat
    caveats = [it for it in pack.items.values() if it.item_type == "linked_caveat"]
    assert len(caveats) > 0
    assert any("Punjab Loans Limitation Act" in c.text for c in caveats)

    # Verifier must pass valid memo and reject Section 264 / Section 57
    memo_json = """
    {
      "answer": "A suit for recovery of money payable for money lent is governed by a limitation period of three years under Article 57 of the Limitation Act, 1908.",
      "claims": [
        {
          "statement": "Under Article 57 of the First Schedule to the Limitation Act, 1908, the period of limitation is 'Three years' from 'When the loan is made'.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": ["Within Punjab province, the period is subject to the Punjab Loans Limitation Act, 1904."],
      "not_found": [],
      "open_questions": []
    }
    """
    rendered_md, report, _ = execute_structured_memo_pipeline(memo_json, pack)
    assert report.is_memo_verified is True
    assert rendered_md.startswith("### Direct Legal Opinion")
    assert "✓ VERIFIED RESEARCH MEMORANDUM" in rendered_md
    assert "Section 264" not in rendered_md
    assert "Section 57" not in rendered_md


# --- Query 2: Cheque Dishonour Query ---
def test_query_2_cheque_dishonour():
    query = "What are the essential ingredients of Section 489-F PPC for dishonour of cheque?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "criminal"
    # Must retrieve Section 489-F PPC
    sec_489f = next((it for it in pack.items.values() if "489" in str(it.number)), None)
    assert sec_489f is not None
    assert sec_489f.unit_type == "section"
    assert "dishonestly issues a cheque" in sec_489f.text.lower()


# --- Query 3: Post-Arrest Bail Query ---
def test_query_3_post_arrest_bail():
    query = "What are the statutory principles for grant of post-arrest bail under Section 497 CrPC?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "criminal"
    sec_497 = next((it for it in pack.items.values() if it.number == "497"), None)
    assert sec_497 is not None
    assert sec_497.unit_type == "section"
    assert "bailable" in sec_497.text.lower()


# --- Query 4: Execution Sale Challenge Query ---
def test_query_4_execution_sale_challenge():
    query = "Can a court auction mortgaged property under Order XXI Rule 90 CPC without notice, and what are the grounds to set aside the auction?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "civil"
    r90 = next((it for it in pack.items.values() if it.number == "90" or "XXI" in str(it.parent or it.heading_description)), None)
    assert r90 is not None
    assert r90.unit_type in ("rule", "order")
    assert "irregularity or fraud" in (r90.heading_description or r90.text).lower()


# --- Query 5: Benami Property Prohibition Query ---
def test_query_5_benami_property():
    query = "Can a real owner recover property held benami against a benamidar under the Benami Transactions (Prohibition) Act, 2017?"
    intent = analyze_statute_query_intent(query)
    assert intent.domain == "civil"
    assert any("benami" in s.lower() for s in intent.likely_statutes)


# --- Query 6: Specific Performance of Agreement to Sell Query ---
def test_query_6_specific_performance_sale():
    query = "What is the governing provision and limitation for filing a suit for specific performance of an agreement to sell under Section 12 SRA?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "civil"
    s12 = next((it for it in pack.items.values() if it.number == "12"), None)
    assert s12 is not None
    assert s12.statute_id in ("specific-relief-act-1877", "sra-1877", "sra_1877")


# --- Query 7: Quashment of FIR Query ---
def test_query_7_quashment_fir():
    query = "Under what provision can a High Court quash a malicious criminal FIR under Section 561-A CrPC?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "criminal"
    s561a = next((it for it in pack.items.values() if "561" in str(it.number)), None)
    assert s561a is not None
    assert s561a.unit_type == "section"
    assert "code-of-criminal-procedure-1898" in s561a.statute_id or "crpc" in s561a.statute_id


# --- Query 8: Temporary Injunction Query ---
def test_query_8_temporary_injunction():
    query = "What are the three essential ingredients for grant of temporary injunction under Order XXXIX Rule 1 CPC?"
    pack, intent = build_evidence_pack_for_query(query)

    assert intent.domain == "civil"
    ord39 = next((it for it in pack.items.values() if "XXXIX" in str(it.parent or it.heading_description) or it.number in ("1", "2")), None)
    assert ord39 is not None
    assert ord39.unit_type in ("rule", "order")
