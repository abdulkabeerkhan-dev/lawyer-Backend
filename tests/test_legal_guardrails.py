import unittest
import sys
import os

# Add parent directory to path so core can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.legal_guardrails import lint_legal_output, SYSTEM_LEGAL_DIRECTIVE

class TestLegalGuardrails(unittest.TestCase):

    def test_lint_legal_output_catches_hallucinations(self):
        """
        Test 1: Validate that lint_legal_output correctly catches:
        - 12-year limitation hallucination for specific performance
        - Foreign statutes (Indian Evidence Act, IPC)
        - Non-existent Section 271 CPC
        - Forum mismatch (High Court of Balochistan for Lahore query)
        """
        bad_output = """
        Suit for Specific Performance of Agreement to Sell regarding plot in DHA Lahore.
        Limitation: Governed by Article 109 under a 12 years limitation period.
        Under Section 114 Indian Evidence Act and Section 228 IPC, the defendant is liable.
        Enforcement must be filed under Section 271 CPC.
        Maintainable Forum: Constitutional Writ before High Court of Balochistan.
        """
        query_context = "Agreement to sell plot in DHA Lahore specific performance"
        
        errors = lint_legal_output(bad_output, query_context=query_context)
        
        self.assertTrue(any("12 years limitation" in e for e in errors), "Failed to detect 12 years limitation for specific performance")
        self.assertTrue(any("Article 109" in e for e in errors), "Failed to detect Article 109 misuse for specific performance")
        self.assertTrue(any("Indian Evidence Act" in e for e in errors), "Failed to detect Indian Evidence Act citation")
        self.assertTrue(any("IPC" in e for e in errors), "Failed to detect IPC citation")
        self.assertTrue(any("Section 271 CPC" in e for e in errors), "Failed to detect phantom Section 271 CPC")
        self.assertTrue(any("High Court of Balochistan" in e for e in errors), "Failed to detect Balochistan forum mismatch for Lahore query")

    def test_clean_specific_performance_response_dha_lahore(self):
        """
        Test 2: Mock a specific performance query for DHA Lahore and assert that
        formatted response complies with guardrails:
        - Mentions Article 113, 3 years, Lahore High Court
        - Does NOT mention Article 109 (12 years) or Balochistan
        """
        valid_response = """
        ### I. EXECUTIVE SUMMARY & LEGAL OPINION
        Suit for Specific Performance of an Agreement to Sell concerning property in DHA Lahore lies under Section 12 of the Specific Relief Act 1877.
        Limitation is strictly THREE (3) YEARS under Article 113 of the Limitation Act 1908.
        The competent forum for civil remedy is the Senior Civil Judge, Lahore, subject to appellate jurisdiction of the Lahore High Court.
        Evidence must be proved in accordance with Article 79 of the Qanun-e-Shahadat Order 1984 (QSO 1984).
        """
        query_context = "Suit for specific performance of agreement to sell for DHA Lahore plot"
        
        errors = lint_legal_output(valid_response, query_context=query_context)
        self.assertEqual(len(errors), 0, f"Valid output triggered unexpected lint errors: {errors}")
        
        self.assertIn("Article 113", valid_response)
        self.assertIn("THREE (3) YEARS", valid_response)
        self.assertIn("Lahore High Court", valid_response)
        self.assertNotIn("Article 109", valid_response)
        self.assertNotIn("12 years", valid_response)
        self.assertNotIn("Balochistan", valid_response)

if __name__ == '__main__':
    unittest.main()
