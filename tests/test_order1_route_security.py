"""
tests/test_order1_route_security.py

Comprehensive Order 1 Route Security and Invariants Test Suite:
1. Dynamically inspects all registered application routes from app.routes (target: exactly 38 application routes).
   Fails immediately if non-existent routes are configured or tested.
2. Unauthenticated access enforcement:
   All protected routes return 401/403 when dev auth bypass is false.
3. Forged JWT rejection:
   All protected routes return 401 when presented with untrusted RSA-signed tokens.
4. Non-whitelisted user rejection:
   All protected routes return 403 for valid tokens of users outside AUTHORIZED_TESTERS.
5. Administrative role gating:
   All /admin/* routes return 403 for whitelisted users who do not have the 'admin' role in Supabase.
6. Mass assignment protection on /users/update-profile:
   Attempts to inject 'role', 'is_whitelisted', or other unauthorized fields return 422 Unprocessable Entity.
7. Cross-user job isolation:
   Jobs owned by User A return 403 when accessed by User B via /query/{job_id}, /query/{job_id}/stream, and /query/{job_id}/continue.
8. PDF route authorization & header integrity:
   /api/judgments/{id}/pdf and /judgment-pdf/{id} return 401 without auth,
   return 401 with forged/expired HMAC token, return 200 with valid HMAC token or Clerk session,
   and strip wildcard 'Access-Control-Allow-Origin: *'.
"""

import os
import sys
import time
import re
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

# Ensure backend root on sys.path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

import main
from main import app, jobs_store, _IN_FLIGHT_JOBS_CACHE, _IN_FLIGHT_JOBS_LOCK
from core.pdf_resolver import create_hmac_pdf_token

class TestOrder1RouteSecurity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.valid_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.valid_public_key = cls.valid_private_key.public_key()

        cls.untrusted_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.untrusted_public_key = cls.untrusted_private_key.public_key()

        cls.issuer = "https://clerk.sectionai.internal"
        cls.authorized_party = "section_ai_frontend"

        cls.whitelisted_user_a = "user_whitelisted_alice_101"
        cls.whitelisted_user_b = "user_whitelisted_bob_202"
        cls.non_whitelisted_user = "user_unauthorized_stranger_999"

        cls.forged_token = cls._build_jwt(
            cls.whitelisted_user_a,
            key=cls.untrusted_private_key,
            issuer=cls.issuer,
            azp=cls.authorized_party
        )

        cls.non_whitelisted_valid_token = cls._build_jwt(
            cls.non_whitelisted_user,
            key=cls.valid_private_key,
            issuer=cls.issuer,
            azp=cls.authorized_party
        )

        cls.user_a_token = cls._build_jwt(
            cls.whitelisted_user_a,
            key=cls.valid_private_key,
            issuer=cls.issuer,
            azp=cls.authorized_party
        )

        cls.user_b_token = cls._build_jwt(
            cls.whitelisted_user_b,
            key=cls.valid_private_key,
            issuer=cls.issuer,
            azp=cls.authorized_party
        )

        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def _build_jwt(cls, sub: str, key, issuer: str, azp: str, exp_offset: int = 3600) -> str:
        headers = {"kid": "key_test_order1", "alg": "RS256"}
        payload = {
            "sub": sub,
            "iss": issuer,
            "azp": azp,
            "aud": azp,
            "exp": int(time.time()) + exp_offset
        }
        return jwt.encode(payload, key, algorithm="RS256", headers=headers)

    @classmethod
    def _resolve_test_path(cls, path: str) -> str:
        resolved = re.sub(r"\{[a-zA-Z_]+:path\}", "SC_1988_SCMR_416", path)
        resolved = re.sub(r"\{[a-zA-Z_]+\}", "test_fixture_123", resolved)
        return resolved

    def _get_registered_app_routes(self):
        """
        Dynamically extracts all application routes from app.routes, excluding auto-generated doc routes.
        Returns dictionary mapping (method, path) to (resolved_path, is_public).
        """
        doc_paths = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
        public_paths = {
            "/health",
            "/coverage",
            "/disclaimer",
            "/privacy",
            "/terms",
            "/request-access",
            "/request-status/{email:path}",
            "/auth/login"
        }

        routes = {}
        for r in app.routes:
            if isinstance(r, APIRoute):
                if r.path in doc_paths:
                    continue
                methods = r.methods - {"HEAD", "OPTIONS"}
                for m in methods:
                    is_public = r.path in public_paths
                    routes[(m, r.path)] = (self._resolve_test_path(r.path), is_public)

        return routes

    def test_dynamic_route_matrix_matches_real_routes(self):
        """Validates that app.routes contains exactly 38 real application routes and fails if mismatched."""
        routes = self._get_registered_app_routes()
        self.assertEqual(len(routes), 38, f"Expected exactly 38 real application routes, found {len(routes)}: {list(routes.keys())}")

    def test_unauthenticated_access_rejected_on_all_protected_routes(self):
        """All protected routes return 401/403 when called without an Authorization header."""
        routes = self._get_registered_app_routes()
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": f"{self.whitelisted_user_a},{self.whitelisted_user_b}"
        }):
            for (method, raw_path), (test_path, is_public) in routes.items():
                with self.subTest(route=f"{method} {raw_path}"):
                    if method == "GET":
                        res = self.client.get(test_path)
                    elif method == "POST":
                        res = self.client.post(test_path, json={})
                    elif method == "DELETE":
                        res = self.client.delete(test_path)
                    else:
                        continue

                    if is_public:
                        self.assertIn(
                            res.status_code, [200, 422, 429, 404],
                            f"Expected public endpoint {method} {raw_path} to return valid public status, got {res.status_code}"
                        )
                    else:
                        self.assertIn(
                            res.status_code, [401, 403],
                            f"Protected endpoint {method} {raw_path} without auth must return 401/403, got {res.status_code}: {res.text}"
                        )

    def test_forged_jwt_rejected_on_all_protected_routes(self):
        """All protected routes return 401 when presented with an untrusted RS256 token."""
        routes = self._get_registered_app_routes()
        auth_headers = {"Authorization": f"Bearer {self.forged_token}"}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": f"{self.whitelisted_user_a},{self.whitelisted_user_b}",
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
            for (method, raw_path), (test_path, is_public) in routes.items():
                if is_public:
                    continue
                with self.subTest(route=f"{method} {raw_path}"):
                    if method == "GET":
                        res = self.client.get(test_path, headers=auth_headers)
                    elif method == "POST":
                        res = self.client.post(test_path, headers=auth_headers, json={})
                    elif method == "DELETE":
                        res = self.client.delete(test_path, headers=auth_headers)
                    else:
                        continue

                    self.assertEqual(
                        res.status_code, 401,
                        f"Expected 401 for forged token on {method} {raw_path}, got {res.status_code}: {res.text}"
                    )

    def test_non_whitelisted_valid_jwt_rejected_on_all_protected_routes(self):
        """All protected routes return 403 when presented with a valid JWT from a non-whitelisted user."""
        routes = self._get_registered_app_routes()
        auth_headers = {"Authorization": f"Bearer {self.non_whitelisted_valid_token}"}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": f"{self.whitelisted_user_a},{self.whitelisted_user_b}",
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
            for (method, raw_path), (test_path, is_public) in routes.items():
                if is_public:
                    continue
                with self.subTest(route=f"{method} {raw_path}"):
                    if method == "GET":
                        res = self.client.get(test_path, headers=auth_headers)
                    elif method == "POST":
                        res = self.client.post(test_path, headers=auth_headers, json={})
                    elif method == "DELETE":
                        res = self.client.delete(test_path, headers=auth_headers)
                    else:
                        continue

                    self.assertEqual(
                        res.status_code, 403,
                        f"Expected 403 for non-whitelisted user on {method} {raw_path}, got {res.status_code}: {res.text}"
                    )

    def test_whitelisted_non_admin_receives_403_on_admin_routes(self):
        """Whitelisted user without the 'admin' database role receives 403 on all /admin/* endpoints."""
        auth_headers = {"Authorization": f"Bearer {self.user_a_token}"}
        admin_routes = [
            ("GET", "/admin/associates"),
            ("POST", "/admin/associates"),
            ("POST", "/admin/associates/test_fixture_123/status"),
            ("DELETE", "/admin/associates/test_fixture_123"),
            ("GET", "/admin/activity"),
            ("GET", "/admin/associates/usage"),
            ("GET", "/admin/export-training-data"),
            ("GET", "/admin/quarantine/records"),
            ("POST", "/admin/quarantine/review"),
            ("GET", "/admin/quarantine/dashboard"),
            ("GET", "/api/indexing-status"),
        ]

        mock_sb = MagicMock()
        mock_sb.table().select().eq().execute.return_value.data = [{"role": "advocate", "id": self.whitelisted_user_a}]

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": f"{self.whitelisted_user_a},{self.whitelisted_user_b}",
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key), patch.object(main, "supabase", mock_sb):
            for method, path in admin_routes:
                with self.subTest(route=f"{method} {path}"):
                    if method == "GET":
                        res = self.client.get(path, headers=auth_headers)
                    elif method == "POST":
                        res = self.client.post(path, headers=auth_headers, json={})
                    elif method == "DELETE":
                        res = self.client.delete(path, headers=auth_headers)
                    else:
                        continue

                    self.assertEqual(
                        res.status_code, 403,
                        f"Expected 403 for non-admin on {method} {path}, got {res.status_code}: {res.text}"
                    )

    def test_profile_update_mass_assignment_prevented(self):
        """POST /users/update-profile rejects unauthorized fields (role, is_whitelisted) with 422."""
        auth_headers = {"Authorization": f"Bearer {self.user_a_token}"}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": self.whitelisted_user_a,
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
            # Attempt 1: Mass assignment with role='admin'
            malicious_payload = {
                "full_name": "Alice Attacker",
                "role": "admin"
            }
            res = self.client.post("/users/update-profile", headers=auth_headers, json=malicious_payload)
            self.assertEqual(
                res.status_code, 422,
                f"Expected 422 Unprocessable Entity for injected 'role' field, got {res.status_code}: {res.text}"
            )

            # Attempt 2: Mass assignment with is_whitelisted=True
            malicious_payload_2 = {
                "full_name": "Alice Attacker",
                "is_whitelisted": True
            }
            res2 = self.client.post("/users/update-profile", headers=auth_headers, json=malicious_payload_2)
            self.assertEqual(
                res2.status_code, 422,
                f"Expected 422 Unprocessable Entity for injected 'is_whitelisted' field, got {res2.status_code}: {res2.text}"
            )

            # Legitimate payload with only allowed fields
            mock_sb = MagicMock()
            mock_sb.table().update().eq().execute.return_value.data = [{"id": self.whitelisted_user_a, "full_name": "Alice Valid"}]
            with patch.object(main, "supabase", mock_sb):
                valid_payload = {"full_name": "Alice Valid"}
                res_valid = self.client.post("/users/update-profile", headers=auth_headers, json=valid_payload)
                self.assertEqual(res_valid.status_code, 200)

    def test_cross_user_job_isolation(self):
        """User B cannot read, stream, or continue a query job created by User A."""
        job_id = "test_job_owned_by_alice_999"

        # Register User A's job in memory and in-flight store
        jobs_store[job_id] = {
            "job_id": job_id,
            "user_id": self.whitelisted_user_a,
            "status": "running",
            "stage": "processing",
            "result": None,
            "error": None
        }

        with _IN_FLIGHT_JOBS_LOCK:
            _IN_FLIGHT_JOBS_CACHE[job_id] = {
                "job_id": job_id,
                "user_id": self.whitelisted_user_a,
                "status": "running",
                "stage": "processing"
            }

        headers_user_b = {"Authorization": f"Bearer {self.user_b_token}"}

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": f"{self.whitelisted_user_a},{self.whitelisted_user_b}",
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):

            # 1. GET /query/{job_id} by User B -> 403 Forbidden
            res_status = self.client.get(f"/query/{job_id}", headers=headers_user_b)
            self.assertEqual(
                res_status.status_code, 403,
                f"Expected 403 for cross-user job status access, got {res_status.status_code}"
            )

            # 2. GET /query/{job_id}/stream by User B -> 403 Forbidden
            res_stream = self.client.get(f"/query/{job_id}/stream", headers=headers_user_b)
            self.assertEqual(
                res_stream.status_code, 403,
                f"Expected 403 for cross-user job stream access, got {res_stream.status_code}"
            )

            # 3. POST /query/{job_id}/continue by User B -> 403 Forbidden
            res_continue = self.client.post(f"/query/{job_id}/continue", headers=headers_user_b)
            self.assertEqual(
                res_continue.status_code, 403,
                f"Expected 403 for cross-user job continuation, got {res_continue.status_code}"
            )

            # Clean up
            jobs_store.pop(job_id, None)
            with _IN_FLIGHT_JOBS_LOCK:
                _IN_FLIGHT_JOBS_CACHE.pop(job_id, None)

    def test_pdf_route_security_and_hmac_token_verification(self):
        """
        PDF endpoints require valid Clerk session or cryptographically signed HMAC token.
        Fails closed with 401 on unauthenticated access or forged token.
        Allows access with valid HMAC token or Clerk session.
        Strips wildcard Access-Control-Allow-Origin: * header.
        """
        cid = "SC_1988_SCMR_416"
        valid_hmac_token = create_hmac_pdf_token(cid, user_id=self.whitelisted_user_a, expires_in=3600)
        expired_hmac_token = create_hmac_pdf_token(cid, user_id=self.whitelisted_user_a, expires_in=-10)
        forged_hmac_token = f"9999999999.{self.whitelisted_user_a}.fake_hmac_signature_hex"

        endpoints = [
            f"/api/judgments/{cid}/pdf",
            f"/judgment-pdf/{cid}"
        ]

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": self.whitelisted_user_a,
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):

            for ep in endpoints:
                with self.subTest(endpoint=ep):
                    # 1. Unauthenticated request -> 401
                    res_unauth = self.client.get(ep)
                    self.assertEqual(
                        res_unauth.status_code, 401,
                        f"Expected 401 for unauthenticated PDF request on {ep}, got {res_unauth.status_code}"
                    )

                    # 2. Forged HMAC token -> 401
                    res_forged = self.client.get(f"{ep}?token={forged_hmac_token}")
                    self.assertEqual(
                        res_forged.status_code, 401,
                        f"Expected 401 for forged HMAC token on {ep}, got {res_forged.status_code}"
                    )

                    # 3. Expired HMAC token -> 401
                    res_expired = self.client.get(f"{ep}?token={expired_hmac_token}")
                    self.assertEqual(
                        res_expired.status_code, 401,
                        f"Expected 401 for expired HMAC token on {ep}, got {res_expired.status_code}"
                    )

                    # 4. Valid HMAC token -> 200
                    res_valid_hmac = self.client.get(f"{ep}?token={valid_hmac_token}")
                    self.assertEqual(
                        res_valid_hmac.status_code, 200,
                        f"Expected 200 for valid HMAC token on {ep}, got {res_valid_hmac.status_code}"
                    )
                    self.assertEqual(res_valid_hmac.headers.get("content-type"), "application/pdf")
                    # Header assertion: Wildcard CORS must NOT be present
                    self.assertNotIn(
                        "access-control-allow-origin",
                        res_valid_hmac.headers,
                        f"Wildcard Access-Control-Allow-Origin header must be stripped on {ep}"
                    )

                    # 5. Valid Clerk session -> 200
                    res_valid_session = self.client.get(ep, headers={"Authorization": f"Bearer {self.user_a_token}"})
                    self.assertEqual(
                        res_valid_session.status_code, 200,
                        f"Expected 200 for valid Clerk session on {ep}, got {res_valid_session.status_code}"
                    )
                    self.assertNotIn("access-control-allow-origin", res_valid_session.headers)

if __name__ == "__main__":
    unittest.main()
