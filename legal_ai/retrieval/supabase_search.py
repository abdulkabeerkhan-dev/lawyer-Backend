"""
legal_ai/retrieval/supabase_search.py

Proactive Postgres Full-Text Search (FTS) and exact citation retrieval driver
for Pakistani Court Judgments from Supabase 'full_judgments' table.
"""

import sys
import re
from typing import Dict, List, Any, Optional
from legal_ai.config import get_supabase_client, safe_supabase_query
from legal_ai.ranking.court_weighting import normalize_court_name


def _format_supabase_record(rec: Dict[str, Any], score: float = 0.60) -> Dict[str, Any]:
    cid = str(rec.get("case_id") or rec.get("id") or "").strip()
    title = str(rec.get("case_title") or rec.get("title") or "Precedent on Record").strip()
    cit = str(rec.get("neutral_citation") or rec.get("citation") or cid).strip()
    raw_court = str(rec.get("court_name") or rec.get("court") or "Supreme Court of Pakistan").strip()
    court = normalize_court_name(raw_court)
    full_text = str(rec.get("full_text") or "").strip()
    date_val = str(rec.get("decision_date") or rec.get("year") or "").strip()

    # Extract year
    m_year = re.search(r'\b(19\d{2}|20\d{2})\b', f"{cit} {date_val}")
    year = int(m_year.group(1)) if m_year else 2020

    content_type = "full_text" if len(full_text.split()) >= 150 else "headnote_only"

    return {
        "id": cid,
        "case_id": cid,
        "score": score,
        "dense_score": 0.0,
        "sparse_score": 0.0,
        "rrf_score": 0.018,
        "is_supabase_fts": True,
        "source_type": "Supabase",
        "citation": cit,
        "title": title,
        "case_name": title,
        "court": court,
        "year": year,
        "content_type": content_type,
        "preview": full_text[:400],
        "metadata": {
            "id": str(rec.get("id")),
            "supabase_id": str(rec.get("id")),
            "case_id": cid,
            "canonical_id": cid,
            "citation": cit,
            "neutral_citation": cit,
            "title": title,
            "case_title": title,
            "court": court,
            "court_name": court,
            "year": year,
            "date": date_val,
            "text": full_text[:3500],
            "full_text": full_text,
            "content_type": content_type,
            "is_supabase_fts": True,
            "source_type": "Supabase"
        }
    }


async def search_supabase_judgments(
    search_terms: List[str],
    limit_per_term: int = 15
) -> List[Dict[str, Any]]:
    """
    Executes proactive multi-term FTS and keyword search against Postgres full_judgments.
    """
    sb = get_supabase_client()
    if not sb:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    for term in search_terms:
        q_clean = term.strip()
        if not q_clean or len(q_clean) < 3:
            continue

        # 1. Exact Citation Check (e.g. "2021 SCMR 554")
        m_cit = re.search(r'\b(?:19|20)\d{2}\s+(?:SCMR|PLD|PCrLJ|CLC|MLD|YLR|CLD|PTD)\s+\d+\b', q_clean, re.IGNORECASE)
        if m_cit:
            target_cit = m_cit.group(0).strip()
            norm_cid = target_cit.replace(' ', '_')
            try:
                def _query_exact():
                    res = sb.table("full_judgments").select(
                        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
                    ).or_(
                        f"neutral_citation.eq.{target_cit},case_id.eq.{norm_cid}"
                    ).limit(5).execute()
                    return res.data or []

                exact_records = safe_supabase_query(_query_exact, retries=2)
                for r in exact_records:
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        candidates.append(_format_supabase_record(r, score=0.95))
            except Exception:
                pass

        # 2. Case ID Check (e.g. "2021_SCMR_554")
        if re.match(r'^(?:19|20)\d{2}_[a-zA-Z]+_\d+', q_clean):
            try:
                def _query_cid():
                    res = sb.table("full_judgments").select(
                        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
                    ).eq(
                        "case_id", q_clean
                    ).limit(2).execute()
                    return res.data or []

                cid_records = safe_supabase_query(_query_cid, retries=2)
                for r in cid_records:
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        candidates.append(_format_supabase_record(r, score=0.95))
            except Exception:
                pass

        # 3. Case Title & Section Keyword Search (Fast Indexed Search)
        # Strips boilerplate words and builds tsquery for title
        STOP_WORDS = {
            'the', 'of', 'and', 'a', 'in', 'to', 'is', 'for', 'on', 'with', 'by', 'at', 'from',
            'an', 'as', 'be', 'under', 'versus', 'vs', 'v', 'state', 'act', 'code', 'law',
            'order', 'section', 'sec', 'petition', 'appeal', 'criminal', 'civil'
        }
        words = [w for w in re.sub(r'[^\w\s]', ' ', q_clean).split() if len(w) > 2 and w.lower() not in STOP_WORDS]
        if words:
            title_ts = " & ".join(words[:3])
            try:
                def _query_title():
                    res = sb.table("full_judgments").select(
                        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
                    ).limit(5).text_search("case_title", title_ts).execute()
                    return res.data or []

                title_records = safe_supabase_query(_query_title, retries=1)
                for r in (title_records or []):
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        candidates.append(_format_supabase_record(r, score=0.75))
            except Exception:
                pass

        # 4. Doctrinal Full-Text Search (Targeted and Guarded)
        # Only fire full_text if we have 2-3 distinctive doctrinal keywords (e.g. dishonest & intention)
        distinctive = [w for w in words if not w.isdigit() and len(w) >= 5]
        if len(distinctive) >= 2:
            ft_ts = " & ".join(distinctive[:2])
            try:
                def _query_fulltext():
                    res = sb.table("full_judgments").select(
                        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
                    ).limit(4).text_search("full_text", ft_ts).execute()
                    return res.data or []

                ft_records = safe_supabase_query(_query_fulltext, retries=1)
                for r in (ft_records or []):
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        candidates.append(_format_supabase_record(r, score=0.70))
            except Exception:
                pass

    return candidates

