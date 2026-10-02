import unittest
import os
import sys
import json
import hashlib
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
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": ""}, clear=False):
            testers = get_authorized_testers()
            self.assertEqual(testers, set(), "Default whitelist must be empty set")

            mock_credentials = MagicMock()
            token = jwt.encode({"sub": "some_user"}, "secret_key_at_least_32_bytes_long_12345", algorithm="HS256")
            mock_credentials.credentials = token

            import asyncio
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

    def test_access_control_permits_authorized_tester(self):
        """A3: Verify authorized testers listed in env var are permitted."""
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "tester_alice,tester_bob"}, clear=False):
            mock_credentials = MagicMock()
            token = jwt.encode({"sub": "tester_alice"}, "secret_key_at_least_32_bytes_long_12345", algorithm="HS256")
            mock_credentials.credentials = token

            import asyncio
            user_id = asyncio.run(verify_clerk_session(credentials=mock_credentials))
            self.assertEqual(user_id, "tester_alice")

    def test_access_control_blocks_unauthorized_users(self):
        """A3: Verify unauthorized users are rejected with HTTP 403 Forbidden."""
        with patch.dict(os.environ, {"AUTHORIZED_TESTERS": "tester_alice"}, clear=False):
            mock_credentials = MagicMock()
            token = jwt.encode({"sub": "unauthorized_external_user_999"}, "secret_key_at_least_32_bytes_long_12345", algorithm="HS256")
            mock_credentials.credentials = token

            import asyncio
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(verify_clerk_session(credentials=mock_credentials))
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("restricted to authorized testers", ctx.exception.detail)

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

    def test_supabase_backup_manifest_integrity(self):
        """A4: Verify external Supabase backup exists and has 191,872 full judgments exported."""
        ext_supabase_manifest = r"C:\Users\kabeer\Documents\lawyer_backups\supabase_snapshot_phase_a\supabase_manifest_sha256.json"
        self.assertTrue(os.path.exists(ext_supabase_manifest), "External Supabase backup manifest missing")
        with open(ext_supabase_manifest, "r", encoding="utf-8") as sf:
            sup_manifest = json.load(sf)
        self.assertIn("full_judgments", sup_manifest)
        self.assertEqual(sup_manifest["full_judgments"]["row_count"], 191872)

if __name__ == "__main__":
    unittest.main()
