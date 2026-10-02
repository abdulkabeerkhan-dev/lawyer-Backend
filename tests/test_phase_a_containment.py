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

    def test_access_control_authorized_testers(self):
        """A3: Verify authorized testers are permitted."""
        testers = get_authorized_testers()
        self.assertIn("mock_clerk_user_id_dev_run", testers)
        self.assertIn("eval_harness", testers)
        self.assertIn("user_3FMZUe1gD9gfJd1VxHxm7BwZsGk", testers)

    def test_access_control_blocks_unauthorized_users(self):
        """A3: Verify unauthorized users are rejected with HTTP 403 Forbidden."""
        mock_credentials = MagicMock()
        # 32+ byte secret key to avoid InsecureKeyLengthWarning
        secret_key = "a_very_secure_secret_key_at_least_32_bytes_long!"
        token = jwt.encode({"sub": "unauthorized_external_user_999"}, secret_key, algorithm="HS256")
        mock_credentials.credentials = token

        import asyncio
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(verify_clerk_session(credentials=mock_credentials))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("restricted to authorized testers", ctx.exception.detail)

    def test_snapshot_backup_integrity(self):
        """A4: Verify snapshot backup exists, has manifest, and hashes match."""
        snapshot_dir = os.path.join(WORKSPACE_DIR, "backups", "snapshot_phase_a_pre_remediation")
        manifest_path = os.path.join(snapshot_dir, "manifest_sha256.json")
        self.assertTrue(os.path.exists(snapshot_dir), "Snapshot directory does not exist")
        self.assertTrue(os.path.exists(manifest_path), "Snapshot manifest does not exist")

        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)

        self.assertGreaterEqual(len(manifest), 50, "Snapshot manifest must contain at least 50 backed-up files")
        # Check hash of sample files
        for rel_key in ["bm25_index.pkl", "data/curated_historical_cases.json"]:
            if rel_key in manifest:
                snap_file = os.path.join(snapshot_dir, rel_key.replace("/", os.sep))
                self.assertTrue(os.path.exists(snap_file), f"Backed-up file {snap_file} missing")
                with open(snap_file, "rb") as bf:
                    calc_h = hashlib.sha256(bf.read()).hexdigest()
                self.assertEqual(calc_h, manifest[rel_key]["sha256"])

if __name__ == "__main__":
    unittest.main()
