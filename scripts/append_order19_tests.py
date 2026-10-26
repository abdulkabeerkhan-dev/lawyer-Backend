import os

file_path = "tests/test_memo_verifier.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

order19_tests = '''
# ---------------------------------------------------------------------------
# ORDER 1.9 TEST SUITE & REGRESSION FIXTURES
# ---------------------------------------------------------------------------
from legal_ai.verification.memo_verifier import (
    attach_system_disputed_banner,
    verify_pleading_citations_and_quotes
)

def test_order19_rule_d_probes(verifier):
    """
    Order 1.9 - Item 2: Test Rule (d) probes for Memo E citations and real heading-only records.
    - 'Order XXXIX Rule 7': valid in-force record
    - 'Rule 2C': not in verified store
    - 'Section 61 FIO': not in verified store
    - 'CPC_1908_SEC_1': real title_only/heading-only record -> BLOCKED
    - 'CPC O.XXI R1, R2, R10' & 'PPC 415, 417': have operative text -> valid
    """
    # 1. Order XXXIX Rule 7
    v1, r1, rec1 = verifier.verify_statutory_citation("Order XXXIX Rule 7", "XXXIX")
    assert v1 is True, f"Rule 7 should be valid, got {r1}"
    assert rec1["tier"] in ["ingested_unreviewed", "page_verified"]

    # 2. Rule 2C (fake)
    v2, r2, rec2 = verifier.verify_statutory_citation("Order XXXIX Rule 2C", "XXXIX")
    assert v2 is False
    assert "not in verified store" in r2

    # 3. Section 61 FIO (fake section)
    v3, r3, rec3 = verifier.verify_statutory_citation("Section 61 of the Financial Institutions Ordinance, 2001")
    assert v3 is False
    assert "not in verified store" in r3

    # 4. CPC Section 1 (title_only in verified store)
    v4, r4, rec4 = verifier.verify_statutory_citation("Section 1 of the Code of Civil Procedure, 1908")
    assert v4 is False
    assert LABEL_HEADING_ONLY in r4

    # 5. CPC O.XXI R1, R2, R10 (have operative text)
    for r_num in ["1", "2", "10"]:
        v_r, reason_r, rec_r = verifier.verify_statutory_citation(f"Order XXI Rule {r_num}", "XXI")
        assert v_r is True, f"Order XXI Rule {r_num} should be valid, got {reason_r}"

    # 6. PPC 415, 417 (have operative text)
    for p_num in ["415", "417"]:
        v_p, reason_p, rec_p = verifier.verify_statutory_citation(f"Section {p_num} of the Pakistan Penal Code, 1860")
        assert v_p is True, f"PPC Section {p_num} should be valid, got {reason_p}"


def test_order19_ellipsis_conditional_vs_non_conditional(verifier):
    """
    Order 1.9 - Item 3: Omitted text always appears in memo.
    BLOCK only on negation/conditional patterns ('shall not', 'unless', 'except', 'provided that', 'subject to', 'notwithstanding', 'if').
    Do not block on 'as provided for in'.
    """
    # Non-blocking case: omits 'on the defendant as provided for in sub-section (5) of section 9,'
    memo_non_blocking = (
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\\n"
        "> (1) In any case in which the summons has been served ... the defendant shall not be entitled to defend the suit"
    )
    res_clean = verifier.verify_memo(memo_non_blocking)
    assert res_clean["quotes_passed"] == 1
    assert res_clean["passed"] is True
    assert len(res_clean["omitted_ellipses"]) == 1
    rendered = res_clean["omitted_ellipses"][0]["rendered_in_memo"]
    assert "OMITTED IN QUOTE (REVIEW)" in rendered
    assert "as provided for in" in rendered

    # Blocking case: omits 'shall not'
    memo_blocking = (
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\\n"
        "> (1) In any case in which the summons has been served on the defendant ... be entitled to defend the suit"
    )
    res_block = verifier.verify_memo(memo_blocking)
    assert res_block["quotes_failed"] == 1
    assert res_block["passed"] is False
    assert any("shall not" in f.get("issue", "") for f in res_block["failures"])


def test_order19_model_written_bold_banner_fails(verifier):
    """
    Order 1.9 - Item 4: Test that model-written plain-text or bold
    '**DISPUTED TEXT - human check required**' does NOT satisfy the disputed check.
    """
    memo_with_bold_banner = (
        "**DISPUTED TEXT - human check required**\\n\\n"
        "Section 22 of the Financial Institutions Ordinance, 2001 governs appeals."
    )
    res = verifier.verify_memo(memo_with_bold_banner, is_system_rendered=False)
    assert res["passed"] is False
    # Disputed section must fail because the bold text does not count as a system structural banner
    assert any("disputed" in f.get("issue", "").lower() for f in res["failures"])


def test_order19_pleading_export_with_client_facts():
    """
    Order 1.9 - Item 7: Pleading verification gate verifies only quoted statute/case spans,
    allowing narrative client facts without Rule (e) unsourced analysis failure.
    """
    pleading_with_facts = (
        "IN THE HIGH COURT OF SINDH AT KARACHI\\n"
        "Suit No. 1234 of 2026\\n\\n"
        "1. The Plaintiff is a banking company having its registered office at I.I. Chundrigar Road, Karachi.\\n"
        "2. The Defendant approached the Plaintiff for finance facility on 15th January 2024.\\n"
        "3. The Plaintiff granted the facility and Defendant executed finance agreements.\\n"
        "4. Section 9 of the Financial Institutions Ordinance, 2001 provides for presentation of plaint.\\n"
        "5. The Plaintiff prays for a decree in terms of Section 10 of the Financial Institutions Ordinance, 2001."
    )
    # verify_pleading_citations_and_quotes allows client facts
    p_res = verify_pleading_citations_and_quotes(pleading_with_facts)
    assert p_res["passed"] is True
    assert p_res["total_failures"] == 0

    # If an invalid fake statute citation is added, it MUST block
    bad_pleading = pleading_with_facts + "\\n6. Section 9999 of the Code of Civil Procedure, 1908 applies."
    p_bad = verify_pleading_citations_and_quotes(bad_pleading)
    assert p_bad["passed"] is False
    assert p_bad["total_failures"] >= 1


def test_order19_repaired_memo_f_accepted(verifier):
    """
    Order 1.9 - Item 11: Repaired Memo F with authentic s.10(1) quote PASSES.
    """
    repaired_memo_f = (
        "# RESEARCH MEMORANDUM: Financial Institutions Ordinance, 2001\\n\\n"
        "### 1. Leave to Defend Procedure\\n\\n"
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\\n\\n"
        "> (1) In any case in which the summons has been served on the defendant as provided for in sub-section (5) of section 9, the defendant shall not be entitled to defend the suit unless he obtains leave from the Banking Court as hereinafter provided to defend the same; and, in default of his doing so, the allegations of fact in the plaint shall be deemed to be admitted and the Banking Court shall forthwith proceed to pass judgment and decree in favour of the plaintiff.\\n\\n"
        "### 2. Appeals\\n\\n"
        "Section 22 of the Financial Institutions Ordinance, 2001 governs appeals."
    )
    # Attach system banner
    system_rendered = attach_system_disputed_banner(repaired_memo_f, [{"provision": "FIO_2001_SEC_22"}])
    res = verifier.verify_memo(system_rendered, is_system_rendered=True)
    assert res["passed"] is True, f"Repaired Memo F expected to PASS, got {res['failures']}"
    assert res["verdict"] == "ACCEPTED"
    assert res["total_failures"] == 0
'''

content += order19_tests

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content)

print("Order 1.9 tests appended to test_memo_verifier.py")
