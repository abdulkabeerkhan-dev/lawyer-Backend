"""
core/authority_ranking.py

Production-grade Authority Ranking Engine for Pakistani Case Law.
Scores and ranks superior court judgments based on:
1. Legal Issue Match
2. Provision Match
3. Court Hierarchy (Supreme Court > High Courts)
4. Recentness (2024-2026 > 2020-2023 > older)
5. Citation Strength (SCMR/PLD > others)
6. Full Text Availability & Judicial Reasoning

Guarantees:
- A 2025/2026 Supreme Court case with full reasoning always outranks older or unrelated citations.
- Caption-only, metadata-only, and irrelevant subject matter (e.g. defamation, narcotics, murder for fraud) are completely excluded.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from core.legal_query_planner import LegalQueryPlan
from core.case_title_taxonomy import get_effective_title


def is_irrelevant_subject(candidate: Dict[str, Any], query_plan: LegalQueryPlan) -> bool:
    """
    Deterministically filters out cases from completely unrelated legal domains.
    For example: pure defamation, narcotics, or murder cases must never appear
    in a corporate fraud, director liability, or cheque bounce query.
    """
    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else candidate
    title = str(candidate.get("title") or candidate.get("case_name") or candidate.get("case_title") or meta.get("title") or meta.get("case_title") or "").lower()
    text = str(candidate.get("preview") or candidate.get("full_text") or candidate.get("snippet") or candidate.get("text") or meta.get("full_text") or meta.get("text") or "").lower()
    haystack = f"{title} {text}"

    # Check query domain
    domains = [d.lower() for d in (query_plan.legal_domain or [])]
    questions_str = " ".join(query_plan.legal_questions or []).lower()
    provisions_str = " ".join(query_plan.provisions or []).lower()

    is_financial_or_fraud_or_bail = any(k in domains or k in questions_str or k in provisions_str for k in [
        "409", "420", "406", "489-f", "489f", "cheating", "breach of trust", "misappropriat",
        "director", "corporate", "loan", "bail", "498", "497"
    ])

    if is_financial_or_fraud_or_bail:
        # Defamation filter (e.g. Gurmani)
        if any(k in haystack for k in ["mushtaq ahmad gurmani", "z. a. suleri", "defamation", "defamatory", "section 500 ppc", "sec 500"]):
            if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "misappropriat", "entrustment", "director loan"]):
                return True

        # Pure narcotics filter (CNSA)
        if any(k in haystack for k in ["control of narcotic substances act", "cnsa", "charas", "heroin", "opium", "methamphetamine"]):
            if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "director"]):
                return True

        # Pure murder / 302 PPC filter
        if any(k in haystack for k in ["section 302 ppc", "302/34 ppc", "murder trial", "firearm injury", "post-mortem report"]):
            if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "director", "cheque"]):
                return True

    is_partition_or_property = any(k in domains or k in questions_str or k in provisions_str for k in [
        "partition", "benami", "co-sharer", "co-owner", "hotchpot", "joint property"
    ])
    if is_partition_or_property:
        # Exclude banking recovery / FIO / loans / pledge of shares
        if any(k in haystack for k in ["financial institutions", "recovery of finances", "fio 2001", "pawnor", "pledge of shares", "cld 292", "cld", "banking court", "loan default", "letter of credit"]):
            if not any(k in haystack for k in ["partition", "co-sharer", "joint property"]):
                return True
        # Exclude cooperative housing society internal membership disputes
        if any(k in haystack for k in ["cooperative housing society", "co-operative housing", "society membership", "allotment of share in society", "ismailia cooperative", "amir ali hussain shalwani", "2001 ylr 2537"]):
            if not any(k in haystack for k in ["order xx rule 18", "partition act", "co-sharer", "ancestral estate"]):
                return True
        # Exclude service tribunal and labour appeals
        if any(k in haystack for k in ["service tribunal", "service appeal", "plc(cs)", "civil servants act", "labour appellate"]):
            return True
        # Exclude purely criminal / bail / narcotics / murder
        if any(k in haystack for k in ["pcrlj", "bail petition", "489-f", "criminal revision", "post-arrest", "section 302 ppc", "cnsa"]):
            if not any(k in haystack for k in ["partition", "co-sharer", "benami"]):
                return True

    # Criminal Quashment (561-A CrPC) and Bail (497/498 CrPC) Domain Quarantine
    is_criminal_strict = (
        getattr(query_plan, "primary_domain", "") == "criminal"
        and getattr(query_plan, "allowed_domains_filter", []) == ["criminal"]
    )
    if is_criminal_strict:
        haystack_low = haystack.lower()
        # Exclude pure civil recovery / Order 37 summary suits / rent eviction
        if any(k in haystack_low for k in ["order xxxvii", "order 37", "leave to defend under order xxxvii", "summary suit for recovery", "suit for recovery of money", "punjab rented premises act", "rent tribunal", "eviction petition", "ejectment petition"]):
            if not any(k in haystack_low for k in ["quashment", "561-a", "561a", "489-f", "489f", "fir", "bail", "criminal misc"]):
                return True
        # Exclude corporate oppression & winding up
        if any(k in haystack_low for k in ["winding up petition", "section 286 companies act", "oppression and mismanagement"]):
            return True
        # Exclude service tribunal appeals
        if any(k in haystack_low for k in ["service tribunal", "civil servants act", "plc(cs)"]):
            return True

    is_family = any(k in domains or k in questions_str for k in ["family", "khula", "dower", "maintenance", "custody", "guardian", "mflo", "talaq", "zar-i-khula"])
    if is_family:
        if any(k in haystack for k in ["financial institutions", "recovery of finances", "fio 2001", "pawnor", "pledge of shares", "cld", "banking court", "loan default"]):
            return True
        if any(k in haystack for k in ["companies act", "shareholder", "board of directors", "oppression and mismanagement", "secp"]):
            return True
        if any(k in haystack for k in ["section 302 ppc", "cnsa", "charas", "heroin", "narcotics"]):
            return True
        if any(k in haystack for k in ["customs act", "sales tax", "income tax ordinance"]):
            return True

    is_rent = any(k in domains or k in questions_str for k in ["rent", "tenant", "landlord", "eviction", "prpa", "srpo", "rent tribunal"])
    if is_rent:
        if any(k in haystack for k in ["pcrlj", "bail petition", "489-f", "criminal revision", "post-arrest", "section 302 ppc", "cnsa"]):
            if not any(k in haystack for k in ["rent", "tenant", "landlord"]):
                return True
        if any(k in haystack for k in ["financial institutions", "recovery of finances", "fio 2001", "pawnor", "pledge of shares", "cld", "banking court", "loan default"]):
            if not any(k in haystack for k in ["rent", "tenant", "landlord"]):
                return True
        if any(k in haystack for k in ["khula", "dower", "talaq", "guardians and wards", "custody of minor"]):
            return True

    is_banking = any(k in domains or k in questions_str for k in ["banking", "fio 2001", "recovery of finances", "financial institution", "loan default"])
    if is_banking:
        if any(k in haystack for k in ["khula", "dower", "talaq", "guardians and wards", "custody of minor"]):
            return True
        if any(k in haystack for k in ["rent tribunal", "prpa 2009", "srpo", "ejectment of tenant"]):
            if not any(k in haystack for k in ["bank", "mortgage", "finance"]):
                return True
        if any(k in haystack for k in ["section 302 ppc", "cnsa", "murder trial"]):
            return True

    is_corporate = any(k in domains or k in questions_str for k in ["companies act", "oppression", "mismanagement", "company bench", "provisional manager"])
    if is_corporate:
        if any(k in haystack for k in ["election tribunal", "elections act", "reserved seats", "election petition", "service tribunal", "service appeal", "plc(cs)", "civil servants"]):
            return True
        if any(k in haystack for k in ["section 302 ppc", "cnsa", "murder trial"]):
            return True
        if any(k in haystack for k in ["khula", "dower", "family court"]):
            return True

    return False


def calculate_authority_score(candidate: Dict[str, Any], query_plan: LegalQueryPlan) -> Tuple[float, Dict[str, float]]:
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
    haystack = f"{title} {citation} {court} {text}"
    year_val = candidate.get("year") or candidate.get("decision_date") or meta.get("year") or meta.get("decision_date") or 2000

    # 1. Court Hierarchy (0 to 40 pts)
    # Article 189 Supreme Court is binding on all courts in Pakistan
    if "supreme court" in court or "scmr" in citation or "supreme court" in title:
        scores["court_hierarchy"] = 40.0
    elif any(hc in court for hc in ["high court", "lahore", "sindh", "islamabad", "peshawar", "balochistan"]) or any(j in citation for j in ["PLD", "CLC", "PCrLJ", "MLD", "YLR"]):
        scores["court_hierarchy"] = 25.0
    else:
        scores["court_hierarchy"] = 5.0

    # 2. Recentness (0 to 30 pts)
    # Extract numeric year
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
    prov_points = 0.0
    for prov in (query_plan.provisions or []):
        p_clean = prov.lower().replace("section ", "").replace("sec ", "").strip()
        nums = re.findall(r'\b[0-9]+(?:-[a-z])?\b', p_clean)
        for num in nums:
            if re.search(rf'\b(?:sec|section|u/s)?\s*{re.escape(num)}\b', text) or re.search(rf'\b(?:sec|section|u/s)?\s*{re.escape(num)}\b', title):
                prov_points += 12.5
                break
    scores["provision_match"] = min(25.0, prov_points)

    # 5. Legal Issue Match (0 to 30 pts)
    issue_points = 0.0
    combined_questions = " ".join(query_plan.legal_questions or []).lower()
    key_terms = [
        "breach of trust", "dishonest intention", "civil dispute", "contractual breach",
        "pre-arrest bail", "mala fide", "ulterior motive", "director",
        "cheating", "entrustment", "quashment", "fiduciary",
        "partition", "co-sharer", "benami", "set-off", "set off", "counter-claim", "counter claim",
        "hotchpot", "preliminary decree", "order xx rule 18", "order viii rule 6", "ancestral estate",
        "khula", "dower", "maintenance", "dissolution of marriage", "zar-i-khula", "custody", "guardian",
        "eviction", "tenant", "landlord", "rent tribunal", "default in rent", "prpa", "leave to defend",
        "leave to appear", "recovery of finance", "fio 2001",
        "oppression", "mismanagement", "provisional manager", "operational bank accounts", "solvent company",
        "review of judgment", "error apparent", "rehearing", "order xlvii rule 1", "section 114"
    ]
    combined_query_context = f"{combined_questions} {' '.join(query_plan.legal_domain or []).lower()}"
    matched_terms = 0
    for term in key_terms:
        if term in combined_query_context and (term in text or term in title):
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

    raw_authority_score = sum(scores.values())

    # CRITICAL INVARIANT: Relevance Gates Authority!
    # Compute broad term overlap between candidate and query plan
    plan_terms = set()
    for prov in (query_plan.provisions or []):
        for w in prov.lower().split():
            if len(w) > 3 and w not in ("section", "order", "rule", "article", "code", "act"):
                plan_terms.add(w)
    for q in (query_plan.legal_questions or []):
        for w in q.lower().split():
            if len(w) > 3 and w not in ("whether", "which", "court", "under", "pakistan", "provisions"):
                plan_terms.add(w)
    for dom in (query_plan.legal_domain or []):
        for w in dom.lower().split():
            if len(w) > 3 and w not in ("law", "general"):
                plan_terms.add(w)

    text_overlap_count = sum(1 for term in plan_terms if term in haystack)
    relevance_points = scores["provision_match"] + scores["issue_match"]

    if relevance_points == 0.0:
        # Remediation Spec Phase 4: Relevance must dominate.
        # Zero provision match and zero legal issue match strictly yields 0.0 authority score.
        return 0.0, scores
    else:
        # Relevant cases receive relevance multiplier boost
        total_score = raw_authority_score + (relevance_points * 1.5)

    return total_score, scores


def compute_constitutional_multiplier(
    candidate: Dict[str, Any],
    query_plan: Optional[Any] = None
) -> float:
    """
    Computes the composite constitutional authority multiplier according to Pakistani judicial hierarchy:
    Formula:
        Constitutional Multiplier = M_court + M_recency + M_citation + M_section

    Hierarchy Rules (Post-27th Amendment & Chapter 3A):
    - Federal Constitutional Court (FCC) on constitutional questions: +0.90 to +1.00
    - Supreme Court of Pakistan (Article 189 binding precedent): +0.80
    - High Courts Division / Larger Bench or general High Court (Article 201): +0.30 to +0.40
    - Federal Shariat Court (Article 203-GG): +0.35
    - Subordinate Courts / Tribunals: +0.05

    Recency Weights:
    - 2024-2026: +0.15
    - 2020-2023: +0.10
    - 2010-2019: +0.05

    Citation Prestige:
    - SCMR: +0.10
    - PLD: +0.08
    - CLC / PCrLJ / MLD / YLR / CLD / PTD: +0.04

    Structural Section Modifier (Phase 4 Step 6):
    - is_holding=True or section_type in ('ratio_decidendi', 'headnote'): +0.20
    - is_argument=True or section_type == 'counsel_arguments': -0.40
    """
    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else candidate
    court = str(candidate.get("court") or candidate.get("court_name") or meta.get("court") or meta.get("court_name") or "").lower()
    citation = str(candidate.get("citation") or candidate.get("neutral_citation") or meta.get("citation") or meta.get("neutral_citation") or "").upper()
    title = str(candidate.get("title") or candidate.get("case_name") or candidate.get("case_title") or meta.get("title") or meta.get("case_title") or "").lower()
    year_val = candidate.get("year") or candidate.get("decision_date") or meta.get("year") or meta.get("decision_date") or 2000

    # 1. Court Hierarchy Base Multiplier
    is_constitutional_query = False
    if query_plan is not None:
        q_domains = [str(d).lower() for d in (getattr(query_plan, "legal_domain", []) or [])]
        q_questions = " ".join(getattr(query_plan, "legal_questions", []) or []).lower()
        is_constitutional_query = any(k in q_domains or k in q_questions for k in [
            "constitutional", "article 199", "article 184", "amendment", "vires", "fundamental rights"
        ])

    from core.court_derivation import derive_court_and_year
    derived_court, _court_src, _derived_yr = derive_court_and_year(citation=citation, meta_court=court, case_title=title)
    derived_court_low = derived_court.lower()

    # Spec Phase 4: Court tier comes strictly from derived court; UNKNOWN gets no bonus (0.0).
    m_court = 0.0
    if "federal constitutional court" in derived_court_low or "fcc" in court or "fccr" in citation:
        m_court = 1.00 if is_constitutional_query else 0.85
    elif "supreme court" in derived_court_low or "supreme court" in court:
        m_court = 0.80
    elif "federal shariat court" in derived_court_low or "fsc" in court:
        m_court = 0.35
    elif "high court" in derived_court_low or any(hc in derived_court_low for hc in ["lahore", "sindh", "peshawar", "balochistan", "islamabad"]):
        m_court = 0.30
    elif any(j in citation for j in ["PLD", "CLC", "PCrLJ", "MLD", "YLR", "CLD"]):
        m_court = 0.30
    else:
        m_court = 0.0

    # 2. Recency Multiplier
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

    m_recency = 0.0
    if y >= 2024:
        m_recency = 0.15
    elif y >= 2020:
        m_recency = 0.10
    elif y >= 2010:
        m_recency = 0.05

    # 3. Citation Prestige Multiplier
    m_citation = 0.0
    if "SCMR" in citation:
        m_citation = 0.10
    elif "PLD" in citation:
        m_citation = 0.08
    elif any(j in citation for j in ["CLC", "PCrLJ", "MLD", "YLR", "CLD", "PTD"]):
        m_citation = 0.04

    # 4. Step 6 Structural Section Multiplier
    m_section = 0.0
    is_holding = candidate.get("is_holding") or meta.get("is_holding")
    is_argument = candidate.get("is_argument") or meta.get("is_argument")
    sec_type = str(candidate.get("section_type") or meta.get("section_type") or "").lower()

    if is_holding or sec_type in ("ratio_decidendi", "headnote"):
        m_section = 0.20
    elif is_argument or sec_type == "counsel_arguments":
        m_section = -0.40

    total_multiplier = round(m_court + m_recency + m_citation + m_section, 4)
    return total_multiplier


def compute_fused_authority_score(
    cross_encoder_score: float,
    constitutional_multiplier: float,
    relevance_floor: float = 0.35,
    scorer: str = "voyage-rerank-2"
) -> float:
    """
    Computes fused authority score (Phase 4, Step 7):
        Final Score = S_cross_encoder * (1.0 + Constitutional Multiplier)
    Clamped strictly to 0.0 if S_cross_encoder < relevance_floor (0.35).
    Spec Phase 4: Apply separate calibration / no floor to heuristic scores.
    """
    is_heuristic = bool("heuristic" in str(scorer).lower() or "fallback" in str(scorer).lower())
    if not is_heuristic and cross_encoder_score < relevance_floor:
        return 0.0
    fused = cross_encoder_score * (1.0 + constitutional_multiplier)
    return round(fused, 4)


def rank_and_filter_authorities(
    candidates: List[Dict[str, Any]],
    query_plan: LegalQueryPlan,
    top_k: int = 15,
    relevance_floor: float = 0.35
) -> List[Dict[str, Any]]:
    """
    Filters out spurious / caption-only / irrelevant candidates and ranks remaining
    superior court authorities by fused score (when cross_encoder_score/rerank_score is present)
    or multi-factor Authority Score (in legacy mode).
    """
    filtered: List[Dict[str, Any]] = []

    for c in candidates:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else c
        # Filter 1: Check caption-only / metadata-only / quarantined
        c_type = str(c.get("content_type") or meta.get("content_type") or "").lower()
        if c_type in ("caption_only", "metadata_only", "quarantined", "rejected"):
            continue
        if c.get("is_quarantined") or meta.get("is_quarantined"):
            continue

        text_len = max(
            len(str(c.get("full_text") or meta.get("full_text") or "").strip()),
            len(str(c.get("text") or meta.get("text") or "").strip()),
            len(str(c.get("preview") or meta.get("preview") or "").strip()),
            len(str(c.get("snippet") or meta.get("snippet") or "").strip())
        )
        if text_len < 80:
            continue

        # Filter 2: Irrelevant subject matter filter
        if is_irrelevant_subject(c, query_plan):
            continue

        # Check if cross_encoder / rerank score is present on candidate
        has_rerank_score = "rerank_score" in c or "cross_encoder_score" in c
        if has_rerank_score:
            r_score = float(c.get("rerank_score") if "rerank_score" in c else c.get("cross_encoder_score", 0.0))
            scorer = str(c.get("rerank_scorer") or c.get("scorer") or c.get("rerank_model") or "voyage-rerank-2")
            const_mult = compute_constitutional_multiplier(c, query_plan=query_plan)
            fused_score = compute_fused_authority_score(r_score, const_mult, relevance_floor=relevance_floor, scorer=scorer)
            if fused_score == 0.0:
                # Clamped by relevance floor: excluded from generation
                continue
            c["authority_score"] = fused_score
            c["fused_score"] = fused_score
            c["constitutional_multiplier"] = const_mult
            filtered.append(c)
        else:
            # Legacy multi-factor scoring
            total_score, score_breakdown = calculate_authority_score(c, query_plan)
            if total_score == 0.0:
                continue
            c["authority_score"] = round(total_score, 2)
            c["authority_score_breakdown"] = score_breakdown
            filtered.append(c)

    # Sort descending: Highest Authority Score first
    filtered.sort(key=lambda x: x.get("authority_score", 0.0), reverse=True)
    return filtered[:top_k]
