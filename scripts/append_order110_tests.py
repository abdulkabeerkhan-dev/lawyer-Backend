import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_dir = os.path.dirname(script_dir)
test_file = os.path.join(repo_dir, "tests", "test_memo_verifier.py")

addition = '''

# ---------------------------------------------------------------------------
# ORDER 1.10 VERIFICATION TESTS
# ---------------------------------------------------------------------------

def test_order110_deceptive_truncation(verifier):
    """
    Order 1.10 - Item 7: Deceptive Truncation Check
    If a quote ends before sentence end and stored text continues with
    an exception clause (unless / provided that / except / save / subject to / notwithstanding / but),
    return BLOCK and show dropped text.
    Test: 'the defendant shall not be entitled to defend the suit' (drops 'unless he obtains leave ...').
    """
    truncated_memo = (
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\\n\\n"
        "> (1) In any case in which the summons has been served on the defendant as provided for in sub-section (5) of section 9, the defendant shall not be entitled to defend the suit"
    )
    res = verifier.verify_memo(truncated_memo)
    assert res["passed"] is False
    assert res["quotes_failed"] >= 1
    trunc_failures = [
        f for f in res["failures"]
        if "DECEPTIVE TRUNCATION" in f.get("issue", "") or "unless" in f.get("issue", "").lower()
    ]
    assert len(trunc_failures) >= 1, f"Expected deceptive truncation failure, got {res['failures']}"
    assert "unless" in trunc_failures[0]["issue"].lower()


def test_order110_disputed_label_unbannered(verifier):
    """
    Order 1.10 - Item 9: Disputed Provision Notice
    A disputed provision without the banner returns 'DISPUTED TEXT — human check required',
    NOT 'not in verified store'.
    """
    unbannered_memo = (
        "# RESEARCH MEMORANDUM\\n\\n"
        "Section 22 of the Financial Institutions Ordinance, 2001 governs appeals."
    )
    res = verifier.verify_memo(unbannered_memo, is_system_rendered=False)
    assert res["passed"] is False
    # Must report DISPUTED TEXT notice
    disputed_fails = [
        f for f in res["failures"]
        if "human check required" in f.get("issue", "").lower() or "DISPUTED TEXT" in f.get("label", "")
    ]
    assert len(disputed_fails) >= 1, f"Expected disputed notice, got {res['failures']}"
    # Must NOT report as missing / not in verified store
    assert not any("not in verified store" in f.get("issue", "").lower() for f in res["failures"])


def test_order110_diary_warns_unverified_citation():
    """
    Order 1.10 - Item 10: Private notes in diary warn, do not block, on unverified citations.
    """
    note_text = "Met client regarding dispute under Section 9999 of the Contract Act, 1872. Need to check limitation."
    from legal_ai.verification.memo_verifier import verify_pleading_citations_and_quotes
    v_res = verify_pleading_citations_and_quotes(note_text)
    assert v_res["passed"] is False
    assert v_res["total_failures"] >= 1
    # Check that it identifies the unverified citation
    assert any("Section 9999" in f.get("span", "") for f in v_res["failures"])


def test_order110_ni_act_staged_pending():
    """
    Order 1.10 - Item 11: NI Act re-ingested into data/pending with status UNVERIFIED.
    Section 138 title is 'Power to appoint notaries public'.
    """
    pending_path = os.path.join("data", "pending", "unified_statutes", "NI_ACT_1881.json")
    assert os.path.exists(pending_path), f"Pending NI Act file missing: {pending_path}"
    with open(pending_path, "r", encoding="utf-8") as f:
        recs = json.load(f)
    assert len(recs) == 168
    s138 = [r for r in recs if r.get("primary_num") == "138"][0]
    assert s138["title"] == "Power to appoint notaries public"
    assert s138["tier"] == "pending_verification"
    assert s138["verification_status"] == "UNVERIFIED"
    assert s138["quoting_allowed"] is False
'''

with open(test_file, "r", encoding="utf-8") as f:
    orig = f.read()

if "test_order110_deceptive_truncation" not in orig:
    with open(test_file, "a", encoding="utf-8") as f:
        f.write(addition)
    print("Appended tests to test_memo_verifier.py")
else:
    print("Tests already present in test_memo_verifier.py")
