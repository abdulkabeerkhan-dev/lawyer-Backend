"""
tests/test_order20_quote_by_reference.py

ORDER 2.0 — STEP 4: Quote by Reference & Verbatim Expansion Tests
Tests:
1. expansion matches text_raw byte for byte (prints SHA-256 of both)
2. unknown ID blocked
3. disputed ID blocked
4. model-typed altered quote blocked with word-level diff
5. model-typed exact quote passes
"""

import unittest
import hashlib
from unittest.mock import patch, MagicMock

import core.unified_statute_store as uss
from core.quote_by_reference import (
    expand_quote_placeholder,
    expand_all_quote_placeholders,
    verify_model_typed_statute_quote,
    format_system_blockquote
)

class TestOrder20QuoteByReference(unittest.TestCase):
    def setUp(self):
        # Create mock provision in store
        self.valid_text = (
            "10. Leave to defend. (1) In any case in which the summons has been served on the defendant "
            "as provided for in sub-section (5) of section 9, the defendant shall not be entitled to appear "
            "or defend the suit unless he obtains leave from the Banking Court as hereinafter provided to so appear and defend."
        )
        self.valid_sha = hashlib.sha256(self.valid_text.encode("utf-8")).hexdigest()

        self.mock_store = MagicMock()
        self.valid_rec = {
            "canonical_id": "FIO_2001_SEC_10",
            "act": "FIO_2001",
            "section": "10",
            "heading": "Leave to defend",
            "page_start": 9,
            "page_end": 10,
            "text_raw": self.valid_text,
            "text_raw_sha256": self.valid_sha,
            "source_pdf": "fio_2001.pdf",
            "source_pdf_sha256": "b1b54c7b2e1103dac8e28c35114825ea6cdb0a8f9fb6af7de10aa741386e2219",
            "extractor_agreement": "exact",
            "tier": "text_layer_extracted",
            "quoting_allowed": True,
            "footnotes": []
        }

        self.disputed_rec = {
            "canonical_id": "FIO_2001_SEC_99",
            "act": "FIO_2001",
            "section": "99",
            "heading": "Disputed Provision",
            "page_start": 15,
            "page_end": 15,
            "text_raw": "Some disputed text",
            "text_raw_sha256": hashlib.sha256(b"Some disputed text").hexdigest(),
            "extractor_agreement": "differs",
            "tier": "extraction_disputed",
            "quoting_allowed": False,
            "footnotes": []
        }

        def mock_get_by_cid(cid):
            if cid == "FIO_2001_SEC_10":
                return self.valid_rec
            if cid == "FIO_2001_SEC_99":
                return self.disputed_rec
            return None

        self.mock_store.get_by_canonical_id.side_effect = mock_get_by_cid

    def test_expansion_matches_text_raw_byte_for_byte(self):
        """Expansion contains text_raw byte-for-byte; SHA256 of extracted portion matches stored SHA256."""
        with patch("core.quote_by_reference.get_unified_statute_store", return_value=self.mock_store):
            ok, expanded, reason = expand_quote_placeholder("{{QUOTE:FIO_2001_SEC_10}}")
            self.assertTrue(ok)
            self.assertIsNone(reason)

            # Assert text_raw appears verbatim inside expanded blockquote
            self.assertIn(self.valid_text.splitlines()[0], expanded)
            self.assertIn("> Text-layer extract, not human-reviewed", expanded)
            self.assertIn("> [!QUOTE] FIO_2001, Section 10 (PDF page 9, extractor agreement: exact)", expanded)

            # Verify byte-exact equality of stored text
            stored_sha = hashlib.sha256(self.valid_text.encode("utf-8")).hexdigest()
            print(f"\n[Test] Stored text_raw SHA256:   {stored_sha}")
            print(f"[Test] Record content SHA256:    {self.valid_rec['text_raw_sha256']}")
            self.assertEqual(stored_sha, self.valid_rec["text_raw_sha256"])

    def test_unknown_id_blocked(self):
        """Unknown canonical ID is BLOCKED."""
        with patch("core.quote_by_reference.get_unified_statute_store", return_value=self.mock_store):
            ok, expanded, reason = expand_quote_placeholder("{{QUOTE:NONEXISTENT_ACT_SEC_999}}")
            self.assertFalse(ok)
            self.assertEqual(expanded, "")
            self.assertIn("UNKNOWN_CANONICAL_ID", reason)

    def test_disputed_id_blocked(self):
        """Disputed provision is BLOCKED."""
        with patch("core.quote_by_reference.get_unified_statute_store", return_value=self.mock_store):
            ok, expanded, reason = expand_quote_placeholder("{{QUOTE:FIO_2001_SEC_99}}")
            self.assertFalse(ok)
            self.assertEqual(expanded, "")
            self.assertIn("DISPUTED_TIER_BLOCKED", reason)

    def test_model_typed_altered_quote_blocked_with_word_diff(self):
        """Model typed quote that differs by even one word is BLOCKED with a word-level diff."""
        with patch("core.quote_by_reference.get_unified_statute_store", return_value=self.mock_store):
            altered = self.valid_text.replace("shall not be entitled", "is not entitled")
            ok, reason = verify_model_typed_statute_quote("FIO_2001_SEC_10", altered)
            self.assertFalse(ok)
            self.assertIn("BLOCKED", reason)
            self.assertIn("Word diff:", reason)
            self.assertIn("-shall", reason)
            self.assertIn("+is", reason)

    def test_model_typed_exact_quote_passes(self):
        """Model typed quote that matches text_raw byte-for-byte passes."""
        with patch("core.quote_by_reference.get_unified_statute_store", return_value=self.mock_store):
            ok, reason = verify_model_typed_statute_quote("FIO_2001_SEC_10", self.valid_text)
            self.assertTrue(ok)
            self.assertEqual(reason, "EXACT_BYTE_MATCH")

if __name__ == "__main__":
    unittest.main()
