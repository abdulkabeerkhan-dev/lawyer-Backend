import unittest
import httpx
import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

RAILWAY_URL = os.environ.get("RAILWAY_URL", "https://web-production-53d0.up.railway.app")

class TestLiveCrosswalk(unittest.TestCase):

    def test_railway_health_check(self):
        """Test that the live Railway backend health check endpoint returns 200 OK."""
        res = httpx.get(f"{RAILWAY_URL}/health", timeout=15.0)
        self.assertEqual(res.status_code, 200)
        self.assertIn("healthy", res.text.lower())

    def test_clean_court_name_no_sindh_leak(self):
        """Test clean_court_name does not leak High Court of Sindh when text mentions Sindh."""
        from main import clean_court_name, format_neutral_citation
        
        c1 = clean_court_name("Peshawar High Court", text="The respondent moved from Sindh to Karachi")
        self.assertEqual(c1, "Peshawar High Court")
        
        c2 = clean_court_name("Lahore High Court, Bahawalpur Bench", text="Cited High Court of Sindh precedent")
        self.assertEqual(c2, "Lahore High Court")
        
        fmt = format_neutral_citation("High Court of Sindh", "Lahore High Court, Bahawalpur Bench", "2020")
        self.assertEqual(fmt, "Lahore High Court, Bahawalpur Bench (2020)")

    def test_direct_citation_lookup_no_refusal(self):
        """Test direct database lookup for 2021 SCMR 2092 in Supabase."""
        import dotenv
        dotenv.load_dotenv()
        from supabase import create_client
        
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            self.skipTest("Supabase credentials not configured in environment.")
            
        sb = create_client(url, key)
        res = sb.table("full_judgments").select("*").eq("neutral_citation", "2021 SCMR 2092").execute()
        self.assertTrue(len(res.data) > 0, "Failed to locate 2021 SCMR 2092 in Supabase full_judgments table")
        rec = res.data[0]
        self.assertEqual(rec.get("neutral_citation"), "2021 SCMR 2092")
        self.assertIn("muhammad nasir shafique", rec.get("case_title", "").lower(), "Case title mismatch for 2021 SCMR 2092")

    def test_sanitize_case_title(self):
        """Test sanitize_case_title strips raw scraper artifacts, citations, and court tags."""
        from main import sanitize_case_title
        raw_1 = "339\t2021 SCMR 2092\tMUHAMMAD NASIR SHAFIQUE VS State- Honorable Justice Sayyed Mazahar Ali Akbar Naqvi"
        self.assertEqual(sanitize_case_title(raw_1), "Muhammad Nasir Shafique v. The State")

        raw_2 = "NOOR AHMED VS THE STATE ETC., High Court of Sindh - LAHORE-HIGH-COURT"
        self.assertEqual(sanitize_case_title(raw_2), "Noor Ahmed v. The State Etc., High Court Of Sindh")

        raw_3 = "Doctor Faqir Nawaz Vs Aurangzeb etc - PESHAWAR-HIGH-COURT"
        self.assertEqual(sanitize_case_title(raw_3), "Doctor Faqir Nawaz v. Aurangzeb Etc")

    def test_sanitize_judgment_content(self):
        """Test sanitize_judgment_content strips HTML, nav headers, footers, divider lines, and irregular whitespace."""
        from scripts.ingest_all_csvs import sanitize_judgment_content

        raw = """<script>console.log("bad");</script>
<style>.header { color: red; }</style>
HOME SEARCH CASE SEARCH
Page 1 of 12
Pakistan Law Site All Rights Reserved Copyright © 2026
--------------------------------------------------
==================================================
This is paragraph 1 of the judgment text.

**************************************************
This is paragraph 2 of the judgment text.
"""
        cleaned = sanitize_judgment_content(raw)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("Page 1 of 12", cleaned)
        self.assertNotIn("--------------------------------------------------", cleaned)
        self.assertIn("This is paragraph 1 of the judgment text.", cleaned)
        self.assertIn("This is paragraph 2 of the judgment text.", cleaned)

    def test_target_source_unbound_error_fix(self):
        """Test non-Supreme Court citation query does not throw target_source UnboundLocalError."""
        from main import extract_and_intercept_citation
        # Non-SCMR citation query
        row, clean_topic = extract_and_intercept_citation("2008 PCrLJ 858")
        self.assertEqual(clean_topic, "")

    def test_2013_scmr_51_direct_lookup(self):
        """Test exact lookup for official apex precedent 2013 SCMR 51 (Mian Allah Ditta v. The State)."""
        from main import extract_and_intercept_citation
        row, clean_topic = extract_and_intercept_citation("Search database for 2013 SCMR 51")
        self.assertIsNotNone(row, "Failed to resolve exact citation 2013 SCMR 51")
        self.assertIn("allah ditta", row.get("case_title", "").lower())
        self.assertEqual(clean_topic, "")

    def test_party_title_fallback(self):
        """Test unmatched reporter citation with party name falls back to party title ilike search."""
        from main import extract_and_intercept_citation
        row, clean_topic = extract_and_intercept_citation("2013 PCrLJ 1403 Mian Allah Ditta v. The State")
        self.assertIsNotNone(row, "Party title fallback failed for Mian Allah Ditta")
        self.assertIn("allah ditta", row.get("case_title", "").lower())

    def test_unmatched_citation_clean_topic(self):
        """Test unmatched reporter citation gracefully extracts clean legal topic for vector fallback."""
        from main import extract_and_intercept_citation
        row, clean_topic = extract_and_intercept_citation("2013 PCrLJ 1403 Section 489-F PPC guarantee cheque")
        self.assertIn("Section 489-F PPC guarantee cheque", clean_topic)

if __name__ == "__main__":
    unittest.main()



