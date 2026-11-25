"""Fixes from the Nov 25 2026 system audit."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.parametrize("raw,expected", [
    ("criminal", "criminal"),
    ("Family Law", "family"),
    ("tax", "tax_corporate"),
    ("banking", "banking_commercial"),
    ("service matters", "service"),
    ("unknown", None),
    (None, None),
])
def test_planner_domain_maps_to_stored_label(raw, expected):
    from legal_ai.retrieval.supabase_search import _corpus_domain
    assert _corpus_domain(raw) == expected


def test_search_queries_exclude_blocked_rows():
    """Every full-text / title search over full_judgments filters out rejected, quarantined
    and restricted rows (10,674 headnote fragments and 291 mismatched texts live there)."""
    flt = 'retrieval_status.not.in.(rejected,quarantined,restricted)'
    for path, n in [("main.py", 4), ("legal_ai/retrieval/supabase_search.py", 2),
                    ("legal_ai/search/judgment_search_service.py", 1)]:
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        assert src.count(flt) >= n, path
    main = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    for m in re.finditer(r"\.text_search\('(?:fts_headnote|case_title)'", main):
        window = main[max(0, m.start() - 300):m.start()]
        assert flt in window


def test_unverified_quote_stripper_matches_curly_quotes():
    main = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    pats = re.findall(r"re\.sub\(r'(\^\\s\*>\\s\*\[[^']+)'", main)
    assert len(pats) == 2
    for p in pats:
        assert re.search(p, "> “The court held X”", re.M)
        assert re.search(p, '> "plain quote"', re.M)
        assert not re.search(p, "> not a quote", re.M)


def test_limitation_articles_have_period_text():
    """Article 113 lost its period and start date in the staging file that feeds Zilliz."""
    rows = json.load(open(os.path.join(ROOT, "data/statutes_v3_staging/LIMITATION_1908.json"), encoding="utf-8"))
    by_id = {r["canonical_id"]: r for r in rows}
    art = by_id.get("LIMITATION_1908_ART_113")
    if art is None:  # article lives in the legacy file
        rows = json.load(open(os.path.join(ROOT, "data/statutes_v3_staging/statutes_v2_legacy.json"), encoding="utf-8"))
        art = {r["canonical_id"]: r for r in rows}["LIMITATION_1908_ART_113"]
    assert "Three years" in art["text"]
    assert "notice that performance is refused" in art["text"]


class _FakeQuery:
    def __init__(self, rows, log):
        self.rows, self.log, self.col, self.vals = rows, log, None, None

    def select(self, cols):
        return self

    def in_(self, col, vals):
        self.col, self.vals = col, set(vals)
        self.log.append((col, len(vals)))
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = [x for x in self.rows if x.get(self.col) in self.vals]
        return r


class _FakeSB:
    def __init__(self, rows):
        self.rows, self.log = rows, []

    def table(self, name):
        return _FakeQuery(self.rows, self.log)


def test_zilliz_keys_resolve_to_supabase_status(monkeypatch):
    """Zilliz keys carry a court code (2005_CLC_SHC_1241); full_judgments.case_id does not."""
    from core import case_store
    rows = [
        {"id": "1", "case_id": "2005_CLC_1241", "neutral_citation": "2005 CLC 1241",
         "court_name": "High Court of Sindh", "retrieval_status": "quarantined"},
        {"id": "2", "case_id": "2007_PLD_SC_87", "neutral_citation": "PLD 2007 SC 87",
         "court_name": "Supreme Court of Pakistan", "retrieval_status": None},
        # serial-number case_id: the row's own citation says it is a different case
        {"id": "3", "case_id": "1978_SCMR_31", "neutral_citation": "1978 SCMR 81",
         "court_name": "Supreme Court of Pakistan", "retrieval_status": "rejected"},
    ]
    monkeypatch.setattr(case_store, "_supabase", lambda: _FakeSB(rows))
    got = case_store.retrieval_statuses(["2005_CLC_SHC_1241", "2007_PLD_SC_87", "1978_SCMR_SC_31", "2001_YLR_LHC_9"])
    assert got["2005_CLC_SHC_1241"] == "quarantined"
    assert got["2007_PLD_SC_87"] == ""
    assert got["1978_SCMR_SC_31"] is None  # never borrow another case's status
    assert got["2001_YLR_LHC_9"] is None


def test_era_toggle_filters_candidates():
    from legal_ai.ranking.era_filter import apply_request_filters
    cands = [
        {"case_id": "2021_SCMR_SC_14", "citation": "2021 SCMR 14", "court_code": "SC"},
        {"case_id": "2015_PLD_LHC_9", "citation": "PLD 2015 Lah 9", "court_code": "LHC"},
        {"case_id": "2022_PLD_AJKSC_3", "metadata": {"citation": "PLD 2022 AJ&K SC 3",
                                                     "court_name": "Supreme Court of Azad Jammu & Kashmir"}},
        {"case_id": "2019_YLR_LHC_77", "year": 2019, "court_code": "LHC"},
    ]
    keep, t = apply_request_filters(cands, {"era": "modern", "min_year": 2018})
    assert [c["case_id"] for c in keep] == ["2021_SCMR_SC_14", "2022_PLD_AJKSC_3", "2019_YLR_LHC_77"]
    keep, _ = apply_request_filters(cands, {"era": "apex", "court_filter": "Supreme Court of Pakistan"})
    assert [c["case_id"] for c in keep] == ["2021_SCMR_SC_14"]
    keep, t = apply_request_filters(cands, {"era": "all"})
    assert keep == cands and t == {}


def test_relevance_filter_drops_cases_blocked_in_supabase(monkeypatch):
    from legal_ai.verification import case_status
    monkeypatch.setattr(case_status, "_lookup", lambda keys: {k: ("quarantined" if k == "2005_CLC_SHC_1241" else "") for k in keys})
    case_status._cache.clear()
    from legal_ai.ranking.relevance_filter import filter_candidate_quality_before_ranking
    cands = [{"case_id": "2005_CLC_SHC_1241", "title": "A v B", "text": "x " * 400},
             {"case_id": "2006_CLC_SHC_7", "title": "C v D", "text": "y " * 400}]
    kept, counts = filter_candidate_quality_before_ranking(raw_candidates=cands, query_plan=None)
    ids = [c["case_id"] for c in kept]
    assert "2005_CLC_SHC_1241" not in ids
    assert counts.get("trust_gate_exclusion") == 1
    # a failed lookup admits the case rather than blocking the query
    monkeypatch.setattr(case_status, "_lookup", lambda keys: (_ for _ in ()).throw(RuntimeError("db down")))
    case_status._cache.clear()
    assert case_status.blocked(["2005_CLC_SHC_1241"]) == set()


def test_bare_court_field_is_not_a_filter():
    from legal_ai.ranking.era_filter import requested_filters
    assert requested_filters({"court": "Lahore High Court"}) == {}
    assert requested_filters({"era": "apex", "court": "Supreme Court of Pakistan"}) == {"court": "Supreme Court of Pakistan"}
