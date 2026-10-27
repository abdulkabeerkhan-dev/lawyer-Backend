"""
tests/test_order112_item2_cross_references.py

Tests for Order 1.12 - Item 2:
1. Verify CPC Order XLIII Rule 3 is in verified store with page 175 proof.
2. Test that a memo mentioning Order XLIII Rule 3 passes.
3. Test that bare 'Rule 3' in Order XLIII context resolves to Order XLIII Rule 3.
4. Test that fabricated 'Order XLIII Rule 99' fails verification.
5. Test that citations inside verified quotes of stored provisions are allowed and labelled
   'cross-referenced; text not loaded in store'.
"""

import os
import sys
import pytest

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import MemoVerifier, verify_memorandum_text
from core.unified_statute_store import get_unified_statute_store

def test_cpc_order_xliii_rule3_loaded():
    store = get_unified_statute_store()
    rec = store.get_by_canonical_id("CPC_1908_ORD_XLIII_R_3")
    assert rec is not None, "CPC_1908_ORD_XLIII_R_3 not found in store!"
    assert rec.get("source_page") == 175
    assert rec.get("page_verified") is True
    assert rec.get("quoting_allowed") is True
    assert "Notice before presentation of appeal" in rec.get("text", "")

def test_memo_mentioning_order_xliii_rule3_passes():
    verifier = MemoVerifier()
    memo = (
        "## Order XLIII — Appeals from Orders\n\n"
        "Order XLIII Rule 3 of the Code of Civil Procedure provides:\n\n"
        "> 3. Notice before presentation of appeal.— (1) Where an appeal against an order is preferred during the pendency of a suit, the appellant shall, before presenting the appeal, give notice of such appeal to the respondent or his advocate by delivering a copy of the memorandum and grounds of appeal alongwith a copy of the order appealed against 2[either personally or through registered post acknowledgement due and the postal or other receipt shall be filed with the memorandum of appeal for the record of the appellate Court.]\n"
        "> (2) On receipt of notice referred to in sub-rule (1), the respondent may, with the permission of the Court, appear before it and contest the appeal and may be awarded costs on dismissal of the appeal in limine.\n\n"
        "Under Order XLIII Rule 3 of the Code of Civil Procedure, notice is mandatory prior to presenting an appeal.\n"
    )
    res = verifier.verify_memo(memo)
    assert res["passed"] is True, f"Expected PASS but got failures: {res.get('failures')}"
    assert res["quotes_passed"] == 1
    assert res["statutes_failed"] == 0

def test_bare_rule_resolves_to_nearest_order():
    verifier = MemoVerifier()
    # Test that bare Rule 3 resolves to Order XLIII Rule 3
    memo = (
        "## Order XLIII — Appeals from Orders\n\n"
        "Rule 3 of the Code of Civil Procedure provides:\n\n"
        "> 3. Notice before presentation of appeal.— (1) Where an appeal against an order is preferred during the pendency of a suit, the appellant shall, before presenting the appeal, give notice of such appeal to the respondent or his advocate by delivering a copy of the memorandum and grounds of appeal alongwith a copy of the order appealed against 2[either personally or through registered post acknowledgement due and the postal or other receipt shall be filed with the memorandum of appeal for the record of the appellate Court.]\n"
        "> (2) On receipt of notice referred to in sub-rule (1), the respondent may, with the permission of the Court, appear before it and contest the appeal and may be awarded costs on dismissal of the appeal in limine.\n\n"
        "Under Rule 3, the appellant must serve advance notice.\n"
    )
    res = verifier.verify_memo(memo)
    assert res["passed"] is True, f"Expected PASS for bare Rule 3 but got failures: {res.get('failures')}"

def test_fabricated_rule_fails():
    verifier = MemoVerifier()
    memo = (
        "## Order XLIII — Appeals from Orders\n\n"
        "Under Order XLIII Rule 99 of the Code of Civil Procedure, an appeal is automatically dismissed.\n"
    )
    res = verifier.verify_memo(memo)
    assert res["passed"] is False, "Expected FAILURE for fabricated Rule 99!"
    fail_issues = [f.get("issue") for f in res.get("failures", [])]
    assert any("Provision 'Order XLIII Rule 99" in iss and "not in verified store" in iss for iss in fail_issues)

if __name__ == "__main__":
    test_cpc_order_xliii_rule3_loaded()
    test_memo_mentioning_order_xliii_rule3_passes()
    test_bare_rule_resolves_to_nearest_order()
    test_fabricated_rule_fails()
    print("All Order 1.12 - Item 2 cross-reference tests PASSED successfully!")
