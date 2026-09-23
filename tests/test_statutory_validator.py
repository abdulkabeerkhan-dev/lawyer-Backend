"""
Unit Tests for Statutory Citation Validator & Hybrid Hallucination Interceptor
Validates parser, canonical ID generator, hybrid rejection, and registry lookup.
"""

import unittest
from core.statutory_validator import (
    generate_canonical_id,
    parse_statutory_citation,
    check_hybrid_hallucination,
    validate_statutory_citation,
    validate_citations_in_text
)


class TestStatutoryValidator(unittest.TestCase):

    def test_canonical_id_generation(self):
        """Verify deterministic canonical ID generation against user test matrix."""
        # Substantive sections & articles
        self.assertEqual(generate_canonical_id("CPC_1908", "9"), "CPC_1908_SEC_9")
        self.assertEqual(generate_canonical_id("CPC_1908", "12", subsection="2"), "CPC_1908_SEC_12_2")
        self.assertEqual(generate_canonical_id("PPC_1860", "302", clause="b"), "PPC_1860_SEC_302_B")
        self.assertEqual(generate_canonical_id("PPC_1860", "22A", subsection="6"), "PPC_1860_SEC_22A_6")
        self.assertEqual(generate_canonical_id("PPC_1860", "22A", subsection="6", clause="a"), "PPC_1860_SEC_22A_6_A")
        self.assertEqual(generate_canonical_id("CRPC_1898", "22A", subsection="6", clause="a"), "CRPC_1898_SEC_22A_6_A")
        self.assertEqual(generate_canonical_id("CONST_1973", "199", provision_type="article"), "CONST_1973_ART_199")
        self.assertEqual(generate_canonical_id("CONST_1973", "184", subsection="3", provision_type="article"), "CONST_1973_ART_184_3")
        self.assertEqual(generate_canonical_id("CONST_1973", "58", subsection="2", clause="b", provision_type="article"), "CONST_1973_ART_58_2_B")
        self.assertEqual(generate_canonical_id("LIMITATION_1908", "5", provision_type="section"), "LIMITATION_1908_SEC_5")
        self.assertEqual(generate_canonical_id("LIMITATION_1908", "181", provision_type="article"), "LIMITATION_1908_ART_181")

        # Procedural Order/Rule
        self.assertEqual(generate_canonical_id("CPC_1908", "XXI", rule_num="58"), "CPC_1908_ORD_XXI_R_58")
        self.assertEqual(generate_canonical_id("CPC_1908", "XXXIX", rule_num="1", sub_rule="2"), "CPC_1908_ORD_XXXIX_R_1_SR_2")
        # Arabic numeral conversion for Order
        self.assertEqual(generate_canonical_id("CPC_1908", "21", rule_num="58"), "CPC_1908_ORD_XXI_R_58")
        self.assertEqual(generate_canonical_id("CPC_1908", "39", rule_num="1", sub_rule="2"), "CPC_1908_ORD_XXXIX_R_1_SR_2")

    def test_hybrid_hallucination_detection(self):
        """Confirm that hybrid citations (Section 12(2) Order XXI) short-circuit immediately."""
        hybrid_cases = [
            "Section 12(2) Order XXI CPC",
            "Section 12(2) of Order XXI",
            "Order XXI Section 12(2) CPC",
            "Section 9 Order VII Rule 11 CPC",
            "Section 12(2) Order 21 CPC"
        ]

        for h in hybrid_cases:
            res = check_hybrid_hallucination(h)
            self.assertIsNotNone(res, f"Failed to detect hybrid hallucination on: {h}")
            self.assertEqual(res["status"], "hybrid_hallucination")
            self.assertFalse(res["is_valid"])

            val_res = validate_statutory_citation(h)
            self.assertEqual(val_res["status"], "hybrid_hallucination")
            self.assertFalse(val_res["is_valid"])

    def test_valid_statutory_validation(self):
        """Confirm valid provisions pass registry lookup with full metadata."""
        valid_citations = [
            ("Section 12(2) CPC", "CPC_1908_SEC_12_2"),
            ("Section 9 CPC", "CPC_1908_SEC_9"),
            ("Section 302(b) PPC", "PPC_1860_SEC_302_B"),
            ("Section 489-F PPC", "PPC_1860_SEC_489F"),
            ("Section 22-A(6)(a) CrPC", "CRPC_1898_SEC_22A_6_A"),
            ("Order XXI Rule 58 CPC", "CPC_1908_ORD_XXI_R_58"),
            ("Order 21 Rule 58 CPC", "CPC_1908_ORD_XXI_R_58"),
            ("Order XXXIX Rule 1(2) CPC", "CPC_1908_ORD_XXXIX_R_1_SR_2"),
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
            self.assertIsNotNone(res.get("source_citation"))

    def test_unverified_provision_detection(self):
        """Confirm non-existent or fabricated sections fail validation."""
        bogus_citations = [
            "Section 999 CPC",
            "Order XXI Rule 999 CPC",
            "Article 999 Constitution",
            "Section 888 PPC",
            "Section 777 CrPC"
        ]

        for bogus in bogus_citations:
            res = validate_statutory_citation(bogus)
            self.assertFalse(res["is_valid"], f"Bogus citation was marked valid: {bogus}")
            self.assertIn("unverified", res["status"])

    def test_text_scanning_and_banner_generation(self):
        """Confirm scanner inspects text, catches hybrid hallucination, and generates warning banner."""
        hallucinating_text = """
        The petitioner submitted an application under Section 12(2) Order XXI CPC seeking to set aside
        the decree passed on the basis of fraud. Alternatively, the petitioner relied on Section 9 CPC
        and Article 199 of the Constitution. The respondent objected under Section 999 CPC.
        """

        scan_res = validate_citations_in_text(hallucinating_text)
        self.assertGreater(scan_res["verified_count"], 0)
        self.assertGreater(scan_res["hybrid_count"], 0)
        self.assertIsNotNone(scan_res["warning_banner"])
        self.assertIn("Section 12(2) Order XXI", scan_res["warning_banner"])
        self.assertIn("Section 999 CPC", scan_res["warning_banner"])


if __name__ == "__main__":
    unittest.main()
