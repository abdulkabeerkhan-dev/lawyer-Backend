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
    """Verify that jobs persisted via persist_in_flight_job_state are recovered after jobs_store is cleared."""
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
        
        # 4. Polling get_query_job_status should return running, NOT 404!
        status_res = await get_query_job_status(test_job_id, authenticated_user_id=test_user_id)
        assert status_res["status"] == "running"
        assert status_res["stage"] == "searching_precedents"

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
