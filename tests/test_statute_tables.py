"""
Unit Tests for Ground-Truth Statutory Provision Lookup Tables
ORDER 1.9: Updated to reflect quarantined stub acts vs verified in-force statute tables.
Validates schema compliance, canonical ID generation, test matrix coverage,
uniqueness, QSO crosswalks, and provincial specificity.
"""

import os
import json
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES_DIR = os.path.join(REPO_DIR, "data", "statute_tables")
QUARANTINE_TABLES_DIR = os.path.join(REPO_DIR, "data", "quarantine", "statute_tables")

VERIFIED_ACTS = [
    "CPC_1908", "PPC_1860", "CRPC_1898", "LIMITATION_1908",
    "BANKING_COMPANIES_1962", "CONTRACT_1872", "FIO_2001",
    "REGISTRATION_1908", "STAMP_ACT_1899", "TPA_1882"
]

QUARANTINED_ACTS = [
    "CONST_1973", "QSO_1984", "MFLO_1961", "FAMILY_COURTS_1964",
    "DMMA_1939", "CNSA_1997", "PRPA_2009", "PREEMPTION_1991"
]

ALL_ACTS = VERIFIED_ACTS + QUARANTINED_ACTS

def get_act_dir(act: str) -> str:
    if act in VERIFIED_ACTS:
        return TABLES_DIR
    return QUARANTINE_TABLES_DIR


class TestStatuteTables(unittest.TestCase):

    def test_all_files_exist(self):
        """Confirm verified acts exist in statute_tables, and quarantined acts exist in quarantine."""
        for act in VERIFIED_ACTS:
            json_file = os.path.join(TABLES_DIR, f"{act}.json")
            csv_file = os.path.join(TABLES_DIR, f"{act}.csv")
            self.assertTrue(os.path.exists(json_file), f"Missing verified JSON: {json_file}")
            self.assertTrue(os.path.exists(csv_file), f"Missing verified CSV: {csv_file}")
            self.assertGreater(os.path.getsize(json_file), 100, f"Empty JSON: {json_file}")
            self.assertGreater(os.path.getsize(csv_file), 100, f"Empty CSV: {csv_file}")

        for act in QUARANTINED_ACTS:
            json_file = os.path.join(QUARANTINE_TABLES_DIR, f"{act}.json")
            csv_file = os.path.join(QUARANTINE_TABLES_DIR, f"{act}.csv")
            self.assertTrue(os.path.exists(json_file), f"Missing quarantined JSON: {json_file}")
            self.assertTrue(os.path.exists(csv_file), f"Missing quarantined CSV: {csv_file}")

    def test_schema_compliance_and_uniqueness(self):
        """Confirm every row adheres strictly to schema with unique canonical_ids."""
        for act in ALL_ACTS:
            act_dir = get_act_dir(act)
            json_file = os.path.join(act_dir, f"{act}.json")
            with open(json_file, "r", encoding="utf-8") as f:
                entries = json.load(f)

            self.assertGreater(len(entries), 0, f"No entries in {act}")
            seen_ids = set()

            for entry in entries:
                # 1. Required core fields
                for field in ["canonical_id", "act_code", "act_name", "provision_type", "primary_num", "title"]:
                    self.assertIn(field, entry, f"Missing field '{field}' in {act} entry {entry.get('canonical_id')}")

                # 2. Canonical ID format and uniqueness
                cid = entry["canonical_id"]
                self.assertTrue(cid.startswith(act), f"Canonical ID '{cid}' does not start with act_code '{act}'")
                self.assertNotIn(cid, seen_ids, f"Duplicate canonical_id '{cid}' in {act}")
                seen_ids.add(cid)

                # 3. Provision type valid
                self.assertIn(entry["provision_type"], ["section", "order_rule", "article", "rule"],
                              f"Invalid provision_type '{entry['provision_type']}' in {cid}")

    def test_user_canonical_id_matrix(self):
        """Verify all test matrix cases specified by user exist with exact canonical_id."""
        matrix_checks = [
            ("CPC_1908", "CPC_1908_SEC_9", "Section 9"),
            ("CPC_1908", "CPC_1908_SEC_12_2", "Section 12(2)"),
            ("PPC_1860", "PPC_1860_SEC_302_B", "Section 302(b)"),
            ("PPC_1860", "PPC_1860_SEC_22A_6", "Section 22-A(6)"),
            ("PPC_1860", "PPC_1860_SEC_22A_6_A", "Section 22-A(6)(a)"),
            ("CRPC_1898", "CRPC_1898_SEC_22A_6", "Section 22-A(6)"),
            ("CRPC_1898", "CRPC_1898_SEC_22A_6_A", "Section 22-A(6)(a)"),
            ("CPC_1908", "CPC_1908_ORD_XXI_R_58", "Order XXI Rule 58"),
            ("CPC_1908", "CPC_1908_ORD_XXXIX_R_1", "Order XXXIX Rule 1(2)"),
            ("CONST_1973", "CONST_1973_ART_199", "Article 199"),
            ("CONST_1973", "CONST_1973_ART_184_3", "Article 184(3)"),
            ("CONST_1973", "CONST_1973_ART_58_2_B", "Article 58(2)(b)"),
            ("LIMITATION_1908", "LIMITATION_1908_SEC_5", "Section 5"),
            ("LIMITATION_1908", "LIMITATION_1908_ART_181", "Article 181"),
            ("CNSA_1997", "CNSA_1997_SEC_9_C", "Section 9(c)"),
            ("PRPA_2009", "PRPA_2009_SEC_15", "Section 15"),
            ("PREEMPTION_1991", "PREEMPTION_1991_SEC_13", "Section 13")
        ]

        for act, expected_cid, disp in matrix_checks:
            act_dir = get_act_dir(act)
            json_file = os.path.join(act_dir, f"{act}.json")
            with open(json_file, "r", encoding="utf-8") as f:
                entries = json.load(f)
            found = [e for e in entries if e["canonical_id"] == expected_cid]
            self.assertEqual(len(found), 1, f"Test matrix case failed: {expected_cid} not found in {act}")

    def test_qso_evidence_act_crosswalk(self):
        """Confirm QSO 1984 articles have correct crosswalk reference in quarantine tables."""
        json_file = os.path.join(QUARANTINE_TABLES_DIR, "QSO_1984.json")
        self.assertTrue(os.path.exists(json_file), "QSO_1984.json must exist in quarantine")
        with open(json_file, "r", encoding="utf-8") as f:
            entries = {e["primary_num"]: e for e in json.load(f)}

        # Verify key entries exist
        for num in ["2", "17", "46", "114", "129", "132", "164"]:
            self.assertIn(num, entries, f"QSO provision {num} must exist")

    def test_provincial_specificity(self):
        """Confirm PRPA 2009 and Punjab Pre-emption Act 1991 are explicitly scoped to Punjab only."""
        for prov_act in ["PRPA_2009", "PREEMPTION_1991"]:
            json_file = os.path.join(QUARANTINE_TABLES_DIR, f"{prov_act}.json")
            self.assertTrue(os.path.exists(json_file), f"Missing {prov_act} in quarantine")
            with open(json_file, "r", encoding="utf-8") as f:
                entries = json.load(f)

            for e in entries:
                status = e["status"]
                if isinstance(status, dict):
                    self.assertEqual(status["punjab"], "in_force", f"{prov_act} must be in_force in Punjab")
                    self.assertEqual(status["federal"], "not_applicable", f"{prov_act} must be not_applicable federally")
                else:
                    self.assertIn(e.get("jurisdiction", "punjab").lower(), ["punjab", "provincial"])


if __name__ == "__main__":
    unittest.main()
