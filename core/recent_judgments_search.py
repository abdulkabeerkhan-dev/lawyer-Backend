import os
import re
import urllib.parse
import urllib.request
import asyncio
from typing import List, Dict, Any, Optional

from core.domain_whitelist import (
    COURT_TIER_1_DOMAINS,
    COURT_DOMAIN_NAMES,
    is_whitelisted_court_url,
    derive_court_from_url as _derive_court_from_url
)
from core.search_provider import (
    BaseProvider,
    build_provider_from_env,
)

WHITELISTED_COURT_DOMAINS = COURT_DOMAIN_NAMES

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def derive_court_from_url(url: str) -> str:
    c = _derive_court_from_url(url)
    return c or "Superior Court"

def _execute_sync_court_search(
    query_text: str,
    max_results: int = 3,
    provider: Optional[BaseProvider] = None
) -> List[Dict[str, Any]]:
    clean_q = re.sub(r'[^A-Za-z0-9\s\-]+', ' ', query_text).strip()
    words = [w for w in clean_q.split() if len(w) > 3][:5]
    issue_terms = " ".join(words) if words else clean_q[:40]

    allowed_court_hosts = sorted(list(COURT_TIER_1_DOMAINS))
    if provider is None:
        provider = build_provider_from_env(os.environ, allowed_court_hosts)

    search_q = f'"{issue_terms}" (judgment OR order)'
    resp = provider.search(search_q, max_results=max_results)
    if not resp.usable:
        return []

    results: List[Dict[str, Any]] = []
    for hit in resp.results:
        u = hit.get("url") or ""
        if not is_whitelisted_court_url(u):
            continue

        raw_title = hit.get("title") or "Recent Judgment / Order"
        raw_snip = hit.get("snippet") or ""

        date_match = re.search(r'\b(202[0-6]|201[0-9])[-/\.](0[1-9]|1[0-2])[-/\.](0[1-9]|[12]\d|3[01])\b', raw_snip + " " + raw_title)
        decision_date = hit.get("date") or (date_match.group(0) if date_match else "Recent")
        content_type = "judgment" if ("judgment" in (raw_title + raw_snip).lower()) else "order"

        results.append({
            "url": u,
            "title": raw_title,
            "court": derive_court_from_url(u),
            "date": str(decision_date),
            "content_type": content_type,
            "snippet": raw_snip[:300] if raw_snip else "Judgment or order available on portal."
        })
        if len(results) >= max_results:
            break

    return results

async def search_recent_external_judgments(
    query_text: str,
    budget_s: float = 2.5,
    mock_fetcher: Optional[Any] = None,
    provider: Optional[BaseProvider] = None
) -> List[Dict[str, Any]]:
    """
    Always-on search for recent judgments on the same issue across official court portals.
    Isolated from primary corpus: nothing enters the database without approval.
    """
    if mock_fetcher:
        try:
            return await mock_fetcher(query_text)
        except Exception:
            return []

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_execute_sync_court_search, query_text, 3, provider),
            timeout=budget_s
        )
    except Exception:
        return []

def format_external_authorities_section(records: List[Dict[str, Any]]) -> str:
    """
    Renders discovered external authorities into a distinct, isolated section.
    """
    if not records:
        return ""

    lines = [
        "### External Authorities (Not Yet in Database)",
        "> *Note: The following authorities were identified via live search on official superior court portals. They have not yet been curated or indexed into the permanent primary database.*",
        ""
    ]
    for r in records:
        title = r.get("title") or "External Judgment"
        from core.court_taxonomy import get_effective_court
        court = get_effective_court(r) or "Superior Court"
        dt = r.get("date") or "Recent"

        c_type = r.get("content_type") or "judgment"
        url = r.get("url") or "#"
        snip = r.get("snippet") or ""

        lines.append(f"- **{title}** ({court}, {dt}, Content Type: {c_type})")
        lines.append(f"  - **Source URL**: {url}")
        if snip:
            lines.append(f"  - **Portal Summary**: {snip}")
        lines.append("")

    return "\n".join(lines).strip()
