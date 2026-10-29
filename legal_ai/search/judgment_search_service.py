"""
legal_ai/search/judgment_search_service.py

High-performance multi-mode judgment search service for Pakistani Case Law (1947 to 2026):
1. Citation Search (Year, Journal, Page, Court pinpoint lookup)
2. Keyword Search (Party names, terms, sections with filters)
3. Intelligent Search (Semantic neural vector search & issue matching)
"""

import os
import re
import json
import urllib.parse
from typing import Dict, List, Any, Optional, Union
from legal_ai.config import get_supabase_client, safe_supabase_query
from legal_ai.retrieval.bm25_search import search_bm25_sparse
from legal_ai.ranking.court_weighting import normalize_court_name
from legal_ai.synthesis.memorandum_generator import sanitize_precedent_card


def clean_case_title(raw_title: str, text: str = "") -> str:
    """Cleans up raw case titles, stripping leading digits, journal codes, or tabs."""
    t = str(raw_title or "").strip()
    # Strip reporter number prefix e.g. "301 2000 MLD 1345 MUHAMMAD HANIF..."
    t = re.sub(r'^\d+\s+\d{4}\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+\d+\s+', '', t)
    # Strip citation prefix
    t = re.sub(r'^(?:\[[^\]]*\]\s*)?(?:CITATION:\s*[^\n]+\s*)?(?:TITLE:\s*)?', '', t, flags=re.IGNORECASE)
    # Strip reporter tab prefix
    t = re.sub(r'^\d{4}\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+\d+\s+—\s+', '', t)
    t = t.strip()
    if not t or t.lower() in ("precedent on record", "reported precedent", "none", "unknown"):
        # Attempt extraction from text
        m_vs = re.search(r'([A-Z0-9\s,\.\(\)/\-\'&]+?\s+(?:VS|V\.|VERSUS)\s+[A-Z0-9\s,\.\(\)/\-\'&]+)', text)
        if m_vs:
            t = m_vs.group(1).strip()
        else:
            t = "Precedent on Record"
    return t


def build_precedent_result(
    cid: str,
    cit: str,
    title: str,
    court: str,
    year: Union[int, str],
    snippet: str = "",
    pdf_url: Optional[str] = None,
    score: float = 1.0,
    bench: str = "",
    source_type: str = "Primary Law Report"
) -> Dict[str, Any]:
    """Builds a standardized, clean precedent card for frontend display."""
    clean_t = clean_case_title(title, snippet)
    clean_c = normalize_court_name(court)
    clean_id = str(cid).strip()

    if not pdf_url:
        encoded_id = urllib.parse.quote(clean_id)
        pdf_url = f"/api/judgments/{encoded_id}/pdf"

    # Clean holding snippet
    holding = snippet.strip()
    holding = re.sub(r'^(?:\[[^\]]*\]\s*)?(?:CITATION:\s*[^\n]+\s*)?(?:TITLE:\s*[^\n]+\s*)?(?:COURT:\s*[^\n]+\s*)?(?:BENCH:\s*[^\n]+\s*)?', '', holding, flags=re.IGNORECASE).strip()
    if len(holding) > 350:
        holding = holding[:350].rsplit(' ', 1)[0] + '...'

    card = {
        "id": clean_id,
        "case_id": clean_id,
        "citation": cit,
        "neutral_citation": cit,
        "title": clean_t,
        "case_title": clean_t,
        "court": clean_c,
        "year": int(year) if str(year).isdigit() else 2020,
        "bench": bench,
        "summary": holding,
        "snippet": holding,
        "pdf_url": pdf_url,
        "score": round(score, 4),
        "source_type": source_type
    }
    return sanitize_precedent_card(card)


async def search_judgments_by_citation(
    year: Optional[Union[int, str]] = None,
    journal: Optional[str] = None,
    page: Optional[Union[int, str]] = None,
    court: Optional[str] = None,
    jurisdiction: Optional[str] = "Pakistan",
    raw_citation: Optional[str] = None
) -> Dict[str, Any]:
    """
    Locates an exact judgment by citation (Year, Journal, Page).
    Searches Supabase full_judgments, curated cases, and local index.
    """
    target_year = str(year).strip() if year and str(year).lower() != "all years" else ""
    target_journal = str(journal).strip().upper() if journal and str(journal).lower() != "all journals" else ""
    target_page = str(page).strip() if page else ""

    # If raw_citation provided, parse it
    if raw_citation and (not target_year or not target_journal or not target_page):
        m = re.search(r'\b(19\d{2}|20\d{2})\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(\d+)\b', raw_citation)
        if m:
            target_year = m.group(1)
            target_journal = m.group(2).upper()
            target_page = m.group(3)
        else:
            m_alt = re.search(r'\b([A-Za-z]+)\s+(19\d{2}|20\d{2})\s+([A-Za-z]+)?\s*(\d+)\b', raw_citation)
            if m_alt:
                target_journal = m_alt.group(1).upper()
                target_year = m_alt.group(2)
                target_page = m_alt.group(4)

    expected_citation = f"{target_year} {target_journal} {target_page}".strip()
    norm_expected = re.sub(r'[\s_\-]+', '_', expected_citation).upper()

    results: List[Dict[str, Any]] = []
    seen_ids = set()

    # 1. Check local curated cases first
    curated_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "curated_historical_cases.json")
    if os.path.exists(curated_path):
        try:
            with open(curated_path, "r", encoding="utf-8") as f:
                curated_cases = json.load(f)
            for c in curated_cases:
                c_cit = (c.get("neutral_citation") or c.get("citation") or "").strip()
                c_norm = re.sub(r'[\s_\-]+', '_', c_cit).upper()
                c_id_norm = re.sub(r'[\s_\-]+', '_', str(c.get("case_id") or "")).upper()
                if (norm_expected and (norm_expected in c_norm or norm_expected in c_id_norm)) or \
                   (target_year and target_year in c_cit and target_journal and target_journal in c_cit.upper() and target_page and target_page in c_cit):
                    res = build_precedent_result(
                        cid=c.get("case_id") or c_cit,
                        cit=c_cit,
                        title=c.get("title") or c.get("case_title") or "Curated Landmark Case",
                        court=c.get("court") or "Supreme Court of Pakistan",
                        year=c.get("year") or target_year or 2020,
                        snippet=c.get("holding") or c.get("snippet") or c.get("full_text") or "",
                        score=1.0,
                        source_type="Authoritative Precedent"
                    )
                    results.append(res)
                    seen_ids.add(res["case_id"])
                    break
        except Exception:
            pass

    # 2. Check Supabase full_judgments
    sb = get_supabase_client()
    if sb and expected_citation:
        try:
            # Query exact neutral_citation or case_id
            for query_field in ["neutral_citation", "case_id"]:
                db_res = safe_supabase_query(
                    lambda: sb.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, holding_snippet, full_text").eq(query_field, expected_citation).limit(5).execute()
                )
                if db_res and db_res.data:
                    for rec in db_res.data:
                        cid = str(rec.get("case_id") or rec.get("id"))
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            cit = rec.get("neutral_citation") or expected_citation
                            title = rec.get("case_title") or ""
                            court_name = rec.get("court_name") or "Supreme Court of Pakistan"
                            year_val = rec.get("year") or target_year or 2020
                            text = rec.get("holding_snippet") or rec.get("full_text") or ""
                            results.append(build_precedent_result(
                                cid=cid,
                                cit=cit,
                                title=title,
                                court=court_name,
                                year=year_val,
                                snippet=text,
                                score=0.99
                            ))
                if results:
                    break

            # If not found, try ILIKE search with journal and page
            if not results and target_journal and target_page:
                pattern = f"%{target_journal}%{target_page}%"
                db_res = safe_supabase_query(
                    lambda: sb.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, holding_snippet, full_text").ilike("neutral_citation", pattern).limit(5).execute()
                )
                if db_res and db_res.data:
                    for rec in db_res.data:
                        cid = str(rec.get("case_id") or rec.get("id"))
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            cit = rec.get("neutral_citation") or expected_citation
                            title = rec.get("case_title") or ""
                            court_name = rec.get("court_name") or "Supreme Court of Pakistan"
                            year_val = rec.get("year") or target_year or 2020
                            text = rec.get("holding_snippet") or rec.get("full_text") or ""
                            results.append(build_precedent_result(
                                cid=cid,
                                cit=cit,
                                title=title,
                                court=court_name,
                                year=year_val,
                                snippet=text,
                                score=0.95
                            ))
        except Exception:
            pass

    # 3. Fallback: Search BM25 sparse index for exact citation
    if not results and expected_citation:
        bm25_matches = search_bm25_sparse(expected_citation, top_k=5)
        for m in bm25_matches:
            cid = m.get("case_id") or m.get("id")
            if cid not in seen_ids:
                seen_ids.add(cid)
                results.append(build_precedent_result(
                    cid=cid,
                    cit=m.get("citation") or expected_citation,
                    title=m.get("title") or "Reported Precedent",
                    court=m.get("court") or "Supreme Court of Pakistan",
                    year=m.get("year") or target_year or 2020,
                    snippet=m.get("preview") or "",
                    score=0.90
                ))

    # Apply optional court filter if requested
    if court and str(court).lower() not in ("all courts", "all", "none"):
        court_lower = str(court).lower()
        results = [r for r in results if court_lower in str(r.get("court", "")).lower()]

    return {
        "citation": expected_citation or raw_citation or "",
        "query_params": {
            "year": target_year,
            "journal": target_journal,
            "page": target_page,
            "court": court,
            "jurisdiction": jurisdiction
        },
        "found": len(results) > 0,
        "total_matches": len(results),
        "results": results
    }


async def search_judgments_by_keyword(
    query: str,
    court: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    date_range: Optional[str] = None,
    journal: Optional[str] = None,
    limit: int = 15
) -> Dict[str, Any]:
    """
    Full-text keyword search across 1947–2026 Pakistani court judgments.
    """
    q_clean = query.strip()
    if not q_clean:
        return {"query": query, "total_matches": 0, "results": []}

    # Resolve date range
    if date_range:
        dr_lower = date_range.lower()
        if "5 years" in dr_lower:
            year_from = 2021
            year_to = 2026
        elif "10 years" in dr_lower:
            year_from = 2016
            year_to = 2026
        elif "20 years" in dr_lower:
            year_from = 2006
            year_to = 2026

    # 1. BM25 Search
    bm25_candidates = search_bm25_sparse(q_clean, top_k=limit * 3)

    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for c in bm25_candidates:
        cid = str(c.get("case_id") or c.get("id"))
        if cid in seen_ids:
            continue

        c_year = c.get("year") or 2020
        c_court = c.get("court") or ""
        c_cit = c.get("citation") or ""

        # Filters
        if year_from and c_year < year_from:
            continue
        if year_to and c_year > year_to:
            continue
        if court and str(court).lower() not in ("all courts", "all cou...", "all", "none"):
            if str(court).lower() not in c_court.lower():
                continue
        if journal and str(journal).lower() not in ("all journals", "all journ...", "all", "none"):
            if str(journal).lower() not in c_cit.lower():
                continue

        seen_ids.add(cid)
        results.append(build_precedent_result(
            cid=cid,
            cit=c_cit,
            title=c.get("title") or "Precedent on Record",
            court=c_court,
            year=c_year,
            snippet=c.get("preview") or "",
            score=c.get("score", 0.8)
        ))
        if len(results) >= limit:
            break

    return {
        "query": query,
        "filters": {
            "court": court,
            "year_from": year_from,
            "year_to": year_to,
            "date_range": date_range,
            "journal": journal
        },
        "total_matches": len(results),
        "results": results
    }


async def search_judgments_intelligent(
    query: str,
    court: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    date_range: Optional[str] = None,
    journal: Optional[str] = None,
    limit: int = 15
) -> Dict[str, Any]:
    """
    Intelligent semantic search using dense vector embeddings (Pinecone) + BM25 RRF fusion.
    """
    from legal_ai.retrieval.unified_orchestrator import retrieve_candidates_parallel

    # Retrieve unified candidates
    merged_candidates, counts = await retrieve_candidates_parallel(
        query_text=query,
        include_external=False,
        top_k_per_engine=30
    )

    # Resolve date range
    if date_range:
        dr_lower = date_range.lower()
        if "5 years" in dr_lower:
            year_from = 2021
            year_to = 2026
        elif "10 years" in dr_lower:
            year_from = 2016
            year_to = 2026
        elif "20 years" in dr_lower:
            year_from = 2006
            year_to = 2026

    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for c in merged_candidates:
        cid = str(c.get("case_id") or c.get("id"))
        if cid in seen_ids:
            continue

        c_year = c.get("year") or 2020
        c_court = c.get("court") or ""
        c_cit = c.get("citation") or ""

        # Filters
        if year_from and c_year < year_from:
            continue
        if year_to and c_year > year_to:
            continue
        if court and str(court).lower() not in ("all courts", "all cou...", "all", "none"):
            if str(court).lower() not in c_court.lower():
                continue
        if journal and str(journal).lower() not in ("all journals", "all journ...", "all", "none"):
            if str(journal).lower() not in c_cit.lower():
                continue

        seen_ids.add(cid)
        results.append(build_precedent_result(
            cid=cid,
            cit=c_cit,
            title=c.get("title") or c.get("case_title") or "Precedent on Record",
            court=c_court,
            year=c_year,
            snippet=c.get("preview") or c.get("snippet") or "",
            score=c.get("rrf_score") or c.get("score") or 0.85,
            source_type=c.get("source_type") or "Neural Semantic Search"
        ))
        if len(results) >= limit:
            break

    return {
        "query": query,
        "mode": "intelligent",
        "engine_counts": counts,
        "filters": {
            "court": court,
            "year_from": year_from,
            "year_to": year_to,
            "date_range": date_range,
            "journal": journal
        },
        "total_matches": len(results),
        "results": results
    }
