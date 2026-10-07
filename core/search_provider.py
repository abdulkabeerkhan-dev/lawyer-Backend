"""
core/search_provider.py

One search layer for: the statute currency check, the recent-judgments search, and the
forum-gap fallback. Replaces scraping html.duckduckgo.com, which returns bot challenges
from cloud servers.

Rules
- Every call returns a SearchResponse with an explicit status. "empty", "blocked",
  "rate_limited", "failed", "quota_exhausted", "circuit_open" and "not_configured" are
  never confused with each other or with a clean "ok" result.
- Results are filtered by HOSTNAME against an allowed list, in code. The site: operator
  is a hint only, never the control.
- A circuit breaker stops hammering a failing provider; a daily cap controls cost.
- Search text should be an act name or issue words. Never send client facts.
- Network access is injectable (http_get) so tests never touch the internet.
- LEGAL REPRODUCTION GUARDRAIL: Sindh High Court (caselaw.shc.gov.pk / shc.gov.pk)
  terms prohibit reproduction of judgment text without the Registrar's permission.
  SHC search results are strictly restricted to LINK AND CITE ONLY (generating clickable
  neutral links and citations). Never ingest, scrape, or reproduce judgment bodies from SHC.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Tuple

OK = "ok"
EMPTY = "empty"
BLOCKED = "blocked"
RATE_LIMITED = "rate_limited"
FAILED = "failed"
QUOTA_EXHAUSTED = "quota_exhausted"
CIRCUIT_OPEN = "circuit_open"
NOT_CONFIGURED = "not_configured"

HttpGet = Callable[[str, Dict[str, str], float], Tuple[int, str]]

_BLOCK_MARKERS = re.compile(
    r"anomaly-modal|bot-detection|cf-chl|cf-challenge|captcha|unusual traffic|"
    r"are you a (?:robot|human)|verify you are human|attention required",
    re.IGNORECASE,
)
_QUOTA_MARKERS = re.compile(r"quota|limitexceeded|ratelimit|rate limit", re.IGNORECASE)


@dataclass
class SearchResponse:
    status: str
    results: List[Dict] = field(default_factory=list)
    provider: str = ""
    error: Optional[str] = None
    elapsed_ms: int = 0
    raw_count: int = 0
    dropped_off_domain: int = 0

    @property
    def usable(self) -> bool:
        return self.status == OK


def default_http_get(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        return e.code, body


def host_allowed(url: str, allowed_hosts: Sequence[str]) -> bool:
    try:
        host = (urllib.parse.urlparse(url or "").hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return bool(host) and any(host == h or host.endswith("." + h) for h in allowed_hosts)


# --- Sindh High Court Guardrail ---
SHC_HOSTS = ("caselaw.shc.gov.pk", "shc.gov.pk")


class SindhHighCourtReproductionError(PermissionError):
    """Raised when an attempt is made to ingest, scrape, or reproduce judgment body text from Sindh High Court."""
    pass


def is_shc_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url or "").hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return bool(host) and any(host == h or host.endswith("." + h) for h in SHC_HOSTS)


def enforce_no_shc_ingestion(url: str, text: Optional[str] = None) -> None:
    """Enforces the SHC reproduction prohibition: blocks ingestion and body reproduction."""
    if is_shc_url(url) and text:
        raise SindhHighCourtReproductionError(
            f"Reproduction of Sindh High Court judgment text from {url} is prohibited under SHC copyright terms. "
            "SHC materials are strictly restricted to LINK AND CITE ONLY."
        )


def sanitize_result_guardrails(res: Dict) -> Dict:
    """Sanitizes search result to enforce copyright reproduction restrictions."""
    u = res.get("url") or res.get("link") or ""
    if is_shc_url(u):
        res["snippet"] = ""
        res["body"] = ""
        res["reproduction_restricted"] = True
        res["restriction_reason"] = "SHC terms prohibit reproduction without Registrar permission. Link and cite only."
    return res


class BaseProvider:
    name = "base"

    def __init__(
        self,
        allowed_hosts: Sequence[str],
        http_get: Optional[HttpGet] = None,
        timeout_s: float = 4.0,
        daily_cap: int = 500,
        failure_threshold: int = 3,
        cooldown_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], str] = lambda: date.today().isoformat(),
    ):
        self.allowed_hosts = [h.lower() for h in allowed_hosts]
        self.http_get = http_get or default_http_get
        self.timeout_s = timeout_s
        self.daily_cap = daily_cap
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._clock, self._today = clock, today
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._count_day, self._count = today(), 0

    # --- provider-specific hooks ---
    def _build(self, query: str, max_results: int) -> Tuple[str, Dict[str, str]]:
        raise NotImplementedError

    def _parse(self, body: str) -> List[Dict]:
        raise NotImplementedError

    # --- shared behaviour ---
    def _scope(self, query: str) -> str:
        # Prioritize apex and high court judgment portals (SC, SHC caselaw, LHC) so they are not cut off
        priority_order = [
            "supremecourt.gov.pk",
            "caselaw.shc.gov.pk",
            "shc.gov.pk",
            "lhc.gov.pk",
            "sys.lhc.gov.pk",
            "ihc.gov.pk",
            "phc.gov.pk",
            "bhc.gov.pk",
            "federalshariatcourt.gov.pk",
        ]
        ordered = [h for h in priority_order if h in self.allowed_hosts]
        remaining = [h for h in self.allowed_hosts if h not in ordered]
        scoped = (ordered + remaining)[:10]
        hosts = " OR ".join(f"site:{h}" for h in scoped)
        return f"{query} ({hosts})" if hosts else query

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        t0 = self._clock()

        def done(status, results=None, error=None, raw=0, dropped=0):
            return SearchResponse(status, results or [], self.name, error,
                                  int((self._clock() - t0) * 1000), raw, dropped)

        if self._clock() < self._open_until:
            return done(CIRCUIT_OPEN, error="provider temporarily disabled after repeated failures")
        if self._today() != self._count_day:
            self._count_day, self._count = self._today(), 0
        if self._count >= self.daily_cap:
            return done(QUOTA_EXHAUSTED, error="daily search cap reached")
        self._count += 1

        try:
            url, headers = self._build(self._scope(query), max_results)
            code, body = self.http_get(url, headers, self.timeout_s)
        except Exception as e:  # timeout, DNS, TLS
            return self._fail(done, FAILED, f"{type(e).__name__}")

        if code == 429:
            return self._fail(done, RATE_LIMITED, "http 429")
        if code in (401, 403):
            status = RATE_LIMITED if _QUOTA_MARKERS.search(body or "") else BLOCKED
            return self._fail(done, status, f"http {code}")
        if code >= 500:
            return self._fail(done, FAILED, f"http {code}")
        looks_html = (body or "").lstrip()[:1] == "<"
        if looks_html and _BLOCK_MARKERS.search(body or ""):
            return self._fail(done, BLOCKED, f"challenge page (http {code})")
        if code != 200:
            return self._fail(done, FAILED, f"http {code}")

        try:
            parsed = self._parse(body)
        except Exception as e:
            return self._fail(done, FAILED, f"parse error: {type(e).__name__}")

        kept = [sanitize_result_guardrails(r) for r in parsed if r.get("url") and host_allowed(r["url"], self.allowed_hosts)]
        self._consecutive_failures = 0
        dropped = len(parsed) - len(kept)
        if not kept:
            return done(EMPTY, [], None, len(parsed), dropped)
        return done(OK, kept[:max_results], None, len(parsed), dropped)

    def _fail(self, done, status, error):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._open_until = self._clock() + self.cooldown_s
            self._consecutive_failures = 0
        return done(status, error=error)


class GoogleCSEProvider(BaseProvider):
    name = "google_cse"

    def __init__(self, api_key: str, cx: str, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key, self.cx = api_key, cx

    def _build(self, query, max_results):
        q = urllib.parse.urlencode({"key": self.api_key, "cx": self.cx, "q": query,
                                    "num": max(1, min(int(max_results), 10))})
        return f"https://www.googleapis.com/customsearch/v1?{q}", {"Accept": "application/json"}

    def _parse(self, body):
        data = json.loads(body)
        out = []
        for it in data.get("items", []) or []:
            meta = ((it.get("pagemap") or {}).get("metatags") or [{}])[0]
            out.append({"title": it.get("title", ""), "url": it.get("link", ""),
                        "snippet": it.get("snippet", ""),
                        "date": meta.get("article:published_time") or meta.get("date")})
        return out


class SearxNGProvider(BaseProvider):
    name = "searxng"

    def __init__(self, base_url: str, *a, api_key: Optional[str] = None, **kw):
        super().__init__(*a, **kw)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _build(self, query, max_results):
        q = urllib.parse.urlencode({"q": query, "format": "json", "language": "en"})
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return f"{self.base_url}/search?{q}", headers

    def _parse(self, body):
        data = json.loads(body)
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("content", ""), "date": r.get("publishedDate")}
                for r in data.get("results", []) or []]


class UnconfiguredProvider(BaseProvider):
    """Returned when no provider is configured, so callers see NOT_CONFIGURED, never a fake empty."""
    name = "unconfigured"

    def search(self, query, max_results=5):
        return SearchResponse(NOT_CONFIGURED, [], self.name, "no search provider configured")


def build_provider_from_env(env: Dict[str, str], allowed_hosts: Sequence[str],
                            http_get: Optional[HttpGet] = None) -> BaseProvider:
    kind = (env.get("SEARCH_PROVIDER") or "").strip().lower()
    cap = int(env.get("SEARCH_DAILY_CAP", "500") or 500)
    if kind == "google_cse" and env.get("GOOGLE_CSE_KEY") and env.get("GOOGLE_CSE_CX"):
        return GoogleCSEProvider(env["GOOGLE_CSE_KEY"], env["GOOGLE_CSE_CX"],
                                 allowed_hosts, http_get, daily_cap=cap)
    if kind == "searxng" and env.get("SEARXNG_URL"):
        api_key = env.get("SEARXNG_API_KEY") or env.get("SEARXNG_SECRET")
        return SearxNGProvider(env["SEARXNG_URL"], allowed_hosts, http_get, daily_cap=cap, api_key=api_key)
    return UnconfiguredProvider(allowed_hosts)


def to_outcome(resp: SearchResponse) -> Dict[str, str]:
    """Map a response to the three states the currency labels need."""
    if resp.status == OK:
        return {"state": "results", "reason": ""}
    if resp.status == EMPTY:
        return {"state": "no_pages_returned", "reason": "search returned no pages from the allowed sources"}
    return {"state": "search_failed", "reason": f"{resp.status}: {resp.error or 'no detail'}"}
