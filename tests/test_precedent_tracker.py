"""
Regression Tests: Precedent Currency & Overruling-Status Tracking (Phase 5 Pilot)
Verifies:
1. Bare citation 'PLD 1958 SC 533' returns precedent_status='overruled'
   and deterministic transparency banner naming Asma Jilani (PLD 1972 SC 139).
2. Semantic / Natural-Language query touching criticized holding triggers transparency banner.
3. Control Test: Direct query for superseding authority (Asma Jilani, PLD 1972 SC 139)
   returns clean result with NO precedent status warning banner.
"""


import unittest
from main import extract_and_intercept_citation
from core.precedent_tracker import (
    get_precedent_annotation,
    format_precedent_status_banner,
    check_citations_and_query_for_precedent_status,
)


class TestPrecedentTracker(unittest.TestCase):

    def test_bare_citation_intercept_dosso(self):
        """PLD 1958 SC 533 (State v. Dosso) must attach overruled banner naming Asma Jilani."""
        card, _ = extract_and_intercept_citation("PLD 1958 SC 533")
        self.assertIsNotNone(card, "Direct citation intercept failed for PLD 1958 SC 533")
        self.assertEqual(card.get("precedent_status"), "overruled")
        self.assertEqual(card.get("precedent_superseded_by"), "PLD 1972 SC 139")

        banner = card.get("precedent_status_banner") or ""
        self.assertIn("State v. Dosso", banner)
        self.assertIn("Asma Jilani v. Government of Punjab", banner)
        self.assertIn("PLD 1972 SC 139", banner)
        self.assertIn("overruled", banner.lower())

    def test_semantic_query_surfacing_dosso(self):
        """When Dosso surfaces in retrieved precedent payload, warning banner must trigger."""
        payload = [{
            "case_id": "1958_PLD_533",
            "citation": "PLD 1958 SC 533",
            "title": "State v. Dosso"
        }]
        banner = check_citations_and_query_for_precedent_status(
            query_text="doctrine of revolutionary legality martial law validity kelsen",
            citations=payload
        )
        self.assertIsNotNone(banner)
        self.assertIn("State v. Dosso", banner)
        self.assertIn("Asma Jilani v. Government of Punjab", banner)

    def test_control_superseding_authority_clean(self):
        """Asma Jilani (PLD 1972 SC 139) is the superseding authority and must NEVER trigger a warning banner."""
        card, _ = extract_and_intercept_citation("PLD 1972 SC 139")
        self.assertIsNotNone(card, "Direct citation intercept failed for PLD 1972 SC 139")
        self.assertIsNone(card.get("precedent_status"))
        self.assertIsNone(card.get("precedent_status_banner"))

        banner = check_citations_and_query_for_precedent_status(
            query_text="Miss Asma Jilani v. Government of the Punjab PLD 1972 SC 139",
            citations=[{
                "case_id": "1972_PLD_139",
                "citation": "PLD 1972 SC 139",
                "title": "Miss Asma Jilani v. Government Of The Punjab"
            }]
        )
        self.assertIsNone(banner, "Warning banner must NOT fire for superseding authority")

    def test_structured_payload_metadata_without_text_alert(self):
        """Verifies find_precedent_status_annotation extracts structured fields for custom UI components."""
        from core.precedent_tracker import find_precedent_status_annotation
        annot = find_precedent_status_annotation(
            query_text="doctrine of revolutionary legality martial law",
            citations=[]
        )
        self.assertIsNotNone(annot)
        self.assertEqual(annot.get("status"), "overruled")
        self.assertEqual(annot.get("superseding_citation"), "PLD 1972 SC 139")
        self.assertEqual(annot.get("superseding_case_name"), "Asma Jilani v. Government of Punjab")
        self.assertIn("revolutionary legality", annot.get("doctrinal_note", ""))


if __name__ == "__main__":
    unittest.main()
