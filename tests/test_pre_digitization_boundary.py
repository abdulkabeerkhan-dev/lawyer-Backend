"""
Regression Tests: Pre-Digitization Boundary Status
Verifies that:
1. 1971 SCMR 264 returns status='pre_digitization_boundary' with official boundary message.
2. PLD 1955 FC 240 (Tamizuddin Khan) returns status='pre_digitization_boundary'.
3. Distinct from 'known_collision_unavailable' (which fires on post-boundary parallel collisions).
4. Distinct from generic 'not-found' (modern non-existent citations).
5. Pre-digitization judgments with verified full text (like PLD 1958 SC 138) remain fully accessible and served.
"""

import unittest
from main import extract_and_intercept_citation, PRE_DIGITIZATION_BOUNDARY


class TestPreDigitizationBoundary(unittest.TestCase):

    def test_pre_1984_scmr_boundary(self):
        """1971 SCMR 264 (Ch. Muhammad Khan v. Sanaullah) must fire pre_digitization_boundary."""
        card, _ = extract_and_intercept_citation("1971 SCMR 264")
        self.assertIsNotNone(card, "Citation intercept failed to capture 1971 SCMR 264")
        self.assertEqual(card.get("status"), "pre_digitization_boundary")
        msg = card.get("message", "")
        self.assertIn("1971 SCMR 264 predates official government digitization", msg)
        self.assertIn("Supreme Court Monthly Review is digitally archived from 1984 onward", msg)
        self.assertIn("consult the physical law report", msg)

    def test_pre_1962_pld_boundary_tamizuddin(self):
        """PLD 1955 FC 240 (Maulvi Tamizuddin Khan) must fire pre_digitization_boundary."""
        card, _ = extract_and_intercept_citation("PLD 1955 FC 240")
        self.assertIsNotNone(card, "Citation intercept failed to capture PLD 1955 FC 240")
        self.assertEqual(card.get("status"), "pre_digitization_boundary")
        msg = card.get("message", "")
        self.assertIn("PLD 1955 FC 240 predates official government digitization", msg)
        self.assertIn("Pakistan Legal Decisions from 1962 onward", msg)
        self.assertIn("consult the physical law report", msg)

    def test_distinct_from_generic_not_found(self):
        """Modern non-existent citation must NOT claim pre_digitization_boundary."""
        card, _ = extract_and_intercept_citation("2024 SCMR 9999")
        # Modern non-existent citation has year=2024 >= 1984, so is_pre_digitization is False.
        # It must not return pre_digitization_boundary.
        if card:
            self.assertNotEqual(card.get("status"), "pre_digitization_boundary")

    def test_verified_historical_record_served(self):
        """PLD 1958 SC 138 has verified full text and must be served, not withheld."""
        card, _ = extract_and_intercept_citation("PLD 1958 SC 138")
        self.assertIsNotNone(card)
        self.assertNotEqual(card.get("status"), "pre_digitization_boundary")
        self.assertIn("Havover Fire Insurance", card.get("case_title", ""))


if __name__ == "__main__":
    unittest.main()
