"""
tests/test_job_persistence_db.py

Unit test for database-backed in-flight job persistence:
1. Replaces local disk JSON with PostgreSQL `query_jobs` table.
2. Simulates full backend restart mid-query and verifies job state recovery.
3. Strictly enforces privacy: zero client query text is persisted to disk or DB metadata.
"""

import os
import sys
import asyncio
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main
from tests.mock_supabase import MockSupabaseClient


@pytest.fixture(autouse=True)
def setup_mock_supabase():
    orig_sb = main.supabase
    mock_sb = MockSupabaseClient()
    main.supabase = mock_sb
    main.jobs_store.clear()
    main._IN_FLIGHT_JOBS_CACHE.clear()
    json_path = Path(__file__).resolve().parent.parent / "data" / "in_flight_jobs.json"
    if json_path.exists():
        json_path.unlink()
    yield mock_sb
    main.supabase = orig_sb
    main.jobs_store.clear()
    main._IN_FLIGHT_JOBS_CACHE.clear()


def test_job_persisted_to_db_and_survives_restart(setup_mock_supabase):
    mock_sb = setup_mock_supabase

    # 1. Start a job mid-query
    job_id = "test-job-uuid-12345"
    user_id = "user_clerk_98765"
    main.persist_in_flight_job_state(
        job_id=job_id,
        stage="deep_statutory_grounding",
        status="running",
        extra={
            "user_id": user_id,
            "early_display": "Interim statutes grounded: FIO 2001 Section 22"
        }
    )

    # Verify table received row
    db_rows = mock_sb.table("query_jobs").select("*").eq("job_id", job_id).execute().data
    assert len(db_rows) == 1
    assert db_rows[0]["stage"] == "deep_statutory_grounding"
    assert db_rows[0]["status"] == "running"
    assert db_rows[0]["user_id"] == user_id

    # 2. SIMULATE RESTART: Clear all in-memory job dictionaries
    main.jobs_store.clear()
    main._IN_FLIGHT_JOBS_CACHE.clear()
    assert len(main.jobs_store) == 0
    assert len(main._IN_FLIGHT_JOBS_CACHE) == 0

    # 3. Recover jobs from database store
    recovered = main._load_in_flight_jobs()
    assert job_id in recovered
    assert recovered[job_id]["stage"] == "deep_statutory_grounding"
    assert recovered[job_id]["status"] == "running"
    assert recovered[job_id]["user_id"] == user_id
    assert recovered[job_id]["early_display"] == "Interim statutes grounded: FIO 2001 Section 22"


def test_zero_query_text_on_disk_or_db(setup_mock_supabase):
    mock_sb = setup_mock_supabase

    job_id = "test-job-privacy-999"
    confidential_text = "Highly confidential client litigation strategy regarding banking decree"

    main.persist_in_flight_job_state(
        job_id=job_id,
        stage="retrieval",
        status="running",
        extra={
            "user_id": "user_private",
            "query": confidential_text,
            "query_text": confidential_text,
            "user_prompt": confidential_text,
            "model": "claude-sonnet-5-5"
        }
    )

    # 1. Assert local disk JSON does not exist
    json_path = Path(__file__).resolve().parent.parent / "data" / "in_flight_jobs.json"
    assert not json_path.exists(), "Found forbidden in_flight_jobs.json file on local disk!"

    # 2. Assert query text is stripped from DB metadata
    db_rows = mock_sb.table("query_jobs").select("*").eq("job_id", job_id).execute().data
    assert len(db_rows) == 1
    meta = db_rows[0].get("metadata") or {}
    assert "query" not in meta
    assert "query_text" not in meta
    assert confidential_text not in str(meta)
    assert meta.get("model") == "claude-sonnet-5-5"


def test_get_query_job_status_after_restart(setup_mock_supabase):
    mock_sb = setup_mock_supabase

    job_id = "test-job-endpoint-456"
    user_id = "user_clerk_valid"

    # Persist job
    main.persist_in_flight_job_state(
        job_id=job_id,
        stage="synthesizing_memo",
        status="running",
        extra={"user_id": user_id, "early_display": "Synthesizing legal opinion..."}
    )

    # Simulate container restart mid-query
    main.jobs_store.clear()
    main._IN_FLIGHT_JOBS_CACHE.clear()

    # Query status endpoint for authenticated owner
    res = asyncio.run(main.get_query_job_status(job_id=job_id, authenticated_user_id=user_id))
    assert res["status"] == "running"
    assert res["stage"] == "synthesizing_memo"
    assert res["early_display"] == "Synthesizing legal opinion..."

    # Query status endpoint for unauthorized user -> 403 Forbidden
    with pytest.raises(Exception) as exc_info:
        asyncio.run(main.get_query_job_status(job_id=job_id, authenticated_user_id="user_unauthorized_attacker"))
    assert "403" in str(exc_info.value) or "Not authorized" in str(exc_info.value)
