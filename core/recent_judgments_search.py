import os
import re
import urllib.parse
import urllib.request
import asyncio
from typing import List, Dict, Any, Optional

WHITELISTED_COURT_DOMAINS = {
    "supremecourt.gov.pk": "Supreme Court of Pakistan",
    "lhc.gov.pk": "Lahore High Court",
    "sys.lhc.gov.pk": "Lahore High Court",
    "shc.gov.pk": "High Court of Sindh",
    "phc.gov.pk": "Peshawar High Court",
    "ihc.gov.pk": "Islamabad High Court",
    "balochistanhighcourt.gov.pk": "High Court of Balochistan",
    "fsc.gov.pk": "Federal Shariat Court",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def is_whitelisted_court_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return any(domain in host for domain in WHITELISTED_COURT_DOMAINS)
    except Exception:
        return False

def derive_court_from_url(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        for domain, court_name in WHITELISTED_COURT_DOMAINS.items():
            if domain in host:
                return court_name
    except Exception:
        pass
    return "Superior Court"

def _execute_sync_court_search(query_text: str, max_results: int = 3) -> List[Dict[str, Any]]:
    clean_q = re.sub(r'[^A-Za-z0-9\s\-]+', ' ', query_text).strip()
    words = [w for w in clean_q.split() if len(w) > 3][:5]
    issue_terms = " ".join(words) if words else clean_q[:40]

    site_filter = " OR ".join([f"site:{d}" for d in ["supremecourt.gov.pk", "lhc.gov.pk", "shc.gov.pk", "phc.gov.pk", "ihc.gov.pk", "fsc.gov.pk"]])
    search_q = f'"{issue_terms}" (judgment OR order) ({site_filter})'
    encoded_q = urllib.parse.quote(search_q)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

    results: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(search_url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            uddg_matches = re.findall(r'uddg=([^&]+)', html)
            snippets = re.findall(r'class="result__snippet[^"]*">(.*?)</a>', html, re.DOTALL)
            titles = re.findall(r'class="result__title[^"]*">(.*?)</h2>', html, re.DOTALL)

            for i, raw_u in enumerate(uddg_matches):
                u = urllib.parse.unquote(raw_u)
                if not is_whitelisted_court_url(u):
                    continue

                raw_title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else "Recent Judgment / Order"
                raw_snip = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""

                date_match = re.search(r'\b(202[0-6]|201[0-9])[-/\.](0[1-9]|1[0-2])[-/\.](0[1-9]|[12]\d|3[01])\b', raw_snip + " " + raw_title)
                decision_date = date_match.group(0) if date_match else "Recent"

                content_type = "judgment" if ("judgment" in (raw_title + raw_snip).lower()) else "order"

                results.append({
                    "url": u,
                    "title": raw_title,
                    "court": derive_court_from_url(u),
                    "date": decision_date,
                    "content_type": content_type,
                    "snippet": raw_snip[:300] if raw_snip else "Judgment or order available on portal."
                })
                if len(results) >= max_results:
                    break
    except Exception:
        pass

    return results

async def search_recent_external_judgments(query_text: str, budget_s: float = 5.0, mock_fetcher: Optional[Any] = None) -> List[Dict[str, Any]]:
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
            asyncio.to_thread(_execute_sync_court_search, query_text, max_results=3),
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
        court = r.get("court") or "Superior Court"
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
