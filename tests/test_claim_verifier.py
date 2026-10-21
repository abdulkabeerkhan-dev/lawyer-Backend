"""
tests/test_claim_verifier.py

Unit tests for the claim-to-source verification and scrubbing engine.
"""

import pytest
from legal_ai.verification.claim_verifier import verify_and_scrub_memo_claims


def test_scrub_foreign_ni_act_138_penalties():
    memo_with_leakage = (
        "## Legal Analysis\n"
        "Under Section 138, the punishment is imprisonment up to two years or "
        "fine which may extend to twice the amount of the cheque or both. "
        "The complainant must issue notice within 30 days of receipt of notice."
    )
    result = verify_and_scrub_memo_claims(
        memo_with_leakage,
        retrieved_precedents=[],
        statutory_context="",
        query_text="Punishment under Section 138 NI Act for bounced cheque in Pakistan?"
    )
    assert result.has_violations
    assert "two years" not in result.cleaned_text
    assert "twice the amount of the cheque" not in result.cleaned_text
    assert "within 30 days of receipt of notice" not in result.cleaned_text
    assert "three years" in result.cleaned_text


def test_scrub_pld_2026_sc_75_security_cheque_holding():
    memo_with_false_holding = (
        "## Judicial Authorities\n"
        "### Legal Fee Case — PLD 2026 SC 75\n"
        "The Supreme Court in PLD 2026 SC 75 definitively held that a security cheque cannot attract Section 489-F PPC."
    )
    result = verify_and_scrub_memo_claims(
        memo_with_false_holding,
        retrieved_precedents=[{"citation": "PLD 2026 SC 75", "holding": "Pre-arrest bail granted in advocate fee cheque dispute."}],
        statutory_context="",
        query_text="Cite the Supreme Court judgment holding a security cheque cannot attract 489-F."
    )
    assert any(v["type"] == "UNGROUNDED_CASE_HOLDING" for v in result.violations)
    assert "definitively held that a security cheque" not in result.cleaned_text
    assert "advocate fee cheque dispute" in result.cleaned_text


def test_correct_order_xxxix_rule_2a_foreign_import():
    memo_with_rule_2a = (
        "Under Order XXXIX Rule 2A CPC, the plaintiff can seek attachment and detention for breach of stay order."
    )
    result = verify_and_scrub_memo_claims(
        memo_with_rule_2a,
        retrieved_precedents=[],
        statutory_context="",
        query_text="Injunction under Order XXXIX Rule 2A CPC for breach of a stay order?"
    )
    assert any(v["type"] == "O39_R2A_INDIAN_IMPORT" for v in result.violations)
    assert "Order XXXIX Rule 2(3) CPC" in result.cleaned_text
    assert "2006 YLR 2758" in result.cleaned_text


def test_correct_section_420_ppc_bailable_mismatch():
    memo_with_bail_error = (
        "Section 420 PPC is bailable as of right and governed by Section 496 Cr.P.C."
    )
    result = verify_and_scrub_memo_claims(
        memo_with_bail_error,
        retrieved_precedents=[],
        statutory_context="",
        query_text="Punishment under Section 420 Indian Penal Code in Pakistan?"
    )
    assert any(v["type"] == "SCHEDULE_II_MISMATCH" for v in result.violations)
    assert "non-bailable" in result.violations[0]["description"]


def test_court_metadata_mismatch_correction():
    memo_with_court_mismatch = (
        "### Sign Source Case — 2007 YLR 2287\n"
        "- **Court**: Supreme Court of Pakistan\n"
        "Supreme Court held in 2007 YLR 2287 that contractual dispute warrants leave."
    )
    result = verify_and_scrub_memo_claims(
        memo_with_court_mismatch,
        retrieved_precedents=[{"citation": "2007 YLR 2287", "court": "High Court of Sindh", "preview": "High Court Karachi bench"}],
        statutory_context="",
        query_text="Dishonour of cheque"
    )
    assert any(v["type"] == "COURT_METADATA_MISMATCH" for v in result.violations)
    assert "Supreme Court of Pakistan" not in result.cleaned_text
    assert "High Court" in result.cleaned_text


def test_negative_holding_query_disclaimer_injection():
    memo = (
        "## Judicial Authorities\n"
        "### Advocate Fee Case — PLD 2026 SC 75\n"
        "- **Court**: Supreme Court of Pakistan\n"
        "- **Holding**: Pre-arrest bail confirmed in fee dispute."
    )
    query = "Cite the Supreme Court judgment holding a security cheque cannot attract 489-F."
    result = verify_and_scrub_memo_claims(
        memo,
        retrieved_precedents=[{"citation": "PLD 2026 SC 75", "holding": "Fee dispute bail."}],
        statutory_context="",
        query_text=query
    )
    assert "I did not find a case that squarely holds this" in result.cleaned_text
    assert any(v["type"] == "NEGATIVE_AUTHORITY_UNLOCATED" for v in result.violations)


def test_strip_residual_certifications_and_word_count():
    memo = (
        "## Application to Query\n"
        "The offence is punishable under Section 489-F PPC.\n\n"
        "Counsel's Certification\n"
        "Prepared by Senior Counsel\n"
        "[Current Date]\n"
        "Word Count: 1450 words\n"
        "All 8 Sections Completed\n"
        "all citations verified active status"
    )
    result = verify_and_scrub_memo_claims(
        memo,
        retrieved_precedents=[],
        statutory_context="",
        query_text="Cheque query"
    )
    assert "Counsel's Certification" not in result.cleaned_text
    assert "Prepared by Senior Counsel" not in result.cleaned_text
    assert "[Current Date]" not in result.cleaned_text
    assert "Word Count" not in result.cleaned_text
    assert "All 8 Sections Completed" not in result.cleaned_text
    assert "all citations verified active status" not in result.cleaned_text
