import unittest
import hashlib
from core.ingestion_verification import (
    verify_case_record_against_text,
    verify_case_record,
    verify_provenance,
    ingest_verified_record,
    compute_content_hash
)

SAMPLE_TEXT = (
    "PLD 1958 Supreme Court 533\n"
    "Present: Muhammad Munir, C.J., Shahabuddin, Cornelius and Rahman, JJ.\n"
    "THE STATE - Appellant versus DOSSO and another - Respondents\n"
    "Criminal Appeals Nos. 25, 26, 27 and 28 of 1958, decided on 14th October 1958.\n"
    "Constitution of Pakistan (1956), Art. 4 -- Laws (Continuance in Force) Order, 1958.\n"
    "The Chief Justice delivered the following judgment of the Court..."
)

class TestIngestionVerification(unittest.TestCase):
    def test_valid_record_passes(self):
        valid_record = {
            "case_title": "State v. Dosso",
            "court_name": "Supreme Court of Pakistan",
            "citation": "PLD 1958 SC 533",
            "year": 1958,
            "source_url": "https://pakistancode.gov.pk/judgments/1958_PLD_SC_533",
            "fetch_date": "2026-10-02",
            "source_type": "official",
            "content_hash": compute_content_hash(SAMPLE_TEXT),
            "full_text": SAMPLE_TEXT
        }
        is_valid, reason = verify_case_record_against_text(valid_record)
        self.assertTrue(is_valid, f"Valid record should pass: {reason}")
        ingested = ingest_verified_record(valid_record, require_provenance=True)
        self.assertEqual(ingested["case_title"], "State v. Dosso")

    def test_contradictory_title_rejected(self):
        """
        Tests that an authored or mismatched record whose title contradicts its source document text
        is deterministically rejected. (e.g. claiming Muhammad Ali v. Nasreen when document is Muhammad Iqbal v. Khair Din)
        """
        contradictory_record = {
            "case_title": "Muhammad Ali v. Mst. Nasreen",
            "court_name": "Supreme Court of Pakistan",
            "citation": "2014 SCMR 33",
            "year": 2014,
            "full_text": (
                "2014 SCMR 33\n"
                "Supreme Court of Pakistan\n"
                "Present: Nasir-ul-Mulk and Gulzar Ahmed, JJ.\n"
                "MUHAMMAD IQBAL - Petitioner versus KHAIR DIN - Respondent\n"
                "Civil Petition No. 1205 of 2013, decided on 15th November 2013.\n"
                "Specific Relief Act (I of 1877), S. 42 -- Declaratory suit regarding title..."
            )
        }
        is_valid, reason = verify_case_record_against_text(contradictory_record)
        self.assertFalse(is_valid, "Record with contradictory title must be rejected.")
        self.assertIn("Case title party token", reason)

        with self.assertRaises(ValueError) as ctx:
            ingest_verified_record(contradictory_record, require_provenance=False)
        self.assertIn("Ingestion Verification Rejected", str(ctx.exception))

    def test_contradictory_court_rejected(self):
        """
        Tests that a record claiming Supreme Court when text is High Court is rejected.
        """
        mismatched_court_record = {
            "case_title": "Rashid Ahmad v. Mst. Bilqees Begum",
            "court_name": "Supreme Court of Pakistan",
            "citation": "2006 YLR 1060",
            "year": 2006,
            "full_text": (
                "2006 YLR 1060\n"
                "Lahore High Court\n"
                "Before: Muhammad Bilal Khan, J.\n"
                "FATEH MUHAMMAD - Petitioner versus ZAHOOR UL HAQ - Respondent\n"
                "Civil Revision No. 450 of 2005, decided on 12th January 2006.\n"
            )
        }
        is_valid, reason = verify_case_record_against_text(mismatched_court_record)
        self.assertFalse(is_valid)

    def test_missing_text_rejected(self):
        missing_text_record = {
            "case_title": "Tabassum Shaheen v. Mst. Tasneem Akhtar",
            "court_name": "Supreme Court of Pakistan",
            "citation": "2012 SCMR 983",
            "year": 2012,
            "full_text": ""
        }
        is_valid, reason = verify_case_record_against_text(missing_text_record)
        self.assertFalse(is_valid)
        self.assertIn("missing", reason.lower())

        not_available_record = {
            "case_title": "Tabassum Shaheen v. Mst. Tasneem Akhtar",
            "court_name": "Supreme Court of Pakistan",
            "citation": "2012 SCMR 983",
            "year": 2012,
            "full_text": "not available"
        }
        is_valid, reason = verify_case_record_against_text(not_available_record)
        self.assertFalse(is_valid)
        self.assertIn("not available", reason.lower())

    def test_missing_provenance_rejected(self):
        rec_no_prov = {
            "case_title": "State v. Dosso",
            "court_name": "Supreme Court of Pakistan",
            "citation": "PLD 1958 SC 533",
            "year": 1958,
            "full_text": SAMPLE_TEXT
        }
        ok, msg = verify_provenance(rec_no_prov)
        self.assertFalse(ok)
        self.assertIn("Missing source_url", msg)
        with self.assertRaises(ValueError) as ctx:
            ingest_verified_record(rec_no_prov, require_provenance=True)
        self.assertIn("Provenance verification failed", str(ctx.exception))

    def test_invalid_source_type_rejected(self):
        rec_bad_type = {
            "source_url": "https://example.com/judgments/1",
            "fetch_date": "2026-10-02",
            "source_type": "scraped_blog",
            "content_hash": compute_content_hash(SAMPLE_TEXT),
            "full_text": SAMPLE_TEXT
        }
        ok, msg = verify_provenance(rec_bad_type)
        self.assertFalse(ok)
        self.assertIn("Invalid source_type", msg)

    def test_hash_mismatch_rejected(self):
        rec_bad_hash = {
            "source_url": "https://pakistancode.gov.pk/judgments/1",
            "fetch_date": "2026-10-02",
            "source_type": "official",
            "content_hash": "deadbeef12345678",
            "full_text": SAMPLE_TEXT
        }
        ok, msg = verify_provenance(rec_bad_hash)
        self.assertFalse(ok)
        self.assertIn("Content hash mismatch", msg)

    def test_headnote_preserved(self):
        headnote_record = {
            "case_title": "State v. Dosso",
            "court_name": "Supreme Court of Pakistan",
            "citation": "PLD 1958 SC 533",
            "year": 1958,
            "is_headnote": True,
            "full_text": SAMPLE_TEXT[:200]
        }
        res = verify_case_record(headnote_record, require_provenance=False)
        self.assertTrue(res["valid"])
        self.assertTrue(res["is_headnote"])
        self.assertTrue(res["retrievable"])

    def test_editorial_marker_rejected_from_retrieval(self):
        editorial_record = {
            "case_title": "State v. Dosso",
            "court_name": "Supreme Court of Pakistan",
            "citation": "PLD 1958 SC 533",
            "year": 1958,
            "full_text": "[EDITORIAL SUMMARY - UNREVIEWED] State v. Dosso judgment summary."
        }
        res = verify_case_record(editorial_record, require_provenance=False)
        self.assertFalse(res["valid"])
        self.assertFalse(res["retrievable"])
        self.assertIn("editorial_marker", res["categories"])

if __name__ == "__main__":
    unittest.main()
