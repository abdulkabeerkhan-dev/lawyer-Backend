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


def test_pld_high_court_key_resolves(monkeypatch):
    from core import case_store
    rows = [{"id": "9", "case_id": "2024_PLD_LAH_1", "neutral_citation": "PLD 2024 Lah 1",
             "court_name": "Lahore High Court", "retrieval_status": "quarantined"},
            {"id": "8", "case_id": "2024_PLD_SC_1", "neutral_citation": "PLD 2024 SC 1",
             "court_name": "Supreme Court of Pakistan", "retrieval_status": None}]
    monkeypatch.setattr(case_store, "_supabase", lambda: _FakeSB(rows))
    got = case_store.retrieval_statuses(["2024_PLD_LHC_1", "2024_PLD_SC_1"])
    assert got == {"2024_PLD_LHC_1": "quarantined", "2024_PLD_SC_1": ""}


def test_production_cors_accepts_only_listed_origins(monkeypatch):
    import main
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://section-frontend-production-f959.up.railway.app")
    assert main._origin_is_allowed("https://section-frontend-production-f959.up.railway.app")
    for o in ("https://evil.up.railway.app", "https://x.lovable.app", "https://a.vercel.app", "https://b.netlify.app"):
        assert not main._origin_is_allowed(o), o
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert main._origin_is_allowed("https://preview.up.railway.app")


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/search/judgments/intelligent", {"query": "bail"}),
    ("post", "/api/search/judgments/keyword", {"query": "bail"}),
    ("post", "/api/search/judgments/citation", {"year": 2020, "journal": "SCMR", "page": 1}),
    ("post", "/api/search/judgments", {"query": "bail"}),
    ("post", "/api/search/statutes", {"query": "bail"}),
    ("get", "/api/search/statutes?query=bail", None),
])
def test_search_endpoints_require_sign_in(method, path, body):
    """These drive embedding spend and expose the whole case database, so a session is required."""
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    r = c.post(path, json=body) if method == "post" else c.get(path)
    assert r.status_code in (401, 403), (path, r.status_code)


def test_limitation_article_182_is_omitted():
    """Official Pakistan Code: 'Article 182 omitted by the Law Reforms Ordinance, 1972'."""
    rows = json.load(open(os.path.join(ROOT, "data/statute_tables/LIMITATION_1908.json"), encoding="utf-8"))
    art = {r["canonical_id"]: r for r in rows}["LIMITATION_1908_ART_182"]
    assert art["in_force"] is False


def test_no_omitted_record_claims_to_be_in_force():
    import glob
    for sub in ("statute_versions", "statute_tables", "statutes_v3_staging"):
        for f in glob.glob(os.path.join(ROOT, "data", sub, "*.json")):
            d = json.load(open(f, encoding="utf-8"))
            for r in d if isinstance(d, list) else []:
                st = r.get("status") if isinstance(r, dict) else None
                if isinstance(st, str) and st.lower() in ("omitted", "repealed"):
                    assert r.get("in_force") is False, (f, r.get("canonical_id"))


@pytest.mark.parametrize("q,want,never", [
    ("Someone keeps cyberstalking and harassing my sister online", ["PECA_2016_SEC_24"], ["PECA_2016_SEC_10"]),
    ("A fake account impersonating me was created on Facebook under PECA", ["PECA_2016_SEC_16"], ["PECA_2016_SEC_10"]),
    ("I was scammed by a phishing link, a cybercrime under PECA", ["PECA_2016_SEC_14"], ["PECA_2016_SEC_10"]),
    ("Posts threatening to terrorise the public and coerce the government, PECA offence", ["PECA_2016_SEC_10"], []),
])
def test_peca_offences_follow_the_facts(q, want, never):
    from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern
    r = extract_legal_issues_from_fact_pattern(q, planner_domain="cybercrime")
    issues = r.issues
    provs = [p for i in issues for p in (getattr(i, "controlling_provisions", None) or [])]
    for w in want:
        assert w in provs, (q, provs)
    for n in never:
        assert n not in provs, (q, provs)


def test_article_184_follows_the_27th_amendment():
    """Constitution (Twenty-seventh Amendment) Act, 2025: Art. 184 omitted; Art. 175E governs."""
    from legal_ai.query_engine import named_provisions as npv
    ids = npv.provisions_named_in("Can I file a petition under Article 184(3)?", lambda c: True)
    assert "CONST_1973_ART_175E" in ids
    assert "CONST_1973_ART_175E" in npv.provisions_for_topics("suo motu notice on a question of public importance", lambda c: True)
    from legal_ai.verification.doctrinal_rules import PATTERN_RULES, rule_matches_sentence
    rule = {r["id"]: r for r in PATTERN_RULES}["ART_184_3_OMITTED_2025"]
    assert rule_matches_sentence(rule, "The Supreme Court may exercise original jurisdiction under Article 184(3).", matter_type="constitutional")
    assert not rule_matches_sentence(rule, "Former Article 184(3), omitted by the 27th Amendment, is now Article 175E(3) before the Federal Constitutional Court.", matter_type="constitutional")
    rows = json.load(open(os.path.join(ROOT, "data/statutes_v3_staging/CONST_1973.json"), encoding="utf-8"))
    by = {r["canonical_id"]: r for r in rows}
    assert by["CONST_1973_ART_184"]["in_force"] is False
    assert "Federal Constitutional Court" in by["CONST_1973_ART_175E"]["text"]
    assert "Article 175F" in json.dumps([r for r in rows if r["canonical_id"] == "CONST_1973_ART_185"] or
                                        [r for f in [os.path.join(ROOT, "data/statutes_v3_staging/statutes_v2_legacy.json")]
                                         for r in json.load(open(f, encoding="utf-8")) if r["canonical_id"] == "CONST_1973_ART_185"])


def test_backend_sends_security_headers(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://section-frontend-production-f959.up.railway.app")
    r = TestClient(main.app).get("/health")
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h["x-content-type-options"] == "nosniff"
    assert "max-age=" in h["strict-transport-security"]
    assert "frame-ancestors 'self' https://section-frontend-production-f959.up.railway.app" in h["content-security-policy"]


def test_production_never_accepts_unsigned_tokens(monkeypatch):
    import asyncio, jwt as pyjwt
    import main
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    forged = pyjwt.encode({"sub": "user_victim", "iss": "https://clerk.attacker.com"}, "x" * 32, algorithm="HS256")
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.verify_clerk_session(HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)))
    assert e.value.status_code in (401, 403)


def test_access_request_sends_clerk_invitation(monkeypatch):
    import main
    sent = []

    class R:
        def __init__(self, data=None): self.data = data or []

    class T:
        def __init__(self, store): self.store, self.op, self.payload, self.flt = store, None, None, None
        def select(self, *_): self.op = "select"; return self
        def insert(self, row): self.op, self.payload = "insert", row; return self
        def update(self, row): self.op, self.payload = "update", row; return self
        def eq(self, k, v): self.flt = (k, v); return self
        def execute(self):
            if self.op == "select":
                return R([r for r in self.store if r.get(self.flt[0]) == self.flt[1]])
            if self.op == "insert":
                self.store.append(dict(self.payload)); return R([self.payload])
            for r in self.store:
                if r.get(self.flt[0]) == self.flt[1]: r.update(self.payload)
            return R()

    store = []

    class SB:
        def table(self, name): return T(store)

    monkeypatch.setattr(main, "supabase", SB())
    monkeypatch.setattr(main, "check_access_request_rate_limit", lambda r: None)
    monkeypatch.setattr(main, "send_clerk_invitation", lambda e, n="", f="": sent.append(e) or "invited")
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    r = c.post("/request-access", json={"full_name": "A B", "firm_name": "F", "email": "New.Lawyer@Example.com"})
    assert r.status_code == 200 and sent == ["new.lawyer@example.com"]
    assert store[0]["status"] == "invited"
    r2 = c.post("/request-access", json={"full_name": "A B", "firm_name": "F", "email": "new.lawyer@example.com"})
    assert r2.json()["status"] == "duplicate" and len(sent) == 1
    assert c.post("/request-access", json={"full_name": "x", "firm_name": "y", "email": "not-an-email"}).status_code == 422


def test_core_codes_are_not_labelled_under_review():
    """The PPC, CrPC and CPC names carried "(Under Review)" from the source file names, and users
    saw it on every answer citing them."""
    for code in ("PPC_1860", "CRPC_1898", "CPC_1908"):
        rows = json.load(open(os.path.join(ROOT, f"data/statutes_v3_staging/{code}.json"), encoding="utf-8"))
        assert rows and not any("Under Review" in (r.get("act_name") or "") + (r.get("text") or "") for r in rows), code
