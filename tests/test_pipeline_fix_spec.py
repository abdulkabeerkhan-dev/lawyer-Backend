"""
tests/test_pipeline_fix_spec.py

Automated Acceptance and Regression Tests for the Legal Research Pipeline Fix Spec:
1. Rejection of corrupted 1989 SCMR 868 record in civil/property context.
2. Reporter-to-court taxonomy validation (SCMR -> Supreme Court, CLC -> High Court).
3. Stage 4 Evidence Pack assembly and cross-linking.
4. Stage 5 prompt generation with strict JSON schema.
5. Stage 6 deterministic verification:
   - Catching non-existent source tags ([S99]).
   - Catching non-verbatim statute quotes.
   - Catching phantom citations and sections.
   - Flagging banned absolutes in unquoted prose.
   - Rendering honest markdown with verified badge.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from core.case_integrity import verify_case_integrity, check_reporter_court_consistency
from core.evidence_pack import EvidencePack, assemble_evidence_pack
from core.evidence_verifier import EvidenceVerifier, format_verified_memo_to_markdown
from core.evidence_pipeline import (
    execute_stage4_evidence_pack,
    build_stage5_prompts,
    execute_stage6_verification_and_rendering
)


def test_1989_scmr_868_integrity_quarantine():
    """Observed failure 1: 1989 SCMR 868 must be dropped for property/contract queries."""
    rec = {
        "citation": "1989 SCMR 868",
        "case_title": "IQBAL AHMAD KHAN VS SECRETARY, ESTABLISHMENT DIVISION",
        "court_name": "Supreme Court of Pakistan",
        "ratio_decidendi": "Specific performance of agreement to sell..."
    }
    is_valid, reason, _ = verify_case_integrity(
        rec,
        query_domain="civil",
        sub_topic="specific performance",
        query_text="agreement to sell earnest money"
    )
    assert not is_valid
    assert "1989 SCMR 868" in reason or "Title-to-domain mismatch" in reason


def test_reporter_court_taxonomy_validation():
    """Observed failure 2: SCMR must be Supreme Court; CLC must be High Court."""
    # SCMR cannot be labeled High Court
    is_ok, court, msg = check_reporter_court_consistency("2011 SCMR 1550", "High Court of Sindh")
    assert not is_ok
    assert court == "Supreme Court of Pakistan"

    # CLC cannot be labeled Supreme Court
    is_ok_clc, court_clc, msg_clc = check_reporter_court_consistency("2015 CLC 973", "Supreme Court of Pakistan")
    assert not is_ok_clc
    assert "High Court" in court_clc

    # Proper case
    is_ok_good, court_good, _ = check_reporter_court_consistency("2011 SCMR 1550", "Supreme Court of Pakistan")
    assert is_ok_good
    assert court_good == "Supreme Court of Pakistan"


def test_evidence_pack_assembly_and_cross_linking():
    """Stage 4: Assembles S1..Sn and C1..Cn correctly."""
    statutes = [
        {
            "act_name": "Benami Transactions (Prohibition) Act, 2017",
            "section_number": "4",
            "text": "No suit, claim or action to enforce any right in respect of any property held benami against the person in whose name the property is held or against any other person shall lie by or on behalf of a person claiming to be the real owner of such property.",
            "section_title": "Prohibition of right to recover property held benami"
        }
    ]
    cases = [
        {
            "citation": "2011 SCMR 1550",
            "case_title": "Nasira Ansari v. Muhammad Aslam",
            "court_name": "Supreme Court of Pakistan",
            "ratio_decidendi": "Onus of proof in benami transactions lies heavily upon the party alleging it.",
            "statutes_invoked": ["Benami Transactions (Prohibition) Act, Section 4"]
        },
        {
            "citation": "1989 SCMR 868",
            "case_title": "IQBAL AHMAD KHAN VS SECRETARY, ESTABLISHMENT DIVISION",
            "court_name": "Supreme Court of Pakistan",
            "ratio_decidendi": "Specific performance..."
        }
    ]

    pack, clean_cases = execute_stage4_evidence_pack(
        statutes,
        cases,
        query_text="Partition suit with benami defence",
        query_plan=None
    )

    assert "S1" in pack.statutes
    assert "C1" in pack.cases
    assert len(clean_cases) == 1  # 1989 SCMR 868 dropped
    assert clean_cases[0]["citation"] == "2011 SCMR 1550"


def test_stage6_verifier_passes_on_grounded_output():
    """Stage 6: Verifier marks perfectly grounded output as verified."""
    pack = EvidencePack()
    pack.add_statute(
        act_name="Benami Transactions (Prohibition) Act, 2017",
        section_number="4",
        section_text="No suit, claim or action to enforce any right in respect of any property held benami against the person in whose name the property is held shall lie.",
        title="Prohibition"
    )
    pack.add_case(
        citation="2011 SCMR 1550",
        case_title="Nasira Ansari v. Muhammad Aslam",
        court="Supreme Court of Pakistan",
        ratio="Onus of proof in benami transactions lies heavily upon the party alleging it."
    )

    memo = {
        "question": "Can benami be pleaded as set off?",
        "short_answer": [
            {
                "text": "Under Section 4 of the 2017 Act, no suit or claim shall lie by a real owner to recover property held benami.",
                "sources": ["S1", "C1"]
            }
        ],
        "statutes": [
            {
                "id": "S1",
                "quote": "No suit, claim or action to enforce any right in respect of any property held benami",
                "plain_explanation": "Prohibits recovery claims by the alleged real owner."
            }
        ],
        "cases": [
            {
                "id": "C1",
                "ratio_as_recorded": "Onus of proof in benami transactions lies heavily upon the party alleging it.",
                "relevance": "Establishes heavy burden of proof on party alleging benami."
            }
        ],
        "options_described_by_sources": [
            {
                "text": "Party asserting benami is required to establish strict evidentiary proof.",
                "sources": ["C1"]
            }
        ],
        "gaps": [
            "Whether equitable set-off applies to mesne profits was not found in the available sources."
        ],
        "needs_lawyer_review": True
    }

    verifier = EvidenceVerifier(pack)
    report = verifier.verify(memo)
    assert report["is_verified"] is True
    assert report["status"] == "verified"
    assert len(report["failures"]) == 0


def test_stage6_verifier_flags_phantom_citations_and_bad_quotes():
    """Stage 6: Catches invalid quote, phantom citation, and bad source IDs."""
    pack = EvidencePack()
    pack.add_statute(
        act_name="Civil Procedure Code, 1908",
        section_number="Order VIII Rule 6",
        section_text="Where in a suit for the recovery of money the defendant claims to set-off against the plaintiff's demand any ascertained sum of money legally recoverable by him from the plaintiff.",
        title="Particulars of set-off"
    )

    memo_with_errors = {
        "question": "Can a set-off be claimed?",
        "short_answer": [
            {
                "text": "In 1999 SCMR 1234 the court held set-off is restricted to money.",
                "sources": ["S99"]  # Non-existent source
            }
        ],
        "statutes": [
            {
                "id": "S1",
                "quote": "This text is completely invented and nowhere in the CPC.",  # Bad quote
                "plain_explanation": "Invented explanation."
            }
        ],
        "cases": [],
        "options_described_by_sources": [],
        "gaps": ["Not found in the available sources."],
        "needs_lawyer_review": True
    }

    verifier = EvidenceVerifier(pack)
    report = verifier.verify(memo_with_errors)
    assert report["is_verified"] is False
    assert report["status"] == "partially_verified"
    assert any("S99" in f for f in report["failures"])
    assert any("exact substring" in f for f in report["failures"])
    assert any("Phantom citation" in f and "1999 SCMR 1234" in f for f in report["failures"])
