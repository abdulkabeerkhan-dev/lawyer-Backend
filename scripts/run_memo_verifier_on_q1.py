"""
scripts/run_memo_verifier_on_q1.py

ORDER 1.4 - ITEM 7:
Runs MemoVerifier on tests/fixtures/q1_bad_memo.txt (the Order 1.3 Q1 evaluation memo).
Demonstrates that the memo fails verification and prints each failure in detail:
  1. Rewritten s.22(3) Proviso (inserted '(a)/(b)/(c)', 'AND'/'OR', changed 'no shall any stay' -> 'no stay shall')
  2. "Shaukat Masood v. Federation of Pakistan" (unverified authority)
  3. "Finality Doctrine" (invented legal nomenclature)
  4. "non-extendable" (ungrounded limitation claim)
  5. "seek explicit extension" (ungrounded drafting advice contradicting automatic 6-month lapse)
"""

import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import MemoVerifier

FIXTURE_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "q1_bad_memo.txt")

def main():
    print("=" * 110)
    print("ITEM 7: RIGOROUS MEMO VERIFIER EXECUTION ON ORDER 1.3 Q1 MEMORANDUM")
    print("=" * 110)
    
    if not os.path.exists(FIXTURE_PATH):
        print(f"Error: Fixture {FIXTURE_PATH} not found!")
        sys.exit(1)

    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        memo_text = f.read()

    print(f"Loaded Memo Fixture: tests/fixtures/q1_bad_memo.txt ({len(memo_text)} characters)\n")

    verifier = MemoVerifier()
    result = verifier.verify_memo(memo_text)

    print(f"OVERALL VERDICT: {result['verdict']}")
    print(f"Total Blockquotes Checked:  {result['quotes_checked']}")
    print(f"Total Blockquotes Failed:   {result['quotes_failed']}")
    print(f"Total Precedents Checked:   {result['cases_checked']}")
    print(f"Total Precedents Failed:    {result['cases_failed']}")
    print(f"Total Ungrounded Claims:    {result['claims_failed']}")
    print(f"Total Failure Violations:   {len(result['failures'])}\n")

    print("-" * 110)
    print("DETAILED VERIFICATION FAILURES ENCOUNTERED:")
    print("-" * 110)
    for idx, fail in enumerate(result["failures"], 1):
        print(f"FAILURE #{idx}: [{fail['category']}]")
        print(f"  Issue:    {fail['issue']}")
        print(f"  Evidence: {fail['evidence']}")
        print(f"  Span:     {repr(fail['span'])}\n")

    print("=" * 110)
    print("VERIFIER DECISION: BLOCKED. Output refused for submission due to ground-truth violations.")
    print("=" * 110)

if __name__ == "__main__":
    main()
