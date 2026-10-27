"""
tests/test_order113_gazette_typos.py

ORDER 1.13 - ITEM 7: GAZETTE TYPOS & [SIC] MARKER TESTS
Verifies that:
1. Authentic printed gazette typos ('that', 'no shall') are stored as they are.
2. Quotes citing the gazette typo with '[sic]' pass verification.
3. Quotes citing the gazette typo without '[sic]' pass verification.
4. Unauthorized emendations (e.g. 'than' instead of 'that') fail with word-level diff.
"""

import pytest
from core.unified_statute_store import get_unified_statute_store
from legal_ai.verification.memo_verifier import MemoVerifier

@pytest.fixture
def store():
    return get_unified_statute_store()

@pytest.fixture
def verifier():
    return MemoVerifier()

def test_stored_text_preserves_authentic_gazette_typos(store):
    fio_s22 = store.get_by_canonical_id("FIO_2001_SEC_22")
    assert fio_s22 is not None
    text = fio_s22.get("text", "")
    assert "not less that two Judges" in text, "Gazette typo 'that' must be preserved verbatim in stored text"
    assert "no shall any stay" in text, "Gazette typo 'no shall' must be preserved verbatim in stored text"

def test_quote_with_sic_marker_passes(verifier):
    memo_with_sic = (
        "## Legal Research Memorandum\n\n"
        "Section 22 of the Financial Institutions (Recovery of Finances) Ordinance provides:\n\n"
        "> (4) An appeal under sub-section (1) shall be heard by a bench of not less that [sic] two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission.\n"
    )
    res = verifier.verify_memo(memo_with_sic, is_system_rendered=True)
    quote_fails = [f for f in res["failures"] if f.get("category") == "UNMATCHED_QUOTE"]
    assert len(quote_fails) == 0, f"Quote with '[sic]' marker should pass, got failures: {quote_fails}"

def test_quote_without_sic_marker_passes(verifier):
    memo_without_sic = (
        "## Legal Research Memorandum\n\n"
        "Section 22 of the Financial Institutions (Recovery of Finances) Ordinance provides:\n\n"
        "> (4) An appeal under sub-section (1) shall be heard by a bench of not less that two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission.\n"
    )
    res = verifier.verify_memo(memo_without_sic, is_system_rendered=True)
    quote_fails = [f for f in res["failures"] if f.get("category") == "UNMATCHED_QUOTE"]
    assert len(quote_fails) == 0, f"Quote without '[sic]' marker should pass, got failures: {quote_fails}"

def test_emended_quote_without_gazette_match_fails(verifier):
    memo_emended = (
        "## Legal Research Memorandum\n\n"
        "Section 22 of the Financial Institutions (Recovery of Finances) Ordinance provides:\n\n"
        "> (4) An appeal under sub-section (1) shall be heard by a bench of not less than two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission.\n"
    )
    res = verifier.verify_memo(memo_emended, is_system_rendered=True)
    quote_fails = [f for f in res["failures"] if f.get("category") == "UNMATCHED_QUOTE"]
    assert len(quote_fails) > 0, "Unauthorized emendation of 'that' to 'than' must fail quote matching"
    assert "that" in quote_fails[0]["issue"] and "than" in quote_fails[0]["issue"]
