"""
Unit Tests for Ground-Truth Statutory Provision Lookup Tables
Validates schema compliance, canonical ID generation, test matrix coverage,
uniqueness, QSO crosswalks, and provincial specificity.
"""

import os
import json
import unittest

TABLES_DIR = r"c:\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master\data\statute_tables"

REQUIRED_FIELDS = [
    "act_code", "act_name", "provision_type", "primary_num", "secondary_num",
    "canonical_id", "display_name", "title", "status",
    "superseded_reference", "source_citation", "source_verified_date"
]

STATUS_KEYS = ["federal", "punjab", "sindh", "kp", "balochistan"]

ALL_ACTS = [
    "CPC_1908", "PPC_1860", "CRPC_1898", "CONST_1973", "QSO_1984", "LIMITATION_1908",
    "MFLO_1961", "FAMILY_COURTS_1964", "DMMA_1939", "CNSA_1997", "PRPA_2009", "PREEMPTION_1991"
]


class TestStatuteTables(unittest.TestCase):

    def test_all_files_exist(self):
        """Confirm both JSON and CSV files exist for all 12 statutes."""
        for act in ALL_ACTS:
            json_file = os.path.join(TABLES_DIR, f"{act}.json")
            csv_file = os.path.join(TABLES_DIR, f"{act}.csv")
            self.assertTrue(os.path.exists(json_file), f"Missing JSON: {json_file}")
            self.assertTrue(os.path.exists(csv_file), f"Missing CSV: {csv_file}")
            self.assertGreater(os.path.getsize(json_file), 100, f"Empty JSON: {json_file}")
            self.assertGreater(os.path.getsize(csv_file), 100, f"Empty CSV: {csv_file}")

    def test_schema_compliance_and_uniqueness(self):
        """Confirm every row adheres strictly to schema with zero empty source citations and unique canonical_ids."""
        for act in ALL_ACTS:
            json_file = os.path.join(TABLES_DIR, f"{act}.json")
            with open(json_file, "r", encoding="utf-8") as f:
                entries = json.load(f)

            self.assertGreater(len(entries), 0, f"No entries in {act}")
            seen_ids = set()

            for entry in entries:
                # 1. Required fields
                for field in REQUIRED_FIELDS:
                    self.assertIn(field, entry, f"Missing field '{field}' in {act} entry {entry.get('canonical_id')}")

                # 2. Canonical ID format and uniqueness
                cid = entry["canonical_id"]
                self.assertTrue(cid.startswith(act), f"Canonical ID '{cid}' does not start with act_code '{act}'")
                self.assertNotIn(cid, seen_ids, f"Duplicate canonical_id '{cid}' in {act}")
                seen_ids.add(cid)

                # 3. Non-empty source citation & verified date
                self.assertTrue(entry["source_citation"] and len(entry["source_citation"]) > 10,
                                f"Missing source citation in {act}: {cid}")
                self.assertEqual(entry["source_verified_date"], "2026-09-23")

                # 4. Status dictionary structure
                status = entry["status"]
                self.assertIsInstance(status, dict, f"Status must be dict in {cid}")
                for sk in STATUS_KEYS:
                    self.assertIn(sk, status, f"Missing status key '{sk}' in {cid}")
                    self.assertIsInstance(status[sk], str)

                # 5. Provision type valid
                self.assertIn(entry["provision_type"], ["section", "order_rule", "article"],
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
            ("CPC_1908", "CPC_1908_ORD_XXXIX_R_1_SR_2", "Order XXXIX Rule 1(2)"),
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
            json_file = os.path.join(TABLES_DIR, f"{act}.json")
            with open(json_file, "r", encoding="utf-8") as f:
                entries = json.load(f)
            found = [e for e in entries if e["canonical_id"] == expected_cid]
            self.assertEqual(len(found), 1, f"Test matrix case failed: {expected_cid} not found in {act}")
            self.assertIn(disp.lower(), found[0]["display_name"].lower(),
                          f"Display name mismatch for {expected_cid}: got {found[0]['display_name']}, expected {disp}")

    def test_qso_evidence_act_crosswalk(self):
        """Confirm QSO 1984 articles have correct Evidence Act 1872 crosswalk references."""
        json_file = os.path.join(TABLES_DIR, "QSO_1984.json")
        with open(json_file, "r", encoding="utf-8") as f:
            entries = {e["primary_num"]: e for e in json.load(f)}

        # Verify key crosswalk mappings
        self.assertIn("Section 3", entries["2"]["superseded_reference"])
        self.assertIn("Section 134", entries["17"]["superseded_reference"])
        self.assertIn("Section 32", entries["46"]["superseded_reference"])
        self.assertIn("Section 115", entries["114"]["superseded_reference"])
        self.assertIn("Section 114", entries["129"]["superseded_reference"])
        self.assertIn("Section 137", entries["132"]["superseded_reference"])
        self.assertIn("Modern devices", entries["164"]["superseded_reference"])

    def test_provincial_specificity(self):
        """Confirm PRPA 2009 and Punjab Pre-emption Act 1991 are explicitly scoped to Punjab only."""
        for prov_act in ["PRPA_2009", "PREEMPTION_1991"]:
            json_file = os.path.join(TABLES_DIR, f"{prov_act}.json")
            with open(json_file, "r", encoding="utf-8") as f:
                entries = json.load(f)

            for e in entries:
                status = e["status"]
                self.assertEqual(status["punjab"], "in_force", f"{prov_act} must be in_force in Punjab")
                self.assertEqual(status["federal"], "not_applicable", f"{prov_act} must be not_applicable federally")
                self.assertEqual(status["sindh"], "not_applicable", f"{prov_act} must be not_applicable in Sindh")
                self.assertEqual(status["kp"], "not_applicable", f"{prov_act} must be not_applicable in KP")
                self.assertEqual(status["balochistan"], "not_applicable", f"{prov_act} must be not_applicable in Balochistan")


if __name__ == "__main__":
    unittest.main()
