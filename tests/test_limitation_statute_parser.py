"""
tests/test_limitation_statute_parser.py

Strict acceptance tests for Limitation Act 1908 structured parser:
1. Article 57: Period is 'Three years', trigger starts with 'When the loan is made'.
2. Article 64: Period is 'Three years', trigger starts with 'When the accounts are stated in writing'.
3. Punjab Loans Limitation Act, 1904 note is attached to Article 57 as a linked caveat and cross-reference.
4. No record has unit_type of 'section' where the source is a schedule article.
5. Sequence-based validation: out-of-sequence candidates without gap match are strictly rejected.
6. Coverage report asserts >= 183 articles parsed and explicit rejection ledger.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from legal_ai.statutes.limitation_act_parser import LimitationActParser, strip_balanced_parens
from legal_ai.statutes.legal_unit_record import LegalUnitRecord, StatuteCoverageReport


CSV_PATH = "I:/Statutes/Federal_Statutes.csv"


@pytest.fixture(scope="module")
def parsed_limitation_act():
    if not os.path.exists(CSV_PATH):
        pytest.skip(f"Test requires {CSV_PATH} on I: drive")
    parser = LimitationActParser()
    records, report = parser.parse_from_csv(CSV_PATH)
    return records, report


def test_balanced_parens_nested():
    """Verify balanced parentheses handles nested parens without losing text."""
    sample = "Article 57 (For Punjab see Act 1904 (Punjab 1 of 1904) and s. 29(1)(b)) For money payable."
    cleaned, footnotes = strip_balanced_parens(sample)
    assert "For Punjab see Act 1904" in footnotes[0]
    assert "Punjab 1 of 1904" in footnotes[0]
    assert "s. 29(1)(b)" in footnotes[0]
    assert "Article 57 For money payable." == " ".join(cleaned.split())


def test_article_57_expected_values(parsed_limitation_act):
    """
    Acceptance Test 1:
    Article 57: three years, from when the loan is made.
    Punjab Loans Limitation Act, 1904 note is attached as a linked caveat.
    """
    records, report = parsed_limitation_act
    art57 = next((r for r in records if r.unit_type == "article" and r.number == "57"), None)

    assert art57 is not None, "Article 57 must exist in parsed records"
    assert art57.unit_type == "article", f"Expected unit_type 'article', got '{art57.unit_type}'"
    assert "for money payable for money lent" in art57.heading_description.lower()
    assert art57.period.lower() == "three years"
    assert art57.trigger.lower().startswith("when the loan is made")
    
    # Assert Punjab caveat
    assert len(art57.caveats) >= 1, "Article 57 must carry Punjab Loans Limitation Act caveat"
    assert "Punjab Loans Limitation Act, 1904" in art57.caveats[0]
    assert "punjab-loans-limitation-act-1904" in art57.cross_references


def test_article_64_expected_values(parsed_limitation_act):
    """
    Acceptance Test 2:
    Article 64: three years, from when the accounts are stated in writing.
    """
    records, report = parsed_limitation_act
    art64 = next((r for r in records if r.unit_type == "article" and r.number == "64"), None)

    assert art64 is not None, "Article 64 must exist in parsed records"
    assert art64.unit_type == "article", f"Expected unit_type 'article', got '{art64.unit_type}'"
    assert "accounts stated" in art64.heading_description.lower()
    assert art64.period.lower() == "three years"
    assert "when the accounts are stated in writing" in art64.trigger.lower()


def test_no_schedule_article_has_unit_type_section(parsed_limitation_act):
    """
    Acceptance Test 3:
    No record has unit_type of section where the source is a schedule article.
    """
    records, report = parsed_limitation_act
    for r in records:
        if r.parent and "schedule" in r.parent.lower():
            assert r.unit_type == "article", (
                f"Violation: Record {r.unit_id} from schedule has unit_type '{r.unit_type}' instead of 'article'"
            )


def test_coverage_and_rejection_ledger(parsed_limitation_act):
    """
    Acceptance Test 4:
    Coverage audit: At least 183 schedule articles parsed.
    Rejection ledger records exact reasons for all un-ingested rows.
    """
    records, report = parsed_limitation_act

    assert report.articles_parsed >= 183, f"Expected >= 183 articles, got {report.articles_parsed}"
    assert report.sections_parsed >= 28, f"Expected >= 28 main sections, got {report.sections_parsed}"
    assert report.sequence_integrity_verified is True
    
    # Verify rejections ledger is non-silent
    assert len(report.rejections) == report.rejected_rows_count
    for rej in report.rejections:
        assert "reason" in rej and len(rej["reason"]) > 0


def test_sequence_based_integrity_rejection():
    """
    Acceptance Test 5:
    Sequence integrity: A random fused candidate that does NOT match the sequence gap
    must be rejected and logged rather than guessed via naive digit stripping.
    """
    parser = LimitationActParser()
    dummy_rows = [
        {"Section_Number": "SCHI, 1", "Section_Title": "Art 1", "Full_Text": "1. Test One year When"},
        {"Section_Number": "SCHI, 999", "Section_Title": "Art 999", "Full_Text": "999. Out of sequence One year When"},
    ]
    parsed, report = parser.parse_rows(dummy_rows)
    # The 999 row should be rejected because expected_next was 2, and 999 does not end with 2
    assert len(parsed) == 1
    assert parsed[0].number == "1"
    assert report.rejected_rows_count >= 1
    reasons = [r["reason"] for r in report.rejections]
    assert any("Out-of-sequence" in r for r in reasons)
