"""
core/in_flight_jobs.py

Decoupled persistent in-flight query jobs manager.
Handles:
1. Thread-safe in-memory caching of active and recent jobs.
2. Local SQLite disk persistence (surviving worker recycling and server restarts).
3. Supabase `query_jobs` table synchronization when available and circuit breaker is healthy.
4. Startup state reconciliation and stuck job reaping.

Decouples in-flight job persistence from main.py to eliminate circular imports and
prevent unhandled startup crashes during background query execution.
"""

import os
import sys
import json
import sqlite3
import tempfile
import threading
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_IN_FLIGHT_JOBS_CACHE: Dict[str, Dict[str, Any]] = {}
_IN_FLIGHT_JOBS_LOCK = threading.Lock()
_LOCAL_JOBS_DB_PATH = os.path.join(tempfile.gettempdir(), "section_jobs_cache.db")
_QUERY_JOBS_TABLE_EXISTS: Optional[bool] = None
_QUERY_JOBS_TABLE_CHECKED_AT: Optional[float] = None
_QUERY_JOBS_TABLE_CACHE_TTL_SECONDS = 60.0
WORKER_INSTANCE_ID = str(uuid.uuid4())

_REGISTERED_JOBS_STORE: Optional[Dict[str, Any]] = None
_REGISTERED_SUPABASE_CLIENT: Any = None


def _parse_utc_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _job_is_stale(record: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    updated_at = _parse_utc_timestamp(record.get("updated_at"))
    if updated_at is None:
        return False
    try:
        timeout_seconds = float(os.environ.get("LEGAL_AI_PIPELINE_TIMEOUT", "100"))
    except ValueError:
        logger.warning("Invalid LEGAL_AI_PIPELINE_TIMEOUT; using 100 seconds for job staleness.")
        timeout_seconds = 100
    stale_after = max(180.0, timeout_seconds + 60.0)
    current_time = now or datetime.now(timezone.utc)
    return (current_time - updated_at).total_seconds() > stale_after


def _timestamp_key(value: Any) -> datetime:
    return _parse_utc_timestamp(value) or datetime.min.replace(tzinfo=timezone.utc)


def _has_valid_final_result(payload: Any) -> bool:
    """Returns True only when a terminal result payload carries usable answer content.

    Metadata-only payloads (e.g. a dict with precedent lists or verification flags but no
    actual textual answer) must not be treated as a valid final result.
    """
    if payload is None:
        return False
    if isinstance(payload, str):
        normalized = payload.strip().casefold()
        return bool(normalized) and normalized != "headnote_only"
    if isinstance(payload, dict):
        for key in (
            "answer",
            "response",
            "model_answer",
            "final_answer",
            "result",
            "text",
            "content",
            "memo",
            "output",
            "summary",
        ):
            if key in payload and _has_valid_final_result(payload.get(key)):
                return True
        return False
    if isinstance(payload, list):
        return any(_has_valid_final_result(item) for item in payload)
    return bool(payload)


def register_jobs_store(jobs_store: Dict[str, Any]) -> None:
    """Registers the active in-memory jobs store from the application context."""
    global _REGISTERED_JOBS_STORE
    _REGISTERED_JOBS_STORE = jobs_store


def register_supabase_client(client: Any) -> None:
    """Registers the active Supabase client from the application context."""
    global _REGISTERED_SUPABASE_CLIENT
    _REGISTERED_SUPABASE_CLIENT = client


def _get_supabase_client(client: Any = None) -> Any:
    if client is not None:
        return client
    if _REGISTERED_SUPABASE_CLIENT is not None:
        return _REGISTERED_SUPABASE_CLIENT
    try:
        from legal_ai.config import supabase
        return supabase
    except Exception:
        return None


def _is_supabase_circuit_healthy() -> bool:
    try:
        from legal_ai.config import is_supabase_circuit_open
        return not is_supabase_circuit_open()
    except Exception:
        return True


def _safe_supabase_exec(query_fn: Any, retries: int = 1) -> Any:
    try:
        from legal_ai.config import safe_supabase_query
        return safe_supabase_query(query_fn, retries=retries)
    except Exception:
        try:
            return query_fn()
        except Exception as e:
            logger.debug(f"Direct supabase query error: {e}")
            return None


def init_local_jobs_db() -> None:
    """Ensures the local SQLite cache table exists on disk."""
    try:
        with sqlite3.connect(_LOCAL_JOBS_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS local_query_jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    stage TEXT,
                    status TEXT,
                    updated_at TEXT,
                    metadata_json TEXT
                )
            """)
    except Exception as e:
        logger.debug(f"Local sqlite jobs db init error: {e}")


# Initialize table on import
init_local_jobs_db()


def check_query_jobs_table_exists(supabase_client: Any = None) -> bool:
    """
    Evaluates whether the public.query_jobs table exists in Supabase.
    Caches the result to avoid repeated schema checks.
    """
    global _QUERY_JOBS_TABLE_EXISTS, _QUERY_JOBS_TABLE_CHECKED_AT
    if (
        _QUERY_JOBS_TABLE_EXISTS is not None
        and _QUERY_JOBS_TABLE_CHECKED_AT is not None
        and time.monotonic() - _QUERY_JOBS_TABLE_CHECKED_AT < _QUERY_JOBS_TABLE_CACHE_TTL_SECONDS
    ):
        return _QUERY_JOBS_TABLE_EXISTS

    sb = _get_supabase_client(supabase_client)
    if not sb:
        return False

    try:
        sb.table("query_jobs").select("job_id").limit(1).execute()
        _QUERY_JOBS_TABLE_EXISTS = True
        _QUERY_JOBS_TABLE_CHECKED_AT = time.monotonic()
        logger.info("[STARTUP SELF-CHECK] Table 'public.query_jobs' verified in Supabase.")
    except Exception as e:
        err_msg = str(e)
        if "PGRST205" in err_msg or "schema cache" in err_msg or "not find" in err_msg:
            _QUERY_JOBS_TABLE_EXISTS = False
            _QUERY_JOBS_TABLE_CHECKED_AT = time.monotonic()
            print(
                "⚠️ [STARTUP SELF-CHECK] Notice: 'public.query_jobs' table is missing in Supabase (PGRST205). "
                "In-flight persistence will use memory store. To enable database persistence, apply migrations/query_jobs.sql.",
                file=sys.stderr,
                flush=True
            )
            logger.warning(f"[STARTUP SELF-CHECK] Table 'public.query_jobs' missing: {err_msg}")
        else:
            _QUERY_JOBS_TABLE_EXISTS = None
            _QUERY_JOBS_TABLE_CHECKED_AT = None
            logger.warning(f"[STARTUP SELF-CHECK] query_jobs check failed; it will be retried: {err_msg}")

    return _QUERY_JOBS_TABLE_EXISTS is True


def load_in_flight_jobs(
    jobs_store: Optional[Dict[str, Any]] = None,
    supabase_client: Any = None
) -> Dict[str, Dict[str, Any]]:
    """
    Load in-flight and recent jobs from persistent local SQLite disk cache and Supabase `query_jobs`.
    Survives worker process recycling and Render service sleep wakeups.
    """
    store: Dict[str, Dict[str, Any]] = {}
    sb = _get_supabase_client(supabase_client)

    # 1. Load from local SQLite cache first (fast, reliable, zero network latency)
    try:
        with sqlite3.connect(_LOCAL_JOBS_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT job_id, user_id, stage, status, updated_at, metadata_json "
                "FROM local_query_jobs ORDER BY updated_at DESC LIMIT 100"
            )
            for row in cursor.fetchall():
                jid, uid, stg, stat, up_at, m_json = row
                meta = {}
                if m_json:
                    try:
                        meta = json.loads(m_json)
                    except Exception:
                        pass
                store[jid] = {
                    "job_id": jid,
                    "user_id": uid,
                    "stage": stg or "processing",
                    "status": stat or "running",
                    "updated_at": up_at,
                    "early_display": meta.get("early_display"),
                    "result": meta.get("result"),
                    "error": meta.get("error"),
                    "worker_instance_id": meta.get("worker_instance_id"),
                }
    except Exception as sq_err:
        logger.debug(f"SQLite jobs cache read error: {sq_err}")

    # 2. Supabase table lookup if circuit breaker is healthy
    if sb and _is_supabase_circuit_healthy():
        try:
            res = _safe_supabase_exec(
                lambda: sb.table("query_jobs")
                .select("job_id, user_id, stage, status, updated_at, metadata")
                .order("updated_at", desc=True)
                .limit(50)
                .execute(),
                retries=1
            )
            if res and hasattr(res, "data") and res.data:
                for row in res.data:
                    meta = row.get("metadata") or {}
                    job_id = row.get("job_id")
                    if job_id and (
                        job_id not in store
                        or _timestamp_key(row.get("updated_at")) > _timestamp_key(store[job_id].get("updated_at"))
                    ):
                        store[row["job_id"]] = {
                            "job_id": row.get("job_id"),
                            "user_id": row.get("user_id"),
                            "stage": row.get("stage", "processing"),
                            "status": row.get("status", "running"),
                            "updated_at": row.get("updated_at"),
                            "early_display": meta.get("early_display"),
                            "result": meta.get("result"),
                            "error": meta.get("error"),
                            "worker_instance_id": meta.get("worker_instance_id"),
                        }
        except Exception as e:
            logger.debug(f"Failed to query query_jobs table: {e}")

    with _IN_FLIGHT_JOBS_LOCK:
        for k, v in _IN_FLIGHT_JOBS_CACHE.items():
            if k not in store:
                store[k] = v
    return store


# Backwards compatibility alias
_load_in_flight_jobs = load_in_flight_jobs


def persist_in_flight_job_state(
    job_id: str,
    stage: str,
    status: str = "running",
    extra: Optional[Dict[str, Any]] = None,
    jobs_store: Optional[Dict[str, Any]] = None,
    supabase_client: Any = None
) -> None:
    """
    Persist job execution stage and status to local memory cache, SQLite disk, and PostgreSQL `query_jobs`.
    Enforces privacy by stripping raw query text from metadata before storing.
    """
    if extra is None:
        extra = {}

    if status == "done":
        result_payload = extra.get("result")
        if not _has_valid_final_result(result_payload):
            status = "failed"
            stage = "failed"
            extra = {**extra, "error": extra.get("error") or "finalization produced no payload", "result": None}

    extra = {**extra, "worker_instance_id": WORKER_INSTANCE_ID}
    user_id = extra.get("user_id") if extra else None
    sanitized_metadata = {}
    if extra:
        for k, v in extra.items():
            if k not in ("job_id", "stage", "status", "user_id"):
                k_lower = k.lower()
                if not any(term in k_lower for term in ("query", "prompt", "question", "text")):
                    sanitized_metadata[k] = v

    now_iso = datetime.now(timezone.utc).isoformat()
    meta_json_str = json.dumps(sanitized_metadata) if sanitized_metadata else "{}"

    # 1. Update memory cache
    with _IN_FLIGHT_JOBS_LOCK:
        rec = _IN_FLIGHT_JOBS_CACHE.get(job_id, {})
        if not user_id:
            user_id = rec.get("user_id")
        rec.update({
            "job_id": job_id,
            "stage": stage,
            "status": status,
            "updated_at": now_iso
        })
        if user_id:
            rec["user_id"] = user_id
        if sanitized_metadata:
            rec.update(sanitized_metadata)
        _IN_FLIGHT_JOBS_CACHE[job_id] = rec

    target_store = jobs_store if jobs_store is not None else _REGISTERED_JOBS_STORE
    if target_store is not None:
        rec_store = target_store.setdefault(job_id, {})
        rec_store["stage"] = stage
        rec_store["status"] = status
        if extra:
            rec_store.update(extra)

    # 2. Persist to local SQLite disk database (survives worker recycle)
    try:
        with sqlite3.connect(_LOCAL_JOBS_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO local_query_jobs (job_id, user_id, stage, status, updated_at, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage, status=excluded.status, "
                "updated_at=excluded.updated_at, metadata_json=excluded.metadata_json, "
                "user_id=CASE WHEN excluded.user_id = '' THEN local_query_jobs.user_id "
                "ELSE excluded.user_id END",
                (job_id, user_id or "", stage, status, now_iso, meta_json_str)
            )
    except Exception as sq_err:
        logger.debug(f"SQLite jobs cache write error: {sq_err}")

    # 3. Supabase async upsert if circuit healthy
    sb = _get_supabase_client(supabase_client)
    if sb and _is_supabase_circuit_healthy() and check_query_jobs_table_exists(sb):
        try:
            payload = {
                "job_id": job_id,
                "stage": stage,
                "status": status,
                "updated_at": now_iso,
                "metadata": sanitized_metadata
            }
            if user_id:
                payload["user_id"] = user_id
            _safe_supabase_exec(lambda: sb.table("query_jobs").upsert(payload).execute(), retries=1)
        except Exception as e:
            logger.debug(f"Failed to upsert job {job_id} to query_jobs table: {e}")


def reap_interrupted_jobs_on_startup(
    jobs_store: Optional[Dict[str, Any]] = None,
    supabase_client: Any = None
) -> int:
    """
    Startup reaper: marks stale running or processing jobs as interrupted.
    A fresh job may belong to a different live application worker.
    """
    reaped_job_ids = set()
    now_iso = datetime.now(timezone.utc).isoformat()
    sb = _get_supabase_client(supabase_client)

    if sb and _is_supabase_circuit_healthy():
        try:
            res = _safe_supabase_exec(
                lambda: sb.table("query_jobs")
                .select("job_id, status, stage, updated_at")
                .in_("status", ["running", "processing"])
                .execute()
            )
            if res and hasattr(res, "data") and res.data:
                for row in res.data:
                    jid = row.get("job_id")
                    if jid and _job_is_stale(row):
                        try:
                            update_query = sb.table("query_jobs").update({
                                "status": "error",
                                "stage": "interrupted",
                                "updated_at": now_iso,
                                "metadata": {
                                    "error": "The research session was interrupted by a server restart. Please re-submit your query."
                                }
                            }).eq("job_id", jid)
                            if row.get("updated_at"):
                                update_query = update_query.eq("updated_at", row["updated_at"])
                            result = _safe_supabase_exec(
                                lambda: update_query.execute()
                            )
                            if result is not None:
                                reaped_job_ids.add(jid)
                        except Exception as update_err:
                            logger.debug(f"Failed to reap query_job {jid}: {update_err}")
        except Exception as e:
            logger.debug(f"Reaper check failed: {e}")

    # Reconcile memory and SQLite cache
    with _IN_FLIGHT_JOBS_LOCK:
        for jid, rec in list(_IN_FLIGHT_JOBS_CACHE.items()):
            if rec.get("status") in ("running", "processing") and _job_is_stale(rec):
                rec["status"] = "error"
                rec["stage"] = "interrupted"
                rec["error"] = "The research session was interrupted by a server restart. Please re-submit your query."
                rec["updated_at"] = now_iso
                reaped_job_ids.add(jid)

    try:
        with sqlite3.connect(_LOCAL_JOBS_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT job_id, updated_at FROM local_query_jobs "
                "WHERE status IN ('running', 'processing')"
            ).fetchall()
            stale_job_ids = [
                jid for jid, updated_at in rows
                if _job_is_stale({"updated_at": updated_at})
            ]
            for jid in stale_job_ids:
                conn.execute(
                    "UPDATE local_query_jobs SET status = 'error', stage = 'interrupted', updated_at = ? "
                    "WHERE job_id = ? AND status IN ('running', 'processing')",
                    (now_iso, jid)
                )
                reaped_job_ids.add(jid)
    except Exception as sq_err:
        logger.debug(f"SQLite jobs cache reaper error: {sq_err}")

    if reaped_job_ids:
        print(f"🧹 [STARTUP REAPER] Cleaned up {len(reaped_job_ids)} abandoned in-flight query jobs.", flush=True)

    return len(reaped_job_ids)
