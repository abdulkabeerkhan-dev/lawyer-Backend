# tests/test_retrieval_trust_gate.py
"""
Runtime Retrieval Trust Gate Tests
Verifies fail-closed enforcement: only explicitly trusted records reach LLM prompt generation context.
Quarantined, rejected, restricted, and UNCLASSIFIED/MISSING status records are strictly excluded.
"""

import unittest
from core.ingestion_verification import (
    verify_retrieval_trust_record,
    filter_trusted_retrieval_records
)


class TestRetrievalTrustGate(unittest.TestCase):

    def test_quarantined_record_blocked_even_if_rank_1(self):
        """A quarantined displaced-text case ranked #1 must be blocked from LLM context."""
        cand_quarantined = {
            "case_id": "2005_PLD_QTA_1",
            "title": "Muhammad Aslam v. State",
            "citation": "PLD 2005 Quetta 1",
            "retrieval_status": "quarantined",
            "verification_reason": "Displaced case identity: title contradicts header parties",
            "full_text": "2005 CLC 1241 Farooq Textile Mills v. HBL...",
            "score": 0.98  # Top ranked by vector similarity
        }
        passed, reason = verify_retrieval_trust_record(cand_quarantined)
        self.assertFalse(passed, "Quarantined record must be blocked from retrieval")
        self.assertIn("Excluded by trust gate", reason)
        self.assertIn("quarantined", reason)

    def test_rejected_record_blocked(self):
        """A rejected listing table or portal chrome must be blocked."""
        cand_rejected = {
            "case_id": "2024_PLD_1_INDEX",
            "title": "Volume Index",
            "citation": "2024 PLD 1",
            "retrieval_status": "rejected",
            "verification_reason": "Scraped volume index listing table",
            "full_text": "# Citation Title Court Read...",
            "score": 0.95
        }
        passed, reason = verify_retrieval_trust_record(cand_rejected)
        self.assertFalse(passed, "Rejected record must be blocked from retrieval")
        self.assertIn("rejected", reason)

    def test_restricted_record_blocked_from_default_generation(self):
        """A restricted record (e.g. contradictory title) must be blocked from default generation."""
        cand_restricted = {
            "case_id": "2021_SCMR_500",
            "title": "Wrong Title Ltd v. Federation",
            "citation": "2021 SCMR 500",
            "retrieval_status": "restricted",
            "verification_reason": "Contradictory title on verified judgment text",
            "full_text": "2021 SCMR 500 Muhammad Arif v. Mst. Bashiran Bibi...",
            "score": 0.92
        }
        passed, reason = verify_retrieval_trust_record(cand_restricted)
        self.assertFalse(passed, "Restricted record must not enter default generation context")
        self.assertIn("restricted", reason)

    def test_unclassified_missing_status_fails_closed(self):
        """A record with missing/NULL retrieval_status must fail closed in production runtime."""
        cand_unclassified = {
            "case_id": "1999_SCMR_100",
            "title": "Some Petitioner v. State",
            "citation": "1999 SCMR 100",
            # retrieval_status is omitted / None
            "full_text": "1999 SCMR 100 Authentic judgment text...",
            "score": 0.95
        }
        passed, reason = verify_retrieval_trust_record(cand_unclassified, allow_dynamic_fallback=False)
        self.assertFalse(passed, "Missing retrieval_status must fail closed in production runtime")
        self.assertIn("FAIL-CLOSED", reason)
        self.assertIn("missing or untrusted status", reason)

    def test_offline_tooling_allows_dynamic_fallback(self):
        """Offline tooling with allow_dynamic_fallback=True can dynamically classify authentic records."""
        cand_unclassified_good = {
            "case_id": "1958_PLD_SC_533",
            "title": "State v. Dosso",
            "citation": "PLD 1958 SC 533",
            "full_text": (
                "PLD 1958 Supreme Court 533\n"
                "Present: Muhammad Munir, C.J.\n"
                "THE STATE - Appellant versus DOSSO - Respondent\n"
                "Criminal Appeal No. 25 of 1958, decided on 14th October 1958.\n"
                "The Chief Justice delivered the following judgment of the Court..."
            ),
            "score": 0.90
        }
        passed, reason = verify_retrieval_trust_record(cand_unclassified_good, allow_dynamic_fallback=True)
        self.assertTrue(passed, f"Dynamic classification for offline tooling should pass authentic case: {reason}")

    def test_trusted_record_passes(self):
        """An authentic trusted record with matching header parties passes cleanly."""
        cand_trusted = {
            "case_id": "1958_PLD_SC_533",
            "title": "State v. Dosso",
            "citation": "PLD 1958 SC 533",
            "retrieval_status": "trusted",
            "verification_reason": "Authentic judicial record",
            "full_text": (
                "PLD 1958 Supreme Court 533\n"
                "Present: Muhammad Munir, C.J.\n"
                "THE STATE - Appellant versus DOSSO - Respondent\n"
                "Criminal Appeal No. 25 of 1958, decided on 14th October 1958.\n"
                "The Chief Justice delivered the following judgment of the Court..."
            ),
            "score": 0.89
        }
        passed, reason = verify_retrieval_trust_record(cand_trusted)
        self.assertTrue(passed, f"Trusted record should pass: {reason}")

    def test_legacy_verified_record_passes(self):
        """A legacy_verified record with valid identity passes trust gate."""
        cand_legacy = {
            "case_id": "2024_SCMR_1719",
            "title": "Mian Muhammad Nawaz v. State",
            "citation": "2024 SCMR 1719",
            "retrieval_status": "legacy_verified",
            "verification_reason": "Authentic legacy authority",
            "full_text": (
                "2024 SCMR 1719 Supreme Court of Pakistan\n"
                "Present: Qazi Faez Isa, C.J.\n"
                "Mian Muhammad Nawaz - Appellant versus The State - Respondent\n"
                "Criminal Petition No. 123 of 2024 decided on 5th June 2024.\n"
                "Section 489-F PPC pre-arrest bail principles..."
            ),
            "score": 0.88
        }
        passed, reason = verify_retrieval_trust_record(cand_legacy)
        self.assertTrue(passed, f"legacy_verified record must pass trust gate: {reason}")

    def test_verified_v2_record_passes(self):
        """A modern verified_v2 record passes trust gate."""
        cand_v2 = {
            "case_id": "2023_SCMR_380",
            "title": "Tahir v. State",
            "citation": "2023 SCMR 380",
            "retrieval_status": "verified_v2",
            "verification_reason": "Canonical verified record",
            "full_text": (
                "2023 SCMR 380 Supreme Court of Pakistan\n"
                "Tahir - Appellant versus The State - Respondent\n"
                "Criminal Petition decided on 10th May 2023.\n"
                "Bail matters under section 489-F PPC..."
            ),
            "score": 0.91
        }
        passed, reason = verify_retrieval_trust_record(cand_v2)
        self.assertTrue(passed, f"verified_v2 record must pass trust gate: {reason}")

    def test_batch_filter_leaves_only_trusted_records(self):
        """Batch filtering must drop all non-trusted and unclassified candidates regardless of ranking."""
        candidates = [
            {"case_id": "c1_quarantined", "retrieval_status": "quarantined", "title": "A v. B", "full_text": "Some text", "score": 0.99},
            {"case_id": "c2_rejected", "retrieval_status": "rejected", "title": "C v. D", "full_text": "Some text", "score": 0.95},
            {"case_id": "c3_restricted", "retrieval_status": "restricted", "title": "E v. F", "full_text": "Some text", "score": 0.90},
            {"case_id": "c4_unlabeled", "title": "G v. H", "full_text": "Some text", "score": 0.88},  # No retrieval_status
            {
                "case_id": "1958_PLD_SC_533",
                "retrieval_status": "trusted",
                "title": "State v. Dosso",
                "citation": "PLD 1958 SC 533",
                "full_text": (
                    "PLD 1958 Supreme Court 533\n"
                    "Present: Muhammad Munir, C.J.\n"
                    "THE STATE - Appellant versus DOSSO - Respondent\n"
                    "Criminal Appeal No. 25 of 1958, decided on 14th October 1958.\n"
                    "The Chief Justice delivered the following judgment of the Court..."
                ),
                "score": 0.85
            },
            {
                "case_id": "2024_SCMR_1719",
                "retrieval_status": "legacy_verified",
                "title": "Mian Muhammad Nawaz v. State",
                "citation": "2024 SCMR 1719",
                "full_text": (
                    "2024 SCMR 1719 Supreme Court\n"
                    "Mian Muhammad Nawaz v. State\n"
                    "Criminal Petition 123 of 2024\n"
                    "Bail under 489-F PPC"
                ),
                "score": 0.84
            }
        ]
        filtered = filter_trusted_retrieval_records(candidates)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["case_id"], "1958_PLD_SC_533")
        self.assertEqual(filtered[1]["case_id"], "2024_SCMR_1719")


if __name__ == "__main__":
    unittest.main()

