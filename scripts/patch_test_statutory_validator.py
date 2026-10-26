file_path = "tests/test_statutory_validator.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''    def test_valid_statutory_validation(self):
        """Confirm valid provisions pass registry lookup with full metadata."""
        valid_citations = [
            ("Section 12(2) CPC", "CPC_1908_SEC_12_2"),
            ("Section 9 CPC", "CPC_1908_SEC_9"),
            ("Section 302(b) PPC", "PPC_1860_SEC_302_B"),
            ("Section 489-F PPC", "PPC_1860_SEC_489F"),
            ("Section 489-F", "PPC_1860_SEC_489F"),
            ("Section 22-A(6)(a) CrPC", "CRPC_1898_SEC_22A_6_A"),
            ("Order XXI Rule 58 CPC", "CPC_1908_ORD_XXI_R_58"),
            ("Order 21 Rule 58 CPC", "CPC_1908_ORD_XXI_R_58"),
            ("Order XXXIX Rule 1 CPC", "CPC_1908_ORD_XXXIX_R_1"),
            ("Article 199 Constitution", "CONST_1973_ART_199"),
            ("Article 184(3) Constitution", "CONST_1973_ART_184_3"),
            ("Article 58(2)(b) Constitution", "CONST_1973_ART_58_2_B"),
            ("Section 5 Limitation Act", "LIMITATION_1908_SEC_5"),
            ("Article 181 Limitation Act", "LIMITATION_1908_ART_181"),
            ("Section 9(c) CNSA", "CNSA_1997_SEC_9_C"),
            ("Section 15 PRPA", "PRPA_2009_SEC_15"),
            ("Section 13 Pre-emption Act", "PREEMPTION_1991_SEC_13")
        ]

        for cit, expected_cid in valid_citations:
            res = validate_statutory_citation(cit)
            self.assertTrue(res["is_valid"], f"Valid citation flagged invalid: {cit} -> {res}")
            self.assertEqual(res["status"], "verified")
            self.assertEqual(res["canonical_id"], expected_cid)
            self.assertIsNotNone(res.get("title"))
            self.assertIsNotNone(res.get("source_citation"))'''

replacement = '''    def test_valid_statutory_validation(self):
        """Confirm verified provisions pass lookup, and quarantined acts return unverified."""
        # Verified citations from the 10 sourced Acts (CPC, PPC, CrPC, Limitation, etc.)
        valid_citations = [
            ("Section 12(2) CPC", "CPC_1908_SEC_12_2"),
            ("Section 9 CPC", "CPC_1908_SEC_9"),
            ("Section 302(b) PPC", "PPC_1860_SEC_302_B"),
            ("Section 489-F PPC", "PPC_1860_SEC_489F"),
            ("Section 489-F", "PPC_1860_SEC_489F"),
            ("Section 22-A(6)(a) CrPC", "CRPC_1898_SEC_22A_6_A"),
            ("Order XXI Rule 58 CPC", "CPC_1908_ORD_XXI_R_58"),
            ("Order 21 Rule 58 CPC", "CPC_1908_ORD_XXI_R_58"),
            ("Order XXXIX Rule 1 CPC", "CPC_1908_ORD_XXXIX_R_1"),
            ("Section 5 Limitation Act", "LIMITATION_1908_SEC_5"),
            ("Article 181 Limitation Act", "LIMITATION_1908_ART_181"),
        ]

        for cit, expected_cid in valid_citations:
            res = validate_statutory_citation(cit)
            self.assertTrue(res["is_valid"], f"Valid citation flagged invalid: {cit} -> {res}")
            self.assertEqual(res["status"], "verified")
            self.assertEqual(res["canonical_id"], expected_cid)
            self.assertIsNotNone(res.get("title"))
            self.assertIsNotNone(res.get("source_citation"))

        # Quarantined citations (Constitution, CNSA, PRPA, Pre-emption) must fail-closed
        quarantined_citations = [
            ("Article 199 Constitution", "CONST_1973_ART_199"),
            ("Article 184(3) Constitution", "CONST_1973_ART_184_3"),
            ("Article 58(2)(b) Constitution", "CONST_1973_ART_58_2_B"),
            ("Section 9(c) CNSA", "CNSA_1997_SEC_9_C"),
            ("Section 15 PRPA", "PRPA_2009_SEC_15"),
            ("Section 13 Pre-emption Act", "PREEMPTION_1991_SEC_13")
        ]
        for cit, cid in quarantined_citations:
            res = validate_statutory_citation(cit)
            self.assertFalse(res["is_valid"], f"Quarantined provision should be invalid: {cit}")
            self.assertIn(res["status"], ["unverified_provision", "missing_act"])'''

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
assert target_norm in content_norm, "target not found"
content_norm = content_norm.replace(target_norm, replacement)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("test_statutory_validator.py updated successfully")
