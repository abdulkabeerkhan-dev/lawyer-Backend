"""core.case_store (Supabase/R2 replacement for Turso) and the Zilliz BM25 keyword index."""
import gzip
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from core import case_store
from legal_ai.retrieval import zilliz_keyword_index as zki


class _Res:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Minimal postgrest-style builder that records the filters it was given."""

    def __init__(self, rows, log):
        self.rows, self.log, self.filters, self.n = rows, log, [], None

    def select(self, cols):
        self.log.append(("select", cols))
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        self.log.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        self.log.append(("in", col, tuple(vals)))
        return self

    def gte(self, col, val):
        self.filters.append(lambda r: r.get(col) >= val)
        return self

    def lt(self, col, val):
        self.filters.append(lambda r: r.get(col) < val)
        return self

    def ilike(self, col, pat):
        needle = pat.strip("%").lower()
        self.filters.append(lambda r: needle in (r.get(col) or "").lower())
        return self

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        out = [dict(r) for r in self.rows if all(f(r) for f in self.filters)]
        return _Res(out[: self.n] if self.n else out)


class FakeSupabase:
    def __init__(self, rows):
        self.rows, self.log = rows, []

    def table(self, name):
        assert name == "full_judgments"
        return FakeQuery(self.rows, self.log)


ROWS = [
    {"id": "a", "case_id": "2020_SCMR_281", "neutral_citation": "2020 SCMR 281", "case_title": "Muhammad Akram v. The State",
     "court_name": "Supreme Court of Pakistan", "full_text": "JUDGMENT\n" + "The appeal is allowed. " * 80, "headnote": "Bail."},
    {"id": "b", "case_id": "2021_SCMR_14", "neutral_citation": "2021 SCMR 14", "case_title": "Zahid v. Bashir",
     "court_name": "Supreme Court of Pakistan", "full_text": "", "headnote": "Short headnote. " * 20},
    {"id": "c", "case_id": "2021_SCMR_140", "neutral_citation": "2021 SCMR 140", "case_title": "Akram Khan v. Federation",
     "court_name": "Supreme Court of Pakistan", "full_text": "", "headnote": "Another headnote. " * 20},
]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    case_store._case_cache.clear()
    case_store._bundle_cache.clear()
    case_store._ct_cache.clear()
    monkeypatch.setattr(case_store, "get_case_text_record", lambda cid: None)
    fake = FakeSupabase(ROWS)
    monkeypatch.setattr("legal_ai.config.get_supabase_client", lambda: fake)
    monkeypatch.setattr(case_store, "_normalize_case_record", lambda r: r)
    return fake


def test_normalize_case_id():
    assert case_store.normalize_case_id("2021 SCMR 1463") == "2021_SCMR_1463"
    assert case_store.normalize_case_id(" 2021_scmr_1463 ") == "2021_SCMR_1463"


def test_get_case_by_identifier_uses_case_id_and_caches(_fresh):
    c = case_store.get_case_by_identifier("2020 SCMR 281")
    assert c["case_id"] == "2020_SCMR_281"
    assert (c["year"], c["journal"], c["page"]) == (2020, "SCMR", 281)
    assert any(e[0] == "in" and e[1] == "case_id" and "2020_SCMR_281" in e[2] for e in _fresh.log)
    n = len(_fresh.log)
    assert case_store.get_case_by_identifier("2020_scmr_281")["case_id"] == "2020_SCMR_281"
    assert len(_fresh.log) == n  # served from cache
    assert case_store.get_case_by_identifier("1999 PLD 1") is None


def test_zilliz_style_keys_resolve_without_court_code():
    assert case_store._variants("2020_SCMR_SC_281") == ["2020_SCMR_SC_281", "2020_SCMR_281"]
    assert case_store._variants("2020_SCMR_281") == ["2020_SCMR_281"]
    assert case_store.get_case_by_identifier("2020_SCMR_SC_281")["case_id"] == "2020_SCMR_281"
    got = case_store.get_cases_batch(["2021_SCMR_SC_14", "2021 SCMR 14"])
    assert [c["case_id"] for c in got] == ["2021_SCMR_14"]


def test_get_cases_batch_skips_unknown():
    got = case_store.get_cases_batch(["2021 SCMR 14", "2020_SCMR_281", "nope_1", "2021 SCMR 14"])
    assert sorted(c["case_id"] for c in got) == ["2020_SCMR_281", "2021_SCMR_14"]


def test_get_cases_batch_without_supabase(monkeypatch):
    monkeypatch.setattr("legal_ai.config.get_supabase_client", lambda: None)
    assert case_store.get_cases_batch(["2021 SCMR 14"]) == []


def _zip(pages):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for p, data in pages.items():
            zf.writestr(f"{p}.pdf", data)
    return buf.getvalue()


def test_pdf_bundle_lookup(monkeypatch):
    monkeypatch.setattr("legal_ai.storage.r2_text_store.r2_configured", lambda: True)
    keys = []
    monkeypatch.setattr("legal_ai.storage.r2_text_store._signed_get",
                        lambda key, timeout_s: keys.append(key) or _zip({251: b"%PDF-a", 499: b"%PDF-b"}))
    assert case_store.get_case_pdf_bytes("1984_SCMR_251") == b"%PDF-a"
    assert case_store.get_case_pdf_bytes("x", target_year=1984, target_journal="scmr", target_page="499") == b"%PDF-b"
    assert keys == ["pdfs/v1/SCMR/1984/1.zip"]  # second call served from the bundle cache
    assert case_store.get_case_pdf_bytes("1984_SCMR_300") is None
    assert case_store.get_case_pdf_bytes("no citation here") is None


def test_pdf_lookup_when_r2_not_configured(monkeypatch):
    monkeypatch.setattr("legal_ai.storage.r2_text_store.r2_configured", lambda: False)
    assert case_store.get_case_pdf_bytes("1984_SCMR_251") is None


def test_legacy_statute_lookup(monkeypatch):
    recs = [{"canonical_id": "AMLA_2010_SEC_3", "act_code": "AMLA_2010", "section_num": "3", "title": "Offence",
             "verbatim_text": "text", "in_force": 1}]
    blob = gzip.compress(json.dumps(recs).encode())
    monkeypatch.setattr("legal_ai.storage.r2_text_store.r2_configured", lambda: True)
    monkeypatch.setattr("legal_ai.storage.r2_text_store._signed_get", lambda key, timeout_s: blob)
    monkeypatch.setattr(case_store, "_statutes", None)
    monkeypatch.setattr(case_store, "_statutes_by_act_sec", {})
    assert case_store.get_statute_provision("amla_2010_sec_3")["title"] == "Offence"
    assert case_store.get_statute_provision("AMLA_2010_SEC_3", act_code="AMLA_2010")["title"] == "Offence"
    assert case_store.get_statute_provision("3", act_code="AMLA_2010")["title"] == "Offence"
    assert case_store.get_statute_provision("PPC_SEC_302", act_code="PPC") is None


def test_supabase_fallback_search_citation_prefix_and_title():
    from legal_ai.search.judgment_search_service import _supplement_with_supabase_cases
    res = []
    _supplement_with_supabase_cases("2021 SCMR 14", set(), res, limit=5)
    assert [r["case_id"] for r in res][:1] == ["2021_SCMR_14"]  # exact hit first
    assert {r["case_id"] for r in res} == {"2021_SCMR_14", "2021_SCMR_140"}
    res = []
    _supplement_with_supabase_cases("Akram", set(), res, limit=5)
    assert {r["case_id"] for r in res} == {"2020_SCMR_281", "2021_SCMR_140"}


class FakeZilliz:
    def __init__(self, hits=None, exc=None):
        self.hits, self.exc, self.calls = hits or [], exc, []

    def search(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return [self.hits]


def _hit(case_key, score, court="LHC", section="headnote"):
    return {"distance": score, "entity": {"case_key": case_key, "citation": case_key.replace("_LHC", "").replace("_", " "),
                                          "journal": "PCRLJ", "year": 2021, "court_code": court,
                                          "content_level": "full_judgment", "section": section, "text": "cheque security"}}


def test_zilliz_keyword_index_shapes_results(monkeypatch):
    fake = FakeZilliz([_hit("2021_PCRLJ_LHC_1393", 38.7), _hit("2013_PCRLJ_PHC_400", 44.9, court="PHC", section="analysis")])
    monkeypatch.setattr("legal_ai.config.get_zilliz_client", lambda: fake)
    monkeypatch.setattr("legal_ai.retrieval.zilliz_search.is_zilliz_circuit_open", lambda: False)
    ix = zki.ZillizKeywordIndex()
    assert ix.corpus_size > 0
    out = ix.search("cheque   given as security", top_k=7)
    assert ix.last_backend == "zilliz_bm25"
    assert [d for d, _, _ in out] == ["2021_PCRLJ_LHC_1393", "2013_PCRLJ_PHC_400"]
    meta = out[1][2]
    assert meta["court"] == "Peshawar High Court" and meta["content_type"] == "full_text"
    assert out[0][2]["content_type"] == "headnote"
    call = fake.calls[0]
    assert call["anns_field"] == "sparse" and call["limit"] == 7 and call["group_by_field"] == "case_key"
    assert call["data"] == ["cheque given as security"]


class _Fallback:
    corpus_size = 10
    doc_metadata = [{"citation": "x"}]

    def search(self, query, top_k=40):
        return [("fb", 1.0, {"case_id": "fb"})]


def test_zilliz_keyword_index_falls_back(monkeypatch):
    monkeypatch.setattr("legal_ai.config.get_zilliz_client", lambda: FakeZilliz(exc=RuntimeError("down")))
    monkeypatch.setattr("legal_ai.retrieval.zilliz_search.is_zilliz_circuit_open", lambda: False)
    ix = zki.ZillizKeywordIndex(fallback=_Fallback())
    assert ix.search("anything")[0][0] == "fb"
    assert ix.last_backend == "in_memory_bm25_fallback"
    assert ix.doc_metadata == [{"citation": "x"}]
    bare = zki.ZillizKeywordIndex()
    assert bare.search("anything") == [] and bare.last_backend == "none"


def test_wrap_keyword_index(monkeypatch):
    monkeypatch.delenv("KEYWORD_SEARCH_BACKEND", raising=False)
    assert isinstance(zki.wrap_keyword_index(None), zki.ZillizKeywordIndex)
    monkeypatch.setenv("KEYWORD_SEARCH_BACKEND", "pickle")
    sentinel = object()
    assert zki.wrap_keyword_index(sentinel) is sentinel


def test_turso_copy_is_preferred_over_supabase(monkeypatch):
    full = "2021 S C M R 1463 ... Present: three Hon'ble Judges ... Appeal allowed"
    copy = {"2021_SCMR_1463": {"case_id": "2021_SCMR_1463", "neutral_citation": "2021 SCMR 1463", "year": 2021,
                               "journal": "SCMR", "page": 1463, "full_text": "portal summary", "headnote": full}}
    monkeypatch.setattr(case_store, "get_case_text_record", lambda cid: dict(copy[cid]) if cid in copy else None)
    c = case_store.get_case_by_identifier("2021 SCMR 1463")
    assert c["headnote"] == full and c["year"] == 2021
    got = case_store.get_cases_batch(["2021_SCMR_SC_1463", "2020 SCMR 281"])
    assert [g["case_id"] for g in got] == ["2021_SCMR_1463", "2020_SCMR_281"]  # copy first, Supabase for the rest


def test_case_text_record_reads_sharded_copy(monkeypatch):
    monkeypatch.undo()
    case_store._ct_cache.clear()
    key = case_store.case_text_key("2021_scmr_1463")
    assert key == "2021_SCMR_1463"
    obj = case_store.case_text_shard_key(key)
    assert obj.startswith("case_texts/v1/") and obj.endswith(".json.gz")
    blob = gzip.compress(json.dumps({key: {"case_id": key, "headnote": "h"}}).encode())
    calls = []
    monkeypatch.setattr("legal_ai.storage.r2_text_store.r2_configured", lambda: True)
    monkeypatch.setattr("legal_ai.storage.r2_text_store._signed_get", lambda o, timeout_s: calls.append(o) or blob)
    assert case_store.get_case_text_record("2021_SCMR_1463")["headnote"] == "h"
    assert case_store.get_case_text_record("2021_scmr_1463")["headnote"] == "h"
    assert calls == [obj]


def test_lookup_matches_real_citation_not_serial_case_id(monkeypatch):
    # full_judgments rows whose case_id page is a serial number, not the citation page
    rows = [
        {"id": "x1", "case_id": "1978_SCMR_31", "neutral_citation": "1978 SCMR 81", "case_title": "MUHAMMAD AKRAM v. STATE",
         "court_name": "Supreme Court of Pakistan", "full_text": "", "headnote": "hn"},
        {"id": "x2", "case_id": "1978_SCMR_81", "neutral_citation": "1978 SCMR 402", "case_title": "OTHER CASE",
         "court_name": "Supreme Court of Pakistan", "full_text": "", "headnote": "hn"},
        {"id": "x3", "case_id": "2003_PLD_LAH_102", "neutral_citation": "2003 PLD 102", "case_title": "LAHORE CASE",
         "court_name": "Lahore High Court", "full_text": "", "headnote": "hn"},
        {"id": "x4", "case_id": "2003_PLD_SC_102", "neutral_citation": "2003 PLD 102", "case_title": "SUPREME CASE",
         "court_name": "Supreme Court of Pakistan", "full_text": "", "headnote": "hn"},
    ]
    fake = FakeSupabase(rows)
    monkeypatch.setattr("legal_ai.config.get_supabase_client", lambda: fake)
    case_store._case_cache.clear()
    assert case_store.get_case_by_identifier("1978 SCMR 81")["case_title"] == "MUHAMMAD AKRAM v. STATE"
    # the row whose case_id is 1978_SCMR_81 is really 1978 SCMR 402 and must not be returned for 81
    assert case_store.get_case_by_identifier("1978 SCMR 402")["id"] == "x2"
    # a Zilliz key's court code picks the right series
    assert case_store.get_case_by_identifier("2003_PLD_SC_102")["case_title"] == "SUPREME CASE"
    assert case_store.get_case_by_identifier("2003_PLD_LHC_102")["case_title"] == "LAHORE CASE"
    got = case_store.get_cases_batch(["1978 SCMR 81", "1978_SCMR_402", "1999 SCMR 1"])
    assert [g["id"] for g in got] == ["x1", "x2"]


def _real_pdf(text):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


def test_shared_series_pdf_is_checked_against_the_case(monkeypatch):
    good = _real_pdf("2003 PLD 102 MUHAMMAD AJMAL VS THE STATE - SUPREME-COURT")
    monkeypatch.setattr("legal_ai.storage.r2_text_store.r2_configured", lambda: True)
    monkeypatch.setattr("legal_ai.storage.r2_text_store._signed_get", lambda key, timeout_s: _zip({102: good}))
    monkeypatch.setattr(case_store, "get_case_by_identifier",
                        lambda cid: {"case_title": "MUHAMMAD AJMAL v. THE STATE"})
    assert case_store.get_case_pdf_bytes("2003_PLD_SC_102") == good
    case_store._bundle_cache.clear()
    monkeypatch.setattr(case_store, "get_case_by_identifier",
                        lambda cid: {"case_title": "ZAHOOR ELAHI v. FEDERATION OF PAKISTAN"})
    assert case_store.get_case_pdf_bytes("2003_PLD_LAH_102") is None  # PDF is a different judgment
    case_store._bundle_cache.clear()
    monkeypatch.setattr(case_store, "get_case_by_identifier", lambda cid: None)
    assert case_store.get_case_pdf_bytes("2003_PLD_102") == good  # unknown title: don't block
