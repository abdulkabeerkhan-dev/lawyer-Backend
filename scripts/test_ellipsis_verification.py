import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from legal_ai.verification.memo_verifier import MemoVerifier

v = MemoVerifier()

# Test Case 1: Ellipsis omitting non-conditional text: "on the defendant as provided for in sub-section (5) of section 9,"
memo_clean_ellipsis = """# TEST MEMO
Section 10 of the Financial Institutions Ordinance, 2001 provides:
> (1) In any case in which the summons has been served ... the defendant shall not be entitled to defend the suit
"""

res1 = v.verify_memo(memo_clean_ellipsis)
print("Res 1 (non-blocking ellipsis):", res1["verdict"], "Failures:", len(res1["failures"]))
if res1["omitted_ellipses"]:
    print("Omitted slice:", res1["omitted_ellipses"][0]["omitted_text_between_segments"])
    print("Rendered in memo:", res1["omitted_ellipses"][0]["rendered_in_memo"][:140])

# Test Case 2: Ellipsis omitting "shall not":
# "In any case in which the summons has been served on the defendant ... be entitled to defend the suit"
# Omitted: "as provided for in sub-section (5) of section 9, the defendant shall not"
# This drops "shall not"! It MUST block!
memo_deceptive_ellipsis = """# TEST MEMO
Section 10 of the Financial Institutions Ordinance, 2001 provides:
> (1) In any case in which the summons has been served on the defendant ... be entitled to defend the suit
"""

res2 = v.verify_memo(memo_deceptive_ellipsis)
print("Res 2 (blocking ellipsis dropping 'shall not'):", res2["verdict"], "Failures:", len(res2["failures"]))
if res2["omitted_ellipses"]:
    print("Deceptive flags:", res2["omitted_ellipses"][0]["deceptive_flags"])
    print("Rendered in memo:", res2["omitted_ellipses"][0]["rendered_in_memo"][:140])

assert res1["quotes_passed"] == 1, "Res 1 quote should have passed"
assert res1["passed"] is True, "Res 1 should have passed verification completely"
assert res2["quotes_failed"] == 1, "Res 2 quote should have failed"
assert res2["passed"] is False, "Res 2 should have been blocked"
print("ELLIPSIS TESTS ALL PASSED PERFECTLY!")
