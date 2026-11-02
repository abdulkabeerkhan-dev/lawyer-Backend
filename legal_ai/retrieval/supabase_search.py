"""
legal_ai/retrieval/supabase_search.py

Proactive Postgres Full-Text Search (FTS) and exact citation retrieval driver
for Pakistani Court Judgments from Supabase 'full_judgments' table.

Phase 4, Step 2 Optimizations:
- Stop-word sanitization stripping conversational and query filler words.
- Dual-format Pakistani neutral citation parser (Year-first & Reporter-first).
- High-efficiency targeted case_title keyword search avoiding unindexed table scans.
- Statement timeout resilience and graceful degradation.
"""

import sys
import re
from typing import Dict, List, Any, Optional, Set, Tuple
from legal_ai.config import get_supabase_client, safe_supabase_query
from legal_ai.ranking.court_weighting import normalize_court_name


LEGAL_CONVERSATIONAL_STOP_WORDS: Set[str] = {
    # Standard English stop words
    'the', 'of', 'and', 'a', 'in', 'to', 'is', 'for', 'on', 'with', 'by', 'at', 'from',
    'an', 'as', 'be', 'under', 'versus', 'vs', 'v', 'per', 'via', 'into', 'upon', 'about',
    'than', 'then', 'there', 'their', 'they', 'them', 'these', 'those', 'this', 'that',
    'it', 'its', 'or', 'nor', 'not', 'no', 'so', 'if', 'all', 'any', 'both', 'each',
    # Conversational, interrogative, and imperative filler
    'whether', 'which', 'what', 'where', 'when', 'how', 'who', 'whom', 'whose', 'why',
    'find', 'give', 'more', 'tell', 'show', 'list', 'explain', 'describe', 'provide', 'search',
    'does', 'did', 'do', 'can', 'could', 'would', 'should', 'might', 'must', 'may', 'shall',
    'regarding', 'between', 'against', 'among', 'concerning', 'respecting', 'without', 'within',
    'across', 'through', 'scenario', 'matter', 'issue', 'question', 'problem', 'situation',
    'including', 'involving', 'included', 'involved', 'include', 'involve',
    # High-frequency generic legal terms that dilute FTS search
    'court', 'courts', 'pakistan', 'pakistani', 'judgment', 'judgments', 'case', 'cases', 'holding',
    'precedent', 'precedents', 'law', 'laws', 'statute', 'statutes', 'act', 'acts',
    'code', 'codes', 'section', 'sec', 'sections', 'order', 'orders', 'rule', 'rules',
    'petition', 'petitions', 'appeal', 'appeals', 'suit', 'suits', 'application', 'applications',
    'appellant', 'respondent', 'petitioner', 'plaintiff', 'defendant', 'accused', 'state'
}


def extract_substantive_tokens(query_text: str) -> List[str]:
    """
    Extracts high-salience substantive legal keywords stripped of conversational filler.
    """
    raw_tokens = re.sub(r'[^\w\s]', ' ', query_text).split()
    substantive = []
    for tok in raw_tokens:
        tok_clean = tok.strip()
        tok_low = tok_clean.lower()
        if (
            len(tok_clean) >= 4
            and not tok_clean.isdigit()
            and tok_low not in LEGAL_CONVERSATIONAL_STOP_WORDS
        ):
            substantive.append(tok_clean)
    return substantive


def extract_pakistani_citations(text: str) -> List[Tuple[str, str]]:
    """
    Extracts neutral citations from text and returns (canonical_cid, display_citation).
    Supports:
    - Year-first: 2026 SCMR 941 -> ('2026_SCMR_941', '2026 SCMR 941')
    - Reporter-first: PLD 1967 SC 97 -> ('1967_PLD_SC_97', '1967 PLD 97')
    """
    found: List[Tuple[str, str]] = []
    seen = set()

    # 1. Year-first format (e.g. 2026 SCMR 941, 2021 SCMR 554, 2006 YLR 2059)
    m_yr = re.finditer(r'\b((?:19|20)\d{2})\s+([A-Za-z]+(?:\s*\([A-Za-z]+\))?)\s+(\d+)\b', text)
    for m in m_yr:
        yr, rep, pg = m.group(1), m.group(2).replace(" ", "_").upper(), m.group(3)
        cid = f"{yr}_{rep}_{pg}"
        disp = f"{yr} {m.group(2).upper()} {pg}"
        if cid not in seen:
            seen.add(cid)
            found.append((cid, disp))

    # 2. Reporter-first format (e.g. PLD 1967 SC 97, PLD 1995 SC 34, PCRLJ 2024 100)
    m_rep = re.finditer(r'\b(PLD|SCMR|PCrLJ|CLC|MLD|YLR|CLD|PTD|PLC)\s+((?:19|20)\d{2})\s+(?:SC|Lah|Kar|Pesh|Quetta|High\s+Court)?\s*(\d+)\b', text, re.IGNORECASE)
    for m in m_rep:
        rep, yr, pg = m.group(1).upper(), m.group(2), m.group(3)
        cid = f"{yr}_{rep}_{pg}"
        disp = f"{yr} {rep} {pg}"
        if cid not in seen:
            seen.add(cid)
            found.append((cid, disp))

    return found


def _format_supabase_record(rec: Dict[str, Any], score: float = 0.60) -> Dict[str, Any]:
    """
    Standardizes raw Supabase row into common Candidate Record payload.
    """
    cid = str(rec.get("case_id") or rec.get("id") or "").strip()
    full_text = str(rec.get("full_text") or "").strip()
    headnote = str(rec.get("headnote") or "").strip()
    ratio = str(rec.get("ratio_decidendi") or "").strip()
    domain = str(rec.get("domain") or "").strip()
    subdomain = str(rec.get("subdomain") or "").strip()
    statutes = rec.get("statutes_cited") or []

    title = str(rec.get("case_title") or rec.get("title") or "").strip()
    if not title or title.lower() in ("precedent on record", "reported precedent", "none", "unknown"):
        m_br = re.search(r'\[[^|\]]+\|\s*([^\]]+)\]', full_text)
        if m_br:
            title = m_br.group(1).strip()
        else:
            m_vs = re.search(r'([A-Z0-9\s,\.\(\)/\-\'&]+?\s+(?:VS|V\.|VERSUS)\s+[A-Z0-9\s,\.\(\)/\-\'&]+)', full_text)
            title = m_vs.group(1).strip() if m_vs else "Precedent on Record"
    cit = str(rec.get("neutral_citation") or rec.get("citation") or cid).strip()
    raw_court = str(rec.get("court_name") or rec.get("court") or "Supreme Court of Pakistan").strip()
    court = normalize_court_name(raw_court)
    date_val = str(rec.get("decision_date") or rec.get("year") or "").strip()

    # Extract year
    m_year = re.search(r'\b(19\d{2}|20\d{2})\b', f"{cit} {date_val}")
    year = int(m_year.group(1)) if m_year else 2020

    content_type = "full_text" if len(full_text.split()) >= 150 else ("ratio_decidendi" if ratio else ("headnote_only" if headnote else "citation_only"))
    display_preview = (headnote[:400] if headnote else "") or (ratio[:400] if ratio else "") or full_text[:400]
    display_text = (full_text[:3500] if full_text else "") or (headnote[:3500] if headnote else "") or (ratio[:3500] if ratio else "")

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
        "domain": domain,
        "legal_domain": domain,
        "subdomain": subdomain,
        "statutes": statutes,
        "statutory_provisions": statutes,
        "headnote": headnote,
        "ratio_decidendi": ratio,
        "content_type": content_type,
        "preview": display_preview,
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
            "domain": domain,
            "legal_domain": domain,
            "subdomain": subdomain,
            "statutes": statutes,
            "statutory_provisions": statutes,
            "headnote": headnote,
            "ratio_decidendi": ratio,
            "text": display_text,
            "full_text": full_text or display_text,
            "content_type": content_type,
            "is_supabase_fts": True,
            "source_type": "Supabase"
        }
    }


async def search_supabase_judgments(
    search_terms: List[str],
    limit_per_term: int = 15,
    query_plan: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Executes proactive multi-term FTS and keyword search against Postgres full_judgments.
    Optimized for sub-second retrieval:
    1. Fast exact citation and case_id lookup.
    2. Domain-aware structured headnote & GIN FTS stored procedure (search_judgments_structured).
    3. Substantive keyword search against case_title with conversational stop-words stripped.
    4. Safe guarded full_text search with statement timeout protection.
    """
    sb = get_supabase_client()
    if not sb:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    # Extract target domain from query_plan if available
    target_domain = None
    if query_plan:
        if hasattr(query_plan, "legal_domain") and query_plan.legal_domain:
            target_domain = str(query_plan.legal_domain).strip().lower()
        elif hasattr(query_plan, "domain") and query_plan.domain:
            target_domain = str(query_plan.domain).strip().lower()
        if target_domain in ("unknown", "general", "none"):
            target_domain = None

    for term in search_terms:
        q_clean = term.strip()
        if not q_clean or len(q_clean) < 3:
            continue

        # 1. Exact Citation Check (Supports both Year-first and Reporter-first)
        citations_to_check = extract_pakistani_citations(q_clean)
        for norm_cid, disp_cit in citations_to_check:
            try:
                def _query_exact():
                    res = sb.table("full_judgments").select(
                        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text, domain, subdomain, headnote, ratio_decidendi, statutes_cited"
                    ).eq("case_id", norm_cid).limit(5).execute()
                    if not (res and res.data):
                        res = sb.table("full_judgments").select(
                            "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text, domain, subdomain, headnote, ratio_decidendi, statutes_cited"
                        ).eq("neutral_citation", disp_cit).limit(5).execute()
                    return res.data or []

                exact_records = safe_supabase_query(_query_exact, retries=1)
                for r in (exact_records or []):
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
                        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text, domain, subdomain, headnote, ratio_decidendi, statutes_cited"
                    ).eq("case_id", q_clean).limit(2).execute()
                    return res.data or []

                cid_records = safe_supabase_query(_query_cid, retries=1)
                for r in (cid_records or []):
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        candidates.append(_format_supabase_record(r, score=0.95))
            except Exception:
                pass

        # 3. Domain-Aware Structured Headnote & GIN FTS Procedure
        substantive = extract_substantive_tokens(q_clean)
        structured_terms = " ".join(substantive[:4]) if substantive else q_clean
        if len(structured_terms) >= 3:
            try:
                def _query_structured():
                    rpc_params = {
                        "p_query_terms": structured_terms,
                        "p_domain": target_domain,
                        "p_limit": limit_per_term
                    }
                    res = sb.rpc("search_judgments_structured", rpc_params).execute()
                    return res.data or []

                struct_records = safe_supabase_query(_query_structured, retries=1)
                for r in (struct_records or []):
                    cid = str(r.get("case_id") or r.get("id"))
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        rank_score = float(r.get("rank") or 0.5)
                        norm_score = min(0.92, 0.70 + (rank_score * 0.05))
                        candidates.append(_format_supabase_record(r, score=norm_score))
            except Exception:
                pass

        # 3. Substantive Title Keyword Search (Sanitized of conversational filler)
        substantive = extract_substantive_tokens(q_clean)
        if substantive:
            tokens_to_search = substantive[:2]
            for tok in tokens_to_search:
                if len(candidates) >= limit_per_term:
                    break
                try:
                    def _query_title():
                        res = sb.table("full_judgments").select(
                            "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
                        ).ilike("case_title", f"%{tok}%").limit(5).execute()
                        return res.data or []

                    title_records = safe_supabase_query(_query_title, retries=1)
                    for r in (title_records or []):
                        cid = str(r.get("case_id") or r.get("id"))
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            candidates.append(_format_supabase_record(r, score=0.75))
                except Exception:
                    pass

        # 4. Doctrinal Full-Text Search (Safe & Timeout-Guarded)
        # Only execute if title search yielded few candidates and distinctive high-specificity keywords exist
        distinctive = [w for w in substantive if len(w) >= 6]
        if len(candidates) < 4 and len(distinctive) >= 2:
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
            except Exception as err:
                # Catch statement timeout (57014) or connection errors gracefully without blocking pipeline
                err_str = str(err)
                if "57014" not in err_str:
                    print(f"⚠️ [supabase_search] Doctrinal FTS skipped: {err_str}", file=sys.stderr, flush=True)

    return candidates
