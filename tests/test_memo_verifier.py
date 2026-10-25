"""
tests/test_memo_verifier.py

ORDER 1.4 - ITEM 7:
Tests the memo verifier on tests/fixtures/q1_bad_memo.txt.
Asserts that the memo verifier strictly rejects the memo (verdict == "BLOCKED")
and flags all 5 critical defects:
  1. Rewritten proviso (structural hallucination / blockquote mismatch)
  2. "Shaukat Masood v. Federation of Pakistan" (unverified authority)
  3. "Finality Doctrine" (ungrounded claim)
  4. "non-extendable" (ungrounded limitation claim)
  5. "seek explicit extension" (ungrounded stay extension advice)
"""

import os
import sys
import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import MemoVerifier

FIXTURE_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "q1_bad_memo.txt")

def test_q1_bad_memo_fixture_exists():
    assert os.path.exists(FIXTURE_PATH), "Fixture tests/fixtures/q1_bad_memo.txt must exist"

def test_q1_bad_memo_fails_verifier():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        memo_text = f.read()

    verifier = MemoVerifier()
    res = verifier.verify_memo(memo_text)

    # 1. Assert overall verdict is BLOCKED
    assert res["passed"] is False, "Order 1.3 Q1 memo must NOT pass verification"
    assert res["verdict"] == "BLOCKED", "Verdict must be BLOCKED"

    failures = res["failures"]
    failure_issues = " ".join([f["issue"] for f in failures])
    failure_spans = " ".join([f["span"] for f in failures])
    combined_failure_text = failure_issues + " " + failure_spans

    # 2. Assert failure on rewritten proviso / structural hallucination
    has_proviso_failure = any(
        f["category"] in ("BLOCKQUOTE_HALLUCINATION", "STRUCTURAL_HALLUCINATION")
        for f in failures
    )
    assert has_proviso_failure, "Verifier must catch the rewritten proviso / structural hallucination"

    # 3. Assert failure on Shaukat Masood v. Federation of Pakistan
    assert "Shaukat Masood" in combined_failure_text, (
        "Verifier must flag 'Shaukat Masood v. Federation of Pakistan' as unverified authority"
    )

    # 4. Assert failure on Finality Doctrine
    assert "Finality Doctrine" in combined_failure_text, (
        "Verifier must flag 'Finality Doctrine' as ungrounded claim"
    )

    # 5. Assert failure on non-extendable
    assert "non-extendable" in combined_failure_text, (
        "Verifier must flag 'non-extendable' as ungrounded limitation claim"
    )

    # 6. Assert failure on seek explicit extension
    assert "seek explicit extension" in combined_failure_text, (
        "Verifier must flag 'seek explicit extension' as ungrounded advice"
    )

def test_clean_grounded_quote_passes():
    """Grounded quote from authentic CPC Order XXXIX Rule 1 must pass."""
    grounded_snippet = (
        "> Where in any suit it is proved by affidavit or otherwise\n"
        "> that any property in dispute in a suit is in danger of being wasted"
    )
    verifier = MemoVerifier()
    quotes = verifier.extract_blockquotes(grounded_snippet)
    assert len(quotes) == 1
    # Check that substring matches in CPC_1908
    q_clean = verifier.clean_quote_markup(quotes[0]).lower()
    cpc_text = verifier.provisions_cache.get("CPC_1908_ORD_XXXIX_R_1", "").lower()
    # Em-dash normalization
    cpc_text_clean = cpc_text.replace("__", "").replace("—", "").replace("-", "")
    q_clean_cmp = q_clean.replace("__", "").replace("—", "").replace("-", "")
    assert "where in any suit it is proved by affidavit or otherwise" in cpc_text
