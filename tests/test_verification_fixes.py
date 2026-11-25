"""Verifier fixes from the 100-question evaluation (Nov 2026):
- citations quoted inside retrieved judgments count as grounded,
- citations not in the corpus are flagged and annotated,
- rent_eviction only triggers on real rent/tenancy words, and the auditor
  takes its topic from the question, not from the memo body."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from legal_ai.verification import citation_keys as ck
from legal_ai.verification.claim_verifier import verify_and_scrub_memo_claims
from legal_ai.verification.doctrinal_rules import detect_topics


@pytest.mark.parametrize("text,key", [
    ("PLD 2004 SC 62", ("2004", "PLD", "62")),
    ("2004 PLD 62", ("2004", "PLD", "62")),
    ("2004_PLD_SC_62", ("2004", "PLD", "62")),
    ("2013 PCr.LJ 400", ("2013", "PCRLJ", "400")),
    ("P.Cr.L.J 2013 400", ("2013", "PCRLJ", "400")),
    ("2018 PLC (CS) 237", ("2018", "PLC(CS)", "237")),
    ("see 2020 YLR Lahore 1445 for this", ("2020", "YLR", "1445")),
])
def test_citation_key_forms(text, key):
    assert ck.citation_key(text) == key


def test_citation_key_ignores_non_citations():
    assert ck.citation_key("Section 489-F PPC, 2016 amendment") is None
    assert ck.keys_in_text("Article 199 of the Constitution, 1973") == set()


def _no_corpus(monkeypatch, known=()):
    monkeypatch.setattr(ck, "known_in_corpus", lambda keys, timeout_s=3.0: {k: (k in set(known)) for k in keys})


MEMO = ("The Supreme Court in 2009 SCMR 1045 held the suit time-barred, following 1991 SCMR 703. "
        "See also 1993 SCMR 1463.")
CARDS = [{"citation": "2009 SCMR 1045", "preview": "Suit for specific performance... (relied on 1991 S C M R 703)"}]


def test_citation_quoted_in_retrieved_authority_is_grounded(monkeypatch):
    _no_corpus(monkeypatch, known=[("2009", "SCMR", "1045"), ("1991", "SCMR", "703"), ("1993", "SCMR", "1463")])
    out = verify_and_scrub_memo_claims(MEMO, retrieved_precedents=CARDS)
    status = {c["citation"]: c["status"] for c in out.verified_claims}
    assert status["2009 SCMR 1045"] == "RETRIEVED_AND_VERIFIED"
    assert status["1991 SCMR 703"] == "CITED_IN_RETRIEVED_AUTHORITY"
    unretrieved = [v["citation"] for v in out.violations if v["type"] == "UNRETRIEVED_CASE_CITATION"]
    assert unretrieved == ["1993 SCMR 1463"]  # real, but not in any source the model saw


def test_evidence_pack_text_also_grounds(monkeypatch):
    _no_corpus(monkeypatch, known=[("1993", "SCMR", "1463"), ("2009", "SCMR", "1045"), ("1991", "SCMR", "703")])
    out = verify_and_scrub_memo_claims(MEMO, retrieved_precedents=CARDS,
                                       evidence_text="E14: ...as held in 1993 SCMR 1463 ...")
    assert not [v for v in out.violations if v["type"] == "UNRETRIEVED_CASE_CITATION"]


def test_citation_not_in_corpus_is_flagged_and_annotated(monkeypatch):
    _no_corpus(monkeypatch, known=[("2009", "SCMR", "1045"), ("1991", "SCMR", "703")])
    out = verify_and_scrub_memo_claims(MEMO, retrieved_precedents=CARDS)
    flags = [v["citation"] for v in out.violations if v["type"] == "CITATION_NOT_IN_CORPUS"]
    assert flags == ["1993 SCMR 1463"]
    assert "1993 SCMR 1463 [citation not found in Section's case database" in out.cleaned_text
    assert out.cleaned_text.count("citation not found") == 1
    # retrieved cases are never looked up, and a lookup failure (None) never flags anything
    _ = verify_and_scrub_memo_claims(MEMO, retrieved_precedents=CARDS, check_corpus=False)
    monkeypatch.setattr(ck, "known_in_corpus", lambda keys, timeout_s=3.0: {k: None for k in keys})
    out2 = verify_and_scrub_memo_claims(MEMO, retrieved_precedents=CARDS)
    assert not [v for v in out2.violations if v["type"] == "CITATION_NOT_IN_CORPUS"]


@pytest.mark.parametrize("text", [
    "The current legal position is different for the parent company and the apparent owner.",
    "Khula without consent of the husband",
    "Bail under Section 302 PPC on a plea of self defence",
    "What was the ruling in Marbury v Madison?",
])
def test_rent_eviction_not_triggered_by_ordinary_words(text):
    assert "rent_eviction" not in detect_topics(text, query_only_text=text)


@pytest.mark.parametrize("text", [
    "Eviction of tenant on ground of default in rent under PRPA",
    "Can a landlord seek ejectment of a tenant?",
    "Recovery of rental arrears from tenancy",
])
def test_rent_eviction_still_triggered_by_real_rent_questions(text):
    assert "rent_eviction" in detect_topics(text, query_only_text=text)


def test_auditor_topics_come_from_the_question():
    from legal_ai.verification.memo_auditor import audit_memo
    memo = ("Question and short answer: A wife may obtain khula. Governing provisions: Family Courts Act 1964 s.10(4). "
            "Analysis: The current position, unlike a landlord-tenant eviction, depends on aversion.")
    res = audit_memo(memo, query="Can a wife obtain khula without her husband's consent?")
    d = res.to_dict() if hasattr(res, "to_dict") else res
    assert "rent_eviction" not in (d.get("topics") or [])
