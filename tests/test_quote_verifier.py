"""
Unit Tests for Quote Attribution Verifier
Validates fuzzy quote verification, OCR noise tolerance, cross-case misattribution correction,
and deterministic disclosure banner formatting.
"""

import unittest
from core.quote_verifier import (
    normalize_text,
    fuzzy_contains,
    extract_quotes_from_text,
    verify_quote_attribution,
    verify_text_quotes
)


class TestQuoteVerifier(unittest.TestCase):

    def setUp(self):
        self.farooq_imran_text = (
            "In Farooq Imran v. Federation of Pakistan, the Supreme Court addressed the question of civil imprisonment. "
            "The Court noted that detention in prison cannot be ordered mechanically without establishing willful default "
            "and active concealment of assets."
        )

        self.tahir_umar_text = (
            "In Tahir Umar v. State, the Court observed: 'The liberty of a citizen is a sacred trust under Article 9 "
            "of the Constitution and cannot be curtailed on mere surmises or unsubstantiated allegations of the judgment creditor.' "
            "Execution proceedings must strictly comply with Section 51 of the Code."
        )

        self.context_payload = {
            "PLD 2018 SC 400": self.farooq_imran_text,  # Farooq Imran
            "2020 SCMR 850": self.tahir_umar_text        # Tahir Umar
        }

    def test_fuzzy_contains_exact_and_ocr_noise(self):
        """Verify exact matching and OCR-noise tolerance."""
        source = "The liberty of a citizen is a sacred trust under Article 9 of the Constitution."

        # Exact
        matched, score = fuzzy_contains("liberty of a citizen is a sacred trust", source)
        self.assertTrue(matched)
        self.assertGreaterEqual(score, 0.95)

        # OCR noise (comma omitted, capitalization difference, slight typo)
        noisy_quote = "the liberty of a citizen is a sacred trust under article 9"
        matched, score = fuzzy_contains(noisy_quote, source)
        self.assertTrue(matched)
        self.assertGreaterEqual(score, 0.90)

        # Unrelated text
        matched, score = fuzzy_contains("completely fabricated judicial holding not in text", source)
        self.assertFalse(matched)
        self.assertLess(score, 0.85)

    def test_correct_attribution_verified(self):
        """Verify that a correctly attributed quote returns status verified."""
        quote = "The liberty of a citizen is a sacred trust under Article 9 of the Constitution"
        res = verify_quote_attribution(
            quote=quote,
            attributed_citation="2020 SCMR 850",
            context_payload=self.context_payload
        )
        self.assertTrue(res["is_verified"])
        self.assertEqual(res["status"], "verified")
        self.assertEqual(res["matched_citation"], "2020 SCMR 850")

    def test_cross_case_misattribution_corrected(self):
        """
        Verify the Farooq Imran / Tahir Umar pattern:
        Quote belongs to Tahir Umar (2020 SCMR 850), but the LLM attributed it to Farooq Imran (PLD 2018 SC 400).
        Verifier must detect that it is NOT in Farooq Imran, find it in Tahir Umar, and auto-correct.
        """
        quote = "The liberty of a citizen is a sacred trust under Article 9 of the Constitution and cannot be curtailed on mere surmises"
        res = verify_quote_attribution(
            quote=quote,
            attributed_citation="PLD 2018 SC 400",  # WRONG attribution
            context_payload=self.context_payload
        )
        self.assertFalse(res["is_verified"])
        self.assertEqual(res["status"], "misattributed_corrected")
        self.assertEqual(res["attributed_citation"], "PLD 2018 SC 400")
        self.assertEqual(res["matched_citation"], "2020 SCMR 850")  # Auto-corrected to Tahir Umar
        self.assertIn("Quote was attributed to 'PLD 2018 SC 400', but was verified in '2020 SCMR 850'", res["message"])

    def test_completely_unverified_quote(self):
        """Verify that a hallucinated quote not present in any context is flagged as unverified."""
        hallucinated_quote = "A debtor who fails to pay within forty-eight hours is presumed to be guilty of willful default and contempt."
        res = verify_quote_attribution(
            quote=hallucinated_quote,
            attributed_citation="PLD 2018 SC 400",
            context_payload=self.context_payload
        )
        self.assertFalse(res["is_verified"])
        self.assertEqual(res["status"], "unverified")
        self.assertIsNone(res["matched_citation"])

    def test_text_scanning_and_banner_generation(self):
        """Verify end-to-end extraction and banner formatting on response text."""
        response_text = (
            "In PLD 2018 SC 400, the Supreme Court held: "
            "\"The liberty of a citizen is a sacred trust under Article 9 of the Constitution and cannot be curtailed on mere surmises.\" "
            "Furthermore, the Court added: \"Every defaulting debtor shall suffer instant forfeiture of property without trial.\""
        )

        res = verify_text_quotes(response_text, self.context_payload)
        self.assertEqual(res["misattributed_count"], 1)
        self.assertEqual(res["unverified_count"], 1)
        self.assertIsNotNone(res["warning_banner"])
        self.assertIn("Quote Attribution Correction", res["warning_banner"])
        self.assertIn("Unverified Quotation Notice", res["warning_banner"])
        self.assertIn("2020 SCMR 850", res["warning_banner"])


if __name__ == "__main__":
    unittest.main()
