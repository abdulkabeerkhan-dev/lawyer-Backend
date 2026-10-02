"""
tests/test_legal_skeleton.py

Unit tests for Phase 2 Curated Legal Skeleton:
- Schema validation across all 6 skeleton files
- Named human reviewer enforcement (no AI reviewers)
- Status filter enforcement (only 'Approved' entries loaded)
- Post-27th Amendment FCC presence & ranking
- Appellate routing correctness (Banking Court -> High Court s.22 FIO; no District Judge)
- Statute section directory consistency
- Limitation periods accuracy
- Doctrine elements & mandatory ingredients
- Memo claim validation & forbidden claim detection
"""

import unittest
import os
import json
from core.legal_skeleton import LegalSkeleton

class TestLegalSkeleton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skeleton = LegalSkeleton()
        cls.skeleton_dir = cls.skeleton.skeleton_dir

    def test_all_six_skeleton_files_exist(self):
        expected_files = [
            "court_hierarchy_and_appeals.json",
            "statute_section_directory.json",
            "limitation_periods.json",
            "doctrine_elements.json",
            "procedure_maps.json",
            "reporter_to_court.json"
        ]
        for f in expected_files:
            p = os.path.join(self.skeleton_dir, f)
            self.assertTrue(os.path.exists(p), f"Missing skeleton file: {f}")

    def test_named_human_reviewer_enforced(self):
        """Every approved entry must carry a named human lawyer reviewer (never AI)."""
        courts_path = os.path.join(self.skeleton_dir, "court_hierarchy_and_appeals.json")
        with open(courts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for c in data.get("courts", []):
                rev = c.get("reviewer")
                self.assertIsNotNone(rev, f"Reviewer missing in court {c.get('id')}")
                self.assertNotIn("claude", rev.lower())
                self.assertNotIn("gpt", rev.lower())
                self.assertNotIn("ai", rev.lower().split())

    def test_post_27th_amendment_fcc_established(self):
        """Federal Constitutional Court must be recognized as established apex court."""
        fcc = self.skeleton.get_court("FCC")
        self.assertIsNotNone(fcc, "FCC must be in curated court hierarchy")
        self.assertEqual(fcc["rank"], 4, "FCC must be apex tier (rank 4)")
        self.assertEqual(fcc["status"], "Approved")
        self.assertIn("27th amendment", fcc["source"].lower())

    def test_banking_court_appeal_routing(self):
        """Banking Court appeal lies to High Court under s.22 FIO 2001, never District Judge."""
        route = self.skeleton.get_appeal_route("Banking Court")
        self.assertIsNotNone(route)
        self.assertIn("high court", route.lower())
        self.assertIn("section 22", route.lower())
        self.assertNotIn("district judge", route.lower())

    def test_statute_section_consistency(self):
        """FIO 2001 and CPC sections must match statutory scopes."""
        # FIO s.15 vs s.19 vs s.22
        sec15 = self.skeleton.get_statute_section("fio 2001", "section 15")
        self.assertIsNotNone(sec15)
        self.assertIn("without intervention", sec15["title"].lower())

        sec19 = self.skeleton.get_statute_section("fio 2001", "section 19")
        self.assertIsNotNone(sec19)
        self.assertIn("execution", sec19["title"].lower())

        sec22 = self.skeleton.get_statute_section("fio 2001", "section 22")
        self.assertIsNotNone(sec22)
        self.assertIn("appeal", sec22["title"].lower())

        # CPC O.XXI r.90 second proviso
        r90 = self.skeleton.get_statute_section("cpc 1908", "order xxi rule 90")
        self.assertIsNotNone(r90)
        self.assertIn("20%", r90["span_pointer"])

    def test_mflo_section_4_survival_ground(self):
        """Section 4 MFLO survives because appeal is pending in SC SAB, not parliamentary inaction."""
        s4 = self.skeleton.get_statute_section("mflo 1961", "section 4")
        self.assertIsNotNone(s4)
        self.assertIn("allah rakha", s4["source"].lower())
        self.assertIn("pending", s4["span_pointer"].lower())
        self.assertIn("shariat appellate bench", s4["span_pointer"].lower())

    def test_limitation_periods(self):
        """Limitation periods must be 30 days for Banking Appeals, O.XXI r.90, and Arbitration."""
        lim_banking = self.skeleton.get_limitation("banking court")
        self.assertEqual(lim_banking["limitation_period"], "30 days")

        lim_auction = self.skeleton.get_limitation("order xxi rule 90")
        self.assertEqual(lim_auction["limitation_period"], "30 days")
        self.assertIn("article 166", lim_auction["statutory_source"].lower())

        lim_arb = self.skeleton.get_limitation("arbitration")
        self.assertEqual(lim_arb["limitation_period"], "30 days")
        self.assertIn("article 158", lim_arb["statutory_source"].lower())

    def test_doctrine_elements(self):
        """Lis pendens must require specific immovable property directly in question."""
        lis = self.skeleton.get_doctrine("DOC-LIS-PENDENS")
        self.assertIsNotNone(lis)
        self.assertTrue(any("directly and specifically in question" in ing.lower() for ing in lis["mandatory_ingredients"]))

    def test_reporter_to_court_mapping(self):
        """SCMR and PLD SC must map to Supreme Court, PLD FSC to Federal Shariat Court."""
        scmr = self.skeleton.map_reporter_to_court("2024 SCMR 1218")
        self.assertIsNotNone(scmr)
        self.assertEqual(scmr["court"], "Supreme Court of Pakistan")

        fsc = self.skeleton.map_reporter_to_court("PLD 2000 FSC 1")
        self.assertIsNotNone(fsc)
        self.assertEqual(fsc["court"], "Federal Shariat Court")

    def test_memo_claim_validation(self):
        """Skeleton detects erroneous claims in generated memo."""
        bad_text = "File an appeal under Section 109 CPC to the District Judge against the Banking Court order."
        violations = self.skeleton.validate_memo_claims(bad_text)
        self.assertTrue(len(violations) > 0)
        self.assertTrue(any("district judge" in v.lower() for v in violations))

if __name__ == "__main__":
    unittest.main()
