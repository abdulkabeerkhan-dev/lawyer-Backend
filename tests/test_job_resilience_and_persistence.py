import os
import sys
import asyncio
import pytest

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["ENVIRONMENT"] = "test"
os.environ["ENABLE_DEV_AUTH_BYPASS"] = "true"
os.environ["DISABLE_IN_MEMORY_BM25"] = "true"

from main import (
    persist_in_flight_job_state,
    _load_in_flight_jobs,
    get_query_job_status,
    jobs_store,
    _LOCAL_JOBS_DB_PATH
)

def test_job_persistence_survives_jobs_store_wipe():
    """Verify that jobs persisted via persist_in_flight_job_state fail fast on orphan rather than hung 404."""
    async def _run():
        test_job_id = "test-job-uuid-12345"
        test_user_id = "test-user-999"
        
        # 1. Persist state
        persist_in_flight_job_state(
            test_job_id,
            stage="searching_precedents",
            status="running",
            extra={"user_id": test_user_id}
        )
        
        # 2. Simulate complete container restart / in-memory jobs_store wipe
        if test_job_id in jobs_store:
            del jobs_store[test_job_id]
            
        # 3. Load from persistent disk/sqlite store
        recovered_store = _load_in_flight_jobs()
        assert test_job_id in recovered_store
        assert recovered_store[test_job_id]["stage"] == "searching_precedents"
        assert recovered_store[test_job_id]["status"] == "running"
        
        # 4. Polling get_query_job_status fails fast on orphaned in-flight jobs after server restart
        status_res = await get_query_job_status(test_job_id, authenticated_user_id=test_user_id)
        assert status_res["status"] == "error"
        assert "interrupted by a server restart" in status_res["error"]

        # 5. Persisted DONE job with result correctly returns done after jobs_store wipe
        done_job_id = "test-done-uuid-67890"
        persist_in_flight_job_state(
            done_job_id,
            stage="done",
            status="done",
            extra={"user_id": test_user_id, "result": {"answer": "Completed legal memo", "citations": []}}
        )
        if done_job_id in jobs_store:
            del jobs_store[done_job_id]
        done_res = await get_query_job_status(done_job_id, authenticated_user_id=test_user_id)
        assert done_res["status"] == "done"
        assert done_res["result"]["answer"] == "Completed legal memo"

    asyncio.run(_run())

def test_lost_job_returns_interrupted_error_instead_of_404():
    """Verify that a completely missing job returns a graceful interrupted error instead of HTTP 404."""
    async def _run():
        unknown_job_id = "non-existent-uuid-99999"
        res = await get_query_job_status(unknown_job_id, authenticated_user_id="any-user")
        assert res["status"] == "error"
        assert res["code"] == "JOB_INTERRUPTED"
        assert "interrupted by a server restart" in res["error"]

    asyncio.run(_run())


def test_done_job_requires_non_empty_result_payload():
    """A job must never be persisted as done when the final result payload is empty or missing."""
    bad_job_id = "bad-done-no-result-001"
    persist_in_flight_job_state(
        bad_job_id,
        stage="done",
        status="done",
        extra={"user_id": "tester-123", "result": None, "error": "finalization produced no payload"}
    )

    job_record = _load_in_flight_jobs().get(bad_job_id)
    assert job_record is not None
    assert job_record["status"] == "failed"
    assert job_record["stage"] == "failed"
    assert job_record["result"] is None

