"""
scripts/print_claim_checks_report.py

ITEM 9: RIGOROUS DETERMINISTIC CLAIM CHECKS EVALUATION REPORT
Prints exact claims, target statutory spans, and pass/fail results
evaluated with pinned production model (claude-haiku-4-5-20251001).
"""

import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_PATH = os.path.join(REPO_DIR, "data", "offline_model_eval_results.json")

def main():
    print("=" * 110)
    print("ITEM 9: DETERMINISTIC STATUTORY CLAIM CHECK RESULTS (PROD MODEL: claude-haiku-4-5-20251001)")
    print("=" * 110)

    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    if isinstance(results, dict):
        items = sorted(results.items())
    elif isinstance(results, list):
        items = [(r.get("query_id") or f"Q{i+1}", r) for i, r in enumerate(results)]
    else:
        items = []

    for qid, res in items:
        query = res.get("query", "")
        model = res.get("model_id", "claude-haiku-4-5-20251001")
        latency = res.get("latency_sec", 0)
        checks = res.get("checks", [])
        passed = sum(1 for c in checks if c.get("passed"))
        total = len(checks)
        verdict = "ALL PASS" if passed == total else f"PARTIAL ({passed}/{total})"
        
        print(f"\n[QUERY {qid}] (Model: {model} | Latency: {latency:.2f}s)")
        print(f"Query: \"{query}\"")
        print(f"Result: {verdict} ({passed}/{total} deterministic checks passed)")
        print("-" * 110)
        
        for idx, check in enumerate(checks, 1):
            prov = check.get("statutory_provision") or check.get("provision", "")
            span = check.get("supporting_span_from_store") or check.get("quoted_span", "")
            req = check.get("requirement", "")
            chk_status = "PASS" if check.get("passed") else "FAIL"
            print(f"  Check #{idx}: [{chk_status}]")
            print(f"    Target Provision:       {prov}")
            print(f"    Requirement:            {req}")
            print(f"    Supporting Store Span:  \"{span}\"")
        print()

    print("=" * 110)

if __name__ == "__main__":
    main()
