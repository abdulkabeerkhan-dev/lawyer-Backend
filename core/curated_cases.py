import json
import os
import re
from typing import List, Dict, Any, Optional

_CURATED_CASES_CACHE: Optional[List[Dict[str, Any]]] = None

def get_curated_cases() -> List[Dict[str, Any]]:
    global _CURATED_CASES_CACHE
    if _CURATED_CASES_CACHE is not None:
        return _CURATED_CASES_CACHE

    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.join(workspace_dir, "data", "curated_historical_cases.json")
    if os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                _CURATED_CASES_CACHE = json.load(f)
                return _CURATED_CASES_CACHE
        except Exception:
            pass
    _CURATED_CASES_CACHE = []
    return _CURATED_CASES_CACHE

def find_curated_case(
    year: Optional[int] = None,
    journal: Optional[str] = None,
    page: Optional[int] = None,
    court: Optional[str] = None,
    citation: Optional[str] = None,
    text: Optional[str] = None,
    case_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    cases = get_curated_cases()
    cit_norm = re.sub(r'[^A-Za-z0-9]+', '', str(citation or "").upper())
    case_id_norm = re.sub(r'[^A-Za-z0-9]+', '', str(case_id or "").upper())
    text_upper = str(text or "").upper()

    for c in cases:
        if year is not None and page is not None and journal:
            c_yr = c.get("year")
            c_pg = c.get("page")
            c_jnl = str(c.get("journal") or "").upper()
            if c_yr == year and c_pg == page and c_jnl == journal.upper():
                c_court = str(c.get("court_code") or "").upper()
                if not court or not c_court or court.upper() == c_court:
                    return c

        for mk in c.get("match_keys", []):
            mk_norm = re.sub(r'[^A-Za-z0-9]+', '', mk.upper())
            if mk_norm and (mk_norm == cit_norm or mk_norm == case_id_norm):
                return c

        for alias in c.get("aliases", []):
            alias_u = alias.upper()
            if alias_u and (alias_u in cit_norm or alias_u in text_upper):
                return c

        for kw in c.get("doctrinal_keywords", []):
            kw_u = kw.upper()
            if kw_u and kw_u in text_upper:
                return c

    return None

def is_curated_historical_exception(
    year: Optional[int] = None,
    page: Optional[int] = None,
    journal: Optional[str] = None,
    court: Optional[str] = None,
    citation: Optional[str] = None,
    text: Optional[str] = None
) -> bool:
    c = find_curated_case(year=year, journal=journal, page=page, court=court, citation=citation, text=text)
    if c and c.get("is_historical_exception"):
        return True
    return False

def find_landmark_cases_for_query(query: str) -> List[Dict[str, Any]]:
    """
    Retrieves curated landmark precedents matching query topics, statutory anchors,
    case aliases, or doctrinal keywords.
    """
    cases = get_curated_cases()
    q_lower = query.lower()
    matches = []
    seen = set()

    for c in cases:
        cid = c.get("neutral_citation") or c.get("case_id")
        if cid in seen:
            continue

        matched = False
        # 1. Match keys
        for mk in c.get("match_keys", []):
            if mk.lower() in q_lower:
                matched = True
                break

        # 2. Aliases
        if not matched:
            for alias in c.get("aliases", []):
                if alias.lower() in q_lower:
                    matched = True
                    break

        # 3. Doctrinal keywords / statutory anchors
        if not matched:
            for kw in c.get("doctrinal_keywords", []):
                if kw.lower() in q_lower:
                    matched = True
                    break

        if matched:
            seen.add(cid)
            matches.append(c)

    return matches
