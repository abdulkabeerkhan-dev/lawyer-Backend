"""
tests/test_grounding_remediation.py

Automated Acceptance Regression Tests for Hallucination and Grounding Remediation
in the Pakistani Legal Research Assistant (lawyer-backend).

Validates the 5 observed failure queries:
1. "Punishment under Section 138 NI Act for bounced cheque in Pakistan?"
2. "Punishment under Section 420 Indian Penal Code in Pakistan?"
3. "Injunction under Order XXXIX Rule 2A CPC for breach of a stay order?"
4. "Cite the Supreme Court judgment holding a security cheque cannot attract 489-F."
5. Cross-cutting: No artificial certifications, fake dates, or word counts.
"""

import pytest
import re
from core.legal_query_planner import (
    create_deterministic_fallback_plan,
    check_query_premises
)
from legal_ai.statutes.statute_store import lookup, get_crpc_schedule_ii
from legal_ai.statutes.statute_injector import inject_statutory_framework
from legal_ai.ranking.relevance_filter import filter_topic_relevance
from legal_ai.verification.claim_verifier import verify_and_scrub_memo_claims
from legal_ai.verification.doctrinal_rules import PATTERN_RULES, rule_matches_sentence
from legal_ai.synthesis.memorandum_generator import purge_debug_warnings


# =========================================================================
# Acceptance Test 1: Bounced Cheque under Section 138 NI Act
# =========================================================================
def test_acceptance_query_1_bounced_cheque_ni_138():
    query = "Punishment under Section 138 NI Act for bounced cheque in Pakistan?"

    # Step 1: Premise check in planner
    corrections = check_query_premises(query)
    assert len(corrections) > 0
    assert any("does not exist" in c.get("explanation", "") for c in corrections)
    assert any("Section 489-F" in c.get("mandatory_opening_thesis", "") for c in corrections)

    plan = create_deterministic_fallback_plan(query)
    assert "Section 489-F PPC" in plan.provisions
    assert "Section 138" not in [p for p in plan.provisions if "NI" in p]
    assert any("cheque" in l["lane"] or "cheque" in l["query"] for l in plan.search_lanes)

    # Step 2: Relevance gate drops Tax and Land cases
    from legal_ai.ranking.relevance_filter import filter_candidate_quality_before_ranking
    retrieved_docs = [
        {"case_id": "c1", "citation": "2026 SCMR 227", "title": "Inland Revenue v. ABC", "preview": "Section 138 of the Income Tax Ordinance 2001 recovery of tax through bank accounts. High Court set aside the recovery notice as illegal."},
        {"case_id": "c2", "citation": "2026 PTD 192", "title": "Taxpayer v. CIR", "preview": "Income Tax Ordinance 2001 Section 138 demand notice and bank attachment without affording reasonable opportunity of being heard."},
        {"case_id": "c3", "citation": "PLD 2026 SC 17", "title": "AJK v. Owners", "preview": "Land Acquisition Act 1894 Section 18 compensation enhancement awarded by Collector Land Acquisition for acquired territory."},
        {"case_id": "c4", "citation": "2025 SCMR 101", "title": "Tariq v. State", "preview": "Section 489-F PPC dishonour of cheque for dishonest issuance towards obligation. Pre-arrest bail confirmed where transaction was commercial."}
    ]
    gated_docs, rejection_stats = filter_candidate_quality_before_ranking(retrieved_docs, plan)
    gated_citations = [d["citation"] for d in gated_docs]
    assert "2026 SCMR 227" not in gated_citations
    assert "2026 PTD 192" not in gated_citations
    assert "PLD 2026 SC 17" not in gated_citations
    assert "2025 SCMR 101" in gated_citations

    # Step 3: Statutory injector injects verified 489-F PPC and premise directive
    injected_result = inject_statutory_framework(plan, query_text=query)
    statute_block = injected_result["statute_block"]
    assert "PREMISE CORRECTION" in statute_block
    assert "Section 489-F" in statute_block
    assert "three years" in statute_block.lower()

    # Step 4: Claim verifier scrubs foreign Indian NI Act regime
    memo_with_foreign_draft = (
        "## Legal Analysis\n"
        "Under Section 138 of the NI Act, the offence is punishable with imprisonment for two years "
        "and a fine which may extend to twice the amount of the cheque. The payee must serve a "
        "30-day legal notice of dishonour before filing the complaint under s.142."
    )
    scrubbed = verify_and_scrub_memo_claims(
        memo_with_foreign_draft,
        retrieved_precedents=gated_docs,
        query_text=query
    )
    assert "two years" not in scrubbed.cleaned_text
    assert "twice the amount of the cheque" not in scrubbed.cleaned_text
    assert "30-day" not in scrubbed.cleaned_text


# =========================================================================
# Acceptance Test 2: Section 420 Indian Penal Code in Pakistan
# =========================================================================
def test_acceptance_query_2_cheating_ipc_420():
    query = "Punishment under Section 420 Indian Penal Code in Pakistan?"

    # Step 1: Premise check in planner
    corrections = check_query_premises(query)
    assert len(corrections) > 0
    assert any("Indian Penal Code" in c.get("mandatory_opening_thesis", "") for c in corrections)
    assert any("Pakistan Penal Code" in c.get("mandatory_opening_thesis", "") or "PPC" in c.get("mandatory_opening_thesis", "") for c in corrections)

    plan = create_deterministic_fallback_plan(query)
    assert "Section 420 PPC" in plan.provisions

    # Step 2: Schedule II verification from verified database
    sched2 = get_crpc_schedule_ii("420")
    assert sched2 is not None
    assert sched2["bailable"] is False
    assert "non-bailable" in sched2.get("bailable_status", "").lower() or "not bailable" in sched2.get("bailable_status", "").lower()
    assert sched2["cognizable"] is True or "arrest without warrant" in sched2.get("police_arrest", "").lower()
    assert "7 years" in sched2["punishment"].lower() or "seven years" in sched2["punishment"].lower()

    # Step 3: Injected statutory context
    injected_result = inject_statutory_framework(plan, query_text=query)
    statute_block = injected_result["statute_block"]
    assert "Section 420" in statute_block
    assert "Not bailable" in statute_block

    # Step 4: Claim verifier checks prohibitory clause or false s.496 claim
    memo_contradiction = (
        "Section 420 PPC is bailable as of right and governed by Section 496 Cr.P.C."
    )
    scrubbed = verify_and_scrub_memo_claims(
        memo_contradiction,
        query_text=query
    )
    assert any(v["type"] == "SCHEDULE_II_MISMATCH" for v in scrubbed.violations)



# =========================================================================
# Acceptance Test 3: Stay Order Breach under Order XXXIX Rule 2A CPC
# =========================================================================
def test_acceptance_query_3_injunction_breach_order_39_rule_2a():
    query = "Injunction under Order XXXIX Rule 2A CPC for breach of a stay order?"

    # Step 1: Store resolves Rule 2A (15-day ex-parte limit per Act XIV of 1994 s.11)
    res = lookup("CPC_1908", "Order XXXIX Rule 2A")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert "fifteen days" in res.text.lower()

    # And Rule 2(3) exists in the store with authentic statutory text
    res_2_3 = lookup("CPC_1908", "Order XXXIX Rule 2(3)")
    assert res_2_3.exists is True
    assert "disobedience" in res_2_3.text.lower()
    assert "prison" in res_2_3.text.lower()
    assert "attached" in res_2_3.text.lower()

    # Step 2: Planner identifies both Rule 2A and Rule 2(3) CPC
    plan = create_deterministic_fallback_plan(query)
    assert any("Order XXXIX Rule 2" in p or "Rule 2" in p for p in plan.provisions)

    # Step 3: Statutory injector provides bare act text of Rule 2(3)
    injected_result = inject_statutory_framework(plan, query_text=query)
    statute_block = injected_result["statute_block"]
    assert "Rule 2" in statute_block

    # Step 4: Claim verifier routes Rule 2A assertions to Rule 2(3) (2006 YLR 2758)
    memo_with_rule_2a_claim = (
        "Under Order XXXIX Rule 2A CPC, the court may attach property and detain the party in prison for breach."
    )
    scrubbed = verify_and_scrub_memo_claims(
        memo_with_rule_2a_claim,
        query_text=query
    )
    assert any(v["type"] in ("O39_R2A_BREACH_MISATTRIBUTION", "O39_R2A_INDIAN_IMPORT") for v in scrubbed.violations)
    assert "Order XXXIX Rule 2(3) CPC" in scrubbed.cleaned_text
    assert "2006 YLR 2758" in scrubbed.cleaned_text


# =========================================================================
# Acceptance Test 4: Negative Holding for Security Cheque & 489-F
# =========================================================================
def test_acceptance_query_4_security_cheque_holding_negative():
    query = "Cite the Supreme Court judgment holding a security cheque cannot attract 489-F."

    retrieved = [
        {
            "citation": "PLD 2026 SC 75",
            "holding": "Pre-arrest bail confirmed in advocate professional fee dispute.",
            "court": "Supreme Court of Pakistan"
        },
        {
            "citation": "2024 SCMR 1719",
            "preview": "Pre-arrest bail in cheque dishonour where civil dispute pending...",
            "truncated": True,
            "court": "Supreme Court of Pakistan"
        }
    ]

    # Model draft erroneously claimed PLD 2026 SC 75 definitively held this
    bad_draft = (
        "## Judicial Authorities\n"
        "### Legal Fee Bail Case — PLD 2026 SC 75\n"
        "- **Court**: Supreme Court of Pakistan\n"
        "The Supreme Court in PLD 2026 SC 75 definitively held that a security cheque cannot attract Section 489-F PPC.\n"
        "This landmark authority provides an authoritative shield against prosecution."
    )

    scrubbed = verify_and_scrub_memo_claims(
        bad_draft,
        retrieved_precedents=retrieved,
        query_text=query
    )

    # 1. Negative holding disclaimer injected
    assert "I did not find a case that squarely holds this" in scrubbed.cleaned_text
    # 2. PLD 2026 SC 75 false security cheque holding neutralized
    assert "definitively held that a security cheque" not in scrubbed.cleaned_text
    assert "advocate professional fee dispute" in scrubbed.cleaned_text
    # 3. Superlatives stripped
    assert "definitively held" not in scrubbed.cleaned_text
    assert "landmark authority" not in scrubbed.cleaned_text
    assert "authoritative shield" not in scrubbed.cleaned_text


# =========================================================================
# Acceptance Test 5: Cross-Cutting Prohibition on Artificial Certifications
# =========================================================================
def test_acceptance_cross_cutting_no_artificial_certifications():
    dirty_memo = (
        "## Legal Issue\n"
        "Scope of Section 489-F PPC.\n\n"
        "## Application to Query\n"
        "The accused may be tried by a Magistrate of the first class.\n\n"
        "Counsel's Certification\n"
        "Prepared by Senior Counsel\n"
        "[Current Date]\n"
        "Word Count: 1820 words\n"
        "All 8 Sections Completed\n"
        "all citations verified active status\n"
        "no conflicting decisions identified\n"
        "Authority Strength: Binding"
    )

    # Test scrubber in memorandum_generator
    purged = purge_debug_warnings(dirty_memo)
    assert "Counsel's Certification" not in purged
    assert "Prepared by Senior Counsel" not in purged
    assert "[Current Date]" not in purged
    assert "Word Count" not in purged
    assert "All 8 Sections Completed" not in purged

    # Test claim verifier
    scrubbed = verify_and_scrub_memo_claims(purged, query_text="Check 489-F")
    assert "Counsel's Certification" not in scrubbed.cleaned_text
    assert "Prepared by Senior Counsel" not in scrubbed.cleaned_text
    assert "[Current Date]" not in scrubbed.cleaned_text
    assert "Word Count" not in scrubbed.cleaned_text
    assert "all citations verified active status" not in scrubbed.cleaned_text
