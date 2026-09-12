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

if __name__ == "__main__":
    unittest.main()
