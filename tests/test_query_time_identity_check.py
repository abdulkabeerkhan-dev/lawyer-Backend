import unittest
import os
import json
import logging
from core.ingestion_verification import (
    verify_query_time_identity,
    filter_retrieved_records_for_model
)

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "query_time_identity_fixtures.json")

MISMATCH_CIDS = [
    '1992_PLD_LAH_11',   # Dev sample
    '1999_PLC(CS)_265',  # Dev sample
    '1989_SCMR_864',     # Dev sample
    '2002_PLD_322',      # Val sample
    '1999_PLC(CS)_177',  # Val sample
    '1987_SCMR_1324',    # Val sample
    '1986_SCMR_166'      # Val sample
]


class TestQueryTimeIdentityCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = {}
        if os.path.exists(FIXTURES_PATH):
            with open(FIXTURES_PATH, 'r', encoding='utf-8') as f:
                cls.records = json.load(f)

    def test_valid_record_passes(self):
        valid_rec = {
            "case_id": "2019_SCMR_984",
            "case_title": "Muhammad Akram v. The State",
            "full_text": "2019 S C M R 984\nPresent: Asif Saeed Khan Khosa, C.J.\nMUHAMMAD AKRAM---Petitioner versus THE STATE---Respondent\nCriminal Petition No. 123 of 2019"
        }
        passed, reason = verify_query_time_identity(valid_rec)
        self.assertTrue(passed, f"Expected valid record to pass, got: {reason}")

    def test_dev_mismatch_1992_pld_lah_11_excluded(self):
        rec = self.records.get('1992_PLD_LAH_11')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("contradicts text header parties", reason)

    def test_dev_mismatch_1999_plc_cs_265_excluded(self):
        rec = self.records.get('1999_PLC(CS)_265')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("contradicts text header parties", reason)

    def test_dev_mismatch_1989_scmr_864_excluded(self):
        rec = self.records.get('1989_SCMR_864')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("contradicts text header parties", reason)

    def test_val_mismatch_2002_pld_322_excluded(self):
        rec = self.records.get('2002_PLD_322')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertTrue("portal chrome" in reason.lower() or "contradicts text header parties" in reason.lower())

    def test_val_mismatch_1999_plc_cs_177_excluded(self):
        rec = self.records.get('1999_PLC(CS)_177')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("contradicts text header parties", reason)

    def test_val_mismatch_1987_scmr_1324_excluded(self):
        rec = self.records.get('1987_SCMR_1324')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("contradicts text header parties", reason)

    def test_val_mismatch_1986_scmr_166_excluded(self):
        rec = self.records.get('1986_SCMR_166')
        if not rec:
            self.skipTest("Corpus snapshot not found")
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("contradicts text header parties", reason)

    def test_filter_retrieved_records_excludes_all_mismatches_and_logs(self):
        if not self.records:
            self.skipTest("Corpus snapshot not found")
            
        valid_rec = {
            "case_id": "2019_SCMR_984",
            "case_title": "Muhammad Akram v. The State",
            "full_text": "2019 S C M R 984\nPresent: Asif Saeed Khan Khosa, C.J.\nMUHAMMAD AKRAM---Petitioner versus THE STATE---Respondent\nCriminal Petition No. 123 of 2019"
        }
        
        test_batch = [valid_rec] + [self.records[cid] for cid in MISMATCH_CIDS if cid in self.records]
        
        with self.assertLogs("query_time_identity_guardrail", level="WARNING") as cm:
            filtered = filter_retrieved_records_for_model(test_batch)
            
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["case_id"], "2019_SCMR_984")
        self.assertEqual(len(cm.output), len(MISMATCH_CIDS))
        for cid in MISMATCH_CIDS:
            self.assertTrue(any(cid in log_msg for log_msg in cm.output), f"Log for {cid} not found in output")

    def test_placeholder_title_resolved_from_text(self):
        rec = {
            "case_id": "1968_SCMR_358",
            "case_title": "Case #358 (1968 SCMR 646)",
            "full_text": "CITATION: 1968 SCMR 646\nTITLE: Case #358 (1968 SCMR 646)\nCOURT: Supreme Court of Pakistan\nHEADNOTES:\n1968 S C M R 1269\nPresent : Fazle-Akbar, C. J. and Sajjad Ahmad, J\nMUHAMMAD BAKHSH AND 3 OTHERS --Petitioners\nversus\nTHE STATE-Respondent"
        }
        passed, reason = verify_query_time_identity(rec)
        self.assertTrue(passed)
        self.assertEqual(rec.get("title_source"), "text")
        self.assertIn("MUHAMMAD BAKHSH", rec.get("resolved_title", ""))

    def test_login_wall_record_excluded(self):
        rec = {
            "case_id": "1987_MLD_1178",
            "case_title": "ABDUL SATTAR v. THE STATE",
            "full_text": "CITATION: 1987 MLD 3179\nTITLE: ABDUL SATTAR v. THE STATE\nHome\nAbout Us\nServices\nSubscription Options\nContact Us\nLOGIN\nI Agree with the Terms and Conditions of Acceptable Use"
        }
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
        self.assertIn("Login-wall", reason)

    def test_scraper_mismatch_1994_mld_424_excluded(self):
        rec = {
            "case_id": "1994_MLD_424",
            "case_title": "MESSRS QURESHI VEGETABLE GHEE MILLS VS DEPUTY COLLECTOR",
            "full_text": "1994 M L D 424\n[Election Tribunal Punjab]\nBefore Sardar Muhammad Dogar, Raja Afrasiab Khan and Muhammad Arif, JJ\nCh. MUHAMMAD ASLAM KAIRA---Appellant\nversus\nRETURNING OFFICER, PP-96, GUJRAT-6---Respondent\nElection Appeal No. 4 of 1993, decided on 8th September, 1993."
        }
        passed, reason = verify_query_time_identity(rec)
        self.assertFalse(passed)
    def test_page_number_never_inferred_from_case_id(self):
        from core.ingestion_verification import verify_case_record
        rec = {
            "case_id": "1991_PLD_LAH_10",
            "citation": None,
            "neutral_citation": None,
            "source_url": "https://example.com/test",
            "source_type": "official",
            "fetch_date": "2026-01-01",
            "content_hash": "dummy",
            "full_text": "P L D 1991 Lahore 33\nBefore Khalil-ur-Rehman Khan, J\nRAUF AHMAD v. SECRETARY"
        }
        res = verify_case_record(rec, require_provenance=False)
        # Verify that '10' from case_id was not parsed as a citation requirement
        self.assertNotIn("page '10'", str(res.get("mismatches", [])))
        self.assertNotIn("citation", res.get("categories", []))


if __name__ == '__main__':
    unittest.main()
