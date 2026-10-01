"""
core/currency_fetcher.py

Statute Currency Fetcher (Part 1, Item 3)
Performs live currency checking against whitelisted Tier 1 portals (Pakistan Code, NA, Senate,
provincial code portals) with:
- 24-hour caching at the ACT level.
- Cache bypass ONLY on recency keywords.
- Strict 6.0s budget enforcement (fails open with NOT_CHECKED on timeout).
- Strict whitelist enforcement (rejects non-Tier-1 domains).
- Extraction into staging store ONLY (zero auto-promotion to main store).
- Logging to statute_currency_checks table (with graceful local fallback).
"""

import os
import re
import time
import json
import uuid
import inspect
import asyncio
import logging
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Callable, Union

from core.statute_currency import (
    global_statute_store,
    classify_source_tier,
    TIER_1_DOMAINS,
    RECENCY_WORDS_PATTERN,
    StatuteVersionStore
)

logger = logging.getLogger("currency_fetcher")
logger.setLevel(logging.INFO)

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTE_STAGING_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_staging")
CACHE_FILE_PATH = os.path.join(STATUTE_STAGING_DIR, "currency_cache.json")
LOG_FILE_PATH = os.path.join(STATUTE_STAGING_DIR, "statute_currency_checks.jsonl")

os.makedirs(STATUTE_STAGING_DIR, exist_ok=True)

# Whitelisted Tier 1 domains (single source of truth)
WHITELISTED_TIER_1_DOMAINS = list(TIER_1_DOMAINS)

# Canonical act full titles for targeted search
ACT_SEARCH_NAMES = {
    "PPC_1860": "Pakistan Penal Code",
    "CRPC_1898": "Code of Criminal Procedure",
    "CPC_1908": "Code of Civil Procedure",
    "CONST_1973": "Constitution of Pakistan",
    "QSO_1984": "Qanun-e-Shahadat Order",
    "CNSA_1997": "Control of Narcotic Substances Act",
    "LIMITATION_1908": "Limitation Act",
    "FAMILY_COURTS_1964": "Family Courts Act",
    "MFLO_1961": "Muslim Family Laws Ordinance",
    "DMMA_1939": "Dissolution of Muslim Marriages Act",
    "PRPA_2009": "Punjab Rented Premises Act",
    "PREEMPTION_1991": "Punjab Pre-emption Act",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# 24-hour cache TTL
CACHE_TTL_SECONDS = 24 * 3600


class CurrencyCache:
    """In-memory and file-backed cache for act-level currency checks."""

    def __init__(self, cache_file: str = CACHE_FILE_PATH):
        self.cache_file = cache_file
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._memory_cache = json.load(f)
            except Exception as e:
                logger.debug(f"Failed to load currency cache: {e}")
                self._memory_cache = {}

    def _save(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._memory_cache, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to persist currency cache: {e}")

    def get(self, act_code: str, bypass_cache: bool = False) -> Optional[Dict[str, Any]]:
        if bypass_cache:
            return None
        key = act_code.upper().strip()
        entry = self._memory_cache.get(key)
        if not entry:
            return None
        cached_time = entry.get("timestamp", 0)
        if (time.time() - cached_time) > CACHE_TTL_SECONDS:
            return None
        return entry.get("data")

    def set(self, act_code: str, data: Dict[str, Any]) -> None:
        key = act_code.upper().strip()
        self._memory_cache[key] = {
            "timestamp": time.time(),
            "data": data
        }
        self._save()

    def clear(self) -> None:
        self._memory_cache.clear()
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except Exception:
                pass


# Global cache instance
global_currency_cache = CurrencyCache()


def is_whitelisted_tier1_domain(url: str) -> bool:
    """Verifies that a URL strictly belongs to a whitelisted Tier 1 portal."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        domain = (parsed.netloc or "").lower().split(":")[0]
        return any(domain == d or domain.endswith("." + d) for d in WHITELISTED_TIER_1_DOMAINS)
    except Exception:
        return False


SIGNAL_TERMS_PATTERN = re.compile(
    r"\b(amendment|amended|ordinance|bill|act\s+no\.|repeal|repealed|substituted|omitted)\b",
    re.IGNORECASE
)


def log_statute_currency_check(
    act_code: str,
    query_text: str,
    status: str,
    duration_ms: int,
    signals_found: int,
    cache_hit: bool,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """Logs the check event locally and optionally to Supabase, strictly storing query hash rather than client facts."""
    query_hash = hashlib.sha256((query_text or "").encode("utf-8")).hexdigest()[:16]
    record = {
        "id": str(uuid.uuid4()),
        "act_code": act_code,
        "query_text": f"hash:{query_hash}",
        "query_hash": query_hash,
        "status": status,
        "duration_ms": duration_ms,
        "signals_found": signals_found,
        "cache_hit": cache_hit,
        "reason": reason,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }
    # Append to local JSONL log
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.debug(f"Local check log notice: {e}")

    # Optional Supabase log
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
        if supabase_url and supabase_key:
            from supabase import create_client
            client = create_client(supabase_url, supabase_key)
            client.table("statute_currency_checks").insert(record).execute()
    except Exception as e:
        logger.debug(f"Supabase statute_currency_checks insert notice: {e}")

    return record


def execute_portal_search_sync(act_code: str, query_text: str, max_results: int = 4) -> Dict[str, Any]:
    """
    Executes a web search against whitelisted Tier 1 portals and NA/Senate bill pages.
    Runs synchronously (wrapped by asyncio.to_thread in the caller).
    Requires positive evidence of an amendment/bill term in the title or snippet.
    Distinguishes:
    - 'no_pages_returned' when search yields 0 results.
    - 'no_signals_found' when pages exist on Tier 1 portals but none contain amendment terms.
    - 'signals_found' when legitimate amendment/bill signals are detected.
    - 'search_failed' on network or HTTP error.
    """
    act_name = ACT_SEARCH_NAMES.get(act_code.upper(), act_code.replace("_", " "))
    search_terms = f'"{act_name}" (amendment OR ordinance OR bill) site:pakistancode.gov.pk OR site:na.gov.pk OR site:senate.gov.pk'
    encoded_q = urllib.parse.quote(search_terms)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

    discovered: List[Dict[str, Any]] = []
    total_whitelisted_seen = 0
    search_outcome = "no_pages_returned"

    try:
        req = urllib.request.Request(search_url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            uddg_matches = re.findall(r'uddg=([^&]+)', html)
            snippets = re.findall(r'class="result__snippet[^"]*">(.*?)</a>', html, re.DOTALL)

            if not uddg_matches:
                return {
                    "signals": [],
                    "search_outcome": "no_pages_returned",
                    "total_seen": 0,
                    "sources_checked": ["Pakistan Code", "National Assembly", "Senate"]
                }

            for i, raw_u in enumerate(uddg_matches):
                u = urllib.parse.unquote(raw_u)
                if not is_whitelisted_tier1_domain(u):
                    continue
                total_whitelisted_seen += 1
                snip = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                title = f"Recent legislative signal for {act_name}"

                # Enforce Rule: Require signal evidence in title or snippet!
                combined_text = f"{title} {snip} {u}"
                match = SIGNAL_TERMS_PATTERN.search(combined_text)
                if not match:
                    continue
                matched_term = match.group(0).lower()

                discovered.append({
                    "source_url": u,
                    "title": title,
                    "snippet": snip,
                    "signal_term": matched_term,
                    "detected_change": f"Reported amendment/bill signal ({matched_term}) on {urllib.parse.urlparse(u).netloc}",
                    "source_tier": "tier_1",
                    "effective_application": "pending_and_prospective"
                })
                if len(discovered) >= max_results:
                    break

            if discovered:
                search_outcome = "signals_found"
            elif total_whitelisted_seen > 0:
                search_outcome = "no_signals_found"
            else:
                search_outcome = "no_pages_returned"

    except Exception as e:
        logger.debug(f"Tier 1 portal search notice: {e}")
        search_outcome = "search_failed"

    return {
        "signals": discovered,
        "search_outcome": search_outcome,
        "total_seen": total_whitelisted_seen,
        "sources_checked": ["Pakistan Code", "National Assembly", "Senate"]
    }


async def fetch_currency_signals(
    act_code: str,
    provisions: Optional[List[Any]] = None,
    query_text: str = "",
    budget_s: float = 6.0,
    mock_fetcher: Optional[Callable[..., Any]] = None,
    cache: Optional[CurrencyCache] = None,
    store: Optional[StatuteVersionStore] = None
) -> Dict[str, Any]:
    """
    Part 1, Item 3:
    Checks statute currency at the ACT level with:
    - 24-hour caching at the ACT level.
    - Bypass cache ONLY when query contains recency words.
    - Strict whitelisting: Only Tier 1 portals and NA/Senate bill pages.
    - Fail open with NOT_CHECKED on timeout (budget_s=6.0) or network failure.
    - Extract ONLY untrusted metadata into statute_staging (never auto-promoted).
    - Logs check to statute_currency_checks.
    """
    start_time = time.time()
    clean_act = act_code.upper().strip()
    active_cache = cache or global_currency_cache
    active_store = store or global_statute_store

    # 1. Determine if query contains recency words to bypass cache
    bypass_cache = bool(RECENCY_WORDS_PATTERN.search(query_text or ""))

    # 2. Check 24-hour cache
    if not bypass_cache:
        cached_result = active_cache.get(clean_act, bypass_cache=False)
        if cached_result:
            duration_ms = int((time.time() - start_time) * 1000)
            log_statute_currency_check(
                act_code=clean_act,
                query_text=query_text,
                status=cached_result.get("status", "CHECKED"),
                duration_ms=duration_ms,
                signals_found=len(cached_result.get("signals", [])),
                cache_hit=True
            )
            cached_result["cache_hit"] = True
            return cached_result

    # 3. Execute search with strict budget enforcement
    status = "CHECKED"
    reason = None
    signals: List[Dict[str, Any]] = []
    search_outcome = "clean_check"
    sources_checked = ["Pakistan Code", "National Assembly", "Senate"]

    try:
        if mock_fetcher:
            if inspect.iscoroutinefunction(mock_fetcher):
                raw_res = await asyncio.wait_for(
                    mock_fetcher(act_code=clean_act, query_text=query_text, provisions=provisions),
                    timeout=budget_s
                )
            else:
                raw_res = await asyncio.wait_for(
                    asyncio.to_thread(mock_fetcher, act_code=clean_act, query_text=query_text, provisions=provisions),
                    timeout=budget_s
                )
        else:
            raw_res = await asyncio.wait_for(
                asyncio.to_thread(execute_portal_search_sync, clean_act, query_text),
                timeout=budget_s
            )

        if isinstance(raw_res, dict):
            raw_signals = raw_res.get("signals", [])
            search_outcome = raw_res.get("search_outcome", "signals_found" if raw_signals else "no_signals_found")
            sources_checked = raw_res.get("sources_checked", sources_checked)
        elif isinstance(raw_res, list):
            raw_signals = raw_res
            search_outcome = "signals_found" if raw_signals else "no_signals_found"
        else:
            raw_signals = []
            search_outcome = "no_pages_returned"

        # Enforce Rule: Failed or empty searches do NOT report clean checks
        if search_outcome == "no_pages_returned":
            status = "NOT_CHECKED"
            reason = "no_pages_returned"
            signals = []
        elif search_outcome == "search_failed":
            status = "NOT_CHECKED"
            reason = "search_failed"
            signals = []
        elif search_outcome == "no_signals_found":
            status = "CHECKED"
            reason = "no_signals_found"
            signals = []
        else:
            status = "CHECKED"
            reason = "signals_found"

        # 4. Filter strictly by whitelisted Tier 1 domains and stage findings with signal evidence
        if status == "CHECKED" and raw_signals:
            for item in raw_signals:
                url = item.get("source_url") or ""
                if not is_whitelisted_tier1_domain(url):
                    logger.debug(f"Rejecting non-whitelisted domain: {url}")
                    continue

                sig_term = item.get("signal_term")
                if not sig_term:
                    match = SIGNAL_TERMS_PATTERN.search(f"{item.get('title','')} {item.get('snippet','')} {url}")
                    if not match:
                        continue
                    sig_term = match.group(0).lower()

                target_cid = None
                if provisions:
                    first_prov = provisions[0]
                    if isinstance(first_prov, tuple) and len(first_prov) > 0:
                        target_cid = first_prov[0]
                    elif isinstance(first_prov, str):
                        target_cid = first_prov
                    elif isinstance(first_prov, dict):
                        target_cid = first_prov.get("canonical_id")

                if not target_cid:
                    target_cid = f"{clean_act}_GENERIC"

                staged = active_store.stage_finding(
                    canonical_id=target_cid,
                    act_code=clean_act,
                    query_trigger=query_text,
                    detected_change=item.get("detected_change") or item.get("title") or "Recent legislative development",
                    source_url=url,
                    raw_snippet=item.get("snippet", ""),
                    effective_application=item.get("effective_application", "pending_and_prospective"),
                    ordinance_expiry=item.get("ordinance_expiry"),
                    signal_term=sig_term
                )
                signals.append(staged)

        if status == "CHECKED" and not signals:
            reason = "no_signals_found"
            search_outcome = "no_signals_found"

    except asyncio.TimeoutError:
        status = "NOT_CHECKED"
        search_outcome = "budget_timeout"
        reason = "budget_timeout"
        signals = []
    except Exception as fetch_err:
        status = "NOT_CHECKED"
        search_outcome = "search_failed"
        reason = str(fetch_err)
        signals = []

    duration_ms = int((time.time() - start_time) * 1000)

    result_payload = {
        "status": status,
        "act_code": clean_act,
        "signals": signals,
        "search_outcome": search_outcome,
        "sources_checked": sources_checked,
        "cache_hit": False,
        "reason": reason,
        "duration_ms": duration_ms,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }

    # Cache only genuine clean checks or positive signals
    if status == "CHECKED":
        active_cache.set(clean_act, result_payload)

    # Log to statute_currency_checks with query_hash
    log_statute_currency_check(
        act_code=clean_act,
        query_text=query_text,
        status=status,
        duration_ms=duration_ms,
        signals_found=len(signals),
        cache_hit=False,
        reason=reason
    )

    return result_payload
