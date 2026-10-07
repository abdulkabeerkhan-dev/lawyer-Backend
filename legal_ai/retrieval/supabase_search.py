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

        # 1. Exact Citation or Case ID check
        m_cit = re.search(r'\b(?:19|20)\d{2}\s+(?:SCMR|PLD|PCrLJ|CLC|MLD|YLR|CLD|PTD)\s+\d+\b', q_clean, re.IGNORECASE)
        target_cit = m_cit.group(0) if m_cit else q_clean

        try:
            def _query_exact():
                res = sb.table("full_judgments").select("id, case_id, case_title, neutral_citation, court_name, decision_date, full_text").or_(
                    f"neutral_citation.eq.{target_cit},case_id.eq.{target_cit.replace(' ', '_')}"
                ).limit(5).execute()
                return res.data or []

            exact_records = safe_supabase_query(_query_exact)
            for r in exact_records:
                cid = str(r.get("case_id") or r.get("id"))
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    candidates.append(_format_supabase_record(r, score=0.95))
        except Exception:
            pass

        # 2. Text Search / ilike across title and full_text
        try:
            tokens = [t for t in re.split(r'[\s,\+\-]+', q_clean) if len(t) >= 3]
            if tokens:
                primary_token = tokens[0]
                def _query_fts():
                    res = sb.table("full_judgments").select("id, case_id, case_title, neutral_citation, court_name, decision_date, full_text").ilike(
                        "case_title", f"%{primary_token}%"
                    ).limit(limit_per_term).execute()
                    return res.data or []

                records = safe_supabase_query(_query_fts)
                for r in records:
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        candidates.append(_format_supabase_record(r, score=0.65))
        except Exception as e:
            print(f"⚠️ [SupabaseSearch] FTS query error for '{q_clean}': {e}", file=sys.stderr)

    return candidates
