"""
tests/test_statute_evidence_verifier.py

Acceptance tests for Layer 7 Deterministic Code Verifier:
1. Blocks 'Section 264' (phantom number + wrong unit type) and blocks verified badge.
2. Blocks 'Section 57' (wrong unit type for Schedule I article) and blocks verified badge.
3. Blocks ungrounded claims that omit evidence IDs.
4. Blocks fabricated quotes not matching stored evidence text.
5. Passes 100% green and awards verified badge for clean Article 57 claim citing valid evidence.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legal_ai.verification.statute_evidence_verifier import StatuteEvidenceVerifier, MemoVerificationReport
from legal_ai.statutes.legal_unit_record import LegalUnitRecord


@pytest.fixture
def mock_evidence_pack():
    art57 = LegalUnitRecord(
        unit_id="limitation-act-1908:article:57",
        statute_id="limitation-act-1908",
        statute_title="Limitation Act, 1908",
        jurisdiction="federal",
        unit_type="article",
        number="57",
        parent="First Schedule",
        heading_description="For money payable for money lent.",
        period="Three years",
        trigger="When the loan is made",
        text="Article 57: For money payable for money lent.\nPeriod of limitation: Three years.\nTime from which period begins to run: When the loan is made.",
        checksum="dummyhash57"
    )
    return {
        "E1": art57
    }


def test_verifier_blocks_section_264(mock_evidence_pack):
    """Assertion: 'Section 264' must be strictly blocked and denied verified badge."""
    verifier = StatuteEvidenceVerifier()
    verifier.register_units(list(mock_evidence_pack.values()))

    memo_payload = {
        "answer": "The suit is barred under Section 264.",
        "claims": [
            {
                "statement": "Under Section 264 of the Limitation Act, 1908, the period is three years.",
                "evidence_ids": ["E1"]
            }
        ]
    }

    report = verifier.verify_structured_memo(memo_payload, mock_evidence_pack)
    assert report.is_memo_verified is False
    assert report.mode == "partial_result"
    assert any("264" in v for v in report.blocking_violations)


def test_verifier_blocks_section_57_unit_type_confusion(mock_evidence_pack):
    """Assertion: Calling Article 57 'Section 57' must be blocked for unit type mismatch."""
    verifier = StatuteEvidenceVerifier()
    verifier.register_units(list(mock_evidence_pack.values()))

    memo_payload = {
        "answer": "Three years.",
        "claims": [
            {
                "statement": "Under Section 57 of the Limitation Act, the limitation is three years.",
                "evidence_ids": ["E1"]
            }
        ]
    }

    report = verifier.verify_structured_memo(memo_payload, mock_evidence_pack)
    assert report.is_memo_verified is False
    assert any("Article" in v and "Section 57" in v for v in report.blocking_violations)


def test_verifier_blocks_claim_with_missing_evidence_id(mock_evidence_pack):
    """Assertion: Claims with no evidence IDs are unverified."""
    verifier = StatuteEvidenceVerifier()
    verifier.register_units(list(mock_evidence_pack.values()))

    memo_payload = {
        "answer": "Answer.",
        "claims": [
            {
                "statement": "Article 57 provides three years for money lent.",
                "evidence_ids": []
            }
        ]
    }

    report = verifier.verify_structured_memo(memo_payload, mock_evidence_pack)
    assert report.is_memo_verified is False
    assert any("no grounded evidence ID" in v for v in report.blocking_violations)


def test_verifier_blocks_fabricated_quote(mock_evidence_pack):
    """Assertion: Quoted text that does not appear in cited evidence must be blocked."""
    verifier = StatuteEvidenceVerifier()
    verifier.register_units(list(mock_evidence_pack.values()))

    memo_payload = {
        "answer": "Answer.",
        "claims": [
            {
                "statement": 'Article 57 states that "all loans shall be repaid within ninety days upon demand".',
                "evidence_ids": ["E1"]
            }
        ]
    }

    report = verifier.verify_structured_memo(memo_payload, mock_evidence_pack)
    assert report.is_memo_verified is False
    assert any("does not match the official text" in v for v in report.blocking_violations)


def test_verifier_accepts_clean_grounded_article_57_claim(mock_evidence_pack):
    """Assertion: Valid claim citing Article 57 with E1 passes and gets verified badge."""
    verifier = StatuteEvidenceVerifier()
    verifier.register_units(list(mock_evidence_pack.values()))

    memo_payload = {
        "answer": "The limitation period for filing a suit for recovery of money lent is three years.",
        "claims": [
            {
                "statement": 'Under Article 57 of the Limitation Act, 1908, the period "For money payable for money lent" is three years from "When the loan is made".',
                "evidence_ids": ["E1"]
            }
        ]
    }

    report = verifier.verify_structured_memo(memo_payload, mock_evidence_pack)
    assert report.is_memo_verified is True
    assert report.verified_claims_count == 1
    assert len(report.blocking_violations) == 0
    assert report.mode == "full"
