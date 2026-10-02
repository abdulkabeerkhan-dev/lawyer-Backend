import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os
import sys
import json
import argparse
from typing import Dict, Any, Optional

def check_release_gate(
    current_report: Dict[str, Any],
    baseline_report: Optional[Dict[str, Any]] = None,
    min_cases: int = 1
) -> bool:
    curr_summary = current_report.get("summary", current_report)
    base_summary = (baseline_report.get("summary", baseline_report) if baseline_report else {})

    print("="*80)
    print("RELEASE GATE EVALUATION")
    print(f"Minimum required cases threshold (N): {min_cases}")
    print("="*80)

    regressions = []

    # 1. Non-vacuous evaluation check (N threshold)
    total_evaluated = curr_summary.get("total_evaluated", 0)
    print(f"- Total Cases Evaluated: {total_evaluated} (Required N >= {min_cases})")
    if total_evaluated < min_cases:
        regressions.append(
            f"Release gate failed: Scored {total_evaluated} approved cases (minimum required: N={min_cases}). "
            "Vacuous pass on empty/unscored sets is strictly prohibited."
        )

    # 2. Strict Citation Precision (Target 100%)
    cit_prec = curr_summary.get("citation_precision", 1.0 if total_evaluated > 0 else 0.0)
    print(f"- Citation Precision: {cit_prec*100:.1f}% (Required: 100.0%)")
    if cit_prec < 1.0:
        regressions.append(f"Citation precision {cit_prec*100:.1f}% is below mandatory 100% target.")

    # 3. Scope Violations (Must be 0)
    curr_violations = curr_summary.get("scope_violations_count", 0)
    print(f"- Scope Violations: {curr_violations} (Required: 0)")
    if curr_violations > 0:
        regressions.append(f"Detected {curr_violations} scope violations in memorandum output.")

    # Compare against baseline if available
    if base_summary and total_evaluated >= min_cases:
        print(f"\nComparing against baseline (commit: {base_summary.get('git_commit', 'unknown')}):")
        
        # Pass Rate
        curr_pass = curr_summary.get("overall_pass_rate", 0.0)
        base_pass = base_summary.get("overall_pass_rate", 0.0)
        print(f"- Overall Pass Rate: current={curr_pass*100:.1f}%, baseline={base_pass*100:.1f}%")
        if curr_pass < base_pass:
            regressions.append(f"Overall pass rate regressed from {base_pass*100:.1f}% to {curr_pass*100:.1f}%.")

        # Claim Support Rate (Judge-based heuristic until Phase 3)
        curr_support = curr_summary.get("claim_support_rate", 0.0)
        base_support = base_summary.get("claim_support_rate", 0.0)
        print(f"- Claim Support Rate [Judge-based]: current={curr_support*100:.1f}%, baseline={base_support*100:.1f}%")
        if curr_support < base_support:
            regressions.append(f"Claim support rate regressed from {base_support*100:.1f}% to {curr_support*100:.1f}%.")

        # Key Authority Recall
        curr_recall = curr_summary.get("key_authority_recall", 0.0)
        base_recall = base_summary.get("key_authority_recall", 0.0)
        print(f"- Key Authority Recall: current={curr_recall*100:.1f}%, baseline={base_recall*100:.1f}%")
        if curr_recall < base_recall:
            regressions.append(f"Key authority recall regressed from {base_recall*100:.1f}% to {curr_recall*100:.1f}%.")

        # Negative Finding Correctness
        curr_neg = curr_summary.get("negative_finding_correctness", 0.0)
        base_neg = base_summary.get("negative_finding_correctness", 0.0)
        print(f"- Negative Finding Correctness: current={curr_neg*100:.1f}%, baseline={base_neg*100:.1f}%")
        if curr_neg < base_neg:
            regressions.append(f"Negative finding correctness regressed from {base_neg*100:.1f}% to {curr_neg*100:.1f}%.")

        # Forum & Limitation Accuracy
        curr_fl = curr_summary.get("forum_limitation_accuracy", 0.0)
        base_fl = base_summary.get("forum_limitation_accuracy", 0.0)
        print(f"- Forum/Limitation Accuracy: current={curr_fl*100:.1f}%, baseline={base_fl*100:.1f}%")
        if curr_fl < base_fl:
            regressions.append(f"Forum & limitation accuracy regressed from {base_fl*100:.1f}% to {curr_fl*100:.1f}%.")

        # Advice Risk Compliance
        curr_ar = curr_summary.get("advice_risk_compliance", 0.0)
        base_ar = base_summary.get("advice_risk_compliance", 0.0)
        print(f"- Advice Risk Compliance: current={curr_ar*100:.1f}%, baseline={base_ar*100:.1f}%")
        if curr_ar < base_ar:
            regressions.append(f"Advice risk compliance regressed from {base_ar*100:.1f}% to {curr_ar*100:.1f}%.")

        # Currency Label Coverage
        curr_cc = curr_summary.get("currency_label_coverage", 0.0)
        base_cc = base_summary.get("currency_label_coverage", 0.0)
        print(f"- Currency Label Coverage: current={curr_cc*100:.1f}%, baseline={base_cc*100:.1f}%")
        if curr_cc < base_cc:
            regressions.append(f"Currency label coverage regressed from {base_cc*100:.1f}% to {curr_cc*100:.1f}%.")

    if regressions:
        print("\n[FAIL] RELEASE GATE FAILED:")
        for r in regressions:
            print(f"  - {r}")
        return False

    print("\n[PASS] RELEASE GATE PASSED: All quality, grounding, and non-regression criteria satisfied.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate release gate.")
    parser.add_argument("current_report", help="Path to current run report JSON.")
    parser.add_argument("--baseline", default=None, help="Path to baseline run report JSON.")
    parser.add_argument("--min-cases", type=int, default=1, help="Minimum number of cases required.")
    args = parser.parse_args()

    with open(args.current_report, "r", encoding="utf-8") as f:
        curr = json.load(f)
    
    base = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, "r", encoding="utf-8") as f:
            base = json.load(f)

    passed = check_release_gate(curr, base, min_cases=args.min_cases)
    sys.exit(0 if passed else 1)
