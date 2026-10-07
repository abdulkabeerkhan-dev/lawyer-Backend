import os
import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException
from main import health_check, safe_create_anthropic_message, verify_clerk_session


class TestRemediationPass1(unittest.IsolatedAsyncioTestCase):
    def test_health_check_no_secret_disclosure(self):
        """Phase 2: Verify /health returns only non-sensitive operational information and zero secret fingerprints."""
        res = health_check()
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "ok")
        self.assertTrue(res.get("healthy"))
        self.assertIn("model", res)
        self.assertIn("version", res)
        self.assertIn("build", res)

        # Strict checks: No sensitive credentials, lengths, suffixes, or workspace IDs
        self.assertNotIn("anthropic_key_len", res)
        self.assertNotIn("anthropic_key_suffix", res)
        self.assertNotIn("workspace_id", res)
        self.assertNotIn("key", str(res).lower())
        self.assertNotIn("secret", str(res).lower())

    def test_pymupdf_fitz_dependency_functional(self):
        """Phase 6: Verify PyMuPDF fitz dependency is available and can create and read PDF in runtime."""
        import fitz
        self.assertTrue(hasattr(fitz, "open"))
        # Test document instantiation
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Pakistani Court Precedent Text Layer Test")
        pdf_bytes = doc.tobytes()
        doc.close()

        # Re-open and extract
        doc2 = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc2), 1)
        text = doc2[0].get_text()
        self.assertIn("Pakistani Court Precedent", text)
        doc2.close()

    async def test_safe_create_anthropic_message_temperature_routing(self):
        """Phase 9: Verify temperature argument is routed to extra_body rather than direct kwarg."""
        mock_client = MagicMock()
        mock_create = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="ok")]
        mock_create.return_value = mock_response
        mock_client.messages.create = mock_create

        with patch("main.async_anthropic_client", mock_client):
            await safe_create_anthropic_message(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                temperature=0.0,
                system="system prompt",
                messages=[{"role": "user", "content": "hello"}]
            )

        self.assertTrue(mock_create.called)
        called_kwargs = mock_create.call_args.kwargs

        # Must NOT be passed directly as keyword argument
        self.assertNotIn("temperature", called_kwargs)
        # Must be encapsulated in extra_body
        self.assertIn("extra_body", called_kwargs)
        self.assertEqual(called_kwargs["extra_body"].get("temperature"), 0.0)

    async def test_auth_bypass_fails_closed_without_token(self):
        """Phase 1: Verify unauthenticated requests fail closed with 401 when dev bypass is disabled."""
        with patch("main.IS_PRODUCTION", True), patch("main.DEV_AUTH_BYPASS_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                await verify_clerk_session(credentials=None)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Access Denied", ctx.exception.detail)

    async def test_auth_mock_token_rejected_in_production(self):
        """Phase 1: Verify mock dev token is strictly rejected with 401 in production."""
        mock_cred = MagicMock()
        mock_cred.credentials = "mock_clerk_user_id_dev_run"

        with patch("main.IS_PRODUCTION", True), patch("main.DEV_AUTH_BYPASS_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                await verify_clerk_session(credentials=mock_cred)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Mock dev credentials are not permitted in production", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
