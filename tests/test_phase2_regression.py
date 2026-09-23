"""
Phase 2 End-to-End Regression Suite
Verifies:
1. Farooq Imran / Tahir Umar cross-case quote misattribution detection & correction
2. Section 12(2) Order XXI CPC hybrid hallucination interception & warning banner
3. Unverified statutory provision detection & warning disclosure banner
"""

import unittest
from core.legal_guardrails import lint_legal_output
from core.statutory_validator import validate_statutory_citation, validate_citations_in_text
from core.quote_verifier import verify_quote_attribution, verify_text_quotes


class TestPhase2Regression(unittest.TestCase):

    def setUp(self):
        # Retrieved context payload simulating the real multi-candidate retrieval block
        self.retrieved_payload = {
            "PLD 2018 SC 400": (
                "Supreme Court of Pakistan - Farooq Imran v. Federation of Pakistan. "
                "The Court addressed the execution of decrees and the principles governing arrest and detention "
                "under Section 51 of the Code of Civil Procedure, 1908. Detention in prison cannot be ordered "
                "mechanically without establishing that the judgment-debtor possesses the means to pay and has "
                "willfully refused or neglected to pay."
            ),
            "2020 SCMR 850": (
                "Supreme Court of Pakistan - Tahir Umar v. State. "
                "The apex court held: 'The liberty of a citizen is a sacred trust under Article 9 of the Constitution "
                "and cannot be curtailed on mere surmises or unsubstantiated allegations of the judgment creditor.' "
                "Strict adherence to constitutional guarantees is mandatory before ordering civil imprisonment."
            )
        }

    def test_farooq_imran_tahir_umar_quote_misattribution_regression(self):
        """
        Regression Case 1: Reconstructed Farooq Imran / Tahir Umar failure mode.
        The LLM generates a response attributing Tahir Umar's quote to Farooq Imran.
        Confirm:
        1. Quote is detected as NOT present in Farooq Imran
        2. Quote is auto-matched and corrected to Tahir Umar
        3. Deterministic disclosure banner is generated with exact case attribution
        """
        response_text = (
            "### ANALYSIS OF CIVIL IMPRISONMENT & DECREE EXECUTION\n\n"
            "In PLD 2018 SC 400 (Farooq Imran v. Federation of Pakistan), the Supreme Court emphasized:\n"
            "\"The liberty of a citizen is a sacred trust under Article 9 of the Constitution "
            "and cannot be curtailed on mere surmises or unsubstantiated allegations of the judgment creditor.\"\n\n"
            "Therefore, the executing court erred in ordering detention under Section 51 CPC."
        )

        res = verify_text_quotes(response_text, self.retrieved_payload)

        # Confirm misattribution was caught
        self.assertEqual(res["misattributed_count"], 1)
        self.assertEqual(res["verified_count"], 0)
        self.assertEqual(res["unverified_count"], 0)

        # Confirm auto-correction identifies Tahir Umar (2020 SCMR 850)
        misattributed = res["misattributed"][0]
        self.assertEqual(misattributed["attributed_citation"], "PLD 2018 SC 400")
        self.assertEqual(misattributed["matched_citation"], "2020 SCMR 850")
        self.assertGreaterEqual(misattributed["similarity_score"], 0.85)

        # Confirm warning banner exists and contains both citations
        banner = res["warning_banner"]
        self.assertIsNotNone(banner)
        self.assertIn("Quote Attribution Correction", banner)
        self.assertIn("PLD 2018 SC 400", banner)
        self.assertIn("2020 SCMR 850", banner)

        # Confirm the auto-corrected citation appears in the final user-facing rendered output
        rendered_output = f"{banner}\n\n{response_text}"
        self.assertIn("was attributed to `PLD 2018 SC 400`, but actually appears in `2020 SCMR 850`", rendered_output)

    def test_section_12_2_order_xxi_hybrid_hallucination_regression(self):
        """
        Regression Case 2: Fabricated statutory citation 'Section 12(2) Order XXI CPC'.
        Confirm:
        1. Caught directly by lint_legal_output reflection hook
        2. Caught by validate_statutory_citation
        3. Produces statutory warning banner when scanning full response
        """
        query_context = "application under Section 12(2) Order XXI CPC challenging decree"
        response_text = (
            "The petitioner has filed an application under Section 12(2) Order XXI CPC seeking to set aside "
            "the execution of the decree on grounds of fraud and lack of jurisdiction."
        )

        # 1. Lint hook check
        lint_errors = lint_legal_output(response_text, query_context=query_context)
        self.assertTrue(
            any("Hybrid Statutory Hallucination" in err for err in lint_errors),
            f"lint_legal_output failed to catch Section 12(2) Order XXI: {lint_errors}"
        )

        # 2. Citation validator check
        val = validate_statutory_citation("Section 12(2) Order XXI CPC")
        self.assertFalse(val["is_valid"])
        self.assertEqual(val["status"], "hybrid_hallucination")
        self.assertIn("conflates a substantive Section with a procedural Order/Rule", val["message"])

        # 3. Full text scan & banner check
        scan = validate_citations_in_text(response_text)
        self.assertEqual(scan["hybrid_count"], 1)
        self.assertIsNotNone(scan["warning_banner"])
        
        # Confirm user-facing rendered response contains exact banner text
        rendered_output = f"{scan['warning_banner']}\n\n{response_text}"
        self.assertIn("⚠️ **Statutory Citation Notice**:", rendered_output)
        self.assertIn("- **Section 12(2) Order XXI CPC**: Conflates substantive section with procedural order (invalid hybrid citation).", rendered_output)

    def test_unverified_provision_notice_regression(self):
        """
        Regression Case 3: Bogus section cited by LLM.
        Confirm:
        1. Flagged as unverified
        2. Produces statutory warning banner with Canonical ID
        """
        response_text = (
            "Under Section 999 of the Code of Civil Procedure, 1908, the court has the power to dismiss "
            "the petition summarily without issuing notice."
        )

        val = validate_statutory_citation("Section 999 CPC")
        self.assertFalse(val["is_valid"])
        self.assertEqual(val["status"], "unverified_provision")
        self.assertEqual(val["canonical_id"], "CPC_1908_SEC_999")

        scan = validate_citations_in_text(response_text)
        self.assertEqual(scan["unverified_count"], 1)
        
        # Confirm user-facing rendered response contains exact unverified notice
        rendered_output = f"{scan['warning_banner']}\n\n{response_text}"
        self.assertIn("⚠️ **Statutory Citation Notice**:", rendered_output)
        self.assertIn("Provision with Canonical ID 'CPC_1908_SEC_999' does not exist in verified statutory lookup tables.", rendered_output)


if __name__ == "__main__":
    unittest.main()
