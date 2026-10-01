import unittest
import os
import sys

import main
from main import find_judgment_by_id_or_canonical

class TestJudgmentFallback(unittest.TestCase):
    def setUp(self):
        self._orig_sb = main.supabase
        main.supabase = None

    def tearDown(self):
        main.supabase = self._orig_sb

    def test_find_judgment_fallback_unknown_id(self):
        unknown_id = "2099_TEST_9999"
        res = find_judgment_by_id_or_canonical(unknown_id)
        self.assertIsNotNone(res)
        self.assertIn("id", res)
        self.assertEqual(res["id"], unknown_id)
        self.assertIn("full_text", res)
        self.assertTrue(len(res["full_text"]) > 0)
        self.assertIn("undergoing index synchronization", res["full_text"])

    def test_find_judgment_fallback_short_text_preservation(self):
        # Even if target_id is passed, it should always return a non-None dict with valid structure
        res = find_judgment_by_id_or_canonical("sample_short_id")
        self.assertIsInstance(res, dict)
        self.assertIn("case_title", res)
        self.assertIn("court_name", res)

if __name__ == "__main__":
    unittest.main()
