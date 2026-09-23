"""
Regression Tests: Precedent Currency & Overruling-Status Tracking (Phase 5 Pilot)
Verifies:
1. Bare citation 'PLD 1958 SC 533' returns precedent_status='overruled'
   and deterministic transparency banner naming Asma Jilani (PLD 1972 SC 139).
2. Semantic / Natural-Language query touching criticized holding triggers transparency banner.
3. Control Test: Direct query for superseding authority (Asma Jilani, PLD 1972 SC 139)
   returns clean result with NO precedent status warning banner.
4. Promoted Overruling Test: '2004 CLC 1186' triggers warning banner naming Liaquat Hussain v. Zil-e-Huma.
5. Promoted Overruling Test: 'PLD 1986 Pesh. 81' triggers warning banner regarding CPC O. XVII, R. 3.
6. Promoted Overruling Test: 'PLD 1998 SC (AJ&K) 26' (Fazal Karim) triggers warning banner.
7. Promoted Overruling Test: '1975 PLC 554' (Livestock Farm Labour Union) triggers warning banner.
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

    def test_promoted_family_court_overruling_2004_clc_1186(self):
        """2004 CLC 1186 must attach warning banner citing Liaquat Hussain v. Zil-e-Huma (2012 CLC 1386)."""
        annot = get_precedent_annotation("2004 CLC 1186")
        self.assertIsNotNone(annot, "Lookup failed for promoted precedent 2004 CLC 1186")
        self.assertEqual(annot.get("status"), "overruled")
        self.assertIn("2012 CLC 1386", annot.get("superseding_citation"))
        self.assertIn("Khula", annot.get("doctrinal_note"))

        banner = format_precedent_status_banner(annot)
        self.assertIn("2004 CLC 1186", banner)
        self.assertIn("2012 CLC 1386", banner)
        self.assertIn("overruled", banner.lower())

        # Test query / citations intercept
        payload = [{
            "case_id": "2004_CLC_1186",
            "citation": "2004 CLC 1186",
            "title": "2004 CLC 1186"
        }]
        query_banner = check_citations_and_query_for_precedent_status(
            query_text="dower return as consideration for khula 2004 CLC 1186",
            citations=payload
        )
        self.assertIsNotNone(query_banner)
        self.assertIn("2012 CLC 1386", query_banner)

    def test_promoted_procedural_overruling_pld_1986_pesh_81(self):
        """PLD 1986 Pesh. 81 must attach warning banner citing Zardar Khan (1997 CLC 1825)."""
        annot = get_precedent_annotation("PLD 1986 Pesh. 81")
        self.assertIsNotNone(annot, "Lookup failed for PLD 1986 Pesh. 81")
        self.assertEqual(annot.get("status"), "overruled")
        self.assertIn("1997 CLC 1825", annot.get("superseding_citation"))
        self.assertIn("Order XVII, Rule 3", annot.get("doctrinal_note"))

        banner = format_precedent_status_banner(annot)
        self.assertIn("1997 CLC 1825", banner)

    def test_promoted_ajk_apex_overruling_fazal_karim(self):
        """PLD 1998 SC (AJ&K) 26 (Fazal Karim) must attach warning banner citing 2019 MLD 846."""
        annot = get_precedent_annotation("PLD 1998 SC (AJ&K) 26")
        self.assertIsNotNone(annot, "Lookup failed for Fazal Karim v. Azad Government")
        self.assertEqual(annot.get("status"), "overruled")
        self.assertIn("Fazal Karim", annot.get("case_name"))
        self.assertIn("2019 MLD 846", annot.get("superseding_citation"))

        banner = format_precedent_status_banner(annot)
        self.assertIn("Fazal Karim", banner)
        self.assertIn("2019 MLD 846", banner)

    def test_promoted_labour_overruling_1975_plc_554(self):
        """1975 PLC 554 (Livestock Farm Labour Union) must attach warning banner citing 1976 PLC 931."""
        annot = get_precedent_annotation("1975 PLC 554")
        self.assertIsNotNone(annot, "Lookup failed for 1975 PLC 554")
        self.assertEqual(annot.get("status"), "overruled")
        self.assertIn("1976 PLC 931", annot.get("superseding_citation"))


if __name__ == "__main__":
    unittest.main()
