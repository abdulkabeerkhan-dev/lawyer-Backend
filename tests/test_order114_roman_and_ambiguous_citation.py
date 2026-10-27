"""
tests/test_order114_roman_and_ambiguous_citation.py

ORDER 1.14 - ITEM 4 TESTS:
1. Canonical Roman numeral parser validates canonical Roman numerals and rejects non-canonical forms.
2. 'section 15(11) of the Ordinance' without full title is BLOCKED as AMBIGUOUS_CITATION.
3. 'Section 15(11) of the Financial Institutions (Recovery of Finances) Ordinance, 2001' resolves cleanly.
"""

import pytest
from core.legal_guardrails import parse_roman_numeral, ROMAN_NUMERAL_MAP, normalize_statute_citation
from legal_ai.verification.memo_verifier import MemoVerifier

def test_canonical_roman_numeral_parser():
    # Valid canonical Roman numerals
    valid_cases = [
        ("I", 1), ("II", 2), ("III", 3), ("IV", 4), ("V", 5), ("VI", 6),
        ("IX", 9), ("X", 10), ("XIV", 14), ("XIX", 19), ("XXI", 21),
        ("XXXIX", 39), ("XL", 40), ("XLIII", 43), ("L", 50), ("LI", 51),
        ("XC", 90), ("C", 100), ("CD", 400), ("D", 500), ("CM", 900), ("M", 1000)
    ]
    for numeral, expected in valid_cases:
        assert parse_roman_numeral(numeral) == expected
        assert parse_roman_numeral(numeral.lower()) == expected
        assert ROMAN_NUMERAL_MAP.get(numeral.lower()) == expected

    # Invalid / non-canonical Roman numerals MUST be rejected (return None)
    invalid_cases = [
        "IIII", "VV", "IL", "IC", "ID", "IM", "XD", "XM", "VX", "LC", "DM",
        "XIVX", "ABC", "42", "", None
    ]
    for bad in invalid_cases:
        assert parse_roman_numeral(bad) is None
        assert ROMAN_NUMERAL_MAP.get(bad) is None

def test_ambiguous_ordinance_citation_blocked():
    verifier = MemoVerifier()
    # Citation with 'of the Ordinance' but NO full title in the paragraph/claim
    cit = "section 15(11) of the Ordinance"
    res = verifier.verify_statutory_citation(cit)
    assert res.is_valid is False, f"Citation '{cit}' without full title must be BLOCKED as AMBIGUOUS_CITATION"
    assert "AMBIGUOUS_CITATION" in (res.reason or "")

def test_unambiguous_ordinance_citation_with_full_title_passes():
    verifier = MemoVerifier()
    # Citation with full title
    cit = "Section 15(11) of the Financial Institutions (Recovery of Finances) Ordinance, 2001"
    res = verifier.verify_statutory_citation(cit)
    assert res.is_valid is True, f"Citation with full title must pass, got reason: {res.reason}"
    assert res.cid == "FIO_2001_SEC_15"
