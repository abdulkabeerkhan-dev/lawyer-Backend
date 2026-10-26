"""
tests/test_memo_verifier.py

ORDER 1.5 - ITEM 6:
Unit tests for rewritten rule-based MemoVerifier.
Tests Rules (a)-(e) independently and rigorously against authentic fixtures and synthetic probes.
"""

import os
import sys
import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import (
    MemoVerifier,
    LABEL_UNVERIFIED_AUTHORITY,
    LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
    LABEL_UNSOURCED_ANALYSIS,
    LABEL_DISPUTED_TEXT_NOTICE,
    LABEL_MISATTRIBUTED_QUOTE
)

FIXTURE_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "q1_bad_memo.txt")
MEMO_D_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "memo_D.md")
MEMO_E_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "memo_E.md")
MEMO_F_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "memo_F.md")

@pytest.fixture(scope="module")
def verifier():
    return MemoVerifier()

# ---------------------------------------------------------------------------
# RULE (a): Quote normalization & comparison
# ---------------------------------------------------------------------------
def test_rule_a_quote_normalized_passes(verifier):
    """
    Rule (a): Quote matches stored provision after normalizing whitespace,
    soft hyphens (\xad), and amendment markers 1[...].
    """
    # Authentic quote from CPC Order XXXIX Rule 1 with soft hyphens, blockquote markers, and extra whitespace
    quote_with_artifacts = (
        "> Where in any suit it is proved by af\xadfidavit or otherwise\n"
        "> (a) that any prop\xaderty in dispute in a suit is in danger of being wasted"
    )
    matched, cid, diff = verifier.verify_quote_against_store(quote_with_artifacts)
    assert matched is True
    assert cid == "CPC_1908_ORD_XXXIX_R_1"

def test_rule_a_quote_with_invented_wording_fails(verifier):
    """
    Rule (a): Quote that alters authentic words or injects structural bullet points fails.
    """
    invented_quote = (
        "> Where in any suit it is proved by affidavit that property is wasted\n"
        "> and (a) an immediate ex-parte injunction shall issue permanently"
    )
    matched, cid, diff = verifier.verify_quote_against_store(invented_quote)
    assert matched is False
    assert diff is not None
    assert "differing text" in diff.lower() or "mismatch" in diff.lower() or "does not match" in diff.lower()

# ---------------------------------------------------------------------------
# RULE (b): System banner structural exemption
# ---------------------------------------------------------------------------
def test_rule_b_system_banner_exempt(verifier):
    """
    Rule (b): System banners starting with `> [!` are exempted by structural marker.
    """
    memo_with_banner = (
        "> [!WARNING]\n"
        "> **HUMAN VERIFICATION REQUIRED**: This provision has not been page verified.\n"
        "> Consult official gazette page images before filing.\n\n"
        "Section 126 of the Contract Act, 1872 defines a contract of guarantee."
    )
    quotes = verifier.extract_blockquotes(memo_with_banner)
    assert len(quotes) == 0, "System banner starting with '> [!' must be exempted structurally"

# ---------------------------------------------------------------------------
# RULE (c): Case authority indexing
# ---------------------------------------------------------------------------
def test_rule_c_indexed_case_passes(verifier):
    """
    Rule (c): An authority present in the apex judicial index passes.
    """
    # Check with an indexed citation from corpus
    if verifier.citations_set:
        sample_cit = list(verifier.citations_set)[0]
        auth = {"type": "citation", "span": sample_cit}
        assert verifier.verify_case_authority(auth) is True

def test_rule_c_unindexed_case_fails(verifier):
    """
    Rule (c): An unindexed authority triggers UNVERIFIED AUTHORITY.
    """
    auth = {
        "type": "case_title",
        "span": "Muhammad Fabricated v. Nonexistent Bank",
        "p1": "Muhammad Fabricated",
        "p2": "Nonexistent Bank"
    }
    assert verifier.verify_case_authority(auth) is False

    memo = "In Muhammad Fabricated v. Nonexistent Bank, the court held that no stay shall issue."
    res = verifier.verify_memo(memo)
    assert res["passed"] is False
    unverified_failures = [f for f in res["failures"] if f["rule"] == "(c)"]
    assert len(unverified_failures) > 0
    assert unverified_failures[0]["label"] == LABEL_UNVERIFIED_AUTHORITY

# ---------------------------------------------------------------------------
# RULE (d): Sourced and in-force statutory citations
# ---------------------------------------------------------------------------
def test_rule_d_sourced_in_force_statute_passes(verifier):
    """
    Rule (d): Sourced, in-force provision (e.g. Contract Act s.126) passes.
    """
    is_valid, reason, rec = verifier.verify_statutory_citation("Section 126 of the Contract Act, 1872")
    assert is_valid is True
    assert rec is not None
    assert rec.get("tier") in ["ingested_unreviewed", "page_verified", "ground_truth"]

def test_rule_d_unsourced_statute_fails(verifier):
    """
    Rule (d): Provision from an unsourced act (e.g. Constitution or Arbitration Act) fails
    with CITED PROVISION NOT IN VERIFIED STORE.
    """
    # 1. Present in store but unsourced tier: Article 199 Constitution
    is_valid, reason, rec = verifier.verify_statutory_citation("Article 199 of the Constitution")
    assert is_valid is False
    assert "tier='unsourced'" in reason or "not sourced" in reason or "not in verified store" in reason

    # 2. Absent from store entirely
    is_valid2, reason2, rec2 = verifier.verify_statutory_citation("Section 18 of the Arbitration Act, 1940")
    assert is_valid2 is False

    memo = "Article 199 of the Constitution governs constitutional writ jurisdiction."
    res = verifier.verify_memo(memo)
    assert res["passed"] is False
    stat_failures = [f for f in res["failures"] if f["rule"] == "(d)"]
    assert len(stat_failures) > 0
    assert stat_failures[0]["label"] == LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE

# ---------------------------------------------------------------------------
# RULE (e): Unsourced analysis sentences
# ---------------------------------------------------------------------------
def test_rule_e_unsourced_sentence_flagged(verifier):
    """
    Rule (e): Narrative sentence asserting legal conclusions without supporting authority
    is labelled UNSOURCED ANALYSIS.
    """
    memo = (
        "Under the Finality Doctrine, concluded proceedings cannot be reopened under any circumstances.\n"
        "Appellants must seek an explicit extension from the executing judge prior to expiry."
    )
    res = verifier.verify_memo(memo)
    assert res["passed"] is False
    unsourced = [f for f in res["failures"] if f["rule"] == "(e)"]
    assert len(unsourced) >= 2
    for u in unsourced:
        assert u["label"] == LABEL_UNSOURCED_ANALYSIS

# ---------------------------------------------------------------------------
# COMPREHENSIVE FIXTURE TEST: Q1 Bad Memo
# ---------------------------------------------------------------------------
def test_q1_bad_memo_fixture_blocked(verifier):
    """
    Verifies that the authentic Order 1.3 Q1 bad memo fixture is strictly BLOCKED
    by rules (a), (c), (d), and (e).
    """
    assert os.path.exists(FIXTURE_PATH), "tests/fixtures/q1_bad_memo.txt must exist"
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        memo_text = f.read()

    res = verifier.verify_memo(memo_text)
    assert res["passed"] is False
    assert res["verdict"] == "BLOCKED"

    rules_triggered = set(f["rule"] for f in res["failures"])
    assert "(a)" in rules_triggered, "Must fail Rule (a) on altered statutory quote"
    assert "(c)" in rules_triggered, "Must fail Rule (c) on unindexed case authority"
    assert "(d)" in rules_triggered, "Must fail Rule (d) on unsourced / disputed statute citations"
    assert "(e)" in rules_triggered, "Must fail Rule (e) on unsourced analytical sentences"

    # Verify specific labels
    labels = set(f.get("label") for f in res["failures"] if f.get("label"))
    assert LABEL_UNVERIFIED_AUTHORITY in labels
    assert LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE in labels
    assert LABEL_UNSOURCED_ANALYSIS in labels

# ---------------------------------------------------------------------------
# ORDER 1.7 - ITEM 9: REGRESSION FIXTURES (MEMO D, MEMO E, MEMO F)
# ---------------------------------------------------------------------------
def test_holdout_memo_d_fixture_accepted(verifier):
    """
    Memo D (clean holdout): Must PASS with verdict ACCEPTED and zero failures.
    - All quotes verbatim (including 'detained in prison' dropping amendment markers).
    - All statutory citations valid and in-force.
    """
    assert os.path.exists(MEMO_D_PATH), f"Fixture missing: {MEMO_D_PATH}"
    with open(MEMO_D_PATH, "r", encoding="utf-8") as f:
        memo_text = f.read()

    res = verifier.verify_memo(memo_text)
    assert res["passed"] is True, f"Memo D expected to PASS, but failed: {res['failures']}"
    assert res["verdict"] == "ACCEPTED"
    assert res["total_failures"] == 0
    assert res["quotes_passed"] == 3
    assert res["quotes_failed"] == 0
    assert res["statutes_failed"] == 0
    assert res["unsourced_sentences_count"] == 0

def test_holdout_memo_e_fixture_blocked(verifier):
    """
    Memo E (adversarial holdout): Must be strictly BLOCKED.
    Verifies detection of:
    1. Substantive quote edits ('two years' instead of 'one year', 'in civil prison' instead of 'inprison').
    2. Misattributed quote (Rule 4 text attributed to Rule 2).
    3. Unindexed authority (2012 SCMR 99999).
    4. Unindexed provision (Section 61 FIO -> 'not in verified store').
    5. Unsourced analysis sentences (including sentence relying on unverified authority).
    6. Ellipsis quotes parsed with omitted text captured.
    """
    assert os.path.exists(MEMO_E_PATH), f"Fixture missing: {MEMO_E_PATH}"
    with open(MEMO_E_PATH, "r", encoding="utf-8") as f:
        memo_text = f.read()

    res = verifier.verify_memo(memo_text)
    assert res["passed"] is False, "Memo E expected to be BLOCKED, but passed"
    assert res["verdict"] == "BLOCKED"
    assert res["total_failures"] >= 6

    # 1. Unmatched quotes with word-level diffs
    unmatched_quotes = [f for f in res["failures"] if f.get("category") == "UNMATCHED_QUOTE"]
    assert len(unmatched_quotes) >= 2
    for uq in unmatched_quotes:
        assert "word-level diff:" in uq["issue"].lower()

    # 2. Misattributed quote
    misattributed = [f for f in res["failures"] if f.get("category") == "MISATTRIBUTED_QUOTE"]
    assert len(misattributed) == 1
    assert misattributed[0]["cited_id"] == "CPC_1908_ORD_XXXIX_R_2"
    assert misattributed[0]["matched_id"] == "CPC_1908_ORD_XXXIX_R_4"

    # 3. Unverified authority
    unverified_cases = [f for f in res["failures"] if f.get("category") == "UNVERIFIED_AUTHORITY"]
    assert len(unverified_cases) == 1
    assert "2012 SCMR 99999" in unverified_cases[0]["issue"]

    # 4. Missing provision (not in verified store)
    missing_provisions = [f for f in res["failures"] if f.get("category") == "CITED_PROVISION_NOT_IN_VERIFIED_STORE"]
    assert any("Section 61" in mp["span"] for mp in missing_provisions)
    assert any("not in verified store" in mp["issue"] for mp in missing_provisions)
    assert all("does not exist" not in mp["issue"] for mp in missing_provisions)

    # 5. Unsourced sentences (sentence relying on unverified authority remains flagged)
    unsourced_sentences = [f for f in res["failures"] if f.get("category") == "UNSOURCED_ANALYSIS"]
    assert any("2012 SCMR 99999" in us["span"] for us in unsourced_sentences)

    # 6. Ellipsis extracted
    assert len(res["omitted_ellipses"]) >= 1

def test_holdout_memo_f_fixture_blocked(verifier):
    """
    Memo F: Blocks accurately on non-verbatim Section 10(1) quote,
    while correctly accepting authentic Section 22 text (U+037E semicolon, amendment markers)
    and allowing disputed Section 22 citation under the structural warning banner.
    """
    assert os.path.exists(MEMO_F_PATH), f"Fixture missing: {MEMO_F_PATH}"
    with open(MEMO_F_PATH, "r", encoding="utf-8") as f:
        memo_text = f.read()

    # System-rendered evaluation: banner is authenticated, so s.22 is permitted under banner
    res_sys = verifier.verify_memo(memo_text, is_system_rendered=True)
    assert res_sys["passed"] is False
    assert res_sys["verdict"] == "BLOCKED"
    assert res_sys["total_failures"] == 1

    failure = res_sys["failures"][0]
    assert failure["rule"] == "(a)"
    assert failure["category"] == "UNMATCHED_QUOTE"
    assert "FIO_2001_SEC_10" in failure["issue"]

    # S.22 quotes must pass
    assert res_sys["quotes_passed"] == 3
    assert res_sys["quotes_failed"] == 1

    # S.22 citation under structural banner must yield DISPUTED TEXT notice, not block
    assert len(res_sys["disputed_notices"]) >= 1
    assert any("FIO_2001_SEC_22" in dn["provision"] for dn in res_sys["disputed_notices"])
    assert any(dn["label"] == LABEL_DISPUTED_TEXT_NOTICE for dn in res_sys["disputed_notices"])

    # Raw model evaluation: model-written banner is stripped and flagged
    res_raw = verifier.verify_memo(memo_text, is_system_rendered=False)
    assert res_raw["passed"] is False
    assert res_raw["verdict"] == "BLOCKED"
    assert res_raw["total_failures"] == 3
    categories = [f["category"] for f in res_raw["failures"]]
    assert "MODEL_INJECTED_BANNER" in categories
    assert "DISPUTED_TEXT_UNNOTICED" in categories
    assert "UNMATCHED_QUOTE" in categories


# ---------------------------------------------------------------------------
# ORDER 1.8 UNIT TESTS
# ---------------------------------------------------------------------------
from legal_ai.verification.memo_verifier import (
    shared_normalize,
    compute_word_diff,
    LABEL_HEADING_ONLY,
    LABEL_DECEPTIVE_ELLIPSIS,
    LABEL_MODEL_BANNER_DETECTED
)

def test_order18_banner_stripping_and_blocking(verifier):
    """
    Item 2: Strip model-written '> [!' blocks before verification.
    System adds banners AFTER verification. Test that a model-written banner is stripped/blocked.
    """
    memo_with_model_banner = (
        "> [!NOTE]\n"
        "> The following advice is verified.\n\n"
        "Order XXXIX Rule 1 of the Code of Civil Procedure, 1908 governs injunctions.\n"
    )
    res_raw = verifier.verify_memo(memo_with_model_banner, is_system_rendered=False)
    assert res_raw["passed"] is False
    assert res_raw["verdict"] == "BLOCKED"
    assert any(f["category"] == "MODEL_INJECTED_BANNER" for f in res_raw["failures"])

    res_sys = verifier.verify_memo(memo_with_model_banner, is_system_rendered=True)
    assert not any(f["category"] == "MODEL_INJECTED_BANNER" for f in res_sys["failures"])

def test_order18_heading_only_record_blocked(verifier):
    """
    Item 3: Rule (d) - If a memo asserts content of a title_only/heading_only record,
    label PROVISION TEXT NOT IN STORE (heading only).
    """
    from core.unified_statute_store import get_unified_statute_store
    store = get_unified_statute_store()
    mock_cid = "CPC_1908_SEC_9999"
    store._by_cid[mock_cid] = {
        "canonical_id": mock_cid,
        "act_code": "CPC_1908",
        "section": "9999",
        "title": "Mock Title Heading",
        "text": "Mock Title Heading",
        "tier": "title_only",
        "has_operative_text": False
    }
    try:
        is_valid, reason, rec = verifier.verify_statutory_citation("Section 9999 of the Code of Civil Procedure, 1908")
        assert is_valid is False
        assert LABEL_HEADING_ONLY in reason
    finally:
        store._by_cid.pop(mock_cid, None)

def test_order18_deceptive_ellipsis_flagged(verifier):
    """
    Item 4: Ellipsis omitting material conditions (if, unless, provided, except, subject to, not)
    must be flagged DECEPTIVE ELLIPSIS — omitted material condition.
    """
    deceptive_quote = (
        "> In any case in which the summons has been served on the defendant... "
        "to defend the same"
    )
    q_res = verifier.verify_quote_against_store(deceptive_quote)
    assert q_res[0] is False
    assert LABEL_DECEPTIVE_ELLIPSIS in q_res[2]
    assert any("unless" in d for d in q_res.deceptive_flags)

def test_order18_word_diff_trimmed_and_no_inprison_glue():
    """
    Item 5: 1[* * *] marker replacement with space prevents 'inprison' glue.
    Word diff is localized to aligned window instead of dumping entire provision.
    """
    raw_with_marker = "detained in 1[* * *] prison"
    normalized = shared_normalize(raw_with_marker)
    assert normalized == "detained in prison"
    assert "inprison" not in normalized

    large_provision = "word " * 100 + "detained in prison for a term not exceeding six months " + "word " * 100
    bad_quote = "detained in civil prison for a term not exceeding two years"
    diff = compute_word_diff(bad_quote, large_provision)
    assert "civil" in diff
    assert "two years" in diff
    assert len(diff) < 300

def test_order18_no_unsourced_text_in_injector_prompt():
    """
    Item 7: Test that no unsourced or quarantined record text reaches a prompt.
    """
    from legal_ai.statutes.statute_injector import inject_statutory_framework
    res = inject_statutory_framework("What does Article 199 of the Constitution provide?")
    assert len(res["provisions_with_text"]) == 0
    assert "[Statutory text not found in verified database]" in res["statute_block"]

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
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\n"
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
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\n"
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
        "**DISPUTED TEXT - human check required**\n\n"
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
        "IN THE HIGH COURT OF SINDH AT KARACHI\n"
        "Suit No. 1234 of 2026\n\n"
        "1. The Plaintiff is a banking company having its registered office at I.I. Chundrigar Road, Karachi.\n"
        "2. The Defendant approached the Plaintiff for finance facility on 15th January 2024.\n"
        "3. The Plaintiff granted the facility and Defendant executed finance agreements.\n"
        "4. Section 9 of the Financial Institutions Ordinance, 2001 provides for presentation of plaint.\n"
        "5. The Plaintiff prays for a decree in terms of Section 10 of the Financial Institutions Ordinance, 2001."
    )
    # verify_pleading_citations_and_quotes allows client facts
    p_res = verify_pleading_citations_and_quotes(pleading_with_facts)
    assert p_res["passed"] is True
    assert p_res["total_failures"] == 0

    # If an invalid fake statute citation is added, it MUST block
    bad_pleading = pleading_with_facts + "\n6. Section 9999 of the Code of Civil Procedure, 1908 applies."
    p_bad = verify_pleading_citations_and_quotes(bad_pleading)
    assert p_bad["passed"] is False
    assert p_bad["total_failures"] >= 1


def test_order19_repaired_memo_f_accepted(verifier):
    """
    Order 1.9 - Item 11: Repaired Memo F with authentic s.10(1) quote PASSES.
    """
    repaired_memo_f = (
        "# RESEARCH MEMORANDUM: Financial Institutions Ordinance, 2001\n\n"
        "### 1. Leave to Defend Procedure\n\n"
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\n\n"
        "> (1) In any case in which the summons has been served on the defendant as provided for in sub-section (5) of section 9, the defendant shall not be entitled to defend the suit unless he obtains leave from the Banking Court as hereinafter provided to defend the same; and, in default of his doing so, the allegations of fact in the plaint shall be deemed to be admitted and the Banking Court may pass a decree in favour of the plaintiff on the basis thereof or such other material as the Banking Court may require in the interests of justice.\n\n"
        "### 2. Appeals\n\n"
        "Section 22 of the Financial Institutions Ordinance, 2001 governs appeals."
    )
    # Attach system banner
    system_rendered = attach_system_disputed_banner(repaired_memo_f, [{"provision": "FIO_2001_SEC_22"}])
    res = verifier.verify_memo(system_rendered, is_system_rendered=True)
    assert res["passed"] is True, f"Repaired Memo F expected to PASS, got {res['failures']}"
    assert res["verdict"] == "ACCEPTED"
    assert res["total_failures"] == 0


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
        "Section 10 of the Financial Institutions Ordinance, 2001 provides:\n\n"
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
        "# RESEARCH MEMORANDUM\n\n"
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
    import json
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
