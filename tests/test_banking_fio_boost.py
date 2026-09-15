import unittest
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import boost_banking_fio_precedents

class TestBankingFIOBoost(unittest.TestCase):
    def test_boost_banking_fio_precedents(self):
        query = "Leave to defend under Section 10 Financial Institutions Ordinance 2001 markup calculation"
        hits = [
            {
                "score": 0.50,
                "metadata": {
                    "case_title": "Generic Civil Case v. State",
                    "text": "General civil procedure discussion under CPC."
                }
            },
            {
                "score": 0.55,
                "metadata": {
                    "case_title": "Aftab Saleem Choudhary v. Soneri Bank",
                    "holding": "Leave to defend under Section 10 Financial Institutions Ordinance 2001",
                    "text": "Dispute regarding markup calculation and interest calculation by banking court."
                }
            }
        ]
        
        boosted = boost_banking_fio_precedents(query, hits)
        self.assertEqual(len(boosted), 2)
        # The Soneri Bank FIO case with Section 10 and markup should be boosted to first position
        self.assertEqual(boosted[0]["metadata"]["case_title"], "Aftab Saleem Choudhary v. Soneri Bank")

    def test_non_banking_query_unmodified(self):
        query = "Khula and dower decree family suit"
        hits = [
            {"score": 0.80, "metadata": {"case_title": "Family Case 1"}},
            {"score": 0.70, "metadata": {"case_title": "Family Case 2"}}
        ]
        res = boost_banking_fio_precedents(query, hits)
        self.assertEqual(res, hits)

if __name__ == "__main__":
    unittest.main()
