"""
tests/test_limitation_schedule_text.py

Deterministic Unit Tests for Limitation Act 1908 Schedule Invariants:
1. Validates that Articles 73, 80, 115, 116, 132, 181 contain the exact 3-column statutory Schedule text:
   - Description of suit / application
   - Period of limitation
   - Time from which period begins to run
2. Validates that Article 182 is tagged as historical / omitted by Law Reforms Ordinance, 1972 (12 of 1972).
3. Validates that Article 64A is tagged as disputed pending official gazette proof.
"""

import os
import sys
import json
import unittest

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

LIMITATION_FILE = os.path.join(WORKSPACE_DIR, "data", "unified_statutes", "LIMITATION_1908.json")

class TestLimitationScheduleText(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(LIMITATION_FILE, "r", encoding="utf-8") as f:
            cls.records = json.load(f)
        cls.articles_by_num = {}
        for r in cls.records:
            prim = str(r.get("primary_num", "")).strip()
            cls.articles_by_num[prim] = r

    def test_article_73_promissory_note_on_demand(self):
        art = self.articles_by_num.get("73")
        self.assertIsNotNone(art, "Article 73 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("On a bill of exchange or promissory note payable on demand", text)
        self.assertIn("Three years", text)
        self.assertIn("The date of the bill or note", text)
        self.assertEqual(art.get("tier"), "ingested_unreviewed")
        self.assertEqual(art.get("source_page"), 26)

    def test_article_80_suit_on_bill_not_expressly_provided(self):
        art = self.articles_by_num.get("80")
        self.assertIsNotNone(art, "Article 80 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("Suit on a bill of exchange, promissory note or bond not herein expressly provided for", text)
        self.assertIn("Three years", text)
        self.assertIn("When the bill, note or bond becomes payable", text)
        self.assertEqual(art.get("tier"), "ingested_unreviewed")
        self.assertEqual(art.get("source_page"), 27)

    def test_article_115_breach_of_contract_unregistered(self):
        art = self.articles_by_num.get("115")
        self.assertIsNotNone(art, "Article 115 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("For compensation for the breach of any contract", text)
        self.assertIn("not in writing registered", text)
        self.assertIn("Three years", text)
        self.assertIn("When the contract is broken", text)
        self.assertEqual(art.get("tier"), "ingested_unreviewed")
        self.assertEqual(art.get("source_page"), 32)

    def test_article_116_breach_of_contract_registered(self):
        art = self.articles_by_num.get("116")
        self.assertIsNotNone(art, "Article 116 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("For compensation for the breach of a contract in writing registered", text)
        self.assertIn("Six years", text)
        self.assertEqual(art.get("tier"), "ingested_unreviewed")
        self.assertEqual(art.get("source_page"), 32)

    def test_article_132_money_charged_on_immovable_property(self):
        art = self.articles_by_num.get("132")
        self.assertIsNotNone(art, "Article 132 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("To enforce payment of money charged upon immoveable property", text)
        self.assertIn("Twelve years", text)
        self.assertIn("When the money sued for becomes due", text)
        self.assertEqual(art.get("tier"), "ingested_unreviewed")
        self.assertEqual(art.get("source_page"), 34)

    def test_article_181_residual_applications(self):
        art = self.articles_by_num.get("181")
        self.assertIsNotNone(art, "Article 181 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("Applications for which no period of limitation is provided elsewhere", text)
        self.assertIn("section 48 of the Code of Civil Procedure", text)
        self.assertIn("Three years", text)
        self.assertIn("When the right to apply accrues", text)
        self.assertEqual(art.get("tier"), "ingested_unreviewed")
        self.assertEqual(art.get("source_page"), 46)

    def test_article_182_omitted_historical_status(self):
        art = self.articles_by_num.get("182")
        self.assertIsNotNone(art, "Article 182 must be present in LIMITATION_1908.json")
        text = art.get("text", "")
        self.assertIn("omitted by the Law Reforms Ordinance, 1972", text)
        self.assertIn("12 of 1972", text)
        self.assertIn("title_only", art.get("tier"))
        self.assertEqual(art.get("status"), "repealed_or_omitted")

    def test_article_64a_disputed_status(self):
        art = self.articles_by_num.get("64A")
        self.assertIsNotNone(art, "Article 64A must be present in LIMITATION_1908.json")
        self.assertEqual(art.get("tier"), "disputed", "Article 64A must be tagged as disputed")
        self.assertEqual(art.get("verification_status"), "disputed")


if __name__ == "__main__":
    unittest.main()
