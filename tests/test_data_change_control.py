"""
tests/test_data_change_control.py

Test Suite for Data Change Control and Provenance Enforcement:
1. Verifies that all current files under data/ pass provenance verification.
2. Verifies that ungrounded/unverified records without provenance are blocked.
3. Verifies that the git pre-commit hook is active and wired to check_data_provenance.py.
"""

import os
import unittest
from scripts.check_data_provenance import verify_record_provenance, check_file, WORKSPACE_DIR

class TestDataChangeControl(unittest.TestCase):
    def test_current_data_clean(self):
        """All production data files under data/ must pass provenance validation."""
        data_dir = os.path.join(WORKSPACE_DIR, "data")
        all_errors = []
        for root, _, files in os.walk(data_dir):
            for f in files:
                if f.endswith(".json") and not f.startswith("audit_"):
                    fpath = os.path.join(root, f)
                    errs = check_file(fpath)
                    all_errors.extend(errs)
        self.assertEqual(all_errors, [], f"Data change control found violations in data/: {all_errors}")

    def test_unverified_record_rejected(self):
        """An unverified record with text but no provenance must be blocked."""
        bad_record = {
            "id": "FAKE_CASE_1",
            "text": "Some fabricated legal holding.",
            "source_url": None,
            "fetch_date": None,
            "source_type": None,
            "content_hash": None
        }
        errors = verify_record_provenance(bad_record, "test_file.json")
        self.assertTrue(len(errors) > 0, "Unverified record must trigger data change control errors.")
        self.assertTrue(any("source_url" in e for e in errors))

    def test_pre_commit_hook_installed(self):
        """Ensures .git/hooks/pre-commit exists and references check_data_provenance.py."""
        hook_path = os.path.join(WORKSPACE_DIR, ".git", "hooks", "pre-commit")
        if os.path.exists(os.path.join(WORKSPACE_DIR, ".git")):
            self.assertTrue(os.path.exists(hook_path), "Git pre-commit hook must be installed.")
            with open(hook_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("check_data_provenance.py", content)

if __name__ == "__main__":
    unittest.main()
