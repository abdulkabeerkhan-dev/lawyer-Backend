"""
tests/test_legal_skeleton.py

Unit tests for Curated Legal Skeleton (Phase 2):
1. Verifies all 6 skeleton files exist.
2. Enforces that any Approved entry must have a valid human reviewer (never AI).
3. Enforces that no reviewer string includes professional credentials unless manually authorized.
4. Enforces that Unreviewed entries are strictly ignored as legal authority.
5. Verifies approved entry loading and accessor methods using valid mock data.
6. Verifies statute section lookup on approved data.
7. Verifies limitation period lookup on approved data.
8. Verifies doctrine elements lookup on approved data.
9. Verifies reporter to court mapping on approved data.
10. Verifies Rule 28 structured claim validation (no audited phrase patterns).
"""

import unittest
import os
import json
import tempfile
import shutil
from core.legal_skeleton import (
    LegalSkeleton,
    check_human_reviewer_credentials,
    AI_REVIEWER_NAMES,
    DISALLOWED_CREDENTIAL_TERMS
)

class TestLegalSkeleton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skeleton = LegalSkeleton()
        cls.skeleton_dir = cls.skeleton.skeleton_dir

    def _get_all_entries(self):
        entries = []
        for fname in os.listdir(self.skeleton_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.skeleton_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "courts" in data:
                        entries.extend(data["courts"])
                    elif "statutes" in data:
                        for s in data["statutes"]:
                            entries.extend(s.get("sections", []))
                    elif "entries" in data:
                        entries.extend(data["entries"])
                    elif "doctrines" in data:
                        entries.extend(data["doctrines"])
                    elif "procedures" in data:
                        entries.extend(data["procedures"])
                    elif "reporters" in data:
                        entries.extend(data["reporters"])
        return entries

    def test_1_all_six_skeleton_files_exist(self):
        """All 6 core skeleton schema files must exist in data/legal_skeleton/."""
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

    def test_2_approved_entries_require_valid_human_reviewer_and_no_ai(self):
        """Any entry marked Approved must carry a named human reviewer (never AI)."""
        entries = self._get_all_entries()
        for e in entries:
            if e.get("status") == "Approved":
                rev = e.get("reviewer")
                self.assertIsNotNone(rev, f"Approved entry {e.get('id')} lacks reviewer")
                self.assertTrue(
                    check_human_reviewer_credentials(rev),
                    f"Approved entry {e.get('id')} has invalid human reviewer: {rev}"
                )

        # Direct unit checks on check_human_reviewer_credentials
        self.assertFalse(check_human_reviewer_credentials(None))
        self.assertFalse(check_human_reviewer_credentials(""))
        self.assertFalse(check_human_reviewer_credentials("Claude 3.5 Sonnet"))
        self.assertFalse(check_human_reviewer_credentials("GPT-4o"))
        self.assertFalse(check_human_reviewer_credentials("AI Assistant"))
        self.assertTrue(check_human_reviewer_credentials("Tariq Mahmood"))

    def test_3_no_reviewer_string_includes_professional_credentials(self):
        """Reviewer strings must not contain professional credentials unless manually authorized."""
        entries = self._get_all_entries()
        for e in entries:
            rev = e.get("reviewer")
            if rev:
                rev_lower = rev.lower()
                for cred in DISALLOWED_CREDENTIAL_TERMS:
                    self.assertNotIn(
                        cred, rev_lower,
                        f"Entry {e.get('id')} contains unauthorized professional credential '{cred}': {rev}"
                    )

        # Direct rejection check for credentialed strings
        self.assertFalse(check_human_reviewer_credentials("Kabeer (Barrister-at-Law, Lincoln's Inn)"))
        self.assertFalse(check_human_reviewer_credentials("Ahmed Khan, Advocate High Court"))
        self.assertFalse(check_human_reviewer_credentials("John Doe, LL.B"))

    def test_4_unreviewed_entries_ignored_as_authority(self):
        """Unreviewed skeleton entries must be completely ignored as legal authority."""
        entries = self._get_all_entries()
        self.assertTrue(len(entries) > 0, "Skeleton directory should have entries")
        self.assertTrue(all(e.get("status") == "Unreviewed" for e in entries), "All entries must currently be Unreviewed")
        
        # When all entries are Unreviewed, skeleton must have 0 authority loaded
        self.assertFalse(self.skeleton.has_authority(), "Unreviewed skeleton must not have authoritative records loaded")
        self.assertIsNone(self.skeleton.get_court("Supreme Court of Pakistan"))
        self.assertIsNone(self.skeleton.get_appeal_route("Banking Court"))
        self.assertIsNone(self.skeleton.get_limitation("banking court"))

    def test_5_approved_entry_loading_with_mock(self):
        """Approved entries with valid human reviewers are loaded correctly into authority maps."""
        mock_dir = tempfile.mkdtemp()
        try:
            courts_data = {
                "courts": [
                    {
                        "id": "COURT-BC",
                        "name": "Banking Court",
                        "abbreviations": ["BC"],
                        "rank": 2,
                        "appeal_route_to": "High Court (Section 22 FIO 2001)",
                        "source": "FIO 2001 s.22",
                        "reviewer": "Tariq Mahmood",
                        "status": "Approved"
                    },
                    {
                        "id": "COURT-DRAFT",
                        "name": "Draft Court",
                        "abbreviations": [],
                        "rank": 1,
                        "appeal_route_to": "District Judge",
                        "source": "Draft",
                        "reviewer": None,
                        "status": "Unreviewed"
                    }
                ]
            }
            with open(os.path.join(mock_dir, "court_hierarchy_and_appeals.json"), "w", encoding="utf-8") as f:
                json.dump(courts_data, f)

            mock_skeleton = LegalSkeleton(skeleton_dir=mock_dir)
            self.assertTrue(mock_skeleton.has_authority())
            bc = mock_skeleton.get_court("Banking Court")
            self.assertIsNotNone(bc)
            self.assertEqual(bc["rank"], 2)
            self.assertEqual(mock_skeleton.get_appeal_route("Banking Court"), "High Court (Section 22 FIO 2001)")
            
            # Draft / unreviewed entry must NOT be loaded
            self.assertIsNone(mock_skeleton.get_court("Draft Court"))
        finally:
            shutil.rmtree(mock_dir)

    def test_6_statute_section_lookup_with_approved_mock(self):
        """Statute sections with Approved status are indexed by statute and section."""
        mock_dir = tempfile.mkdtemp()
        try:
            statutes_data = {
                "statutes": [
                    {
                        "statute_name": "Financial Institutions (Recovery of Finances) Ordinance 2001",
                        "short_name": "FIO 2001",
                        "sections": [
                            {
                                "section": "Section 22",
                                "title": "Appeal to High Court",
                                "source": "FIO 2001 s.22",
                                "reviewer": "Tariq Mahmood",
                                "status": "Approved"
                            },
                            {
                                "section": "Section 99",
                                "title": "Unreviewed Section",
                                "source": "Draft",
                                "reviewer": None,
                                "status": "Unreviewed"
                            }
                        ]
                    }
                ]
            }
            with open(os.path.join(mock_dir, "statute_section_directory.json"), "w", encoding="utf-8") as f:
                json.dump(statutes_data, f)

            mock_skeleton = LegalSkeleton(skeleton_dir=mock_dir)
            sec22 = mock_skeleton.get_statute_section("fio 2001", "section 22")
            self.assertIsNotNone(sec22)
            self.assertEqual(sec22["title"], "Appeal to High Court")
            self.assertIsNone(mock_skeleton.get_statute_section("fio 2001", "section 99"))
        finally:
            shutil.rmtree(mock_dir)

    def test_7_limitation_lookup_with_approved_mock(self):
        """Limitation periods with Approved status are queried by proceeding keyword."""
        mock_dir = tempfile.mkdtemp()
        try:
            lim_data = {
                "entries": [
                    {
                        "id": "LIM-FIO-APP",
                        "proceeding": "Banking Court Appeal under Section 22 FIO 2001",
                        "limitation_period": "30 days",
                        "statutory_source": "FIO 2001 s.22(1)",
                        "reviewer": "Tariq Mahmood",
                        "status": "Approved"
                    }
                ]
            }
            with open(os.path.join(mock_dir, "limitation_periods.json"), "w", encoding="utf-8") as f:
                json.dump(lim_data, f)

            mock_skeleton = LegalSkeleton(skeleton_dir=mock_dir)
            lim = mock_skeleton.get_limitation("banking court")
            self.assertIsNotNone(lim)
            self.assertEqual(lim["limitation_period"], "30 days")
        finally:
            shutil.rmtree(mock_dir)

    def test_8_doctrine_lookup_with_approved_mock(self):
        """Doctrine elements with Approved status are accessible with mandatory ingredients."""
        mock_dir = tempfile.mkdtemp()
        try:
            doc_data = {
                "doctrines": [
                    {
                        "id": "DOC-LIS-PENDENS",
                        "name": "Lis Pendens",
                        "mandatory_ingredients": ["Specific immovable property directly and specifically in question"],
                        "reviewer": "Tariq Mahmood",
                        "status": "Approved"
                    }
                ]
            }
            with open(os.path.join(mock_dir, "doctrine_elements.json"), "w", encoding="utf-8") as f:
                json.dump(doc_data, f)

            mock_skeleton = LegalSkeleton(skeleton_dir=mock_dir)
            doc = mock_skeleton.get_doctrine("DOC-LIS-PENDENS")
            self.assertIsNotNone(doc)
            self.assertIn("directly and specifically in question", doc["mandatory_ingredients"][0])
        finally:
            shutil.rmtree(mock_dir)

    def test_9_reporter_mapping_with_approved_mock(self):
        """Approved reporter entries map citation strings to correct courts."""
        mock_dir = tempfile.mkdtemp()
        try:
            rep_data = {
                "reporters": [
                    {
                        "prefix": "SCMR",
                        "court": "Supreme Court of Pakistan",
                        "tier": 4,
                        "reviewer": "Tariq Mahmood",
                        "status": "Approved"
                    }
                ]
            }
            with open(os.path.join(mock_dir, "reporter_to_court.json"), "w", encoding="utf-8") as f:
                json.dump(rep_data, f)

            mock_skeleton = LegalSkeleton(skeleton_dir=mock_dir)
            rep = mock_skeleton.map_reporter_to_court("2024 SCMR 1218")
            self.assertIsNotNone(rep)
            self.assertEqual(rep["court"], "Supreme Court of Pakistan")
        finally:
            shutil.rmtree(mock_dir)

    def test_10_rule_28_structured_claims_validation(self):
        """Rule 28 structured claims validator detects forum & limitation mismatches without phrase copies."""
        # Unreviewed skeleton must produce 0 violations (no authority to assert)
        unreviewed_violations = self.skeleton.validate_structured_claims(
            "Forum: District Judge\nLimitation: 90 days\nBanking Court execution."
        )
        self.assertEqual(len(unreviewed_violations), 0)

        # Mock skeleton with Approved entries validates structured claims
        mock_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(mock_dir, "court_hierarchy_and_appeals.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "courts": [{
                        "id": "COURT-BC",
                        "name": "Banking Court",
                        "rank": 2,
                        "appeal_route_to": "High Court (Section 22 FIO 2001)",
                        "source": "FIO s.22",
                        "reviewer": "Tariq Mahmood",
                        "status": "Approved"
                    }]
                }, f)
            with open(os.path.join(mock_dir, "limitation_periods.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "entries": [{
                        "id": "LIM-BC",
                        "proceeding": "banking court",
                        "limitation_period": "30 days",
                        "reviewer": "Tariq Mahmood",
                        "status": "Approved"
                    }]
                }, f)

            mock_skeleton = LegalSkeleton(skeleton_dir=mock_dir)
            bad_memo = "Originating Forum: Banking Court\nAppellate Forum: District Judge\nLimitation: 90 days"
            violations = mock_skeleton.validate_structured_claims(bad_memo)
            self.assertTrue(len(violations) >= 2)
            self.assertTrue(any("District Judge" in v for v in violations))
            self.assertTrue(any("90 days" in v for v in violations))

            good_memo = "Originating Forum: Banking Court\nAppellate Forum: High Court (Section 22 FIO 2001)\nLimitation: 30 days"
            clean_violations = mock_skeleton.validate_structured_claims(good_memo)
            self.assertEqual(len(clean_violations), 0)
        finally:
            shutil.rmtree(mock_dir)

if __name__ == "__main__":
    unittest.main()
