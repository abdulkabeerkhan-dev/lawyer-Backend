"""
tests/test_phase1_7_in_flight_restart.py

Phase 1.7 verification: In-flight job persistence across server restarts.
Verifies that mid-query in-flight jobs retain their stage and status across
process restarts, and cannot be accessed by unauthorized users.
"""

import pytest
import asyncio
import uuid
from fastapi import HTTPException
from main import (
    jobs_store,
    persist_in_flight_job_state,
    get_query_job_status,
    _load_in_flight_jobs,
)


@pytest.mark.anyio
async def test_interrupted_job_fails_fast_and_completed_job_survives_restart():
    job_id = f"test-in-flight-restart-{uuid.uuid4()}"
    owner_user_id = "clerk_user_legitimate_advocate"

    # Step 1: Simulate in-flight job reaching stage 'checking_law'
    persist_in_flight_job_state(
        job_id=job_id,
        stage="checking_law",
        status="running",
        extra={
            "user_id": owner_user_id,
            "query_text": "What does Section 22 FIO 2001 say about appeals?",
        }
    )

    # Verify state is written to persistent storage
    persisted = _load_in_flight_jobs()
    assert job_id in persisted
    assert persisted[job_id]["stage"] == "checking_law"
    assert persisted[job_id]["status"] == "running"

    # Step 2: SIMULATE PROCESS RESTART (Wipe in-memory jobs_store completely)
    jobs_store.clear()
    assert len(jobs_store) == 0

    # Step 3: An orphaned in-flight job must fail fast rather than remain "running".
    status_resp = await get_query_job_status(job_id=job_id, authenticated_user_id=owner_user_id)
    assert status_resp["status"] == "error"
    assert status_resp["stage"] == "error"
    assert status_resp["result"] is None
    assert "interrupted by a server restart" in status_resp["error"]

    # Step 4: Unauthorized users cannot read an interrupted job.
    with pytest.raises(HTTPException) as exc_info:
        await get_query_job_status(job_id=job_id, authenticated_user_id="clerk_intruder_attacker")
    assert exc_info.value.status_code == 403

    # Step 5: Complete a job and verify completion survives restart.
    final_result = {
        "answer": "Section 22 FIO 2001 provides an appeal within 30 days to a High Court Division Bench.",
        "citations": [],
        "precedents": [],
    }
    persist_in_flight_job_state(job_id=job_id, stage="done", status="done", extra={"result": final_result})
    jobs_store.clear()  # Third restart after completion

    status_resp_3 = await get_query_job_status(job_id=job_id, authenticated_user_id=owner_user_id)
    assert status_resp_3["status"] == "done"
    assert status_resp_3["stage"] == "done"
    assert "Section 22 FIO 2001" in status_resp_3["result"]["answer"]
