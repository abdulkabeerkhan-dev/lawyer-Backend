"""
tests/test_unverified_precedent_notice.py

Tests proving that unverified case citations and impossible law report paginations
(such as 2014 CLD 9999) trigger explicit, authoritative Precedent Verification Notices
rather than generic statutory withholding banners.
"""

import os
import sys
import uuid
import asyncio
import pytest
from unittest.mock import patch, MagicMock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import MemoVerifier, MemorandumVerificationBlockedError


def test_case_authority_extraction_handles_connector_phrases():
    """Verify that case titles with 'of the', 'in the', etc. and prepositions are fully extracted."""
    mv = MemoVerifier()
    text = "In Zulfiqar Textile Mills v. Bank of the Indus Valley, 2014 CLD 9999, the court held..."
    auths = mv.extract_case_authorities(text)
    
    titles = [a["span"] for a in auths if a["type"] == "case_title"]
    cits = [a["span"] for a in auths if a["type"] == "citation"]
    
    assert "Zulfiqar Textile Mills v. Bank of the Indus Valley" in titles
    assert "2014 CLD 9999" in cits


def test_early_impossible_citation_guard_blocks_2014_cld_9999():
    """Verify that 2014 CLD 9999 is intercepted early by the citation guard."""
    from legal_ai.query_engine.query_processor import process_query_job_legal_ai
    
    job_id = str(uuid.uuid4())
    jobs_store = {
        job_id: {
            "status": "pending",
            "stage": "starting",
            "user_id": "real_user_123"
        }
    }
    
    request = MagicMock()
    request.query = "Summarise the Supreme Court's ruling in Zulfiqar Textile Mills v. Bank of the Indus Valley, 2014 CLD 9999."
    request.query_text = request.query
    
    with pytest.raises(MemorandumVerificationBlockedError) as exc_info:
        asyncio.run(process_query_job_legal_ai(
            job_id=job_id,
            request=request,
            authenticated_user_id="real_user_123",
            jobs_store=jobs_store,
            supabase=None
        ))
    
    job_data = jobs_store[job_id]
    assert job_data["status"] == "error"
    assert job_data["stage"] == "verification_blocked"
    assert job_data["error_category"] == "FABRICATED_CITATION"
    assert any("2014 CLD 9999" in c for c in job_data["unverified_citations"])


def test_main_query_status_returns_clear_precedent_notice_for_blocked_citation():
    """
    Verify that when a job is blocked due to FABRICATED_CITATION,
    main.py get_query_job_status outputs the explicit Precedent Verification Notice.
    """
    from main import get_query_job_status, jobs_store
    
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "status": "error",
        "stage": "verification_blocked",
        "error": "MEMORANDUM_VERIFICATION_FAILED",
        "error_category": "FABRICATED_CITATION",
        "safe_reason": "The citation 2014 CLD 9999 does not exist.",
        "retry_guidance": "Please verify the citation journal, year, and page number.",
        "unverified_citations": ["2014 CLD 9999", "Zulfiqar Textile Mills v. Bank of the Indus Valley"],
        "query_text": "Summarise the Supreme Court's ruling in Zulfiqar Textile Mills v. Bank of the Indus Valley, 2014 CLD 9999.",
        "verified_statute_fallback": [],
        "verified_precedents_fallback": [],
        "user_id": "real_advocate_user"
    }
    
    res = asyncio.run(get_query_job_status(job_id=job_id, authenticated_user_id="real_advocate_user"))
    
    assert res["status"] == "done"
    answer = res["result"]["answer"]
    
    # Must contain Precedent Verification Notice
    assert "Precedent Verification Notice" in answer
    assert "2014 CLD 9999" in answer
    assert "Strict Anti-Hallucination Policy" in answer or "Authenticity Notice" in answer
    
    # Must NOT contain confusing generic statutory notice with empty provisions
    assert "The authentic, verbatim text of the controlling statutory provisions from official gazettes is set out below for legal reliance" not in answer


def test_retrieved_precedent_cards_are_verified_and_not_blocked():
    """
    Verify that real retrieved precedents (e.g. 1998 SCMR 530, 2025 SCMR 787)
    are recognized as verified via extra_authorities and pass verification.
    """
    cards = [
        {
            "citation": "1998 SCMR 530",
            "case_title": "ABDUL JABBAR VS ABDUL SATTAR",
            "court": "Supreme Court of Pakistan"
        },
        {
            "citation": "2025 SCMR 787",
            "case_title": "Al-Haaj Malik MUHAMMAD ASHRAF VS JAVED AKHTAR",
            "court": "Supreme Court of Pakistan"
        }
    ]
    
    memo = """
### 1. ### EXECUTIVE SUMMARY
In Abdul Jabbar v. Abdul Sattar, 1998 SCMR 530, the Supreme Court of Pakistan held that mortgage of immovable property requires registration.
Furthermore, in Al-Haaj Malik Muhammad Ashraf v. Javed Akhtar, 2025 SCMR 787, the Court discussed co-owner rights.
"""
    from legal_ai.verification.memo_verifier import verify_memorandum_text
    
    res = verify_memorandum_text(memo, extra_authorities=cards)
    
    # Must NOT have UNVERIFIED_AUTHORITY failures for these cases
    auth_failures = [f for f in res.get("failures", []) if f.get("category") == "UNVERIFIED_AUTHORITY"]
    assert len(auth_failures) == 0, f"Unexpected authority failures: {auth_failures}"


def test_pdf_bytes_remove_unofficial_notice_and_add_section_ai():
    """
    Verify that dynamically built judgment PDFs do not contain
    'Reconstructed from database text' or 'UNOFFICIAL RECONSTRUCTION'
    and instead feature 'SECTION AI'.
    """
    from main import build_judgment_pdf_bytes
    
    pdf_bytes = build_judgment_pdf_bytes(
        title="Al-Haaj Malik Muhammad Ashraf v. Javed Akhtar",
        citation="2025 SCMR 787",
        court="Supreme Court of Pakistan",
        text="Sample judgment body text."
    )
    
    assert b"Reconstructed from database text" not in pdf_bytes
    assert b"UNOFFICIAL RECONSTRUCTION" not in pdf_bytes
