"""Unit tests for legal_ai.retrieval.zilliz_fulltext (Zilliz mocked; no network)."""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from legal_ai.retrieval import zilliz_fulltext as zf


def _chunk(case_key, section, n, body, court="SC", citation="2024 SCMR 14"):
    return {"chunk_id": f"{case_key}:{section}:{n:03d}", "case_key": case_key, "citation": citation,
            "court_code": court, "section": section,
            "text": f"[{citation} | Court | Criminal | X | {section}]\n\n{body}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ZILLIZ_URI", "https://example")
    monkeypatch.setenv("ZILLIZ_TOKEN", "t")
    zf._cache.clear()


def test_citation_key_normalises_common_formats():
    assert zf.citation_key("PLD 1989 Lah. 64") == "1989 PLD 64"
    assert zf.citation_key("2018_PLC(CS)_237") == "2018 PLC(CS) 237"
    assert zf.citation_key("2024 SCMR 0014") == "2024 SCMR 14"
    assert zf.citation_key("not a citation") is None


def test_assemble_orders_sections_and_strips_headers():
    chunks = [_chunk("K", "order", 1, "Appeal allowed."), _chunk("K", "facts", 2, "Fact two."),
              _chunk("K", "headnote", 1, "Head."), _chunk("K", "facts", 1, "Fact one."),
              _chunk("K", "holding", 1, "Held: bail.")]
    t = zf.assemble_case(chunks)
    assert t["full_text"] == "Head.\n\nFact one.\n\nFact two.\n\nHeld: bail.\n\nAppeal allowed."
    assert t["headnote"] == "Head."
    assert t["ratio_decidendi"] == "Held: bail."


def test_hydrate_fills_only_empty_fields(monkeypatch):
    calls = []

    def fake(citations, timeout_s):
        calls.append(citations)
        return [_chunk("2024_SCMR_SC_14", "headnote", 1, "Head."), _chunk("2024_SCMR_SC_14", "facts", 1, "Facts.")]

    monkeypatch.setattr(zf, "_query_chunks", fake)
    rows = [{"case_id": "2024_SCMR_14", "neutral_citation": "2024 SCMR 14", "court_name": "Supreme Court of Pakistan",
             "full_text": None, "headnote": "kept headnote"},
            {"case_id": "2020_PLD_1", "full_text": "already here"}]
    zf.hydrate_rows(rows)
    assert rows[0]["full_text"] == "Head.\n\nFacts."
    assert rows[0]["headnote"] == "kept headnote"
    assert rows[0]["text_source"] == "zilliz"
    assert rows[1]["full_text"] == "already here" and "text_source" not in rows[1]
    assert calls == [["2024 SCMR 14"]]
    zf.hydrate_rows([dict(rows[0], full_text="")])  # second lookup served from cache
    assert len(calls) == 1


def test_ambiguous_citation_uses_court_or_leaves_row(monkeypatch):
    chunks = [_chunk("2010_PLD_LHC_5", "facts", 1, "Lahore case.", court="LHC", citation="2010 PLD 5"),
              _chunk("2010_PLD_SHC_5", "facts", 1, "Sindh case.", court="SHC", citation="2010 PLD 5")]
    monkeypatch.setattr(zf, "_query_chunks", lambda c, t: chunks)
    lhc = {"neutral_citation": "2010 PLD 5", "court_name": "Lahore High Court", "full_text": None}
    unknown = {"neutral_citation": "2010 PLD 5", "court_name": "Tribunal", "full_text": None}
    zf.hydrate_rows([lhc, unknown])
    assert lhc["full_text"] == "Lahore case."
    assert unknown["full_text"] is None


def test_nested_crosswalk_rows_are_hydrated(monkeypatch):
    monkeypatch.setattr(zf, "_query_chunks", lambda c, t: [_chunk("K", "facts", 1, "Body.")])
    data = [{"citation": "2024 SCMR 14", "full_judgments": {"neutral_citation": "2024 SCMR 14", "full_text": ""}}]
    zf.hydrate_rows(data)
    assert data[0]["full_judgments"]["full_text"] == "Body."


def test_zilliz_failure_never_raises(monkeypatch):
    def boom(c, t):
        raise RuntimeError("down")
    monkeypatch.setattr(zf, "_query_chunks", boom)
    rows = [{"neutral_citation": "2024 SCMR 14", "full_text": None}]
    assert zf.hydrate_rows(rows) is rows and rows[0]["full_text"] is None


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("ZILLIZ_FULLTEXT_HYDRATE", "false")
    monkeypatch.setattr(zf, "_query_chunks", lambda c, t: pytest.fail("should not query"))
    zf.hydrate_rows([{"neutral_citation": "2024 SCMR 14", "full_text": None}])


def test_client_wrapper_hydrates_full_judgments_only(monkeypatch):
    monkeypatch.setattr(zf, "_query_chunks", lambda c, t: [_chunk("K", "facts", 1, "Body.")])

    class Res:
        def __init__(self, data): self.data = data

    class Builder:
        def __init__(self, data): self.data = data
        def select(self, *_): return self
        def eq(self, *_): return self
        def limit(self, *_): return self
        def execute(self): return Res(self.data)

    class Client:
        auth = "auth-obj"
        def table(self, name):
            return Builder([{"neutral_citation": "2024 SCMR 14", "full_text": None}])

    wc = zf.wrap_supabase_client(Client())
    assert zf.wrap_supabase_client(wc) is wc
    assert wc.auth == "auth-obj"
    got = wc.table("full_judgments").select("*").eq("id", 1).limit(1).execute().data
    assert got[0]["full_text"] == "Body."
    other = wc.table("queries").select("*").execute().data
    assert other[0]["full_text"] is None
