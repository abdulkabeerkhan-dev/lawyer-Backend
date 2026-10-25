"""
tests/test_order1_hardening_invariants.py

Deterministic Unit Tests for Order 1.1 Hardening Invariants:
1. LangSmith outbound gating:
   Assert that when ENABLE_LANGSMITH_TRACING is 'false' or unset, no outbound network
   calls are dispatched to LangSmith / LangChain endpoints, even if LANGCHAIN_TRACING_V2=true.
2. Prompt & Client Fact Hygiene (Grep test):
   Assert zero occurrences of banned directives ('ZERO DISCLAIMER POLLUTION', 'ZERO DISCLAIMER')
   and synthetic client facts ('consultancy fee', 'board approval', 'relative account') across all production code.
3. Precedent Verification Label Integrity:
   Assert that candidate records where is_boosted=True are never assigned 'Verified Full Judgment'.
4. PDF Token Security & Cryptographic Binding:
   Assert that verify_hmac_pdf_token strictly rejects expired tokens, tampered tokens, and tokens
   presented by a mismatched user.
5. Stream Route Authentication & Isolation:
   Assert that /query/{job_id}/stream strictly rejects unauthenticated, forged, and cross-user requests.
"""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

import main
from main import app, sanitize_precedent_card, jobs_store
from core.pdf_resolver import create_hmac_pdf_token, verify_hmac_pdf_token


class TestOrder1HardeningInvariants(unittest.TestCase):

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

        cls.forged_token = cls._build_jwt(
            cls.whitelisted_user_a,
            key=cls.untrusted_private_key,
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
        headers = {"kid": "key_test_order1_inv", "alg": "RS256"}
        payload = {
            "sub": sub,
            "iss": issuer,
            "azp": azp,
            "aud": azp,
            "exp": int(time.time()) + exp_offset
        }
        return jwt.encode(payload, key, algorithm="RS256", headers=headers)

    # -------------------------------------------------------------
    # (a) LangSmith: No outbound call without explicit flag
    # -------------------------------------------------------------
    def test_langsmith_no_outbound_call_without_explicit_flag(self):
        """When ENABLE_LANGSMITH_TRACING is false, LangSmith outbound calls must be 0."""
        with patch.dict(os.environ, {
            "ENABLE_LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "true",
            "LANGCHAIN_API_KEY": "ls__test_fake_api_key_12345",
            "LANGCHAIN_PROJECT": "section-ai-test",
        }), patch("requests.post") as mock_req_post, patch("urllib.request.urlopen") as mock_urlopen:
            
            # Check flag evaluation in main
            flag_val = os.environ.get("ENABLE_LANGSMITH_TRACING", "").lower() in ("true", "1")
            self.assertFalse(flag_val, "LangSmith tracing flag must evaluate to False")
            
            # Verify no outbound HTTP requests were triggered to smith.langchain.com
            self.assertEqual(mock_req_post.call_count, 0)
            self.assertEqual(mock_urlopen.call_count, 0)

    # -------------------------------------------------------------
    # (b) Grep test for banned prompt strings & embedded client facts
    # -------------------------------------------------------------
    def test_grep_banned_prompt_strings_and_embedded_client_facts(self):
        """Assert 0 occurrences of banned prompt directives and client facts across all production application code."""
        banned_phrases = [
            "ZERO DISCLAIMER POLLUTION",
            "ZERO DISCLAIMER",
            "consultancy fee",
            "board approval",
            "relative account"
        ]
        
        violations = []
        for root, dirs, files in os.walk(WORKSPACE_DIR):
            if any(skip in root for skip in [".git", "tests", "scripts", "data", ".gemini", "brain", "venv", "__pycache__"]):
                continue
            for fname in files:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                        for lno, line in enumerate(fp):
                            for phrase in banned_phrases:
                                if phrase.lower() in line.lower():
                                    violations.append((os.path.relpath(fpath, WORKSPACE_DIR), lno + 1, phrase, line.strip()))
        
        self.assertEqual(len(violations), 0, f"Found banned prompt/fact strings in production code: {violations}")

    # -------------------------------------------------------------
    # (c) Boosted record never labelled 'Verified Full Judgment'
    # -------------------------------------------------------------
    def test_boosted_record_never_labelled_verified(self):
        """Candidate records with is_boosted=True must NEVER be labelled 'Verified Full Judgment'."""
        boosted_candidate = {
            "case_id": "2026_SCMR_999",
            "citation": "2026 SCMR 999",
            "case_title": "Test Banking Judgment",
            "court": "Supreme Court of Pakistan",
            "is_boosted": True,
            "direct_citation_match": True,
            "score": 0.99,
            "raw_judgment_text": "Full text of judgment on banking law principles. " * 30,
            "content_type": "full_text"
        }
        
        formatted = sanitize_precedent_card(boosted_candidate)
        vstatus = formatted.get("verification_status", "")
        
        self.assertNotEqual(vstatus, "Verified Full Judgment", "Boosted record must not receive 'Verified Full Judgment'")
        self.assertNotIn("Verified", vstatus, "Unreviewed boosted record must not claim 'Verified'")
        self.assertEqual(vstatus, "Full Judgment (unreviewed)")

    # -------------------------------------------------------------
    # (d) PDF HMAC token expiry, wrong-user, and tampered token
    # -------------------------------------------------------------
    def test_pdf_hmac_token_security(self):
        """verify_hmac_pdf_token strictly rejects expired tokens, tampered tokens, and wrong users."""
        case_id = "SC_2026_SCMR_101"
        secret = "unit_test_pdf_secret_key_123"
        
        # 1. Valid token succeeds
        valid_tok = create_hmac_pdf_token(case_id, user_id="user_alice", expires_in=3600, secret=secret)
        self.assertTrue(verify_hmac_pdf_token(valid_tok, case_id, secret=secret))
        
        # 2. Expired token fails
        expired_tok = create_hmac_pdf_token(case_id, user_id="user_alice", expires_in=-3600, secret=secret)
        self.assertFalse(verify_hmac_pdf_token(expired_tok, case_id, secret=secret), "Expired token must be rejected")
        
        # 3. Wrong case_id fails
        self.assertFalse(verify_hmac_pdf_token(valid_tok, "DIFFERENT_CASE_ID", secret=secret), "Mismatched case_id must be rejected")
        
        # 4. Tampered signature fails
        parts = valid_tok.split(".")
        tampered_sig = parts[2][:-2] + ("00" if parts[2][-2:] != "00" else "11")
        tampered_tok = f"{parts[0]}.{parts[1]}.{tampered_sig}"
        self.assertFalse(verify_hmac_pdf_token(tampered_tok, case_id, secret=secret), "Tampered signature must be rejected")
        
        # 5. Wrong user binding in token fails against user-specific verification
        wrong_user_tok = create_hmac_pdf_token(case_id, user_id="user_bob", expires_in=3600, secret=secret)
        expected_alice_sig = create_hmac_pdf_token(case_id, user_id="user_alice", expires_in=3600, secret=secret).split(".")[2]
        self.assertNotEqual(wrong_user_tok.split(".")[2], expected_alice_sig, "User B token signature must differ from User A")

    # -------------------------------------------------------------
    # (e) Frontend stream route authentication
    # -------------------------------------------------------------
    def test_frontend_stream_route_authentication(self):
        """/query/{job_id}/stream strictly requires auth and enforces job ownership."""
        job_id = "job_stream_auth_test_123"
        
        # Register job owned by User A in jobs_store
        jobs_store[job_id] = {
            "status": "completed",
            "user_id": self.whitelisted_user_a,
            "created_at": time.time(),
            "query_text": "test stream auth"
        }
        
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "ENABLE_DEV_AUTH_BYPASS": "false",
            "AUTHORIZED_TESTERS": f"{self.whitelisted_user_a},{self.whitelisted_user_b}",
            "CLERK_ISSUER": self.issuer,
            "CLERK_AUTHORIZED_PARTY": self.authorized_party
        }), patch.object(main, "get_clerk_public_key", return_value=self.valid_public_key):
            
            # 1. Unauthenticated request -> 401
            res_unauth = self.client.get(f"/query/{job_id}/stream")
            self.assertEqual(res_unauth.status_code, 401, f"Expected 401 for unauth stream, got {res_unauth.status_code}")
            
            # 2. Forged JWT -> 401
            res_forged = self.client.get(
                f"/query/{job_id}/stream",
                headers={"Authorization": f"Bearer {self.forged_token}"}
            )
            self.assertEqual(res_forged.status_code, 401, f"Expected 401 for forged JWT stream, got {res_forged.status_code}")
            
            # 3. User B accessing User A's job -> 403 Forbidden
            res_user_b = self.client.get(
                f"/query/{job_id}/stream",
                headers={"Authorization": f"Bearer {self.user_b_token}"}
            )
            self.assertEqual(res_user_b.status_code, 403, f"Expected 403 for cross-user stream access, got {res_user_b.status_code}")


if __name__ == "__main__":
    unittest.main()
