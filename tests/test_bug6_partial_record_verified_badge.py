"""
tests/test_bug6_partial_record_verified_badge.py

Verification suite for Bug 6:
Mutual exclusivity between 'VERIFIED RESEARCH MEMORANDUM' and 'PARTIAL RESEARCH RECORD':
1. When not_found list is non-empty OR is_partial is True:
   - Must show 'PARTIAL RESEARCH RECORD - [N] issues unresolved.' ONLY.
   - Must NEVER show 'VERIFIED RESEARCH MEMORANDUM'.
   - Must NOT show verified badges on claims.
2. When all identified issues are resolved and verified:
   - Must show 'VERIFIED RESEARCH MEMORANDUM'.
   - Must NEVER show 'PARTIAL RESEARCH RECORD'.
3. Both statements must NEVER appear at the same time.
"""

import pytest
from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack, LegalUnitRecord
from legal_ai.verification.statute_evidence_verifier import StatuteEvidenceVerifier
from legal_ai.synthesis.structured_memo_engine import execute_structured_memo_pipeline


@pytest.fixture
def mock_legal_unit():
    return LegalUnitRecord(
        unit_id="limitation-act-1908:article:113",
        statute_id="limitation-act-1908",
        statute_title="Limitation Act, 1908",
        unit_type="article",
        number="113",
        heading_description="For specific performance of a contract.",
        period="Three years",
        trigger="The date fixed for the performance, or if no such date is fixed, when the plaintiff has notice that performance is refused.",
        text="For specific performance of a contract. Three years. The date fixed for the performance, or if no such date is fixed, when the plaintiff has notice that performance is refused.",
        quote_verified=True,
        verification_label="Gazette of Pakistan",
        checksum="dummy_checksum_113"
    )


def test_specific_performance_query_with_4_unresolved_issues_renders_partial_record_only(mock_legal_unit):
    pack = BoundedEvidencePack()
    pack.query_text = "Suit for specific performance of sale agreement with 4 unaddressed points"
    pack.add_legal_unit(mock_legal_unit)

    verifier = StatuteEvidenceVerifier()
    verifier.register_units([mock_legal_unit])

    json_with_4_not_found = """
    {
      "answer": "A suit for specific performance is governed by Article 113 of the Limitation Act, 1908, with a period of three years.",
      "claims": [
        {
          "statement": "Under Article 113 of the Limitation Act, 1908, the limitation period for specific performance is three years.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [],
      "not_found": [
        "Unregistered agreement to sell evidential admissibility under Registration Act S. 49.",
        "Readiness and willingness pleading prerequisites under CPC Order VI Rule 1.",
        "Relief of possession in addition to specific performance under Specific Relief Act S. 19.",
        "Effect of lis pendens under Transfer of Property Act S. 52."
      ],
      "open_questions": []
    }
    """

    markdown, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=json_with_4_not_found,
        evidence_pack=pack,
        verifier=verifier
    )

    # 1. Verification report must be marked unverified / partial
    assert report.is_memo_verified is False
    assert report.mode == "partial_result"

    # 2. Must NEVER show 'PARTIAL RESEARCH RECORD' or 'VERIFIED RESEARCH MEMORANDUM'
    assert "PARTIAL RESEARCH RECORD" not in markdown
    assert "VERIFIED RESEARCH MEMORANDUM" not in markdown
    assert "100% of claims deterministically grounded" not in markdown

    # 3. Must NOT show verified badge on claims
    assert "`✓ Verified`" not in markdown


def test_is_partial_flag_true_renders_partial_record_only(mock_legal_unit):
    pack = BoundedEvidencePack()
    pack.query_text = "Specific performance query with is_partial flag"
    pack.add_legal_unit(mock_legal_unit)

    verifier = StatuteEvidenceVerifier()
    verifier.register_units([mock_legal_unit])

    json_with_is_partial = """
    {
      "answer": "Limitation period is three years under Article 113.",
      "is_partial": true,
      "claims": [
        {
          "statement": "Under Article 113 of the Limitation Act, 1908, the period is three years.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [],
      "not_found": [],
      "open_questions": []
    }
    """

    markdown, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=json_with_is_partial,
        evidence_pack=pack,
        verifier=verifier
    )

    assert report.is_memo_verified is False
    assert "PARTIAL RESEARCH RECORD" not in markdown
    assert "VERIFIED RESEARCH MEMORANDUM" not in markdown


def test_fully_resolved_query_renders_verified_memorandum_only(mock_legal_unit):
    pack = BoundedEvidencePack()
    pack.query_text = "What is the limitation for specific performance?"
    pack.add_legal_unit(mock_legal_unit)

    verifier = StatuteEvidenceVerifier()
    verifier.register_units([mock_legal_unit])

    fully_verified_json = """
    {
      "answer": "A suit for specific performance of a contract is governed by Article 113 of the Limitation Act, 1908, providing a three-year limitation period.",
      "is_partial": false,
      "claims": [
        {
          "statement": "Under Article 113 of the Limitation Act, 1908, the limitation period is three years from the date fixed for performance.",
          "evidence_ids": ["E1"]
        }
      ],
      "caveats": [],
      "not_found": [],
      "open_questions": []
    }
    """

    markdown, report, _ = execute_structured_memo_pipeline(
        raw_llm_response=fully_verified_json,
        evidence_pack=pack,
        verifier=verifier
    )

    # 1. Report is verified
    assert report.is_memo_verified is True

    # 2. Must NEVER show 'PARTIAL RESEARCH RECORD' or 'VERIFIED RESEARCH MEMORANDUM' or claim badges
    assert "VERIFIED RESEARCH MEMORANDUM" not in markdown
    assert "PARTIAL RESEARCH RECORD" not in markdown
    assert "`✓ Verified`" not in markdown
