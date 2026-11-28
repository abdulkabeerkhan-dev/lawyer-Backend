"""Precedents reach the answer model with their headnote and holding, not only a ~300-char passage."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _cards():
    return [
        {"citation": "2000 SCMR 1647", "case_title": "A v B", "court": "Supreme Court of Pakistan",
         "ratio_decidendi": "10. Before parting with this matter, we cannot help observing that the"},
        {"citation": "CPC 1908 SEC 151", "case_title": "Precedent", "ratio_decidendi": "Inherent powers"},
    ]


def test_headnote_and_holding_are_added(monkeypatch):
    from legal_ai.query_engine import statute_router as sr
    seen = {}

    def fake_fetch(wanted, timeout_s=5.0):
        seen["wanted"] = wanted
        return {("2000 SCMR 1647", "SC"): {"headnote": "Benami---Four tests: source of consideration, possession...",
                                             "ratio_decidendi": "Held, the burden lies on the person alleging benami."}}
    monkeypatch.setattr(sr, "_fetch_headnotes", fake_fetch)
    pack, _ = sr.build_evidence_pack_for_query("benami transaction ingredients", precedent_cards=_cards())
    cases = [it for it in pack.items.values() if it.item_type == "judicial_precedent"]
    assert [c.citation for c in cases] == ["2000 SCMR 1647"]          # statute id is not a judgment
    assert seen["wanted"] == [("2000 SCMR 1647", "SC")]
    r = cases[0].ratio
    assert r.startswith("HEADNOTE: Benami---Four tests") and "HOLDING: Held, the burden" in r
    assert "PASSAGE MATCHING THE QUERY: 10. Before parting" in r


def test_falls_back_to_the_passage_when_texts_are_unavailable(monkeypatch):
    from legal_ai.query_engine import statute_router as sr

    def boom(wanted, timeout_s=5.0):
        raise RuntimeError("zilliz down")
    monkeypatch.setattr(sr, "_fetch_headnotes", boom)
    pack, _ = sr.build_evidence_pack_for_query("benami", precedent_cards=_cards()[:1])
    case = next(it for it in pack.items.values() if it.item_type == "judicial_precedent")
    assert case.ratio.startswith("10. Before parting")


def test_limitation_instructions_only_for_dated_matters(monkeypatch):
    from legal_ai.synthesis import structured_memo_engine as sme
    from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack
    import core.limitation_engine as le
    monkeypatch.setattr(le, "analyze_matter_limitation", lambda q: {"is_applicable": False})
    _, user = sme.build_structured_memo_prompts(BoundedEvidencePack(), "Is cheating under s.420 PPC bailable?")
    assert "specific performance" not in user and "Section 55 Contract Act" not in user
    assert "15 September 2024" not in open(sme.__file__, encoding="utf-8").read()


def test_headnote_fetch_reads_only_summary_sections_and_caches_trimmed(monkeypatch):
    import legal_ai.config as cfg
    import legal_ai.retrieval.zilliz_search as zs
    from legal_ai.query_engine import statute_router as sr
    calls = []

    class Client:
        def query(self, collection_name, filter, limit, timeout, output_fields):
            calls.append(filter)
            return [{"chunk_id": "a#1", "case_key": "k", "citation": "2000 SCMR 1647", "court_code": "SC",
                     "section": "headnote", "text": "H" * 5000},
                    {"chunk_id": "a#2", "case_key": "k", "citation": "2000 SCMR 1647", "court_code": "SC",
                     "section": "holding", "text": "R" * 5000}]
    monkeypatch.setattr(cfg, "get_zilliz_client", lambda: Client())
    monkeypatch.setattr(zs, "is_zilliz_circuit_open", lambda: False)
    sr._PRECEDENT_CACHE.clear()
    out = sr._fetch_headnotes([("2000 SCMR 1647", "SC")], 1.0)
    t = out[("2000 SCMR 1647", "SC")]
    assert len(t["headnote"]) == sr.PRECEDENT_HEADNOTE_CHARS and len(t["ratio_decidendi"]) == sr.PRECEDENT_HOLDING_CHARS
    assert 'section in ["headnote","holding","ratio"]' in calls[0]
    sr._fetch_headnotes([("2000 SCMR 1647", "SC")], 1.0)
    assert len(calls) == 1                                   # second call served from the cache
    sr._PRECEDENT_CACHE.clear()


def test_pack_tells_the_model_not_to_cite_cases_inside_headnotes():
    from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack
    pack = BoundedEvidencePack()
    pack.add_case_precedent(citation="2000 SCMR 1647", case_title="A v B", court="SC", ratio="HEADNOTE: relying on 1985 SCMR 1949")
    assert "do not cite them as authorities of their own" in pack.format_pack_for_llm()


def test_headnote_drops_party_line_and_citation_lists():
    from legal_ai.query_engine.statute_router import _clean_headnote
    raw = "ZAHID REHMAN VS State\n1994 SCMR 1327, 1997 SCMR 1307, 2003 SCMR 1419\nBail---Further inquiry---Bail allowed."
    assert _clean_headnote(raw) == "Bail---Further inquiry---Bail allowed."
    kept = "In Hyderabad Electric v. Mushtaq Ali Brohi (2010 PSC 1392), this Court held X."
    assert _clean_headnote(kept) == kept      # one citation inside the reasoning stays
