import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.legal_guardrails import lint_legal_output, SYSTEM_LEGAL_DIRECTIVE, verify_case_grounding


class TestExecutionAndAttributionGuardrails(unittest.TestCase):

    def test_order_xxi_rule_96_attachment_misuse(self):
        bad_text = (
            "The decree-holder can seek attachment of the judgment-debtor's immovable property "
            "under Order XXI Rule 96 of the Code of Civil Procedure to restrain alienation."
        )
        errors = lint_legal_output(bad_text, query_context="execution of money decree attach property")
        self.assertTrue(
            any("Order XXI Rule 96 CPC for attachment" in e for e in errors),
            f"Expected Order XXI Rule 96 error, got: {errors}"
        )

    def test_section_54_sra_cancellation_misuse(self):
        bad_text = (
            "The plaintiff should institute a suit under Section 54 of the Specific Relief Act "
            "for the cancellation of the fraudulent sale deed and to declare the void deed null."
        )
        errors = lint_legal_output(bad_text, query_context="cancel fraudulent deed")
        self.assertTrue(
            any("Section 54 Specific Relief Act 1877 for cancellation" in e for e in errors),
            f"Expected Section 54 SRA cancellation error, got: {errors}"
        )

    def test_section_52_tpa_void_mischaracterization(self):
        bad_text = (
            "Section 52 of the Transfer of Property Act renders the alienation completely void "
            "and illegal ab initio because the suit was already pending."
        )
        errors = lint_legal_output(bad_text, query_context="sale of property during pending suit")
        self.assertTrue(
            any("Section 52 Transfer of Property Act 1882 (Lis Pendens) as 'void'" in e for e in errors),
            f"Expected Section 52 void error, got: {errors}"
        )

    def test_section_41_tpa_bona_fide_purchaser_as_exception_to_s52(self):
        bad_text = (
            "While Section 52 applies, Section 41 is an exception to Section 52 where a bona fide purchaser "
            "for value without notice can defeat lis pendens."
        )
        errors = lint_legal_output(bad_text, query_context="purchaser pendente lite protection")
        self.assertTrue(
            any("Section 41 TPA (bona fide purchaser protection) protects a transferee against or is an exception to Section 52" in e for e in errors),
            f"Expected Section 41 vs 52 error, got: {errors}"
        )

    def test_family_court_execution_without_section_17_exclusion(self):
        bad_text = (
            "In execution of a Family Court maintenance decree, the court proceeds under Order XXI of the Code "
            "of Civil Procedure to issue warrants."
        )
        errors = lint_legal_output(bad_text, query_context="execution of family court maintenance decree")
        self.assertTrue(
            any("Family Courts Act 1964 expressly bars the application of the CPC" in e for e in errors),
            f"Expected Family Courts Act CPC exclusion error, got: {errors}"
        )

    def test_cases_discussed_statutory_leakage(self):
        bad_text = (
            "### Legal Analysis\nThe relevant provisions govern execution.\n\n"
            "### Cases Discussed\n"
            "- Section 52 Transfer of Property Act\n"
            "- Order XXI Rule 54 CPC\n"
            "- Section 39 Specific Relief Act\n"
        )
        errors = lint_legal_output(bad_text, query_context="execution and lis pendens")
        self.assertTrue(
            any("'Cases Discussed' section contains statutory citations" in e for e in errors),
            f"Expected Cases Discussed statutory leakage error, got: {errors}"
        )

    def test_fabricated_four_part_test(self):
        bad_text = (
            "In Tabassum Shaheen, the court established a four-part test for applying Section 52 "
            "to maintenance suits where property is transferred to close relatives."
        )
        errors = lint_legal_output(bad_text, query_context="Tabassum Shaheen four-part test")
        self.assertTrue(
            any("fabricated 'four-part test'" in e for e in errors),
            f"Expected four-part test fabrication error, got: {errors}"
        )

    def test_clean_proper_execution_and_lis_pendens_text(self):
        good_text = (
            "### Legal Analysis\n"
            "Under Section 52 of the Transfer of Property Act 1882, the transfer of property during the pendency "
            "of a suit is not void ab initio; rather, it remains subservient to the rights of the parties under "
            "the eventual decree. Section 52 strictly overrides Section 41, so the transferee pendente lite cannot "
            "plead bona fide purchase without notice.\n\n"
            "For decree execution, attachment of immovable property is effected under Order XXI Rule 54 CPC.\n"
            "If a third-party stranger raises an independent title claim, it must be investigated through objection "
            "proceedings under Order XXI Rule 58 CPC or via a substantive suit under Section 53 TPA and Section 39 "
            "of the Specific Relief Act 1877 for cancellation of fraudulent deeds.\n\n"
            "In Family Court maintenance execution, Section 17 of the Family Courts Act 1964 explicitly excludes the "
            "application of the CPC, and execution proceeds under Section 13 of the Family Courts Act 1964.\n\n"
            "### Cases Discussed\n"
            "- Tabassum Shaheen v. Mst. Tasneem Akhtar (2025 PLD 63 Lahore)\n"
            "- Muhammad Aslam v. Mst. Rabia (2024 SCMR 102)\n"
        )
        errors = lint_legal_output(good_text, query_context="execution of maintenance decree and lis pendens")
        self.assertEqual(len(errors), 0, f"Sound legal text triggered unexpected errors: {errors}")

    def test_verify_case_grounding_valid(self):
        source_judgment = (
            "The suit was instituted for declaration and possession under Section 42 of the Specific Relief Act. "
            "During the pendency of the suit, the appellant transferred the property via registered sale deed. "
            "Under Section 52 of the Transfer of Property Act, 1882, transfer pendente lite does not affect the rights "
            "of any other party thereto under any decree or order which may be made therein."
        )
        assertion = "Under Section 52 of the Transfer of Property Act, a transfer made during pending litigation remains subject to the decree."
        res = verify_case_grounding("Tabassum Shaheen", source_judgment, assertion)
        self.assertTrue(res["is_grounded"])
        self.assertEqual(res["entailment_score"], 1.0)
        self.assertEqual(len(res["unsupported_propositions"]), 0)

    def test_verify_case_grounding_detects_domain_and_statutory_extrapolation(self):
        source_judgment = (
            "The suit was instituted for declaration and possession under Section 42 of the Specific Relief Act. "
            "During the pendency of the suit, the appellant transferred the property via registered sale deed. "
            "Section 52 applies because specific immovable property was directly in issue."
        )
        assertion = (
            "The court formulated a four-part test holding that in maintenance suits, any transfer to relatives "
            "is presumed fraudulent under Section 53 TPA and cancelled under Section 54 SRA."
        )
        res = verify_case_grounding("Tabassum Shaheen", source_judgment, assertion)
        self.assertFalse(res["is_grounded"])
        self.assertLess(res["entailment_score"], 0.70)
        self.assertTrue(any("maintenance" in p for p in res["unsupported_propositions"]))
        self.assertTrue(any("four-part test" in p for p in res["unsupported_propositions"]))
        self.assertTrue(any("Section 53" in p or "Section 54" in p for p in res["unsupported_propositions"]))


if __name__ == '__main__':
    unittest.main()
