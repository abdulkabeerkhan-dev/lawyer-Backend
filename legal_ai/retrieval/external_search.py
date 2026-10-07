"""
legal_ai/retrieval/external_search.py

External Fallback Search driver for fresh judicial portals (Supreme Court & High Courts)
and online law reporters when corpus-miss occurs.
"""

import sys
from typing import Dict, List, Any, Optional
from legal_ai.ranking.court_weighting import normalize_court_name


async def search_external_judgments(
    query_text: str,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Executes external judicial portal and SearxNG searches for fresh court precedents.
    """
    if not query_text:
        return []

    try:
        from core.recent_judgments_search import search_recent_external_judgments
        external_results = search_recent_external_judgments(query_text, max_results=max_results)
    except Exception as e:
        print(f"⚠️ [ExternalSearch] External search error: {e}", file=sys.stderr)
        return []

    candidates: List[Dict[str, Any]] = []
    for item in (external_results or []):
        meta = item.get("metadata", {}) if isinstance(item, dict) else getattr(item, "metadata", {}) or {}
        cid = str(item.get("case_id") or item.get("id") or meta.get("case_id") or "").strip()
        cit = str(item.get("citation") or item.get("neutral_citation") or meta.get("citation") or cid).strip()
        title = str(item.get("title") or item.get("case_title") or meta.get("title") or "Recent Judgment").strip()
        court = normalize_court_name(str(item.get("court") or meta.get("court") or "Supreme Court of Pakistan"))
        text = str(item.get("text") or item.get("full_text") or meta.get("text") or "").strip()

        candidates.append({
            "id": cid or cit,
            "score": 0.50,
            "dense_score": 0.0,
            "sparse_score": 0.0,
            "rrf_score": 0.0,
            "source_type": "External",
            "is_external": True,
            "citation": cit,
            "title": title,
            "case_name": title,
            "court": court,
            "year": item.get("year", 2026),
            "content_type": "full_text" if len(text.split()) >= 150 else "headnote_only",
            "preview": text[:400],
            "metadata": meta or item
        })

    return candidates
