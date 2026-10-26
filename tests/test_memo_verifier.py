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
    LABEL_UNSOURCED_ANALYSIS
)

FIXTURE_PATH = os.path.join(REPO_DIR, "tests", "fixtures", "q1_bad_memo.txt")

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
