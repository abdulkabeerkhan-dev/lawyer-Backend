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
    assert "tier='unsourced'" in reason or "not sourced" in reason

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

    res = verifier.verify_memo(memo_text)
    # Fails ONLY on the non-verbatim s.10(1) quote
    assert res["passed"] is False
    assert res["verdict"] == "BLOCKED"
    assert res["total_failures"] == 1

    failure = res["failures"][0]
    assert failure["rule"] == "(a)"
    assert failure["category"] == "UNMATCHED_QUOTE"
    assert "FIO_2001_SEC_10" in failure["issue"]

    # S.22 quotes must pass
    assert res["quotes_passed"] == 3
    assert res["quotes_failed"] == 1

    # S.22 citation under structural banner must yield DISPUTED TEXT notice, not block
    assert len(res["disputed_notices"]) >= 1
    assert any("FIO_2001_SEC_22" in dn["provision"] for dn in res["disputed_notices"])
    assert any(dn["label"] == LABEL_DISPUTED_TEXT_NOTICE for dn in res["disputed_notices"])

