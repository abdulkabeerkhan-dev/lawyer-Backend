"""
tests/test_order20_case_law_quotes.py

ORDER 2.0 — STEP 7: Case-Law Quotes Tests
"""

import unittest
from core.case_law_quotes import CaseLawQuoteVerifier, LOCAL_CASE_LAW_FIXTURES

class TestOrder20CaseLawQuotes(unittest.TestCase):
    def setUp(self):
        self.verifier = CaseLawQuoteVerifier()

    def test_exact_quote_passes(self):
        exact_quote = (
            "It is well settled that the jurisdiction of the Banking Court under the Financial Institutions "
            "(Recovery of Finances) Ordinance, 2001 is exclusive and overriding."
        )
        ok, reason = self.verifier.verify_case_quote("2023_SCMR_380", exact_quote, is_block_quote=True)
        self.assertTrue(ok)
        self.assertEqual(reason, "QUOTE_VERIFIED")

    def test_altered_quote_blocked(self):
        # One word altered: "well settled" -> "settled law"
        altered_quote = (
            "It is settled law that the jurisdiction of the Banking Court under the Financial Institutions "
            "(Recovery of Finances) Ordinance, 2001 is exclusive and overriding."
        )
        ok, reason = self.verifier.verify_case_quote("2023_SCMR_380", altered_quote, is_block_quote=True)
        self.assertFalse(ok)
        self.assertIn("QUOTE_MISMATCH", reason)

    def test_unindexed_judgment_blocked(self):
        ok, reason = self.verifier.verify_case_quote("2025_SCMR_9999", "Some judgment text", is_block_quote=True)
        self.assertFalse(ok)
        self.assertIn("JUDGMENT_NOT_IN_INDEX", reason)

    def test_shc_block_quote_blocked(self):
        shc_exact_quote = (
            "Under section 10 of the Financial Institutions Ordinance, 2001, leave to defend must disclose "
            "substantial questions of law and fact."
        )
        # Block quote must be blocked
        ok, reason = self.verifier.verify_case_quote("2021_CLD_1420", shc_exact_quote, is_block_quote=True)
        self.assertFalse(ok)
        self.assertIn("SHC_BLOCK_QUOTE_DENIED", reason)

    def test_shc_link_and_cite_allowed(self):
        shc_exact_quote = (
            "Under section 10 of the Financial Institutions Ordinance, 2001, leave to defend must disclose "
            "substantial questions of law and fact."
        )
        # Link-and-cite non-block quote passes byte-for-byte check
        ok, reason = self.verifier.verify_case_quote("2021_CLD_1420", shc_exact_quote, is_block_quote=False)
        self.assertTrue(ok)
        self.assertEqual(reason, "QUOTE_VERIFIED")

if __name__ == "__main__":
    unittest.main()
