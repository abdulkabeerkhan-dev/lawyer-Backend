import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
"""
eval/release_gate.py

Release Gate Script:
- Compares current evaluation run summary against the last accepted benchmark run.
- Gate checks:
  1. Citation precision must be 1.0 (100%).
  2. Overall pass rate must not regress.
  3. Claim-support rate must not regress.
  4. Key authority recall must not regress.
  5. Scope violations count must not increase.
- Exits with code 0 on pass, code 1 on regression.
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, Optional

def check_release_gate(current_report: Dict[str, Any], baseline_report: Optional[Dict[str, Any]] = None) -> bool:
    curr_summary = current_report.get("summary", current_report)
    base_summary = (baseline_report.get("summary", baseline_report) if baseline_report else {})

    print("="*80)
    print("RELEASE GATE EVALUATION")
    print("="*80)

    regressions = []

    # 1. Strict Citation Precision (Target 100%)
    cit_prec = curr_summary.get("citation_precision", 1.0)
    print(f"- Citation Precision: {cit_prec*100:.1f}% (Required: 100.0%)")
    if cit_prec < 1.0:
        regressions.append(f"Citation precision {cit_prec*100:.1f}% is below mandatory 100% target.")

    # Compare against baseline if available
    if base_summary:
        print(f"Comparing against baseline (commit: {base_summary.get('git_commit', 'unknown')}):")
        
        # Pass Rate
        curr_pass = curr_summary.get("overall_pass_rate", 0.0)
        base_pass = base_summary.get("overall_pass_rate", 0.0)
        print(f"- Overall Pass Rate: current={curr_pass*100:.1f}%, baseline={base_pass*100:.1f}%")
        if curr_pass < base_pass:
            regressions.append(f"Overall pass rate regressed from {base_pass*100:.1f}% to {curr_pass*100:.1f}%.")

        # Claim Support Rate
        curr_support = curr_summary.get("claim_support_rate", 0.0)
        base_support = base_summary.get("claim_support_rate", 0.0)
        print(f"- Claim Support Rate: current={curr_support*100:.1f}%, baseline={base_support*100:.1f}%")
        if curr_support < base_support:
            regressions.append(f"Claim support rate regressed from {base_support*100:.1f}% to {curr_support*100:.1f}%.")

        # Key Authority Recall
        curr_recall = curr_summary.get("key_authority_recall", 0.0)
        base_recall = base_summary.get("key_authority_recall", 0.0)
        print(f"- Key Authority Recall: current={curr_recall*100:.1f}%, baseline={base_recall*100:.1f}%")
        if curr_recall < base_recall:
            regressions.append(f"Key authority recall regressed from {base_recall*100:.1f}% to {curr_recall*100:.1f}%.")

        # Scope Violations
        curr_violations = curr_summary.get("scope_violations_count", 0)
        base_violations = base_summary.get("scope_violations_count", 0)
        print(f"- Scope Violations: current={curr_violations}, baseline={base_violations}")
        if curr_violations > base_violations:
            regressions.append(f"Scope violations increased from {base_violations} to {curr_violations}.")

    if regressions:
        print("\n[FAIL] RELEASE GATE FAILED:")
        for r in regressions:
            print(f"  - {r}")
        return False

    print("\n[PASS] RELEASE GATE PASSED: All quality and grounding criteria satisfied.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate release gate.")
    parser.add_argument("current_report", help="Path to current run report JSON.")
    parser.add_argument("--baseline", default=None, help="Path to baseline run report JSON.")
    args = parser.parse_args()

    with open(args.current_report, "r", encoding="utf-8") as f:
        curr = json.load(f)
    
    base = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, "r", encoding="utf-8") as f:
            base = json.load(f)

    passed = check_release_gate(curr, base)
    sys.exit(0 if passed else 1)
