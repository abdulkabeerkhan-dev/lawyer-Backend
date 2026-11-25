"""Governing provisions reach the evidence pack (issue 3 from the Nov 2026 evaluation)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from legal_ai.query_engine import named_provisions as npv

ALL = lambda cid: True  # treat every id as existing for the pure parsing tests


@pytest.mark.parametrize("q,expected", [
    ("Powers of the High Court under Article 199 and Article 184(3)", ["CONST_1973_ART_199", "CONST_1973_ART_184_3"]),
    ("Is the suit barred under Article 113 Limitation Act?", ["LIMITATION_1908_ART_113"]),
    ("Offence under Section 489-F PPC", ["PPC_1860_SEC_489F"]),
    ("Sections 468 and 471 PPC and Article 59 QSO", ["PPC_1860_SEC_468", "PPC_1860_SEC_471", "QSO_1984_ART_59"]),
    ("objection under O.XXI r.58 that he is a purchaser under s.41 TPA and s.47 CPC bars it",
     ["CPC_1908_ORD_XXI_R_58", "TPA_1882_SEC_41", "CPC_1908_SEC_47"]),
    ("Does S.4 MFLO give orphaned grandchildren a share?", ["MFLO_1961_SEC_4"]),
    ("Application under Section 12(2) CPC", ["CPC_1908_SEC_12_2", "CPC_1908_SEC_12"]),
])
def test_named_provisions(q, expected):
    got = npv.provisions_named_in(q, ALL)
    for e in expected:
        if e == "CPC_1908_SEC_12":
            continue  # only the first existing candidate per mention is kept
        assert e in got, (q, got)


def test_named_provisions_respect_store():
    exists = lambda c: c in {"CPC_1908_SEC_12"}
    assert npv.provisions_named_in("Section 12(2) CPC", exists) == ["CPC_1908_SEC_12"]
    assert npv.provisions_named_in("Section 999 PPC", lambda c: False) == []


@pytest.mark.parametrize("q,expected", [
    ("Qisas and Diyat Ordinance provisions on Badal-i-Sulh", ["PPC_1860_SEC_310"]),
    ("Consequences of a second marriage without permission of the Arbitration Council", ["MFLO_1961_SEC_6"]),
    ("Do orphaned grandchildren inherit when their father died before the grandfather?", ["MFLO_1961_SEC_4"]),
    ("We filed objections to an arbitration award in the civil court", ["ARBITRATION_1940_SEC_30"]),
    ("The Banking Court directed a 50% deposit before hearing our objection to the auction", ["CPC_1908_ORD_XXI_R_90"]),
    ("Limitation for a female co-heir to challenge an inheritance mutation", ["LIMITATION_1908_ART_120"]),
])
def test_topic_anchors(q, expected):
    got = npv.provisions_for_topics(q, ALL)
    for e in expected:
        assert e in got, (q, got)


def test_topic_anchor_precision():
    assert "ATA_1997_SEC_7" not in npv.provisions_for_topics("Penalty for cyber terrorism under PECA", ALL)
    assert "LIMITATION_1908_ART_120" not in npv.provisions_for_topics("Mutation of land in favour of a gift donee", ALL)
    assert npv.provisions_for_topics("How to bake a chocolate cake?", ALL) == []


def test_planner_generic_default_is_ignored():
    assert npv.useful_planned(["CPC_1908_SEC_9", "CPC_1908_SEC_151"]) == []
    assert npv.useful_planned(["MFLO_1961_SEC_6", "CPC_1908_SEC_9"]) == ["MFLO_1961_SEC_6", "CPC_1908_SEC_9"]


def test_act_of():
    assert npv.act_of("CPC_1908_ORD_XXI_R_90") == "CPC_1908"
    assert npv.act_of("CONST_1973_ART_184_3") == "CONST_1973"


def test_evidence_pack_puts_governing_law_first():
    from legal_ai.query_engine.statute_router import build_evidence_pack_for_query
    pack, _ = build_evidence_pack_for_query(
        "Explain the powers of the High Court under Article 199 and the Supreme Court under Article 184(3).",
        precedent_cards=[])
    items = list(pack.to_dict().values())
    first = [(i.get("statute_id"), str(i.get("number"))) for i in items[:2]]
    assert first == [("constitution-1973", "199"), ("constitution-1973", "184")]
    # no unrelated acts once the governing act is known
    assert all(i.get("statute_id") == "constitution-1973" for i in items)


def test_planned_provisions_enter_the_pack():
    from legal_ai.query_engine.statute_router import build_evidence_pack_for_query
    pack, _ = build_evidence_pack_for_query("What happens if a man marries again?", precedent_cards=[],
                                            planned_provisions=["MFLO_1961_SEC_6"])
    assert ("mflo-1961", "6") in [(i.get("statute_id"), str(i.get("number"))) for i in pack.to_dict().values()]


def test_foreign_statute_guard():
    from legal_ai.verification.claim_verifier import verify_and_scrub_memo_claims
    out = verify_and_scrub_memo_claims(
        "Expert evidence is admissible under the Indian Evidence Act, 1872 and section 45.",
        retrieved_precedents=[], check_corpus=False)
    assert "Qanun-e-Shahadat Order 1984 governs" in out.cleaned_text
    assert any(v["type"] == "FOREIGN_STATUTORY_REGIME_LEAKAGE" for v in out.violations)
    ok = verify_and_scrub_memo_claims("Article 59 of the Qanun-e-Shahadat Order 1984 applies.",
                                      retrieved_precedents=[], check_corpus=False)
    assert not any(v["type"] == "FOREIGN_STATUTORY_REGIME_LEAKAGE" for v in ok.violations)
