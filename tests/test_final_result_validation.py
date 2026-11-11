from uuid import uuid4

from core.in_flight_jobs import _has_valid_final_result
from core.in_flight_jobs import load_in_flight_jobs, persist_in_flight_job_state
from legal_ai.query_engine.query_processor import _has_contentful_final_result


def test_metadata_only_payload_is_rejected():
    payload = {
        "answer": "",
        "response": "",
        "model_answer": "",
        "precedents": [],
        "citations": ["2024 SCMR 123"],
        "verification_report": {"passed": True},
        "evidence_pack": {"items": []},
    }

    assert not _has_valid_final_result(payload)
    assert not _has_contentful_final_result(payload)


def test_headnote_only_placeholder_is_rejected():
    assert not _has_valid_final_result("headnote_only")
    assert not _has_contentful_final_result("headnote_only")
    assert not _has_valid_final_result({"answer": " HEADNOTE_ONLY "})
    assert not _has_contentful_final_result({"answer": " HEADNOTE_ONLY "})


def test_headnote_only_job_is_persisted_as_failed():
    job_id = f"headnote-only-{uuid4()}"
    jobs_store = {}

    persist_in_flight_job_state(
        job_id,
        stage="done",
        status="done",
        extra={"user_id": "test-user", "result": {"answer": "headnote_only"}},
        jobs_store=jobs_store,
    )

    assert jobs_store[job_id]["status"] == "failed"
    assert jobs_store[job_id]["stage"] == "failed"
    assert jobs_store[job_id]["result"] is None

    recovered_job = load_in_flight_jobs(jobs_store={})[job_id]
    assert recovered_job["status"] == "failed"
    assert recovered_job["stage"] == "failed"
    assert recovered_job["result"] is None


def test_real_answer_payload_is_accepted():
    payload = {
        "answer": "The suit is within time under Article 113 and the client may seek specific performance.",
        "response": "The suit is within time under Article 113 and the client may seek specific performance.",
        "model_answer": "The suit is within time under Article 113 and the client may seek specific performance.",
        "precedents": [],
        "citations": [],
    }

    assert _has_valid_final_result(payload)
    assert _has_contentful_final_result(payload)
