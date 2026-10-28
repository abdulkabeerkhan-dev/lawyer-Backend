import os
import sys
import uuid
import asyncio
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import MemoVerifier
from legal_ai.synthesis.memorandum_generator import filter_and_cap_authorities, sanitize_precedent_card
from core.legal_query_planner import LegalQueryPlan
from main import get_query_job_status, jobs_store, export_court_pleading, PleadingExportRequest


def test_order21_item2_void_ab_initio_rejected():
    mv = MemoVerifier()
    # Latin doctrine with "v." must not be extracted
    auths = mv.extract_case_authorities("is a contract automatically void ab initio v. voidable at the option of the company?")
    assert len(auths) == 0

    auths_title = mv.extract_case_authorities("Void Ab Initio v. Voidable")
    assert len(auths_title) == 0

    # Non-party doctrinal concept comparison must not be extracted
    auths_interim = mv.extract_case_authorities("Permissible Interim Measures v. Prohibited Sweeping Intervention (2017 CLD 847)")
    case_spans = [a["span"] for a in auths_interim if a["type"] == "case_title"]
    assert "Permissible Interim Measures v. Prohibited Sweeping Intervention" not in case_spans


def test_order21_item2_messrs_extracted():
    mv = MemoVerifier()
    auths = mv.extract_case_authorities("In Messrs A v. B, 2020 SCMR 1, the Court held...")
    spans = [a["span"] for a in auths]
    assert "Messrs A v. B" in spans
    assert "2020 SCMR 1" in spans


def test_order21_item2_case_word_following_extracted():
    mv = MemoVerifier()
    auths = mv.extract_case_authorities("In Messrs A v. B case, the rule was applied.")
    spans = [a["span"] for a in auths]
    assert "Messrs A v. B" in spans


def test_order21_item3_pagination_failed_shows_authenticity_and_guidance():
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "status": "error",
        "stage": "verification_blocked",
        "error": "MEMORANDUM_VERIFICATION_FAILED",
        "error_category": "FABRICATED_CITATION",
        "safe_reason": "Out of range page number",
        "retry_guidance": "Please verify the citation journal, year, and page number.",
        "unverified_citations": ["2014 CLD 9999"],
        "query_text": "summarize 2014 CLD 9999",
        "verified_statute_fallback": [],
        "verified_precedents_fallback": [],
        "user_id": "test_user_item3"
    }
    res = asyncio.run(get_query_job_status(job_id=job_id, authenticated_user_id="test_user_item3"))
    answer = res["result"]["answer"]
    assert "Precedent Verification Notice" in answer
    assert "Authenticity Notice" in answer
    assert "Legal Guidance" in answer
    assert res["result"]["export_allowed"] is False
    assert res["result"]["copy_allowed"] is False


def test_order21_item3_normal_blocked_does_not_show_authenticity_or_guidance():
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "status": "error",
        "stage": "verification_blocked",
        "error": "MEMORANDUM_VERIFICATION_FAILED",
        "error_category": "STATUTORY_MISQUOTATION",
        "safe_reason": "Statutory misquotation detected",
        "retry_guidance": "Ensure exact quotes match official bare acts.",
        "unverified_citations": [],
        "query_text": "Companies Act query",
        "verified_statute_fallback": [],
        "verified_precedents_fallback": [],
        "user_id": "test_user_item3b"
    }
    res = asyncio.run(get_query_job_status(job_id=job_id, authenticated_user_id="test_user_item3b"))
    answer = res["result"]["answer"]
    assert "Statutory Verification Notice" in answer
    assert "Authenticity Notice" not in answer
    assert "Legal Guidance" not in answer
    assert res["result"]["export_allowed"] is False
    assert res["result"]["copy_allowed"] is False


def test_order21_item4_percentages_and_act_binding():
    from core.statute_currency import detect_statutory_provisions_in_query
    from core.statutory_validator import parse_statutory_citation
    q = (
        "A director of a company under the Companies Act, 2017 had a 60% controlling interest. "
        "Two shareholders sued under Section 205 and Section 207 of the Companies Act, 2017."
    )
    # 60% must not be parsed as a statute
    p = parse_statutory_citation("60% controlling interest", context=q)
    assert p.get("is_valid") is False

    # Detection must bind only to Companies Act 2017
    cids = [c[0] for c in detect_statutory_provisions_in_query(q)]
    assert "COMPANIES_2017_SEC_205" in cids
    assert "COMPANIES_2017_SEC_207" in cids
    assert not any("CPC" in c for c in cids)
    assert not any("60" in c for c in cids)


def test_order21_item5_heading_only_goes_under_not_in_verified_store():
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "status": "error",
        "stage": "verification_blocked",
        "error": "MEMORANDUM_VERIFICATION_FAILED",
        "error_category": "UNSOURCED_ANALYSIS",
        "safe_reason": "Analysis withheld",
        "unverified_citations": [],
        "query_text": "A director of a public unlisted company...",
        "verified_statute_fallback": [
            {
                "canonical_id": "COMPANIES_2017_SEC_205",
                "display_name": "Section 205, Companies Act, 2017",
                "tier": "heading_only",
                "has_text": False,
                "text": "no text available"
            },
            {
                "canonical_id": "COMPANIES_2017_SEC_207",
                "display_name": "Section 207, Companies Act, 2017",
                "tier": "heading_only",
                "has_text": False,
                "text": "no text available"
            }
        ],
        "verified_precedents_fallback": [],
        "user_id": "test_user_item5"
    }
    res = asyncio.run(get_query_job_status(job_id=job_id, authenticated_user_id="test_user_item5"))
    answer = res["result"]["answer"]
    assert "Verified Statutory Provisions on Record" not in answer
    assert "### Not in verified store" in answer
    assert "Section 205, Companies Act, 2017" in answer
    assert "Section 207, Companies Act, 2017" in answer
    assert "no text available" in answer


def test_order21_item7_filters_irrelevant_election_and_service_cases():
    plan = LegalQueryPlan(
        governing_statutes=["Companies Act, 2017"],
        provisions=["Section 205, Companies Act, 2017", "Section 207, Companies Act, 2017"],
        legal_domain=["corporate law", "company law"],
        matter_type=["commercial", "civil"]
    )
    candidates = [
        {
            "citation": "PLD 2025 Quetta 9",
            "case_title": "NAFEESA REHMAN VS The ELECTION TRIBUNAL BALOCHISTAN, QUETTA",
            "court": "High Court of Balochistan",
            "preview": "Elections Act (XXXIII of 2017) S. 104 Reserved seats for women in Assemblies Election petition",
            "holding": "Elections Act matter"
        },
        {
            "citation": "2025 PLC(CS) 1528",
            "case_title": "MUHAMMAD HASSAN MUSTAFA (Late) v. OGDCL",
            "court": "Islamabad High Court",
            "preview": "Service appeal under Service Tribunals Act regarding employee pension and removal from service",
            "holding": "Service appeal matter"
        }
    ]
    query = "A director of a public unlisted company incorporated under the Companies Act, 2017..."
    filtered = filter_and_cap_authorities(candidates=candidates, query_plan=plan, query_text=query)
    # Must NOT list PLD 2025 Quetta 9 or 2025 PLC(CS) 1528; must show nothing (empty list)
    assert len(filtered) == 0
    assert not any("Quetta" in c["citation"] for c in filtered)
    assert not any("1528" in c["citation"] for c in filtered)


def test_order21_item9_withheld_output_rejected_on_export():
    withheld_text = (
        "> ⚠️ **Precedent Verification Notice**: The requested authority could not be verified...\n\n"
        "### Not in verified store\n- **Section 205, Companies Act, 2017**: no text available\n"
    )
    payload = PleadingExportRequest(
        memorandum_text=withheld_text,
        court_level="High Court",
        case_type="Civil Petition"
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(export_court_pleading(payload=payload, authenticated_user_id="real_advocate_user"))
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail.get("error") == "EXPORT_WITHHELD_BLOCKED"


def test_order21_item10_snippets_cut_at_word_boundaries_and_strip_headers():
    card = {
        "citation": "2025 PLC(CS) 1528",
        "title": "Sample Case",
        "preview": "CITATION: 2025 PLC(CS) 1528 TITLE: MUHAMMAD HASSAN MUSTAFA (Late) COURT: Honorable Justice Muhammad Asif BENCH: Before Khadim Hussain Soomro and Muhammad Asif JJ. In this case the court examined whether the employee was entitled to service benefits under the applicable statutory service regulations.",
        "court": "Supreme Court of Pakistan"
    }
    sanitized = sanitize_precedent_card(card)
    holding = sanitized["holding"]
    assert "CITATION:" not in holding
    assert "TITLE:" not in holding
    assert "COURT:" not in holding
    assert "BENCH:" not in holding
    # Ensure it ends with full word + '...' or sentence end, never ending mid-word (no 'Muha...')
    assert not holding.endswith("Muha...")
    if holding.endswith("..."):
        word_before_ellipsis = holding[:-3].strip().split()[-1]
        assert len(word_before_ellipsis) > 1
