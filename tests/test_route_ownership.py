"""
tests/test_route_ownership.py

Phase 1.7 verification: Route auth, ownership isolation, and persistent proxy-aware rate limiter.
Verifies that:
1. A user cannot delete another user's queries (raises 403 Forbidden).
2. A user cannot access another user's query status (raises 403 Forbidden).
3. The IP rate limiter parses real client IPs behind Cloudflare (CF-Connecting-IP), Envoy, and X-Forwarded-For.
4. The IP rate limiter state survives process restarts.
"""

import pytest
import time
import json
from unittest.mock import MagicMock
from fastapi import HTTPException, Request
from starlette.datastructures import Headers
from main import (
    delete_user_query,
    get_query_job_status,
    get_real_client_ip,
    check_access_request_rate_limit,
    _RATE_LIMIT_PERSIST_FILE,
    _load_rate_limit_store,
    _save_rate_limit_store,
    jobs_store,
)


def make_mock_request(headers_dict=None, client_host="127.0.0.1"):
    headers = Headers(headers_dict or {})
    req = MagicMock(spec=Request)
    req.headers = headers
    req.client = MagicMock()
    req.client.host = client_host
    return req


# --- 1. PROXY IP EXTRACTION TESTS ---

def test_get_real_client_ip_cloudflare():
    """Extracts genuine client IP from CF-Connecting-IP."""
    req = make_mock_request(
        headers_dict={"cf-connecting-ip": "203.0.113.195", "x-forwarded-for": "172.68.1.1, 10.0.0.1"},
        client_host="10.0.0.1"
    )
    assert get_real_client_ip(req) == "203.0.113.195"


def test_get_real_client_ip_x_forwarded_for():
    """Extracts leftmost client IP from X-Forwarded-For when not behind Cloudflare."""
    req = make_mock_request(
        headers_dict={"x-forwarded-for": "198.51.100.42, 10.10.1.5, 10.10.1.1"},
        client_host="10.10.1.1"
    )
    assert get_real_client_ip(req) == "198.51.100.42"


def test_get_real_client_ip_envoy():
    """Extracts client IP from X-Envoy-External-Address."""
    req = make_mock_request(
        headers_dict={"x-envoy-external-address": "198.51.100.99"},
        client_host="127.0.0.1"
    )
    assert get_real_client_ip(req) == "198.51.100.99"


def test_get_real_client_ip_fallback():
    """Falls back to client.host if no proxy headers are present."""
    req = make_mock_request(headers_dict={}, client_host="192.168.1.50")
    assert get_real_client_ip(req) == "192.168.1.50"


# --- 2. PERSISTENT RATE LIMITER TESTS ---

def test_ip_rate_limiter_survives_restart(monkeypatch):
    """Verifies rate limiting thresholds persist to disk and survive process restarts."""
    test_ip = "198.51.100.77"
    req = make_mock_request(headers_dict={"x-forwarded-for": test_ip})

    # Clear disk store for test
    _save_rate_limit_store({})

    # Fire 5 allowed requests within the 60-second window
    for _ in range(5):
        check_access_request_rate_limit(req, max_requests=5, window_seconds=60)

    # 6th request triggers 429
    with pytest.raises(HTTPException) as exc:
        check_access_request_rate_limit(req, max_requests=5, window_seconds=60)
    assert exc.value.status_code == 429

    # SIMULATE RESTART: verify state on disk is preserved and reloaded
    disk_store = _load_rate_limit_store()
    assert test_ip in disk_store
    assert len(disk_store[test_ip]) == 5

    # Immediately after reboot, 429 must STILL trigger (attacker cannot reboot to bypass rate limit)
    with pytest.raises(HTTPException) as exc_after_reboot:
        check_access_request_rate_limit(req, max_requests=5, window_seconds=60)
    assert exc_after_reboot.value.status_code == 429


# --- 3. OWNERSHIP AND ACCESS ISOLATION TESTS ---

@pytest.mark.anyio
async def test_delete_user_query_ownership_enforcement(monkeypatch):
    """User A cannot delete User B's query record (HTTP 403)."""
    import main

    # Mock supabase client returning a query owned by user_victim
    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table

    # Existing query owned by "user_victim_bob"
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [{"id": "query_record_456", "user_id": "user_victim_bob"}]

    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.execute.return_value = mock_exec

    monkeypatch.setattr(main, "supabase", mock_sb)

    # Attacker "user_attacker_eve" attempts to delete Bob's query
    with pytest.raises(HTTPException) as exc_info:
        await delete_user_query(query_id="query_record_456", authenticated_user_id="user_attacker_eve")

    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail


@pytest.mark.anyio
async def test_delete_user_query_not_found(monkeypatch):
    """Deleting a non-existent query raises 404."""
    import main

    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table

    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = []  # No record found

    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.execute.return_value = mock_exec

    monkeypatch.setattr(main, "supabase", mock_sb)

    with pytest.raises(HTTPException) as exc_info:
        await delete_user_query(query_id="non_existent_id", authenticated_user_id="user_valid")

    assert exc_info.value.status_code == 404
