"""Security fixes from the Nov 27 2026 hardening pass."""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class _Res:
    def __init__(self, data=None):
        self.data = data or []


class _Table:
    """Just enough of the supabase-py query builder for these endpoints."""

    def __init__(self, rows):
        self.rows, self.op, self.payload, self.filters = rows, "select", None, []

    def select(self, *_a, **_k): self.op = "select"; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def upsert(self, row): self.op, self.payload = "upsert", row; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.filters.append((k, v)); return self
    def limit(self, *_): return self

    def _match(self):
        return [r for r in self.rows if all(r.get(k) == v for k, v in self.filters)]

    def execute(self):
        hit = self._match()
        if self.op == "select":
            return _Res([dict(r) for r in hit])
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
            return _Res([dict(r) for r in hit])
        if self.op in ("upsert", "insert"):
            self.rows.append(dict(self.payload))
            return _Res([dict(self.payload)])
        for r in hit:
            self.rows.remove(r)
        return _Res(hit)


class _DB:
    def __init__(self, **tables):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        return _Table(self.tables.setdefault(name, []))


@pytest.fixture
def app_with(monkeypatch):
    import main

    def make(db, user_id, verified_email="", admin=False):
        monkeypatch.setattr(main, "supabase", db)
        monkeypatch.setattr(main, "safe_supabase_query", lambda fn: fn())
        monkeypatch.setattr(main, "clerk_verified_email", lambda uid: verified_email)
        main.app.dependency_overrides[main.verify_clerk_session] = lambda: user_id
        if admin:
            main.app.dependency_overrides[main.verify_admin_role] = lambda: user_id
        return TestClient(main.app)

    yield make
    main.app.dependency_overrides.clear()


def test_sync_ignores_email_sent_by_the_browser(app_with, monkeypatch):
    """A new account claiming the admin's email must neither take over the admin's row nor get admin."""
    monkeypatch.setenv("ADMIN_EMAILS", "boss@firm.pk")
    db = _DB(users=[{"id": "user_boss", "email": "boss@firm.pk", "full_name": "Boss", "role": "admin"}],
             access_requests=[{"email": "boss@firm.pk", "status": "admin_approved"}])
    c = app_with(db, "user_attacker", verified_email="attacker@mail.com")
    r = c.post("/users/sync", json={"email": "boss@firm.pk", "full_name": "Mallory"})
    assert r.status_code == 200
    body = r.json()["user"]
    assert body["email"] == "attacker@mail.com" and body["role"] == "associate"
    boss = next(u for u in db.tables["users"] if u["email"] == "boss@firm.pk")
    assert boss["id"] == "user_boss" and boss["role"] == "admin"


def test_sync_without_verified_email_writes_nothing(app_with):
    db = _DB(users=[{"id": "user_boss", "email": "boss@firm.pk", "role": "admin"}])
    c = app_with(db, "user_new", verified_email="")
    r = c.post("/users/sync", json={"email": "boss@firm.pk", "full_name": "X"})
    assert r.json()["status"] == "fallback"
    assert [u["id"] for u in db.tables["users"]] == ["user_boss"]


def test_sync_grants_admin_only_to_verified_admin_email(app_with, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@firm.pk")
    db = _DB(users=[], access_requests=[{"email": "boss@firm.pk", "status": "admin_approved"}])
    c = app_with(db, "user_boss", verified_email="boss@firm.pk")
    assert c.post("/users/sync", json={"full_name": "Boss"}).json()["user"]["role"] == "admin"


def test_associate_status_cannot_set_a_role(app_with, monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(main, "clerk_backend_request", lambda m, p, b=None: calls.append((m, p)) or {})
    db = _DB(users=[{"id": "user_a", "role": "associate", "status": "active"}])
    c = app_with(db, "user_admin", admin=True)
    assert c.post("/admin/associates/user_a/status", json={"status": "admin"}).status_code == 422
    assert c.post("/admin/associates/user_admin/status", json={"status": "inactive"}).status_code == 400
    r = c.post("/admin/associates/user_a/status", json={"status": "inactive"})
    assert r.status_code == 200
    assert db.tables["users"][0] == {"id": "user_a", "role": "associate", "status": "inactive"}
    assert calls == [("POST", "/users/user_a/ban")]
    c.post("/admin/associates/user_a/status", json={"status": "active"})
    assert calls[-1] == ("POST", "/users/user_a/unban")


def test_removing_an_associate_also_bans_the_clerk_account(app_with, monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(main, "clerk_backend_request", lambda m, p, b=None: calls.append((m, p)) or {})
    db = _DB(users=[{"id": "user_a"}])
    c = app_with(db, "user_admin", admin=True)
    assert c.delete("/admin/associates/user_admin").status_code == 400
    assert c.delete("/admin/associates/user_a").status_code == 200
    assert db.tables["users"] == [] and calls == [("POST", "/users/user_a/ban")]


def test_admin_errors_do_not_leak_internals(app_with):
    class Boom(_DB):
        def table(self, name):
            raise RuntimeError("relation users does not exist; host=db.internal")

    c = app_with(Boom(), "user_admin", admin=True)
    r = c.post("/admin/associates/user_a/status", json={"status": "active"})
    assert r.status_code == 500 and "db.internal" not in r.text


# ---- token checks, with a real RS256 key ------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_ISS = "https://clerk.example-test.net"


def _token(**claims):
    now = int(time.time())
    body = {"sub": "user_t", "iss": _ISS, "exp": now + 60, "iat": now, "azp": "https://sectionai.net"}
    body.update(claims)
    return pyjwt.encode(body, _KEY, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def verifier(monkeypatch):
    import main
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CLERK_ISSUER", _ISS)
    monkeypatch.setattr(main, "get_clerk_public_key", lambda kid, force_refresh=False: _KEY.public_key())
    monkeypatch.setattr(main, "get_authorized_testers", lambda: {"*"})
    monkeypatch.setattr(main, "is_user_deactivated", lambda uid: False)

    def run(tok):
        return asyncio.run(main.verify_clerk_session(HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok)))
    return run


def test_authorized_party_accepts_a_list(verifier, monkeypatch):
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTY", "https://sectionai.net, https://www.sectionai.net")
    assert verifier(_token()) == "user_t"
    assert verifier(_token(azp="https://www.sectionai.net")) == "user_t"
    with pytest.raises(HTTPException) as e:
        verifier(_token(azp="https://evil.example"))
    assert e.value.status_code == 401


def test_expired_tokens_get_seconds_not_minutes_of_grace(verifier):
    assert verifier(_token(exp=int(time.time()) - 5)) == "user_t"
    with pytest.raises(HTTPException):
        verifier(_token(exp=int(time.time()) - 120))


def test_deactivated_accounts_are_refused(verifier, monkeypatch):
    import main
    monkeypatch.setattr(main, "is_user_deactivated", lambda uid: uid == "user_t")
    with pytest.raises(HTTPException) as e:
        verifier(_token())
    assert e.value.status_code == 403


def test_is_user_deactivated_reads_status_and_survives_db_outage(monkeypatch):
    import main
    main._DEACTIVATED_CACHE.clear()
    monkeypatch.setattr(main, "supabase", _DB(users=[{"id": "user_x", "status": "inactive"}, {"id": "user_y", "status": "active"}]))
    assert main.is_user_deactivated("user_x") is True
    assert main.is_user_deactivated("user_y") is False

    class Down(_DB):
        def table(self, name):
            raise ConnectionError("down")

    monkeypatch.setattr(main, "supabase", Down())
    assert main.is_user_deactivated("user_z") is False
    assert main.is_user_deactivated("user_x") is True      # cached answer still applies
    main._DEACTIVATED_CACHE.clear()


# ---- request size, PDF links ------------------------------------------------------------------

def test_oversized_requests_are_refused(monkeypatch):
    import main
    monkeypatch.setattr(main, "MAX_REQUEST_BYTES", 1000)
    r = TestClient(main.app).post("/request-access", content=b"x" * 2000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_pdf_links_have_no_secret_written_in_the_code(monkeypatch):
    from core import pdf_resolver
    src = open(os.path.join(ROOT, "core/pdf_resolver.py"), encoding="utf-8").read()
    assert "section_ai_pdf_signing_secret" not in src
    monkeypatch.delenv("PDF_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    tok = pdf_resolver.create_hmac_pdf_token("PLD_2020_SC_1")
    assert pdf_resolver.verify_hmac_pdf_token(tok, "PLD_2020_SC_1")
    assert not pdf_resolver.verify_hmac_pdf_token(tok, "PLD_2020_SC_2")
    forged = pdf_resolver.create_hmac_pdf_token("PLD_2020_SC_1", secret="section_ai_pdf_signing_secret_prod_secure")
    assert not pdf_resolver.verify_hmac_pdf_token(forged, "PLD_2020_SC_1")


def test_anonymous_pdf_callers_are_rate_limited_per_ip():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert '"browser_user", "dev_bypass_user")' in src and 'rate_limit_id = "ip:" + (get_real_client_ip(request)' in src


def test_statute_search_falls_back_instead_of_crashing(monkeypatch):
    """When Zilliz is unreachable the local store answers; a typo here used to raise NameError,
    so every statute lookup silently returned nothing during a Zilliz outage."""
    from legal_ai.retrieval import statute_search
    monkeypatch.setattr(statute_search, "get_zilliz_client", lambda: None)
    hits = asyncio.run(statute_search.search_statutes_hybrid("punishment for cheating dishonestly inducing delivery", top_k=5))
    assert hits and any(h.get("canonical_id") == "PPC_1860_SEC_420" for h in hits)
    assert asyncio.run(statute_search.search_statutes_hybrid("cheating", top_k=3, act_codes=["PPC_1860"])) is not None
