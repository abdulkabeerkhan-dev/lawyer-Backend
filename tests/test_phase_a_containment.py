import unittest
import os
import sys
import json
import hashlib
import time
import asyncio
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import pypdf
import jwt
from docx import Document
import io

# Ensure backend root is on path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from main import PROTOTYPE_BANNER, verify_clerk_session, get_authorized_testers, build_judgment_pdf_bytes
from core.document_builder import generate_court_docx

class TestPhaseAContainment(unittest.TestCase):

    def test_prototype_banner_wording(self):
        """A2: Verify the exact required prototype banner wording exists."""
        expected_phrase = "Prototype. Not verified for use in pleadings. Verify every citation and statement against the original judgment."
        self.assertIn(expected_phrase, PROTOTYPE_BANNER)

    def test_prototype_banner_in_docx_export(self):
        """A2: Verify generated DOCX includes the prototype warning banner."""
        buffer = generate_court_docx("Test Case Title", "Supreme Court of Pakistan", "This is test pleading body text.")
        doc = Document(buffer)
        full_doc_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("PROTOTYPE — NOT VERIFIED FOR USE IN PLEADINGS", full_doc_text)
        self.assertIn("Verify every citation and statement against the original judgment", full_doc_text)

    def test_prototype_banner_in_pdf_export(self):
        """A2: Verify generated judgment PDF includes the prototype warning banner."""
        pdf_bytes = build_judgment_pdf_bytes("Test Case", "PLD 2020 SC 1", "Supreme Court of Pakistan", "Judgment body text.")
        self.assertTrue(len(pdf_bytes) > 0)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_pdf_text = "".join(page.extract_text() for page in reader.pages)
        self.assertIn("PROTOTYPE", full_pdf_text)
        self.assertIn("NOT VERIFIED FOR USE IN PLEADINGS", full_pdf_text)

    def test_authorized_testers_default_empty_fail_closed(self):
        """A3: Verify AUTHORIZED_TESTERS defaults to empty set and fails closed."""
        import main
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": ""}, clear=False):
            testers = get_authorized_testers()
            self.assertEqual(testers, set(), "Default whitelist must be empty set")

            mock_credentials = MagicMock()
            token = self._make_clerk_token("some_user")
            mock_credentials.credentials = token

            with patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(verify_clerk_session(credentials=mock_credentials))
                self.assertEqual(ctx.exception.status_code, 403)
                self.assertIn("Prototype access is closed", ctx.exception.detail)

    def test_mock_credentials_strictly_blocked_in_production(self):
        """A3: Verify mock dev credentials are completely rejected in production."""
        import main
        with patch.object(main, "IS_PRODUCTION", True):
            mock_credentials = MagicMock()
            mock_credentials.credentials = "mock_clerk_user_id_dev_run"

            import asyncio
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(verify_clerk_session(credentials=mock_credentials))
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Mock dev credentials are not permitted in production", ctx.exception.detail)

    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        # Generate genuine test RSA keypair
        cls.valid_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.valid_public_key = cls.valid_private_key.public_key()
        
        # Generate an untrusted / third-party RSA keypair
        cls.other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_public_key = cls.other_private_key.public_key()
        cls.test_kid = "ins_test_key_123"

    def _make_clerk_token(self, sub: str, exp_offset: int = 3600, key=None, kid=None, alg="RS256", iss="https://clerk.accounts.dev"):
        signing_key = key or self.valid_private_key
        token_kid = kid or self.test_kid
        headers = {"kid": token_kid, "alg": alg}
        payload = {
            "sub": sub,
            "exp": int(time.time()) + exp_offset,
            "iss": iss
        }
        if alg == "HS256":
            return jwt.encode(payload, "forged_symmetric_secret_key", algorithm="HS256", headers=headers)
        return jwt.encode(payload, signing_key, algorithm="RS256", headers=headers)

    def test_forged_token_with_whitelisted_user_gives_401(self):
        """Mandate 1: Forged token (e.g. HS256 alg or forged signature) with a whitelisted user gives 401."""
        import main
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "whitelisted_lawyer_1"}, clear=False):
            # Forgery 1: HS256 symmetric forgery attempt
            token_hs256 = self._make_clerk_token("whitelisted_lawyer_1", alg="HS256")
            mock_cred = MagicMock()
            mock_cred.credentials = token_hs256

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(verify_clerk_session(credentials=mock_cred))
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Only RS256 tokens are permitted", ctx.exception.detail)

            # Forgery 2: Corrupted signature
            valid_token = self._make_clerk_token("whitelisted_lawyer_1")
            tampered_token = valid_token[:-8] + "ABCDEFGH"
            mock_cred.credentials = tampered_token
            with patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
                with self.assertRaises(HTTPException) as ctx2:
                    asyncio.run(verify_clerk_session(credentials=mock_cred))
                self.assertEqual(ctx2.exception.status_code, 401)

    def test_expired_token_gives_401(self):
        """Mandate 1: Expired token gives 401."""
        import main
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "whitelisted_lawyer_1"}, clear=False):
            # Token expired 10 minutes ago
            token_expired = self._make_clerk_token("whitelisted_lawyer_1", exp_offset=-600)
            mock_cred = MagicMock()
            mock_cred.credentials = token_expired

            with patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(verify_clerk_session(credentials=mock_cred))
                self.assertEqual(ctx.exception.status_code, 401)
                self.assertIn("expired", ctx.exception.detail.lower())

    def test_token_signed_by_another_key_gives_401(self):
        """Mandate 1: Token signed by another key gives 401."""
        import main
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "whitelisted_lawyer_1"}, clear=False):
            # Signed by other_private_key but verified against valid_public_key
            token_other_key = self._make_clerk_token("whitelisted_lawyer_1", key=self.other_private_key)
            mock_cred = MagicMock()
            mock_cred.credentials = token_other_key

            with patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(verify_clerk_session(credentials=mock_cred))
                self.assertEqual(ctx.exception.status_code, 401)
                self.assertIn("signature verification failed", ctx.exception.detail.lower())

    def test_valid_token_for_non_listed_user_gives_403(self):
        """Mandate 1: Valid signed token for a non-whitelisted user gives 403."""
        import main
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "whitelisted_lawyer_1"}, clear=False):
            token_valid = self._make_clerk_token("unauthorized_user_outside_whitelist")
            mock_cred = MagicMock()
            mock_cred.credentials = token_valid

            with patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(verify_clerk_session(credentials=mock_cred))
                self.assertEqual(ctx.exception.status_code, 403)
                self.assertIn("restricted to authorized testers", ctx.exception.detail)

    def test_valid_token_for_whitelisted_user_succeeds(self):
        """Mandate 1: Valid signed token for whitelisted user passes with correct user_id."""
        import main
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "whitelisted_lawyer_1"}, clear=False):
            token_valid = self._make_clerk_token("whitelisted_lawyer_1")
            mock_cred = MagicMock()
            mock_cred.credentials = token_valid

            with patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
                user_id = asyncio.run(verify_clerk_session(credentials=mock_cred))
                self.assertEqual(user_id, "whitelisted_lawyer_1")

    def test_auth_login_returns_404_in_production(self):
        """Mandate 3: POST /auth/login must return 404 in production."""
        import main
        from main import handle_backend_login, LoginPayload
        with patch.object(main, "IS_PRODUCTION", True):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(handle_backend_login(LoginPayload(email="test@lawyer.com", password="pwd")))
            self.assertEqual(ctx.exception.status_code, 404)

    def test_request_access_rate_limiting(self):
        """Mandate 4: Verify in-memory IP rate limiting on /request-access."""
        import main
        from main import check_access_request_rate_limit
        mock_req = MagicMock()
        mock_req.client.host = "192.168.1.100"
        
        main._request_access_ip_history.clear()
        # 5 requests should pass
        for _ in range(5):
            check_access_request_rate_limit(mock_req, max_requests=5, window_seconds=60)
            
        # 6th request must trigger 429
        with self.assertRaises(HTTPException) as ctx:
            check_access_request_rate_limit(mock_req, max_requests=5, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Rate limit exceeded", ctx.exception.detail)

    def test_client_ip_header_spoofing_prevention(self):
        """Directive 1: Verify get_real_client_ip strictly ignores spoofable headers (X-Real-IP, CF-Connecting-IP, XFF)."""
        import main
        from main import get_real_client_ip
        
        # Scenario A: Attacker supplies spoofed headers
        mock_req = MagicMock()
        mock_req.client.host = "10.0.0.1"
        mock_req.headers = {
            "x-real-ip": "1.1.1.1",
            "cf-connecting-ip": "2.2.2.2",
            "x-forwarded-for": "3.3.3.3, 4.4.4.4"
        }
        # Must ignore spoofed headers and fall back to trusted connection host
        ip = get_real_client_ip(mock_req)
        self.assertEqual(ip, "10.0.0.1", "Spoofed headers (X-Real-IP, CF-Connecting-IP, XFF) must be ignored")

        # Scenario B: Railway Envoy edge proxy provides X-Envoy-External-Address
        mock_req.headers["x-envoy-external-address"] = "203.0.113.195"
        ip_envoy = get_real_client_ip(mock_req)
        self.assertEqual(ip_envoy, "203.0.113.195", "Genuine X-Envoy-External-Address must be respected")

    def test_startup_check_requires_allowed_origins_in_production(self):
        """Directive 2: validate_production_auth_config must refuse startup if ALLOWED_ORIGINS is missing in production."""
        import main
        with patch.object(main, "IS_PRODUCTION", True):
            with patch.dict(os.environ, {
                "CLERK_ISSUER": "https://clerk.test",
                "CLERK_AUTHORIZED_PARTY": "test_app",
                "AUTHORIZED_TESTERS": "user_1",
                "ALLOWED_ORIGINS": "",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_KEY": "test_service_key"
            }, clear=False):
                with self.assertRaises(RuntimeError) as ctx:
                    main.validate_production_auth_config()
                self.assertIn("ALLOWED_ORIGINS", str(ctx.exception))

    def test_startup_check_requires_supabase_in_production(self):
        """Item 11: validate_production_auth_config must refuse startup if SUPABASE_URL or SUPABASE_SERVICE_KEY is missing in production."""
        import main
        with patch.object(main, "IS_PRODUCTION", True):
            # Test missing SUPABASE_URL
            with patch.dict(os.environ, {
                "CLERK_ISSUER": "https://clerk.test",
                "CLERK_AUTHORIZED_PARTY": "test_app",
                "AUTHORIZED_TESTERS": "user_1",
                "ALLOWED_ORIGINS": "https://app.test",
                "SUPABASE_URL": "",
                "SUPABASE_SERVICE_KEY": "test_service_key"
            }, clear=False):
                with self.assertRaises(RuntimeError) as ctx:
                    main.validate_production_auth_config()
                self.assertIn("SUPABASE_URL", str(ctx.exception))

            # Test missing SUPABASE_SERVICE_KEY
            with patch.dict(os.environ, {
                "CLERK_ISSUER": "https://clerk.test",
                "CLERK_AUTHORIZED_PARTY": "test_app",
                "AUTHORIZED_TESTERS": "user_1",
                "ALLOWED_ORIGINS": "https://app.test",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_KEY": ""
            }, clear=False):
                with self.assertRaises(RuntimeError) as ctx:
                    main.validate_production_auth_config()
                self.assertIn("SUPABASE_SERVICE_KEY", str(ctx.exception))

    def test_cors_strictly_refuses_arbitrary_origins_in_production(self):
        """Directive 2: _origin_is_allowed must strictly refuse unlisted origins in production."""
        import main
        with patch.object(main, "IS_PRODUCTION", True), patch.object(main, "ALLOWED_ORIGINS", ["https://trusted-lawyer.com"]):
            self.assertTrue(main._origin_is_allowed("https://trusted-lawyer.com"))
            self.assertFalse(main._origin_is_allowed("https://attacker-mirror.com"))
            self.assertFalse(main._origin_is_allowed("https://random-origin.org"))

    def test_snapshot_manifest_integrity_in_repo(self):
        """A4/A5: Verify manifest exists in repo, has >=70 entries, and matches external snapshot."""
        manifest_path = os.path.join(WORKSPACE_DIR, "backups", "manifest_sha256.json")
        self.assertTrue(os.path.exists(manifest_path), "Snapshot manifest missing in backups/manifest_sha256.json")

        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)

        self.assertGreaterEqual(len(manifest), 70, "Snapshot manifest must contain at least 70 entries")

        ext_snapshot_dir = r"C:\Users\kabeer\Documents\lawyer_backups\snapshot_phase_a_pre_remediation"
        if os.path.exists(ext_snapshot_dir):
            for rel_key in ["bm25_index.pkl", "data/curated_historical_cases.json"]:
                snap_file = os.path.join(ext_snapshot_dir, rel_key.replace("/", os.sep))
                self.assertTrue(os.path.exists(snap_file), f"External backed-up file {snap_file} missing")
                with open(snap_file, "rb") as bf:
                    calc_h = hashlib.sha256(bf.read()).hexdigest()
                self.assertEqual(calc_h, manifest[rel_key]["sha256"])

    def test_bm25_index_sha256_integrity(self):
        """Mandate 7: Assert bm25_index.pkl matches pinned SHA-256 and fail build if modified without approval."""
        bm25_path = os.path.join(WORKSPACE_DIR, "bm25_index.pkl")
        self.assertTrue(os.path.exists(bm25_path), "bm25_index.pkl must exist in repository root")
        with open(bm25_path, "rb") as f:
            computed_sha = hashlib.sha256(f.read()).hexdigest()
        EXPECTED_SHA = "b66429c55e0d43170ff2ed9c717de592ee8c948ea0d67cca5b8d21bb8a95d747"
        self.assertEqual(
            computed_sha, EXPECTED_SHA,
            f"bm25_index.pkl SHA-256 mismatch! Got {computed_sha}, expected {EXPECTED_SHA}. Any index change requires formal review and approval."
        )

    def test_bm25_smoke_query(self):
        """Mandate 4: Smoke test that loads BM25 index and retrieves results for a query."""
        from hybrid_search import BM25Index
        bm25_path = os.path.join(WORKSPACE_DIR, "bm25_index.pkl")
        self.assertTrue(os.path.exists(bm25_path), "bm25_index.pkl missing")
        index = BM25Index.load(bm25_path)
        self.assertEqual(index.corpus_size, 33940, "BM25 index must contain exactly 33,940 chunks")
        results = index.search("bail under Section 497 CrPC non-bailable", top_k=5)
        self.assertGreater(len(results), 0, "BM25 search must return at least 1 result")
        doc_id, score, meta = results[0]
        self.assertGreater(score, 0.0, "Top score must be positive")
        self.assertIn("case_id", meta, "Result metadata must contain case_id")

if __name__ == "__main__":
    unittest.main()
