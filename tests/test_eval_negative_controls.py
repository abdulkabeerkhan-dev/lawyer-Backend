"""
tests/test_eval_negative_controls.py

Negative-Control Test Suite:
1. Test Bad Memo 1 (Banking Auction): asserts FAIL on forbidden claims:
   - s.109 appeal to District Judge
   - "ultra vires" for 50% direction
   - "no precedent exists"
   - advice to pay 20% without dismissal warning
2. Test Bad Memo 2 (MFLO s.4): asserts FAIL on forbidden claims:
   - [[CITATION REMOVED]] residual marker
   - statute surviving due to Parliament inaction fallacy
   - missing pending appeal before SC Shariat Appellate Bench
   - telling lawyer to 'rely confidently' on headnote-only record
3. Test Hand-Written Good Memo: asserts PASS on required points,
   forum/limitation accuracy, advice-risk compliance, currency check,
   and zero forbidden claims.
"""

import unittest
import os
import json
import asyncio
from eval.harness import (
    evaluate_single_case,
    check_advice_risk_in_text,
    check_currency_labels_in_text,
    check_forum_limitation_accuracy
)

# Bad Memo 1 snippet / representation from Audit
BAD_MEMO_BANKING_AUCTION = """# LEGAL MEMORANDUM: BANKING COURT AUCTION PROCEDURE UNDER FIO 2001 & ORDER XXI RULE 90 CPC
## EXECUTIVE SUMMARY
The statutory pre-deposit under Order XXI Rule 90 CPC is 20%, NOT 50%.
Any court order imposing a 50% pre-deposit is ultra vires and immediately challengeable.
On valuation: no precedent exists on whether a banking court must obtain a fresh valuation.

## STATUTORY FRAMEWORK & FORUM
Statutory Text (Paraphrased): The second proviso to Order XXI Rule 90 sets a 20% ceiling.
Appellate remedies:
If the Banking Court imposes a 50% deposit, file an Intra-Court Appeal under Section 109 CPC to the District Judge.
Alternatively, advise client to pay only 20% deposit.
"""

# Bad Memo 2 snippet / representation from Audit
BAD_MEMO_MFLO_S4 = """# LEGAL MEMORANDUM: STATUS OF SECTION 4 MFLO 1961
## EXECUTIVE SUMMARY
Section 4 remains operative despite the Federal Shariat Court declaration in Allah Rakha [[CITATION REMOVED: PLD 2000 Federal Shariat Court 1 ungrounded in retrieved records]].
Under the Article 203-D(2) proviso, the matter is referred to Parliament.
Because Parliament has not amended or repealed the statute within the prescribed period, the statute remains operative.

## CASE LAW
Rely confidently on Mst. Hayat Begum v. Rehman Malik (PLD 2023 Pesh 6) as the latest appellate authority.
"""

# Hand-Written Good Memo for Banking Auction (GS-003)
GOOD_MEMO_BANKING_AUCTION = """# LEGAL MEMORANDUM: BANKING COURT AUCTION & ORDER XXI RULE 90 PRE-DEPOSIT
**Date of Review**: 2026-10-02
**Statutory Currency**: [CHECKED, NO CHANGE FOUND: Pakistan Code on 2026-10-02]

## 1. EXECUTIVE SUMMARY & ADVICE
1. **Statutory Pre-Deposit Framework**: Under the second proviso to Order XXI Rule 90 of the Code of Civil Procedure 1908 (CPC), an executing court may require an objector to deposit up to 20% (one-fifth) of the auction amount or furnish security before entertaining an objection petition (2024 SCMR 1218).
2. **Legal Basis for Amounts Above 20%**: It is not found in the retrieved sources that an executing court has statutory authority to demand a 50% cash deposit under Order XXI Rule 90 CPC.
3. **CRITICAL PROCEDURAL WARNING**: Do NOT unilaterally ignore the Banking Court's 50% deposit direction or tender only 20% without court leave. Failure to deposit the amount ordered by the court risks immediate summary dismissal of your client's objection petition for non-compliance.
4. **Recommended Course of Action**:
   - Immediately file an urgent application before the Banking Court for modification, stay, or review of the deposit order, or deposit the amount under protest.
   - Appeal Route: Under Section 22 of the Financial Institutions (Recovery of Finances) Ordinance 2001 (FIO 2001), an appeal against any final decree or order of a Banking Court lies exclusively to the High Court within thirty (30) days. (Appeals do NOT lie to the District Judge or under Section 109 CPC).
   - Limitation for O.XXI r.90 objection: Thirty (30) days from auction date under Article 166 of the Limitation Act 1908.

## 2. VALUATION, RESERVE PRICE & PROCLAMATION DEFECTS
- Under Section 19 FIO 2001 and controlling superior court authorities (2026 CLD 96, 2023 SCMR 890), mortgaged property in banking execution sales must be evaluated by approved valuers on the Pakistan Banks' Association (PBA) panel.
- Gross inadequacy of reserve price fixed without fresh PBA evaluation constitutes a material irregularity under Order XXI Rule 90 CPC.
"""

async def hermetic_mock_judge(prompt: str):
    """Offline hermetic judge for unit testing that simulates LLM response."""
    return {
        "required_points_results": [
            {"point": "proviso", "passed": True, "evidence": "20% proviso mentioned"},
            {"point": "sources", "passed": True, "evidence": "sources addressed"},
            {"point": "scope", "passed": True, "evidence": "described at actual scope"},
            {"point": "warning", "passed": True, "evidence": "warned against non-compliance dismissal"},
            {"point": "appeal", "passed": True, "evidence": "s.22 FIO appeal route given"},
            {"point": "valuation", "passed": True, "evidence": "separated valuation and reserve price"}
        ],
        "forbidden_claims_results": [],
        "advice_risk_result": {"passed": True, "reason": "Adequate dismissal warning given"},
        "negative_findings_result": {"passed": True, "reason": "Stated not found in retrieved sources"}
    }

class TestEvalNegativeControls(unittest.TestCase):
    def setUp(self):
        gold_file = os.path.join(os.path.dirname(__file__), "..", "eval", "gold_set_examples.json")
        with open(gold_file, "r", encoding="utf-8") as f:
            self.gold_cases = {c["id"]: c for c in json.load(f)}

    def test_bad_memo_1_banking_auction_fails(self):
        gold_case = self.gold_cases["GS-003"]
        retrieved_citations = [{"citation": "2006 YLR 2776", "court": "Lahore High Court"}]
        
        eval_result = asyncio.run(evaluate_single_case(
            gold_case,
            BAD_MEMO_BANKING_AUCTION,
            retrieved_citations,
            llm_judge_fn=hermetic_mock_judge
        ))
        
        # Must FAIL overall
        self.assertFalse(eval_result["passed"], "Bad Memo 1 must fail evaluation.")
        
        # Must catch deterministic violations
        det_violations = eval_result["details"]["deterministic_violations"]
        self.assertTrue(
            any("s.109" in v.lower() or "district judge" in v.lower() for v in det_violations),
            "Must flag s.109 appeal to District Judge violation"
        )
        self.assertTrue(
            any("ultra vires" in v.lower() for v in det_violations),
            "Must flag ultra vires forbidden claim"
        )
        self.assertTrue(
            any("no precedent exists" in v.lower() for v in det_violations),
            "Must flag 'no precedent exists' forbidden claim"
        )
        
        # Advice risk must fail (advised 20% without dismissal warning)
        adv_res = eval_result["details"]["advice_risk"]
        self.assertFalse(adv_res["passed"], "Bad Memo 1 advice risk check must fail.")
        
        # Forum/limitation check must fail (claims District Judge / s.109 CPC)
        fl_res = eval_result["details"]["forum_limitation"]
        self.assertFalse(fl_res["passed"], "Bad Memo 1 forum check must fail.")

    def test_bad_memo_2_mflo_section_4_fails(self):
        gold_case = self.gold_cases["GS-002"]
        retrieved_citations = [{"citation": "PLD 2023 Pesh 6", "court": "Peshawar High Court"}]
        
        eval_result = asyncio.run(evaluate_single_case(
            gold_case,
            BAD_MEMO_MFLO_S4,
            retrieved_citations,
            llm_judge_fn=hermetic_mock_judge
        ))
        
        # Must FAIL overall
        self.assertFalse(eval_result["passed"], "Bad Memo 2 must fail evaluation.")
        
        # Must catch [[CITATION REMOVED]] marker and fail citation precision
        det_violations = eval_result["details"]["deterministic_violations"]
        self.assertTrue(
            any("citation removed" in v.lower() for v in det_violations),
            "Must detect [[CITATION REMOVED]] marker"
        )
        self.assertEqual(
            eval_result["metrics"]["citation_precision"],
            0.0,
            "Citation precision must be 0.0 when [[CITATION REMOVED]] marker exists"
        )
        
        # Advice risk must fail (missing pending appeal warning and currency check date)
        adv_res = eval_result["details"]["advice_risk"]
        self.assertFalse(adv_res["passed"], "Bad Memo 2 advice risk check must fail.")
        
        # Currency check must fail (no currency label)
        curr_res = eval_result["details"]["currency_check"]
        self.assertFalse(curr_res["passed"], "Bad Memo 2 currency check must fail.")

    def test_hand_written_good_memo_passes(self):
        gold_case = self.gold_cases["GS-003"]
        retrieved_citations = [
            {"citation": "2024 SCMR 1218", "court": "Supreme Court of Pakistan"},
            {"citation": "2026 CLD 96", "court": "High Court"},
            {"citation": "2023 SCMR 890", "court": "Supreme Court of Pakistan"}
        ]
        
        eval_result = asyncio.run(evaluate_single_case(
            gold_case,
            GOOD_MEMO_BANKING_AUCTION,
            retrieved_citations,
            llm_judge_fn=hermetic_mock_judge
        ))
        
        # Must PASS overall
        self.assertTrue(eval_result["passed"], f"Good Memo must pass. Failures: {eval_result.get('failed_reasons')}")
        
        # Zero violations
        self.assertEqual(len(eval_result["details"]["forbidden_claims"]), 0)
        self.assertEqual(len(eval_result["details"]["deterministic_violations"]), 0)
        
        # 100% citation precision
        self.assertEqual(eval_result["metrics"]["citation_precision"], 1.0)
        
        # Authority recall must be 1.0
        self.assertEqual(eval_result["metrics"]["key_authority_recall"], 1.0)
        
        # Forum & Limitation must pass
        self.assertTrue(eval_result["details"]["forum_limitation"]["passed"])
        
        # Advice risk must pass
        self.assertTrue(eval_result["details"]["advice_risk"]["passed"])
        
        # Currency check must pass
        self.assertTrue(eval_result["details"]["currency_check"]["passed"])

    def test_gs003_paraphrase_variants_all_flagged(self):
        """
        Requirement 10: Test that all paraphrase variants of '50% is unlawful'
        are deterministically flagged as scope violations.
        """
        gold_case = self.gold_cases["GS-003"]
        retrieved_citations = [{"citation": "2006 YLR 2776", "court": "Lahore High Court"}]
        
        variants = [
            "The Banking Court's order demanding a 50% deposit violates the express terms of Order XXI Rule 90.",
            "The direction to pre-deposit 50% is without statutory sanction under the Ordinance.",
            "Demanding a 50% pre-deposit is legally unsustainable.",
            "Any court order imposing a 50% pre-deposit is ultra vires and immediately challengeable.",
            "The Banking Court exceeds statutory authority by requiring a 50% deposit before hearing objections.",
            "The condition of 50% deposit is unlawful under the second proviso.",
            "Requiring a 50% pre-deposit from the judgment debtor is contrary to law."
        ]
        
        for variant in variants:
            memo = f"# LEGAL MEMORANDUM\n{variant}\nAppellate remedies: appeal to High Court under s.22 FIO 2001."
            res = asyncio.run(evaluate_single_case(
                gold_case,
                memo,
                retrieved_citations,
                llm_judge_fn=hermetic_mock_judge
            ))
            det_v = res["details"]["deterministic_violations"]
            self.assertTrue(
                any("50%" in v and ("ultra vires" in v.lower() or "unlawful" in v.lower()) for v in det_v),
                f"Variant failed to be flagged: '{variant}'. Violations: {det_v}"
            )
            self.assertFalse(res["passed"], f"Memo containing variant must fail: '{variant}'")

if __name__ == "__main__":
    unittest.main()
