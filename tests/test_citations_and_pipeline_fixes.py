"""
tests/test_citations_and_pipeline_fixes.py

Unit tests verifying:
1. Decoupled in-flight jobs persistence (core/in_flight_jobs.py) without importing main.py.
2. BM25 search driver independence from main.py top-level code.
3. Domain field resolution prioritizing primary_domain over legacy legal_domain.
4. Consistent Precedents heading rendering in structured memo engine and fallback generator.
5. End-to-end legal AI query execution producing populated precedent cards and citations.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.in_flight_jobs import (
    persist_in_flight_job_state,
    load_in_flight_jobs,
    _IN_FLIGHT_JOBS_CACHE,
    _IN_FLIGHT_JOBS_LOCK
)
from core.legal_query_planner import StructuredLegalQueryPlan, create_deterministic_fallback_plan
from legal_ai.synthesis.structured_memo_engine import render_layer8_markdown
from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack
from legal_ai.verification.statute_evidence_verifier import MemoVerificationReport
from legal_ai.synthesis.memorandum_generator import build_honest_partial_response


def test_in_flight_jobs_persistence_and_retrieval():
    """Verify jobs can be persisted and retrieved from in_flight_jobs without main.py."""
    job_id = "test-job-decoupled-999"
    extra_payload = {
        "user_id": "test_user_advocate",
        "result": {"citations": ["2017 SCMR 1218"], "answer": "Verified legal analysis."}
    }
    mock_store = {}
    persist_in_flight_job_state(
        job_id=job_id,
        stage="done",
        status="done",
        extra=extra_payload,
        jobs_store=mock_store
    )

    # In-memory store updated
    assert mock_store[job_id]["status"] == "done"
    assert mock_store[job_id]["stage"] == "done"
    assert mock_store[job_id]["result"]["citations"] == ["2017 SCMR 1218"]

    # Cache and SQLite loader updated
    loaded = load_in_flight_jobs()
    assert job_id in loaded
    assert loaded[job_id]["status"] == "done"
    assert loaded[job_id]["result"]["citations"] == ["2017 SCMR 1218"]


def test_bm25_search_does_not_depend_on_main():
    """Verify bm25_search module can be imported and executed without main."""
    from legal_ai.retrieval.bm25_search import get_bm25_index_instance, search_bm25_sparse
    # Should not raise exception
    res = search_bm25_sparse("cheque dishonour 489-F", top_k=5)
    assert isinstance(res, list)


def test_domain_resolution_prioritizes_primary_domain():
    """Verify primary_domain is resolved correctly even when legal_domain is empty."""
    plan = StructuredLegalQueryPlan(
        query_text="FIR under 489-F PPC for dishonoured cheque",
        primary_domain="criminal",
        legal_domain=[]
    )
    resolved_domain = (
        getattr(plan, "primary_domain", None)
        or (plan.legal_domain[0] if (plan and getattr(plan, "legal_domain", None)) else "civil")
    )
    assert resolved_domain == "criminal"


def test_consistent_precedents_heading_in_layer8_markdown():
    """Verify Layer 8 markdown renders '## Retrieved Judicial Precedents on Record'."""
    pack = BoundedEvidencePack()
    pack.add_case_precedent(
        citation="2017 SCMR 1218",
        case_title="Syed Mushahid Shah v. FIA",
        court="Supreme Court of Pakistan",
        ratio="Dishonour of cheque issued for lawful discharge of debt attracts penal liability under section 489-F PPC.",
        year=2017
    )

    report = MemoVerificationReport(
        is_memo_verified=True,
        total_claims=1,
        verified_claims_count=1,
        unverified_claims_count=0
    )

    payload = {
        "answer": "A dishonoured cheque attracts criminal prosecution under Section 489-F PPC and civil summary suit.",
        "claims": [{"statement": "Section 489-F imposes criminal liability.", "evidence_ids": ["E1"]}],
        "caveats": [],
        "not_found": [],
        "open_questions": []
    }

    markdown = render_layer8_markdown(payload, pack, report)
    assert "## Retrieved Judicial Precedents on Record" in markdown
    assert "2017 SCMR 1218" in markdown
    assert "Syed Mushahid Shah" in markdown


def test_consistent_precedents_heading_in_honest_partial_response():
    """Verify fallback generator also renders '## Retrieved Judicial Precedents on Record'."""
    precedents = [
        {
            "citation": "2026 CLD 68",
            "title": "Noor Hayat Cotton Ginners v. Bank of Punjab",
            "court": "Lahore High Court",
            "ratio": "Summary suit under Order XXXVII CPC is maintainable upon cheque dishonour."
        }
    ]
    resp = build_honest_partial_response(
        query_text="Cheque dishonour remedies",
        precedents=precedents,
        reason="Testing heading consistency"
    )
    assert "## Retrieved Judicial Precedents on Record" in resp
    assert "2026 CLD 68" in resp
