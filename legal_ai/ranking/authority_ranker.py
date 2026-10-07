"""
legal_ai/ranking/authority_ranker.py

Production-grade Multi-Factor Authority Ranking Engine for Pakistani Court Precedents.
Ranks superior court judgments based on:
1. Legal Issue Match & Factual Matrix Alignment
2. Canonical Provision Match (Section numbers in title or text)
3. Constitutional Hierarchy (Supreme Court Art. 189 > High Courts Art. 201 > Tribunals)
4. Temporal Recency (2024-2026 > 2020-2023 > older)
5. Citation Prestige (SCMR / PLD > CLC / PCrLJ / MLD / YLR)
6. Substantive Full Text Reasoning vs Summary Headnotes
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from legal_ai.ranking.court_weighting import get_court_hierarchy_weight, get_recency_weight, normalize_court_name


def calculate_authority_score(candidate: Dict[str, Any], query_plan: Any) -> Tuple[float, Dict[str, float]]:
    """
    Computes multi-factor Authority Score for a legal judgment candidate.
    Formula:
    Authority Score = Issue Match + Provision Match + Court Hierarchy + Recentness + Citation Strength + Full Text Substance
    """
    scores: Dict[str, float] = {
        "court_hierarchy": 0.0,
        "recentness": 0.0,
        "full_text_substance": 0.0,
        "provision_match": 0.0,
        "issue_match": 0.0,
        "citation_strength": 0.0
    }

    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else candidate
    title = str(candidate.get("title") or candidate.get("case_name") or candidate.get("case_title") or meta.get("title") or meta.get("case_title") or "").lower()
    citation = str(candidate.get("citation") or candidate.get("neutral_citation") or meta.get("citation") or meta.get("neutral_citation") or "").upper()
    court = str(candidate.get("court") or candidate.get("court_name") or candidate.get("canonical_court_name") or meta.get("court") or meta.get("court_name") or "").lower()
    text = str(candidate.get("preview") or candidate.get("full_text") or candidate.get("snippet") or candidate.get("text") or meta.get("full_text") or meta.get("text") or "").lower()
    year_val = candidate.get("year") or candidate.get("decision_date") or meta.get("year") or meta.get("decision_date") or 2000

    # 1. Court Hierarchy (0 to 40 pts)
    if "supreme court" in court or "scmr" in citation or "supreme court" in title:
        scores["court_hierarchy"] = 40.0
    elif any(hc in court for hc in ["high court", "lahore", "sindh", "islamabad", "peshawar", "balochistan"]) or any(j in citation for j in ["PLD", "CLC", "PCrLJ", "MLD", "YLR"]):
        scores["court_hierarchy"] = 25.0
    else:
        scores["court_hierarchy"] = 5.0

    # 2. Recentness (0 to 30 pts)
    y = 2000
    if isinstance(year_val, int):
        y = year_val
    elif isinstance(year_val, str):
        m_y = re.search(r'\b(19\d{2}|20\d{2})\b', year_val)
        if m_y:
            y = int(m_y.group(1))
    if y == 2000:
        m_cit_y = re.search(r'\b(19\d{2}|20\d{2})\b', citation)
        if m_cit_y:
            y = int(m_cit_y.group(1))

    if y >= 2024:
        scores["recentness"] = 30.0
    elif y >= 2020:
        scores["recentness"] = 20.0
    elif y >= 2010:
        scores["recentness"] = 12.0
    elif y >= 2000:
        scores["recentness"] = 6.0
    else:
        scores["recentness"] = 2.0

    # 3. Full Text Availability & Judicial Reasoning (0 to 25 pts)
    content_type = str(candidate.get("content_type") or "").lower()
    is_headnote = candidate.get("is_headnote_only") or (content_type == "headnote_only")
    text_len = len(text.strip())

    if not is_headnote and text_len >= 1200:
        scores["full_text_substance"] = 25.0
    elif not is_headnote and text_len >= 400:
        scores["full_text_substance"] = 18.0
    elif is_headnote or text_len >= 150:
        scores["full_text_substance"] = 8.0
    else:
        scores["full_text_substance"] = 0.0

    # 4. Provision Match (0 to 25 pts)
    provisions = []
    if query_plan:
        if hasattr(query_plan, "provisions") and query_plan.provisions:
            provisions = query_plan.provisions
        elif isinstance(query_plan, dict) and query_plan.get("provisions"):
            provisions = query_plan["provisions"]

    prov_points = 0.0
    for prov in provisions:
        p_clean = str(prov).lower().replace("section ", "").replace("sec ", "").strip()
        nums = re.findall(r'\b[0-9]+(?:-[a-z])?\b', p_clean)
        for num in nums:
            if re.search(rf'\b(?:sec|section|u/s)?\s*{re.escape(num)}\b', text) or re.search(rf'\b(?:sec|section|u/s)?\s*{re.escape(num)}\b', title):
                prov_points += 12.5
                break
    scores["provision_match"] = min(25.0, prov_points)

    # 5. Legal Issue Match (0 to 30 pts)
    questions = []
    if query_plan:
        if hasattr(query_plan, "legal_questions") and query_plan.legal_questions:
            questions = query_plan.legal_questions
        elif isinstance(query_plan, dict) and query_plan.get("legal_questions"):
            questions = query_plan["legal_questions"]

    issue_points = 0.0
    combined_questions = " ".join([str(q) for q in questions]).lower()
    key_terms = [
        "breach of trust", "dishonest intention", "civil dispute", "contractual breach",
        "pre-arrest bail", "mala fide", "ulterior motive", "director", "consultancy fee",
        "cheating", "entrustment", "quashment", "fiduciary"
    ]
    matched_terms = 0
    for term in key_terms:
        if term in combined_questions and (term in text or term in title):
            matched_terms += 1

    scores["issue_match"] = min(30.0, matched_terms * 6.0)

    # 6. Citation Strength (0 to 15 pts)
    if "SCMR" in citation:
        scores["citation_strength"] = 15.0
    elif "PLD" in citation:
        scores["citation_strength"] = 12.0
    elif any(j in citation for j in ["CLC", "PCrLJ", "PTD", "PLC", "MLD", "YLR"]):
        scores["citation_strength"] = 8.0
    else:
        scores["citation_strength"] = 3.0

    total_score = sum(scores.values())
    return total_score, scores


def rank_and_filter_authorities(
    candidates: List[Dict[str, Any]],
    query_plan: Any,
    top_k: int = 15
) -> List[Dict[str, Any]]:
    """
    Ranks candidates strictly by multi-factor Authority Score.
    """
    filtered: List[Dict[str, Any]] = []

    for c in candidates:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else c
        c_type = str(c.get("content_type") or meta.get("content_type") or "").lower()
        if c_type in ("caption_only", "metadata_only", "quarantined", "rejected"):
            continue

        raw_txt = str(c.get("preview") or c.get("full_text") or c.get("text") or meta.get("full_text") or meta.get("text") or "").strip()
        if len(raw_txt) < 80:
            continue

        total_score, score_breakdown = calculate_authority_score(c, query_plan)
        c["authority_score"] = round(total_score, 2)
        c["authority_score_breakdown"] = score_breakdown
        filtered.append(c)

    filtered.sort(key=lambda x: x.get("authority_score", 0.0), reverse=True)
    return filtered[:top_k]
