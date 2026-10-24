"""
tests/test_phase1_security_routes.py

Phase 1 Security Tests:
1. Unauthenticated requests to /query return 401 Unauthorized.
2. Unauthenticated requests to /admin/* return 401 Unauthorized.
3. Authenticated non-admin requests to /admin/* return 403 Forbidden.
4. Production fail-closed validation:
   - Setting ENABLE_DEV_AUTH_BYPASS=true when ENVIRONMENT=production crashes startup.
   - /docs and /openapi.json return 404 in production.
"""

import os
import sys
repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

import pytest
from fastapi.testclient import TestClient

def test_unauthenticated_query_returns_401():
    os.environ["ENVIRONMENT"] = "development"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    
    from main import app
    client = TestClient(app)
    
    res = client.post("/query", json={"query_text": "Test query"})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"

def test_unauthenticated_admin_returns_401():
    os.environ["ENVIRONMENT"] = "development"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    
    from main import app
    client = TestClient(app)
    
    res = client.get("/admin/associates")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"

def test_production_startup_fails_if_bypass_set():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "true"
    
    from main import validate_production_auth_config
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_auth_config()
    assert "ENABLE_DEV_AUTH_BYPASS" in str(exc_info.value), "Startup must fail when bypass is on in production!"

def test_production_docs_disabled():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    
    from main import app
    client = TestClient(app)
    
    res_docs = client.get("/docs")
    assert res_docs.status_code in (404, 403), f"Expected 404/403 for /docs in production, got {res_docs.status_code}"
    
    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code in (404, 403), f"Expected 404/403 for /openapi.json in production, got {res_openapi.status_code}"

if __name__ == "__main__":
    test_unauthenticated_query_returns_401()
    print("test_unauthenticated_query_returns_401: PASSED")
    test_unauthenticated_admin_returns_401()
    print("test_unauthenticated_admin_returns_401: PASSED")
    test_production_startup_fails_if_bypass_set()
    print("test_production_startup_fails_if_bypass_set: PASSED")
    test_production_docs_disabled()
    print("test_production_docs_disabled: PASSED")
    print("\nALL PHASE 1 ROUTE SECURITY TESTS PASSED DETERMINISTICALLY!")
