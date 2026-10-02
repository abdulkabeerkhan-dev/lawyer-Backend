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

# Absolute quality targets for release gate
TARGET_CITATION_PRECISION = 1.0     # 100.0%
TARGET_OVERALL_PASS_RATE = 0.80      # 80.0%
TARGET_KEY_AUTHORITY_RECALL = 0.70   # 70.0%
TARGET_FORUM_LIMITATION_ACCURACY = 0.85  # 85.0%
TARGET_ADVICE_RISK_COMPLIANCE = 0.85     # 85.0%
TARGET_CURRENCY_LABEL_COVERAGE = 0.85    # 85.0%
TARGET_MAX_SCOPE_VIOLATIONS = 0

def check_release_gate(
    current_report: Dict[str, Any],
    baseline_report: Optional[Dict[str, Any]] = None,
    min_cases: int = 30
) -> bool:
    curr_summary = current_report.get("summary", current_report)
    base_summary = (baseline_report.get("summary", baseline_report) if baseline_report else {})

    print("="*80)
    print("RELEASE GATE EVALUATION")
    print(f"Minimum required approved cases threshold (N): {min_cases}")
    print("="*80)

    failures = []

    # 1. Non-vacuous evaluation check (N threshold)
    total_evaluated = curr_summary.get("total_evaluated", 0)
    print(f"- Total Cases Evaluated: {total_evaluated} (Required N >= {min_cases})")
    if total_evaluated < min_cases:
        failures.append(
            f"Release gate failed: Scored {total_evaluated} cases (minimum required: N={min_cases}). "
            "Vacuous pass on empty/unscored sets is strictly prohibited."
        )

    # 2. Strict Citation Precision (Target 100.0%)
    cit_prec = curr_summary.get("citation_precision", 1.0 if total_evaluated > 0 else 0.0)
    print(f"- Citation Precision: {cit_prec*100:.1f}% (Required: {TARGET_CITATION_PRECISION*100:.1f}%)")
    if cit_prec < TARGET_CITATION_PRECISION:
        failures.append(f"Citation precision {cit_prec*100:.1f}% is below mandatory {TARGET_CITATION_PRECISION*100:.1f}% target.")

    # 3. Scope Violations (Must be 0)
    curr_violations = curr_summary.get("scope_violations_count", 0)
    print(f"- Scope Violations: {curr_violations} (Required: {TARGET_MAX_SCOPE_VIOLATIONS})")
    if curr_violations > TARGET_MAX_SCOPE_VIOLATIONS:
        failures.append(f"Detected {curr_violations} scope violations in memorandum output (maximum allowed: {TARGET_MAX_SCOPE_VIOLATIONS}).")

    # 4. Absolute Metric Targets
    curr_pass = curr_summary.get("overall_pass_rate", 0.0)
    curr_recall = curr_summary.get("key_authority_recall", 0.0)
    curr_fl = curr_summary.get("forum_limitation_accuracy", 0.0)
    curr_ar = curr_summary.get("advice_risk_compliance", 0.0)
    curr_cc = curr_summary.get("currency_label_coverage", 0.0)

    print(f"- Overall Pass Rate: {curr_pass*100:.1f}% (Target: >={TARGET_OVERALL_PASS_RATE*100:.1f}%)")
    if curr_pass < TARGET_OVERALL_PASS_RATE:
        failures.append(f"Overall pass rate {curr_pass*100:.1f}% is below target threshold {TARGET_OVERALL_PASS_RATE*100:.1f}%.")

    if "key_authority_recall" in curr_summary:
        print(f"- Key Authority Recall: {curr_recall*100:.1f}% (Target: >={TARGET_KEY_AUTHORITY_RECALL*100:.1f}%)")
        if curr_recall < TARGET_KEY_AUTHORITY_RECALL:
            failures.append(f"Key authority recall {curr_recall*100:.1f}% is below target threshold {TARGET_KEY_AUTHORITY_RECALL*100:.1f}%.")

    if "forum_limitation_accuracy" in curr_summary:
        print(f"- Forum/Limitation Accuracy: {curr_fl*100:.1f}% (Target: >={TARGET_FORUM_LIMITATION_ACCURACY*100:.1f}%)")
        if curr_fl < TARGET_FORUM_LIMITATION_ACCURACY:
            failures.append(f"Forum/limitation accuracy {curr_fl*100:.1f}% is below target threshold {TARGET_FORUM_LIMITATION_ACCURACY*100:.1f}%.")

    if "advice_risk_compliance" in curr_summary:
        print(f"- Advice Risk Compliance: {curr_ar*100:.1f}% (Target: >={TARGET_ADVICE_RISK_COMPLIANCE*100:.1f}%)")
        if curr_ar < TARGET_ADVICE_RISK_COMPLIANCE:
            failures.append(f"Advice risk compliance {curr_ar*100:.1f}% is below target threshold {TARGET_ADVICE_RISK_COMPLIANCE*100:.1f}%.")

    if "currency_label_coverage" in curr_summary:
        print(f"- Currency Label Coverage: {curr_cc*100:.1f}% (Target: >={TARGET_CURRENCY_LABEL_COVERAGE*100:.1f}%)")
        if curr_cc < TARGET_CURRENCY_LABEL_COVERAGE:
            failures.append(f"Currency label coverage {curr_cc*100:.1f}% is below target threshold {TARGET_CURRENCY_LABEL_COVERAGE*100:.1f}%.")

    # 5. Regression checks against baseline if available
    if base_summary and total_evaluated >= min_cases:
        print(f"\nComparing against baseline (commit: {base_summary.get('git_commit', 'unknown')}):")
        
        base_pass = base_summary.get("overall_pass_rate", 0.0)
        if curr_pass < base_pass:
            failures.append(f"Overall pass rate regressed from {base_pass*100:.1f}% to {curr_pass*100:.1f}%.")

        curr_support = curr_summary.get("claim_support_rate", 0.0)
        base_support = base_summary.get("claim_support_rate", 0.0)
        if curr_support < base_support:
            failures.append(f"Claim support rate regressed from {base_support*100:.1f}% to {curr_support*100:.1f}%.")

        if "key_authority_recall" in base_summary:
            base_recall = base_summary.get("key_authority_recall", 0.0)
            if curr_recall < base_recall:
                failures.append(f"Key authority recall regressed from {base_recall*100:.1f}% to {curr_recall*100:.1f}%.")

        if "negative_finding_correctness" in base_summary:
            curr_neg = curr_summary.get("negative_finding_correctness", 0.0)
            base_neg = base_summary.get("negative_finding_correctness", 0.0)
            if curr_neg < base_neg:
                failures.append(f"Negative finding correctness regressed from {base_neg*100:.1f}% to {curr_neg*100:.1f}%.")

        if "forum_limitation_accuracy" in base_summary:
            base_fl = base_summary.get("forum_limitation_accuracy", 0.0)
            if curr_fl < base_fl:
                failures.append(f"Forum & limitation accuracy regressed from {base_fl*100:.1f}% to {curr_fl*100:.1f}%.")

        if "advice_risk_compliance" in base_summary:
            base_ar = base_summary.get("advice_risk_compliance", 0.0)
            if curr_ar < base_ar:
                failures.append(f"Advice risk compliance regressed from {base_ar*100:.1f}% to {curr_ar*100:.1f}%.")

        if "currency_label_coverage" in base_summary:
            base_cc = base_summary.get("currency_label_coverage", 0.0)
            if curr_cc < base_cc:
                failures.append(f"Currency label coverage regressed from {base_cc*100:.1f}% to {curr_cc*100:.1f}%.")

    if failures:
        print("\n[FAIL] RELEASE GATE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return False

    print("\n[PASS] RELEASE GATE PASSED: All quality, grounding, and non-regression criteria satisfied.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate release gate.")
    parser.add_argument("current_report", help="Path to current run report JSON.")
    parser.add_argument("--baseline", default=None, help="Path to baseline run report JSON.")
    parser.add_argument("--min-cases", type=int, default=30, help="Minimum number of cases required (default: 30).")
    args = parser.parse_args()

    with open(args.current_report, "r", encoding="utf-8") as f:
        curr = json.load(f)
    
    base = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, "r", encoding="utf-8") as f:
            base = json.load(f)

    passed = check_release_gate(curr, base, min_cases=args.min_cases)
    sys.exit(0 if passed else 1)
