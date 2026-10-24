"""
tests/test_phase1_auth_comprehensive.py

Comprehensive Phase 1 Auth Tests:
1. Missing credentials returns 401.
2. Malformed / invalid signature token returns 401.
3. Expired RS256 token returns 401.
4. Valid RS256 token for non-whitelisted user returns 403 Forbidden.
5. {"bypass_auth": true} in request body in production without credentials returns 401.
6. Mock user id (mock_clerk_user_id_dev_run) in production returns 401.
7. CORS request from disallowed origin in production returns 403 Forbidden.
8. Unauthenticated /admin/associates returns 401.
"""

import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt

# Generate ephemeral RSA keypair for deterministic JWT testing
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_pem_private = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

def _generate_test_token(sub: str, exp_offset: int = 3600, kid: str = "test_kid", iss: str = "https://clerk.test.local"):
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": iss,
        "iat": now,
        "exp": now + exp_offset
    }
    return jwt.encode(payload, _pem_private, algorithm="RS256", headers={"kid": kid})

def setup_module():
    import main
    # Inject test public key into Clerk JWKS cache
    with main._clerk_jwks_cache["lock"]:
        main._clerk_jwks_cache["keys"]["test_kid"] = _public_key
        main._clerk_jwks_cache["last_fetched"] = time.time() + 999999

def test_missing_token_returns_401():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    from main import app
    client = TestClient(app)
    res = client.post("/query", json={"query_text": "Who is the Chief Justice?"})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"

def test_invalid_malformed_token_returns_401():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    from main import app
    client = TestClient(app)
    res = client.post(
        "/query",
        json={"query_text": "Test query"},
        headers={"Authorization": "Bearer invalid.malformed.jwt.signature"}
    )
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"

def test_expired_token_returns_401():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    os.environ["CLERK_ISSUER"] = "https://clerk.test.local"
    from main import app
    client = TestClient(app)
    expired_token = _generate_test_token(sub="test_user", exp_offset=-300)
    res = client.post(
        "/query",
        json={"query_text": "Test query"},
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"
    assert "expired" in res.text.lower(), f"Expected 'expired' in response: {res.text}"

def test_non_whitelisted_user_returns_403():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    os.environ["CLERK_ISSUER"] = "https://clerk.test.local"
    os.environ["AUTHORIZED_TESTERS"] = "whitelisted_advocate_1,whitelisted_advocate_2"
    from main import app
    client = TestClient(app)
    unauthorized_token = _generate_test_token(sub="unauthorized_random_user", exp_offset=3600)
    res = client.post(
        "/query",
        json={"query_text": "Test query"},
        headers={"Authorization": f"Bearer {unauthorized_token}"}
    )
    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
    assert "not authorized" in res.text.lower(), f"Expected 'not authorized' in response: {res.text}"

def test_bypass_auth_body_in_production_returns_401():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    from main import app
    client = TestClient(app)
    res = client.post("/query", json={"query_text": "Test query", "bypass_auth": True})
    assert res.status_code == 401, f"Expected 401 on bypass attempt in production, got {res.status_code}: {res.text}"

def test_mock_user_id_in_production_returns_401():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    from main import app
    client = TestClient(app)
    res = client.post(
        "/query",
        json={"query_text": "Test query"},
        headers={"Authorization": "Bearer mock_clerk_user_id_dev_run"}
    )
    assert res.status_code == 401, f"Expected 401 on mock user in production, got {res.status_code}: {res.text}"

def test_disallowed_cors_origin_returns_403():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    os.environ["ALLOWED_ORIGINS"] = "https://app.lovable.dev,https://legalaid.pk"
    from main import app
    client = TestClient(app)
    # Preflight from evil origin
    res = client.options(
        "/query",
        headers={
            "Origin": "https://malicious-external-site.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type"
        }
    )
    assert res.status_code in (403, 400), f"Expected 403 for disallowed origin, got {res.status_code}"

def test_unauthenticated_admin_returns_401():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ENABLE_DEV_AUTH_BYPASS"] = "false"
    from main import app
    client = TestClient(app)
    res = client.get("/admin/associates")
    assert res.status_code == 401, f"Expected 401 for admin endpoint, got {res.status_code}: {res.text}"

if __name__ == "__main__":
    setup_module()
    test_missing_token_returns_401()
    print("test_missing_token_returns_401: PASSED")
    test_invalid_malformed_token_returns_401()
    print("test_invalid_malformed_token_returns_401: PASSED")
    test_expired_token_returns_401()
    print("test_expired_token_returns_401: PASSED")
    test_non_whitelisted_user_returns_403()
    print("test_non_whitelisted_user_returns_403: PASSED")
    test_bypass_auth_body_in_production_returns_401()
    print("test_bypass_auth_body_in_production_returns_401: PASSED")
    test_mock_user_id_in_production_returns_401()
    print("test_mock_user_id_in_production_returns_401: PASSED")
    test_disallowed_cors_origin_returns_403()
    print("test_disallowed_cors_origin_returns_403: PASSED")
    test_unauthenticated_admin_returns_401()
    print("test_unauthenticated_admin_returns_401: PASSED")
    print("\nALL 8 COMPREHENSIVE AUTH TESTS PASSED DETERMINISTICALLY!")
