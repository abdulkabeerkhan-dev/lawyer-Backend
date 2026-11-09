# tests/test_twenty_queries_benchmark.py
"""
Definitive 20-Query Legal Benchmark Suite for Section AI (Layers 1-8).
Evaluates Section AI against the 20 canonical benchmarks:
- Core Provisions (Queries 1-14)
- Mixed & Judgment Calls (Query 15)
- Traps & Negative Controls (Queries 16-17)
- Out-of-Coverage & Lawyer Safety Controls (Queries 18-20)

Recording & Verification Dimensions per Run:
1. Answer line correctness.
2. Every citation exists with correct unit type (Article vs Section vs Order/Rule).
3. Any quoted text matches stored text.
4. Verified badges attached strictly per claim.
5. Gaps admitted honestly rather than filled from memory.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legal_ai.query_engine.statute_router import (
    analyze_statute_query_intent,
    retrieve_statute_provisions,
    build_evidence_pack_for_query
)
from legal_ai.synthesis.structured_memo_engine import execute_structured_memo_pipeline
from legal_ai.verification.statute_evidence_verifier import StatuteEvidenceVerifier


# --- 1. Money Lent Limitation (Query 1) ---
def test_q1_money_lent_limitation():
    q = "What is the limitation period for a suit to recover money lent?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    e1 = pack.items["E1"]
    assert e1.statute_id == "limitation-act-1908"
    assert e1.unit_type == "article"
    assert e1.number == "57"
    assert e1.period == "Three years"
    assert e1.trigger == "When the loan is made"

    caveats = [it for it in pack.items.values() if it.item_type == "linked_caveat"]
    assert len(caveats) > 0
    assert any("Punjab Loans Limitation Act" in c.text for c in caveats)

    memo_json = """
    {
      "answer": "A suit for recovery of money payable for money lent is governed by a limitation period of three years under Article 57 of the Limitation Act, 1908.",
      "claims": [
        {
          "statement": "Under Article 57 of the Limitation Act, 1908, the limitation period 'For money payable for money lent' is 'Three years' running from 'When the loan is made'.",
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
    assert "✓ VERIFIED RESEARCH MEMORANDUM" in rendered_md
    assert "Section 57" not in rendered_md
    assert "Section 264" not in rendered_md


# --- 2. Specific Performance of Agreement to Sell (Query 2) ---
def test_q2_specific_performance_limitation():
    q = "Limitation for a suit for specific performance of an agreement to sell?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    art113 = next((it for it in pack.items.values() if it.number == "113"), None)
    assert art113 is not None
    assert art113.unit_type == "article"
    assert "date fixed for the performance" in art113.trigger.lower() or "notice that performance is refused" in art113.trigger.lower()

    s12 = next((it for it in pack.items.values() if it.number == "12"), None)
    assert s12 is not None
    assert s12.unit_type == "section"
    assert s12.statute_id in ("specific-relief-act-1877", "sra-1877")


# --- 3. Condonation of Delay in Suits (Query 3) ---
def test_q3_condonation_of_delay_in_suits():
    q = "Can the court condone delay in filing a civil suit?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    s5 = next((it for it in pack.items.values() if it.number == "5"), None)
    s3 = next((it for it in pack.items.values() if it.number == "3"), None)
    assert s5 is not None
    assert s3 is not None
    assert s5.unit_type == "section"
    assert s3.unit_type == "section"
    # Section 5 text applies to appeals and applications, not suits
    assert "appeal" in s5.text.lower() and "application" in s5.text.lower()
    # Section 3 establishes dismissal of late suits
    assert "shall be dismissed" in s3.text.lower()


# --- 4. Cheque Dishonour Punishment (Query 4) ---
def test_q4_cheque_dishonour_penalty():
    q = "Punishment for dishonestly issuing a cheque?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"
    s489f = next((it for it in pack.items.values() if "489" in str(it.number)), None)
    assert s489f is not None
    assert s489f.unit_type == "section"
    assert "extend to three years" in s489f.text.lower()


# --- 5. Cheating and Punishment (Query 5) ---
def test_q5_cheating_definition_and_punishment():
    q = "What is cheating under the PPC and what is the punishment?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"
    s415 = next((it for it in pack.items.values() if it.number == "415"), None)
    s420 = next((it for it in pack.items.values() if it.number == "420"), None)
    assert s415 is not None and s415.unit_type == "section"
    assert s420 is not None and s420.unit_type == "section"
    assert "deceiving any person" in s415.text.lower()
    assert "extend to seven years" in s420.text.lower()


# --- 6. Punishment for Murder (Query 6) ---
def test_q6_murder_punishment_subclauses_kept_separate():
    q = "Punishment for murder?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"
    s302 = next((it for it in pack.items.values() if it.number == "302"), None)
    assert s302 is not None
    assert s302.unit_type == "section"
    # Sub-clauses (a), (b), (c) kept separate; Qisas and Ta'zir not merged
    assert "qisas" in s302.text.lower()
    assert "ta'zir" in s302.text.lower() or "tazir" in s302.text.lower()
    assert "(a)" in s302.text and "(b)" in s302.text and "(c)" in s302.text


# --- 7. Post-Arrest Bail in Non-Bailable Offence (Query 7) ---
def test_q7_post_arrest_bail():
    q = "How do I get bail in a non-bailable offence after arrest?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"
    s497 = next((it for it in pack.items.values() if it.number == "497"), None)
    assert s497 is not None
    assert s497.unit_type == "section"
    assert "non-bailable offence" in s497.text.lower() or "bailable" in s497.text.lower()


# --- 8. Pre-Arrest Bail Distinguished from Post-Arrest (Query 8) ---
def test_q8_pre_arrest_bail_distinguished():
    q = "Can I get bail before arrest?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"
    s498 = next((it for it in pack.items.values() if it.number == "498"), None)
    assert s498 is not None
    assert s498.unit_type == "section"


# --- 9. FIR Quashment under Inherent Powers (Query 9) ---
def test_q9_quashment_of_fir():
    q = "How can an FIR be quashed?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"
    s561a = next((it for it in pack.items.values() if "561" in str(it.number)), None)
    assert s561a is not None
    assert s561a.unit_type == "section"
    assert "abuse of the process" in s561a.text.lower()


# --- 10. Execution Sale Challenge (Query 10) ---
def test_q10_execution_sale_challenge_order_and_rule():
    q = "How do I challenge an execution sale?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    r90 = next((it for it in pack.items.values() if "90" in str(it.number)), None)
    assert r90 is not None
    # Crucial: Must be labelled Order and Rule, NOT Section
    assert r90.unit_type == "rule"
    assert "Order XXI" in r90.number
    assert "irregularity or fraud" in (r90.heading_description + r90.text).lower()


# --- 11. Temporary Injunction (Query 11) ---
def test_q11_temporary_injunction():
    q = "How do I get a temporary injunction?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    r1 = next((it for it in pack.items.values() if "Rule 1" in it.number), None)
    r2 = next((it for it in pack.items.values() if "Rule 2" in it.number), None)
    assert r1 is not None and r1.unit_type == "rule"
    assert r2 is not None and r2.unit_type == "rule"
    assert "Order XXXIX" in r1.number


# --- 12. Rejection of Plaint (Query 12) ---
def test_q12_rejection_of_plaint():
    q = "When can a plaint be rejected?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    r11 = next((it for it in pack.items.values() if "11" in str(it.number)), None)
    assert r11 is not None
    assert r11.unit_type == "rule"
    assert "Order VII" in r11.number
    assert "cause of action" in r11.text.lower() or "rejection of plaint" in r11.heading_description.lower()


# --- 13. Contract Breach Damages (Query 13) ---
def test_q13_contract_breach_damages():
    q = "What damages can I claim for breach of contract?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    s73 = next((it for it in pack.items.values() if it.number == "73"), None)
    s74 = next((it for it in pack.items.values() if it.number == "74"), None)
    assert s73 is not None and s73.unit_type == "section"
    assert s74 is not None and s74.unit_type == "section"
    assert "compensation for loss or damage caused by breach" in s73.text.lower()
    assert "penalty" in s74.text.lower()


# --- 14. Benami Prohibition (Query 14) ---
def test_q14_benami_prohibition():
    q = "Is a benami transaction prohibited?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "civil"
    s4 = next((it for it in pack.items.values() if it.number == "4"), None)
    assert s4 is not None
    assert s4.unit_type == "section"
    assert "property held benami" in (s4.heading_description + s4.text).lower()


# --- 15. Partner Joint Account Dispute (Mixed and Judgment Call, Query 15) ---
def test_q15_partner_joint_account_dual_route():
    q = "My partner took Rs. 5 million from our joint account. What are my options?"
    pack, intent = build_evidence_pack_for_query(q)
    # Crucial: Spotting that one fact pattern raises two domains (Mixed)
    assert intent.domain == "mixed"

    # Criminal route present: Breach of trust / cheating
    has_criminal = any(it.statute_id == "pakistan-penal-code-1860" and it.number in ("405", "406", "420") for it in pack.items.values())
    assert has_criminal is True

    # Civil route present: Partnership dissolution / recovery / Limitation Act
    has_partnership = any(it.statute_id == "partnership-act-1932" for it in pack.items.values())
    has_limitation = any(it.statute_id == "limitation-act-1908" for it in pack.items.values())
    assert has_partnership is True
    assert has_limitation is True


# --- 16. Trap: Section 999 PPC (Query 16) ---
def test_q16_trap_section_999_ppc():
    q = "What does Section 999 of the PPC say?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.is_trap is True
    assert intent.trap_type == "non_existent_section"
    # Zero invented records loaded
    statute_units = [it for it in pack.items.values() if it.item_type == "statute_unit"]
    assert len(statute_units) == 0

    # Verifier must deny verified badge if an LLM hallucinates text for Section 999
    verifier = StatuteEvidenceVerifier()
    memo_payload = {
        "answer": "Section 999 provides death penalty.",
        "claims": [
            {
                "statement": "Section 999 of the PPC provides death penalty for cyber treason.",
                "evidence_ids": ["E1"]
            }
        ]
    }
    report = verifier.verify_structured_memo(memo_payload, pack.to_dict())
    assert report.is_memo_verified is False
    assert any("999" in v or "does not exist" in v for v in report.blocking_violations)


# --- 17. Trap: Section 57 Limitation Act Premise Correction (Query 17) ---
def test_q17_trap_section_57_limitation_act():
    q = "What is the limitation under Section 57 of the Limitation Act?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.is_trap is True
    assert intent.trap_type == "premise_error"
    # Admitted unit must be Article 57, not Section 57
    art57 = next((it for it in pack.items.values() if it.number == "57"), None)
    assert art57 is not None
    assert art57.unit_type == "article"

    # Verifier denies 'Section 57' but approves corrected 'Article 57'
    verifier = StatuteEvidenceVerifier()
    bad_memo = {
        "answer": "Three years under Section 57.",
        "claims": [{"statement": "Under Section 57 of the Limitation Act, 1908, the period is three years.", "evidence_ids": ["E1"]}]
    }
    bad_report = verifier.verify_structured_memo(bad_memo, pack.to_dict())
    assert bad_report.is_memo_verified is False
    assert any("Section 57" in v for v in bad_report.blocking_violations)

    good_memo = {
        "answer": "Section 57 is a misnomer; under Article 57 of the First Schedule to the Limitation Act, 1908, the limitation period for money lent is three years.",
        "claims": [{"statement": "Under Article 57 of the Limitation Act, 1908, the limitation period for money lent is three years.", "evidence_ids": ["E1"]}]
    }
    good_report = verifier.verify_structured_memo(good_memo, pack.to_dict())
    assert good_report.is_memo_verified is True


# --- 18. Out of Coverage: Punjab Tenant Eviction (Query 18) ---
def test_q18_out_of_coverage_punjab_tenancy():
    q = "Can a tenant be evicted without notice in Punjab?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.is_out_of_coverage is True
    assert "Punjab Rented Premises Act" in intent.out_of_coverage_reason
    # Zero unrelated provisions admitted (specifically no Transfer of Property Act 1882)
    statute_units = [it for it in pack.items.values() if it.item_type == "statute_unit"]
    assert len(statute_units) == 0
    assert not any("transfer-of-property" in it.statute_id for it in pack.items.values())


# --- 19. Out of Coverage: Income Tax Calculation on Salary (Query 19) ---
def test_q19_out_of_coverage_income_tax():
    q = "How is income tax calculated on a salary of Rs. 100,000?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.is_out_of_coverage is True
    assert "Income Tax Ordinance" in intent.out_of_coverage_reason
    statute_units = [it for it in pack.items.values() if it.item_type == "statute_unit"]
    assert len(statute_units) == 0


# --- 20. Out of Coverage: Supreme Court Judgments Request (Query 20) ---
def test_q20_out_of_coverage_case_law():
    q = "Give me Supreme Court judgments on cheque dishonour."
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.is_out_of_coverage is True
    assert "precedent" in intent.out_of_coverage_reason.lower() or "judicial" in intent.out_of_coverage_reason.lower()
    # Precedent items must be empty; cites zero cases from memory
    case_items = [it for it in pack.items.values() if it.item_type == "judicial_precedent"]
    assert len(case_items) == 0


# --- 21. Cheque Dishonour Fact Pattern (Query 21) ---
def test_q21_cheque_dishonour_fact_pattern():
    q = "My client deposited a cheque of Rs. 15 lakh issued by the defendant. It was returned unpaid for insufficient funds. We want to initiate criminal proceedings. What provision applies, what is the procedure, and is there a limitation period?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"

    sec_tuples = [(it.statute_id, it.number) for it in pack.items.values() if it.item_type == "statute_unit"]
    assert ("pakistan-penal-code-1860", "489F") in sec_tuples
    assert ("code-of-criminal-procedure-1898", "200") in sec_tuples
    assert ("code-of-criminal-procedure-1898", "190") in sec_tuples
    assert ("code-of-criminal-procedure-1898", "154") in sec_tuples

    # Verify Section 489-F PPC text is authentic
    ppc_item = next(it for it in pack.items.values() if it.number == "489F")
    assert "dishonestly issues a cheque" in ppc_item.text.lower()
    assert "repayment of a loan" in ppc_item.text.lower()

    # Verify structured memo pipeline
    memo_json = """
    {
      "answer": "The dishonour of a cheque issued towards repayment of a loan or fulfillment of an obligation constitutes a cognizable criminal offence under Section 489-F of the Pakistan Penal Code, 1860, punishable with up to three years imprisonment. Criminal proceedings may be initiated by lodging an FIR under Section 154 CrPC or by filing a direct private complaint before the Judicial Magistrate under Section 200 CrPC. Under settled Pakistani criminal jurisprudence, no statutory limitation period under the Limitation Act, 1908 applies to the lodging of an FIR or institution of a criminal complaint, though promptness is vital to establish bona fides; concurrent civil summary recovery under Order XXXVII CPC carries a three-year limitation period.",
      "claims": [
        {
          "statement": "Under Section 489-F PPC, 'Whoever dishonestly issues a cheque towards repayment of a loan or fulfillment of an obligation which is dishonoured on presentation, shall be punishable with imprisonment which may extend to three years, or with fine, or with both'.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": ["Under Section 489-F PPC, the burden of proof rests on the accused to establish that he had made arrangements with his bank to ensure the cheque would be honoured."],
      "not_found": [],
      "open_questions": ["Whether the cheque was issued towards repayment of an existing debt versus as a security or guarantee."]
    }
    """
    md, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=memo_json,
        evidence_pack=pack,
        fallback_query=q
    )
    assert report.is_memo_verified is True
    assert "Section 489-F" in md


# --- 22. Section 302 PPC Arrest & Bail Fact Pattern (Query 22) ---
def test_q22_section_302_arrest_and_bail_fact_pattern():
    q = "Accused arrested under Section 302 PPC. We want to apply for bail. What are the grounds and relevant sections?"
    pack, intent = build_evidence_pack_for_query(q)
    assert intent.domain == "criminal"

    sec_tuples = [(it.statute_id, it.number) for it in pack.items.values() if it.item_type == "statute_unit"]
    assert ("pakistan-penal-code-1860", "302") in sec_tuples
    assert ("code-of-criminal-procedure-1898", "497") in sec_tuples
    assert ("code-of-criminal-procedure-1898", "498") in sec_tuples

    s302_item = next(it for it in pack.items.values() if it.number == "302")
    assert "punishment" in s302_item.text.lower()
    assert "fasad" in s302_item.text.lower()

    s497_item = next(it for it in pack.items.values() if it.number == "497")
    assert "bailable" in s497_item.text.lower()

    # Test memo verification
    memo_json = """
    {
      "answer": "An accused arrested under Section 302 PPC for Qatl-i-Amd faces a capital charge falling within the prohibitory clause of Section 497(1) CrPC. Post-arrest bail can be granted by the trial court or High Court under Section 497 CrPC only if the case falls under the statutory exceptions of sickness, infirmity, minority, or womanhood, or if there are reasonable grounds for further inquiry under Section 497(2) CrPC. Pre-arrest bail under Section 498 CrPC requires demonstrating ulterior motives and mala fides.",
      "claims": [
        {
          "statement": "Section 302 PPC penalizes Qatl-i-Amd with death, imprisonment for life, or imprisonment up to twenty-five years where the principle of fasad-fil-arz applies.",
          "evidence_ids": ["E1"]
        },
        {
          "statement": "Under Section 497 CrPC, an accused shall not be released on bail in a non-bailable offence if there appear reasonable grounds for believing that he has been guilty of an offence punishable with death or imprisonment for life, unless falling under statutory provisos or further inquiry.",
          "evidence_ids": ["E2"]
        }
      ],
      "caveats": ["Bail in capital offences under Section 302 PPC is governed strictly by the prohibitory clause of Section 497(1) CrPC."],
      "not_found": [],
      "open_questions": ["Whether there is direct ocular evidence or recovery linking the accused."]
    }
    """
    md, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=memo_json,
        evidence_pack=pack,
        fallback_query=q
    )
    assert report.is_memo_verified is True
    assert "Section 497" in md
