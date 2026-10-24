"""
tests/test_statute_claim_verifier_general.py

Deterministic tests for the generalized statute claim verifier:
1. Seeded errors on 3 distinct Pakistani enactments (PPC, SRA, NI Act).
2. Case-to-statute attribution validation (preventing cross-enactment hallucinations like 2026 CLD 39 on CPC).
"""

import sys
import unittest
sys.stdout.reconfigure(encoding='utf-8')

from core.statute_claim_verifier import (
    verify_memo_statutory_claims,
    verify_case_statute_attribution,
    STATUTORY_CONCEPT_BENCHMARKS
)

class TestStatuteClaimVerifierGeneral(unittest.TestCase):

    def test_concept_benchmarks_are_general(self):
        """Assert concepts cover penalties, limitation, bench composition, natural justice, financial conditions."""
        concept_names = [c[0] for c in STATUTORY_CONCEPT_BENCHMARKS]
        self.assertIn("deposit_percentage", concept_names)
        self.assertIn("imprisonment_duration", concept_names)
        self.assertIn("limitation_period", concept_names)
        self.assertIn("procedural_notice", concept_names)
        self.assertIn("bench_composition", concept_names)
        self.assertIn("interlocutory_bar", concept_names)

    def test_seeded_error_ppc_section_489f(self):
        """PPC 489-F provides for up to 3 years imprisonment or fine. Seeded error claims 7 years and 25% deposit."""
        stored_ppc = {
            "PPC_1860_SEC_489F": (
                "489-F. Dishonestly issuing a cheque. Whoever dishonestly issues a cheque towards repayment of a "
                "loan or fulfillment of an obligation which is dishonoured on presentation, shall be punishable with "
                "imprisonment which may extend to three years, or with fine, or with both, unless he can establish, "
                "for which the burden of proof shall rest on him, that he had made arrangements with his bank to ensure "
                "that the cheque would be honoured and that the bank was at fault in not honouring the cheque."
            )
        }

        # Seeded memo with 7 years imprisonment and 25% deposit
        faulty_memo = (
            "## Relevant Provisions\n"
            "Under Section 489-F of the Pakistan Penal Code, the convict is sentenced to imprisonment for seven years.\n"
            "The court further demands a deposit in cash equal to 25% of the cheque amount.\n"
        )

        res = verify_memo_statutory_claims(faulty_memo, stored_ppc, primary_section="489f")
        self.assertFalse(res.passed)
        # Should flag deposit_percentage or 25% and decretal amount
        violation_terms = [v["unsupported_term"] for v in res.violations]
        self.assertTrue(any("deposit" in t for t in violation_terms))

    def test_seeded_error_sra_section_12(self):
        """SRA Section 12 governs specific performance. Seeded error claims an invented cross-reference to Section 45 and 15 days limitation."""
        stored_sra = {
            "SRA_1877_SEC_12": (
                "12. Cases in which specific performance enforceable. Except as otherwise provided in this Chapter, "
                "the specific performance of any contract may in the discretion of the Court be enforced: "
                "(a) when the act agreed to be done is in the performance wholly or partly of a trust; "
                "(b) when there exists no standard for ascertaining the actual damage caused by the non-performance of the act agreed to be done; "
                "(c) when the act agreed to be done is such that pecuniary compensation for its non-performance would not afford adequate relief; or "
                "(d) when it is probable that pecuniary compensation cannot be got for the non-performance of the act agreed to be done."
            )
        }

        faulty_memo = (
            "## Relevant Provisions\n"
            "Section 12 specific performance is subject to Section 45.\n"
            "The suit must be filed within fifteen days.\n"
        )

        res = verify_memo_statutory_claims(faulty_memo, stored_sra, primary_section="12")
        self.assertFalse(res.passed)
        violation_types = [v["type"] for v in res.violations]
        self.assertIn("unsupported_external_cross_reference", violation_types)

    def test_seeded_error_ni_act_section_138(self):
        """NI Act Section 138 (notice). Seeded error claims ninety days notice and division bench requirement."""
        stored_ni = {
            "NI_ACT_1881_SEC_138": (
                "138. Dishonour of cheque for insufficiency, etc., of funds in the account. Where any cheque drawn by a person "
                "is returned by the bank unpaid, provided that notice in writing was given within thirty days."
            )
        }

        faulty_memo = (
            "## Relevant Provisions\n"
            "Under Section 138, notice in writing must be delivered within ninety days to a division bench.\n"
        )

        res = verify_memo_statutory_claims(faulty_memo, stored_ni, primary_section="138")
        self.assertFalse(res.passed)
        violation_terms = [v["unsupported_term"] for v in res.violations]
        self.assertIn("bench_composition", violation_terms)

    def test_case_statute_attribution_validation(self):
        """Validates that 2026 CLD 39 is not attributed to Civil Procedure Code when it concerns FIO 2001."""
        precedent_cards = [
            {
                "citation": "2026 CLD 39",
                "court": "Lahore High Court",
                "case_name": "Bank Alfalah v. Industrial Gases",
                "text": "Ss.9 & 22---Financial Institutions (Recovery of Finances) Ordinance (XLVI of 2001)---Refusal to reframe issues."
            }
        ]

        # False memo attributing 2026 CLD 39 to CPC
        false_memo = (
            "In 2026 CLD 39, the Lahore High Court decided an appeal under the Civil Procedure Code.\n"
        )
        attribution_violations = verify_case_statute_attribution(false_memo, precedent_cards)
        self.assertEqual(len(attribution_violations), 1)
        self.assertEqual(attribution_violations[0]["citation"], "2026 CLD 39")
        self.assertEqual(attribution_violations[0]["false_enactment"], "Civil Procedure Code")

        # Correct memo attributing 2026 CLD 39 to FIO
        correct_memo = (
            "In 2026 CLD 39, the Lahore High Court held that refusal to reframe issues under FIO Section 22 is an interlocutory order.\n"
        )
        correct_violations = verify_case_statute_attribution(correct_memo, precedent_cards)
        self.assertEqual(len(correct_violations), 0)

if __name__ == "__main__":
    unittest.main()
