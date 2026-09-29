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

    def test_is_structural_or_title_quote_helper(self):
        """Verify helper correctly classifies short titles, colons, dashes, and long prose."""
        from core.legal_guardrails import is_structural_or_title_quote
        # <= 6 words
        self.assertTrue(is_structural_or_title_quote("Mst. Aisha Bibi v. Federation"))
        self.assertTrue(is_structural_or_title_quote("Legal Opinion on Bail"))
        # Colon suffix
        self.assertTrue(is_structural_or_title_quote("EXECUTIVE SUMMARY AND COMPREHENSIVE LEGAL ANALYSIS:"))
        # Dash suffix
        self.assertTrue(is_structural_or_title_quote("SECTION 489-F PPC BAIL PRINCIPLES —"))
        # Substantive sentence (> 6 words, no colon/dash)
        self.assertFalse(is_structural_or_title_quote("The liberty of a citizen is a sacred trust under the Constitution."))

    def test_structural_quotes_do_not_trigger_unverified_banner(self):
        """Verify response text containing quoted headings does not trigger Unverified Quotation Notice."""
        response_text = (
            "Here is the formal memorandum:\n\n"
            "\"EXECUTIVE SUMMARY & LEGAL OPINION:\"\n"
            "Under Section 489-F PPC, bail is the rule rather than the exception.\n\n"
            "\"STATUTORY & PROCEDURAL FRAMEWORK:\"\n"
            "Section 497(1) prohibitory clause does not bar bail for three-year offences.\n"
        )
        res = verify_text_quotes(response_text, self.context_payload)
        self.assertEqual(res["unverified_count"], 0)
        self.assertIsNone(res["warning_banner"])


    def test_sanitize_unverified_quotes_strips_quotes_silently(self):
        """Verify Option A: Silent Sanitization strips quotes into authoritative prose."""
        from core.quote_verifier import sanitize_unverified_quotes
        text = (
            "The High Court held: \"The petitioner has committed fraud beyond reasonable doubt.\" "
            "Additionally, the court noted ‘no remedy lies in equity’ for willful defaulters."
        )
        unverified = [
            "The petitioner has committed fraud beyond reasonable doubt.",
            "no remedy lies in equity"
        ]
        sanitized = sanitize_unverified_quotes(text, unverified)
        self.assertNotIn("\"The petitioner has committed fraud beyond reasonable doubt.\"", sanitized)
        self.assertNotIn("‘no remedy lies in equity’", sanitized)
        self.assertIn("The High Court held: The petitioner has committed fraud beyond reasonable doubt.", sanitized)
        self.assertIn("additionally, the court noted no remedy lies in equity for willful defaulters.".lower(), sanitized.lower())

    def test_verify_text_quotes_silent_sanitize_option_a(self):
        """Verify verify_text_quotes with silent_sanitize=True strips quotes and suppresses unverified banner."""
        from core.quote_verifier import verify_text_quotes
        response_text = (
            "In PLD 2018 SC 400, the Court held: "
            "\"Every defaulting debtor shall suffer instant forfeiture of property without trial.\""
        )
        res = verify_text_quotes(response_text, self.context_payload, silent_sanitize=True)
        self.assertEqual(res["unverified_count"], 1)
        # Warning banner should NOT contain Unverified Quotation Notice when silent_sanitize=True
        self.assertIsNone(res["warning_banner"])
        # Sanitized text should be clean and unquoted
        self.assertNotIn("\"Every defaulting debtor shall suffer instant forfeiture of property without trial.\"", res["sanitized_text"])
        self.assertIn("Every defaulting debtor shall suffer instant forfeiture of property without trial.", res["sanitized_text"])


if __name__ == "__main__":
    unittest.main()
