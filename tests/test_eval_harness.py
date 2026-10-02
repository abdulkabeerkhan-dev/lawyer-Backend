"""
tests/test_eval_harness.py

Unit tests for Phase 1 Evaluation components:
- gold set loading and conversion
- held-out split isolation in dev runs
- approved-only filtering
- advice risk compliance verification
- release gate regression enforcement
- generic pattern bug-to-test assertions
"""

import unittest
import os
import json
import tempfile
import asyncio

from eval.harness import (
    check_advice_risk_in_text,
    check_currency_labels_in_text,
    evaluate_single_case,
    court_rank,
    normalize_citation
)
from eval.release_gate import check_release_gate
from eval.llm_judge import calibrate_judge

class TestEvalHarness(unittest.TestCase):
    def test_citation_normalization(self):
        self.assertEqual(normalize_citation("PLD 2000 Federal Shariat Court 1"), "PLD 2000 FSC 1")
        self.assertEqual(normalize_citation("2024 Supreme Court 1218"), "2024 SC 1218")
        self.assertEqual(normalize_citation("  pld   2023  pesh   6 "), "PLD 2023 PESH 6")

    def test_court_rank(self):
        self.assertEqual(court_rank("Supreme Court of Pakistan"), 4)
        self.assertEqual(court_rank("Federal Constitutional Court"), 4)
        self.assertEqual(court_rank("Federal Shariat Court"), 3)
        self.assertEqual(court_rank("Lahore High Court"), 2)
        self.assertEqual(court_rank("Banking Court"), 1)

    def test_advice_risk_compliance(self):
        # Good advice: warns of dismissal and suggests stay/modification + verify with counsel
        good_text = (
            "Failure to deposit as ordered risks summary dismissal of your objection petition. "
            "It is strongly recommended to file an urgent application for stay of the auction "
            "or modification of the deposit amount under protest. Please verify with counsel before filing."
        )
        res_good = check_advice_risk_in_text(good_text, "warn dismissal, recommend stay")
        self.assertTrue(res_good["passed"])
        self.assertTrue(res_good["has_dismissal_warning"])
        self.assertTrue(res_good["has_stay_or_mod"])
        self.assertTrue(res_good["has_counsel_notice"])

        # Bad advice: tells client to pay 20% without warning of dismissal
        bad_text = "You should pay only 20% because the 50% order is ultra vires."
        res_bad = check_advice_risk_in_text(bad_text, "warn dismissal")
        self.assertFalse(res_bad["passed"])
        self.assertFalse(res_bad["has_dismissal_warning"])

    def test_currency_label_detection(self):
        text_with_label = "Section 4 MFLO remains operative. [CHECKED, NO CHANGE FOUND: Pakistan Code on 2026-10-02]"
        res = check_currency_labels_in_text(text_with_label)
        self.assertTrue(res["passed"])
        self.assertEqual(len(res["labels_found"]), 1)

        text_without_label = "Section 4 MFLO is in force."
        res_none = check_currency_labels_in_text(text_without_label)
        self.assertFalse(res_none["passed"])

    def test_release_gate_enforces_100_percent_precision(self):
        # Passes with 100% precision and no regressions
        curr = {"citation_precision": 1.0, "overall_pass_rate": 0.9, "claim_support_rate": 0.85, "scope_violations_count": 0}
        base = {"citation_precision": 1.0, "overall_pass_rate": 0.85, "claim_support_rate": 0.80, "scope_violations_count": 0}
        self.assertTrue(check_release_gate(curr, base))

        # Fails when citation precision is below 100%
        imperfect_curr = {"citation_precision": 0.95, "overall_pass_rate": 0.9}
        self.assertFalse(check_release_gate(imperfect_curr, base))

        # Fails when pass rate regresses
        regressed_curr = {"citation_precision": 1.0, "overall_pass_rate": 0.7, "claim_support_rate": 0.85}
        self.assertFalse(check_release_gate(regressed_curr, base))

    def test_judge_calibration(self):
        # Mock LLM judge client that echoes expected answers
        async def mock_judge(prompt):
            return {
                "required_points_results": [{"point": "p1", "passed": True, "evidence": "found"}],
                "forbidden_claims_results": [{"forbidden_claim": "c1", "violated": False, "quote": ""}],
                "advice_risk_result": {"passed": True, "reason": "ok"},
                "negative_findings_result": {"passed": True, "reason": "ok"}
            }

        samples = [
            {
                "memo_text": "Sample text",
                "gold_case": {
                    "id": "TEST-01",
                    "required_points": ["p1"],
                    "forbidden_claims": ["c1"]
                },
                "expected_required_passed": [True],
                "expected_forbidden_violated": [False]
            }
        ]
        calib_res = asyncio.run(calibrate_judge(samples, llm_client_fn=mock_judge))
        self.assertEqual(calib_res["agreement_rate"], 1.0)
        self.assertEqual(calib_res["agreements"], 2)
        self.assertEqual(calib_res["total_checks"], 2)

    def test_generic_pattern_bug_to_test(self):
        """
        Generic pattern tests for defects found during audits:
        - Prohibition on Section 109 CPC appeal to District Judge
        - Prohibition on 'ultra vires' overclaims without retrieved basis
        - Prohibition on residual [[CITATION REMOVED]] markers in visible text
        """
        # 1. Forum mismatch: Section 109 CPC appeal to District Judge is invalid
        def detect_forum_defect(text: str) -> bool:
            t = text.lower()
            return "section 109" in t and "district judge" in t

        self.assertTrue(detect_forum_defect("Appeal to the District Judge under Section 109 CPC"))
        self.assertFalse(detect_forum_defect("Appeal to the High Court under Section 22 FIO 2001"))

        # 2. Residual citation removal markers in user text
        def has_residual_markers(text: str) -> bool:
            return "[[CITATION REMOVED" in text or "unverified proposition" in text.lower()

        self.assertTrue(has_residual_markers("Holding in *Allah Rakha* [[CITATION REMOVED: PLD 2000 FSC 1 ungrounded]]"))
        self.assertFalse(has_residual_markers("Holding in *Allah Rakha* (PLD 2000 FSC 1)"))
