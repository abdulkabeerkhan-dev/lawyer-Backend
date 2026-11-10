"""
tests/test_structured_memo_pipeline.py

Acceptance tests for Layer 5 (Bounded Evidence Pack), Layer 6 (Structured Memo Engine),
Layer 7 (Deterministic Verifier), and Layer 8 (Rendering).
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from legal_ai.statutes.legal_unit_record import LegalUnitRecord
from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack, EvidenceItem
from legal_ai.verification.statute_evidence_verifier import StatuteEvidenceVerifier
from legal_ai.synthesis.structured_memo_engine import (
    build_structured_memo_prompts,
    parse_structured_memo_response,
    render_layer8_markdown,
    execute_structured_memo_pipeline
)


@pytest.fixture
def sample_limitation_article_57():
    return LegalUnitRecord(
        unit_id="limitation-act-1908:article:57",
        statute_id="limitation-act-1908",
        statute_title="Limitation Act, 1908",
        jurisdiction="federal",
        unit_type="article",
        number="57",
        parent="First Schedule, First Division: Suits, Part VI",
        heading_description="For money payable for money lent",
        period="Three years",
        trigger="When the loan is made",
        text="For money payable for money lent. Three years. When the loan is made.",
        footnotes=["Punjab Loans Limitation Act, 1904 (Punjab 1 of 1904), and s. 29 (1) (b) of this Act."],
        caveats=["Punjab Loans Limitation Act, 1904: Local extension/variance applies within Punjab province."],
        checksum="dummy_checksum_57"
    )


def test_bounded_evidence_pack_auto_pulls_caveats(sample_limitation_article_57):
    """
    Layer 5 Invariant: Adding a LegalUnitRecord with caveats automatically
    creates and binds a dedicated linked evidence item (e.g. E2 for Punjab caveat).
    """
    pack = BoundedEvidencePack()
    e1_id = pack.add_legal_unit(sample_limitation_article_57, pull_linked_caveats=True)

    assert e1_id == "E1"
    assert "E1" in pack.items
    assert pack.items["E1"].unit_type == "article"
    assert pack.items["E1"].number == "57"

    # Must automatically pull Punjab caveat as E2
    assert "E2" in pack.items
    assert pack.items["E2"].item_type == "linked_caveat"
    assert "Punjab Loans Limitation Act" in pack.items["E2"].text

    formatted_pack = pack.format_pack_for_llm()
    assert "[E1] Limitation Act, 1908 — Article 57" in formatted_pack
    assert "[E2] CAVEAT / LOCAL OVERRIDE:" in formatted_pack
    assert "When the loan is made" in formatted_pack


def test_structured_memo_pipeline_valid_opinion(sample_limitation_article_57):
    """
    Layers 6, 7, 8: Valid JSON memo with correct Article 57 reference and quote
    passes deterministic verification, awards verified badges, and renders answer first.
    """
    pack = BoundedEvidencePack()
    pack.add_legal_unit(sample_limitation_article_57, pull_linked_caveats=True)

    verifier = StatuteEvidenceVerifier()
    verifier.register_units([sample_limitation_article_57])

    valid_json = """
    {
      "answer": "A suit for the recovery of money lent must be instituted within three years from when the loan is made.",
      "claims": [
        {
          "statement": "Under Article 57 of the Limitation Act, 1908, the prescribed period is 'three years' running from 'when the loan is made'.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [
        "In Punjab, the suit is subject to the provisions of the Punjab Loans Limitation Act, 1904."
      ],
      "not_found": [],
      "open_questions": []
    }
    """

    markdown, report, memo_payload = execute_structured_memo_pipeline(
        raw_llm_response=valid_json,
        evidence_pack=pack,
        verifier=verifier
    )

    assert report.is_memo_verified is True
    assert report.total_claims == 1
    assert report.verified_claims_count == 1
    assert report.unverified_claims_count == 0
    assert len(report.blocking_violations) == 0

    # Layer 8 Invariants: Answer First!
    assert markdown.startswith("### Direct Legal Opinion")
    assert "A suit for the recovery of money lent" in markdown
    assert "✓ VERIFIED RESEARCH MEMORANDUM" in markdown
    assert "`✓ Verified` [E1]" in markdown
    assert "Article 57" in markdown
    assert "Section 57" not in markdown
    assert "Section 264" not in markdown


def test_structured_memo_pipeline_blocks_section_264_and_section_57(sample_limitation_article_57):
    """
    Layer 7 Deterministic Verifier: Strictly blocks 'Section 264' (phantom)
    and 'Section 57' (wrong unit_type).
    """
    pack = BoundedEvidencePack()
    pack.add_legal_unit(sample_limitation_article_57, pull_linked_caveats=True)

    verifier = StatuteEvidenceVerifier()
    verifier.register_units([sample_limitation_article_57])

    # Case A: Phantom Section 264
    invalid_json_264 = """
    {
      "answer": "Money suits are barred after 3 years.",
      "claims": [
        {
          "statement": "Under Section 264 of the Limitation Act, 1908, recovery of money is barred after three years.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [],
      "not_found": [],
      "open_questions": []
    }
    """

    markdown_264, report_264, _ = execute_structured_memo_pipeline(
        raw_llm_response=invalid_json_264,
        evidence_pack=pack,
        verifier=verifier
    )

    assert report_264.is_memo_verified is False
    assert report_264.unverified_claims_count == 1
    assert any("Section 264" in v or "does not exist" in v for v in report_264.blocking_violations)
    assert "PARTIAL RESEARCH RECORD" in markdown_264
    assert "`⚠️ Unverified`" in markdown_264

    # Case B: Calling Article 57 'Section 57'
    invalid_json_sec57 = """
    {
      "answer": "Money suits are barred after 3 years.",
      "claims": [
        {
          "statement": "Section 57 of the Limitation Act, 1908 prescribes three years.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [],
      "not_found": [],
      "open_questions": []
    }
    """

    markdown_sec57, report_sec57, _ = execute_structured_memo_pipeline(
        raw_llm_response=invalid_json_sec57,
        evidence_pack=pack,
        verifier=verifier
    )

    assert report_sec57.is_memo_verified is False
    assert any("Section 57" in v or "Article 57" in v for v in report_sec57.blocking_violations)


def test_structured_memo_pipeline_blocks_unadmitted_evidence_id(sample_limitation_article_57):
    """
    Layer 7 Verifier: Blocks claims citing non-existent evidence IDs like E99.
    """
    pack = BoundedEvidencePack()
    pack.add_legal_unit(sample_limitation_article_57, pull_linked_caveats=True)

    verifier = StatuteEvidenceVerifier()

    hallucinated_eid_json = """
    {
      "answer": "Suit is governed by limitation rules.",
      "claims": [
        {
          "statement": "The limitation period is three years under general civil law.",
          "evidence_ids": ["E99"]
        }
      ],
      "caveats": [],
      "not_found": [],
      "open_questions": []
    }
    """

    _, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=hallucinated_eid_json,
        evidence_pack=pack,
        verifier=verifier
    )

    assert report.is_memo_verified is False
    assert any("E99" in v for v in report.blocking_violations)


def test_structured_memo_pipeline_blocks_verified_banner_on_not_found(sample_limitation_article_57):
    """
    Fix A: Whenever not_found[] is non-empty, '✓ VERIFIED RESEARCH MEMORANDUM' is blocked
    and replaced with 'PARTIAL RESEARCH RECORD - [N] issues unresolved.'
    """
    pack = BoundedEvidencePack()
    pack.query_text = "What is the limitation for money lent and what about foreign loans?"
    pack.add_legal_unit(sample_limitation_article_57, pull_linked_caveats=True)
    verifier = StatuteEvidenceVerifier()
    verifier.register_units([sample_limitation_article_57])

    json_with_not_found = """
    {
      "answer": "Money lent is barred after three years under Article 57.",
      "claims": [
        {
          "statement": "Under Article 57 of the Limitation Act, 1908, the period is three years.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [],
      "not_found": ["Limitation rules for foreign cross-border loans were not found in the primary store."],
      "open_questions": []
    }
    """

    markdown, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=json_with_not_found,
        evidence_pack=pack,
        verifier=verifier
    )

    assert report.is_memo_verified is False
    assert "✓ VERIFIED RESEARCH MEMORANDUM" not in markdown
    assert "100% of claims deterministically grounded" not in markdown
    assert "PARTIAL RESEARCH RECORD - 1 issues unresolved." in markdown
