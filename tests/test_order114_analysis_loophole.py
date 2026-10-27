"""
tests/test_order114_analysis_loophole.py

ORDER 1.14 - ITEM 1 TESTS:
1. Analysis claim with an invented case -> BLOCKED
2. Analysis claim with "Section 61 FIO allows a second appeal in sixty days" -> BLOCKED
3. Analysis claim with "the court must always grant" -> BLOCKED
4. Analysis claim with a harmless application of facts ("On your facts, the delay looks long") -> PASSES
"""

import pytest
from core.claim_first_memo import ClaimFirstVerifier, render_claim_first_memo

@pytest.fixture
def verifier():
    return ClaimFirstVerifier()

def test_analysis_with_invented_case_blocked(verifier):
    claim = {
        "text": "In Messrs Alpha Ltd v. State Bank (2025 SCMR 99999), the Supreme Court laid down strict principles.",
        "type": "analysis",
        "support": None
    }
    res = verifier.verify_claim_memo([claim])
    assert res["passed"] is False, "Analysis with invented case must be BLOCKED"
    assert any(f["category"] in ("CITATION_IN_ANALYSIS", "UNVERIFIED_AUTHORITY", "STATUTORY_OR_JUDICIAL_HOLDING_IN_ANALYSIS") for f in res["failures"])

def test_analysis_with_statute_claim_and_number_blocked(verifier):
    claim = {
        "text": "Section 61 FIO allows a second appeal in sixty days against an interlocutory order.",
        "type": "analysis",
        "support": None
    }
    res = verifier.verify_claim_memo([claim], user_question="Can I appeal a Banking Court order?")
    assert res["passed"] is False, "Analysis with statute statement must be BLOCKED"
    categories = [f["category"] for f in res["failures"]]
    assert "CITATION_IN_ANALYSIS" in categories or "STATUTORY_OR_JUDICIAL_HOLDING_IN_ANALYSIS" in categories or "UNSOURCED_NUMBER_IN_ANALYSIS" in categories

def test_analysis_with_absolute_words_blocked(verifier):
    claim = {
        "text": "The court must always grant an interim injunction if a prima facie case exists.",
        "type": "analysis",
        "support": None
    }
    res = verifier.verify_claim_memo([claim])
    assert res["passed"] is False, "Analysis with absolute words 'must always' must be BLOCKED"
    assert any(f["category"] == "ABSOLUTE_ASSERTION_IN_ANALYSIS" for f in res["failures"])

def test_analysis_harmless_facts_application_passes(verifier):
    claim = {
        "text": "On your facts, the delay looks long and client should provide reasons for the lapse of time.",
        "type": "analysis",
        "support": None
    }
    res = verifier.verify_claim_memo([claim], user_question="Is the delay in filing our application too long?")
    assert res["passed"] is True, f"Harmless application of facts must PASS, got failures: {res['failures']}"
    assert res["total_failures"] == 0

def test_analysis_rendering_header(verifier):
    claims = [
        {"text": "22. Appeal. (1) Subject to sub-section (2)...", "type": "quote", "support": "FIO_2001_SEC_22(1)"},
        {"text": "On your facts, the delay looks long.", "type": "analysis", "support": None}
    ]
    rendered = render_claim_first_memo(claims)
    assert "### Unreviewed analysis — not checked against any source" in rendered
    assert "[analysis (unreviewed)]" in rendered
    assert "On your facts, the delay looks long." in rendered
