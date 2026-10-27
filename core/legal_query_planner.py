"""
core/legal_query_planner.py

Production-grade Legal Query Understanding Engine for Pakistani Law.
Before any retrieval is executed, every user query is analyzed to extract:
- Legal domains (e.g. criminal law, corporate crime, bail, civil, rent, property)
- Matter type (civil, criminal, rent, family, commercial, constitutional)
- Province and forum
- Binding courts (Article 189 apex, Article 201 provincial) and persuasive courts
- Statutory provisions (e.g. Section 409 PPC, Order XXXIX Rule 1 CPC)
- Governing statutes
- Legal questions / issues
- Factual matrix elements
- Specialized multi-lane search queries
"""

import re
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field

from core.legal_guardrails import (
    decompose_compound_legal_query,
    extract_positive_query_anchors
)


class LegalQueryPlan(BaseModel):
    legal_domain: List[str] = Field(default_factory=list)
    provisions: List[str] = Field(default_factory=list)
    legal_questions: List[str] = Field(default_factory=list)
    factual_matrix: List[str] = Field(default_factory=list)
    jurisdiction: str = "Pakistan"
    required_authorities: List[str] = Field(default_factory=lambda: ["Supreme Court of Pakistan", "High Courts"])
    search_lanes: List[Dict[str, str]] = Field(default_factory=list)
    # Phase 2 upgraded fields:
    matter_type: List[str] = Field(default_factory=lambda: ["civil"])
    province: str = "Federal"
    forum: str = "Civil Court / High Court"
    governing_statutes: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    binding_courts: List[str] = Field(default_factory=lambda: ["Supreme Court of Pakistan"])
    persuasive_courts: List[str] = Field(default_factory=list)
    # Task 3.1 upgraded fields:
    forum_hierarchy: List[str] = Field(default_factory=list)
    employee_status_branching: Optional[Dict[str, Any]] = None
    # Fix B: Query-premise checks
    premise_corrections: List[Dict[str, Any]] = Field(default_factory=list)


def resolve_jurisdiction_hierarchy(province: str) -> Tuple[List[str], List[str]]:
    """
    Maps provincial jurisdiction to binding and persuasive courts under Pakistani Constitution.
    - Article 189: Supreme Court of Pakistan is binding nationwide.
    - Article 201: Provincial High Court is binding within that province; sister High Courts are persuasive.
    """
    prov_norm = (province or "Federal").strip().title()
    supreme = "Supreme Court of Pakistan"
    court_map = {
        "Punjab": "Lahore High Court",
        "Sindh": "High Court of Sindh",
        "Khyber Pakhtunkhwa": "Peshawar High Court",
        "Kp": "Peshawar High Court",
        "Kpk": "Peshawar High Court",
        "Balochistan": "High Court of Balochistan",
        "Islamabad": "Islamabad High Court",
        "Ict": "Islamabad High Court",
    }
    all_high_courts = [
        "Lahore High Court",
        "High Court of Sindh",
        "Peshawar High Court",
        "High Court of Balochistan",
        "Islamabad High Court"
    ]
    if prov_norm in court_map:
        binding_hc = court_map[prov_norm]
        binding = [supreme, binding_hc]
        persuasive = [hc for hc in all_high_courts if hc != binding_hc]
        return binding, persuasive
    else:
        return [supreme], all_high_courts


PLANNER_SYSTEM_PROMPT = """You are a senior Pakistani legal research director and legal query planner.
Analyze the user's legal scenario and produce an actionable, structured legal research plan.

Identify:
1. legal_domain: Specific areas of Pakistani law (e.g. "criminal law", "corporate crime", "pre-arrest bail", "civil procedure", "rent restriction", "adverse possession").
2. matter_type: Broad categories (e.g. ["civil"], ["criminal"], ["rent"], ["family"], ["commercial"], ["constitutional"]).
3. province: The relevant Pakistani province if specified or discernible from facts/cities (e.g. "Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan", "Islamabad", or "Federal" if general/unspecified).
4. forum: Relevant judicial or statutory forum (e.g. "Civil Court / District Judge", "Special Court", "Rent Tribunal", "High Court", "Supreme Court").
5. governing_statutes: Primary Acts or Ordinances engaged (e.g. ["Code of Civil Procedure, 1908", "Specific Relief Act, 1877", "Limitation Act, 1908", "Punjab Rented Premises Act, 2009"]).
6. provisions: Exact canonical statutory provisions mentioned or directly engaged (e.g. "Section 409 PPC", "Order XXXIX Rule 1 CPC", "Section 22 Financial Institutions (Recovery of Finances) Ordinance 2001" for banking appeals/decrees/stay deposit, "Section 10 FIO" for leave to defend, "Section 28 Limitation Act", "Article 144 Limitation Act", "Article 149 Limitation Act").
   NEVER treat enactment years (1860, 1898, 1908, 2017) as section numbers. PPC sections only range from 1 to 511.
7. legal_questions / issues: Precise substantive legal doctrines and issues to research.
8. factual_matrix: Key material facts from the prompt.
9. jurisdiction: "Pakistan"
10. required_authorities: Court hierarchy needed (e.g. ["Supreme Court of Pakistan", "High Courts"]).
11. search_lanes: 3 to 5 targeted, highly distinct search subqueries for vector and BM25 search engines. Each lane must focus on a single doctrinal issue.

Output ONLY valid JSON matching this schema:
{
  "legal_domain": ["..."],
  "matter_type": ["..."],
  "province": "Punjab",
  "forum": "...",
  "governing_statutes": ["..."],
  "provisions": ["..."],
  "legal_questions": ["..."],
  "issues": ["..."],
  "factual_matrix": ["..."],
  "jurisdiction": "Pakistan",
  "required_authorities": ["Supreme Court of Pakistan", "High Courts"],
  "search_lanes": [
    {"lane": "issue_1", "query": "..."},
    {"lane": "issue_2", "query": "..."}
  ]
}
"""


def check_query_premises(query: str) -> List[Dict[str, Any]]:
    """
    Extracts provisions and statutes from query and verifies them against the Pakistan statute store.
    Returns structured premise checks for any confirmed absent, unverified, or existing provisions.
    """
    from legal_ai.statutes.statute_store import get_statute_store
    store = get_statute_store()
    extracted = store.extract_provisions_from_query(query)
    checks: List[Dict[str, Any]] = []

    for statute_hint, prov_str in extracted:
        res = store.lookup(statute_hint, prov_str)
        if res.status == "CONFIRMED_ABSENT":
            checks.append({
                "queried_statute": statute_hint,
                "queried_provision": prov_str,
                "status": "CONFIRMED_ABSENT",
                "is_foreign": res.is_foreign_statute,
                "pakistani_equivalent": res.pakistani_equivalent,
                "explanation": res.explanation,
                "mandatory_opening_thesis": (
                    f"PREMISE CORRECTION: {prov_str} ({statute_hint}) does not apply in Pakistan. "
                    f"{res.explanation} "
                    f"Controlling Pakistani law: {res.pakistani_equivalent}."
                ),
                "schedule_ii": res.schedule_ii
            })
        elif res.status == "UNVERIFIED":
            checks.append({
                "queried_statute": statute_hint,
                "queried_provision": prov_str,
                "status": "UNVERIFIED",
                "is_foreign": False,
                "explanation": res.explanation,
                "mandatory_opening_thesis": f"Verification status: Could not verify '{prov_str}' in database."
            })
        elif res.status == "EXISTS":
            checks.append({
                "queried_statute": statute_hint,
                "queried_provision": prov_str,
                "status": "EXISTS",
                "canonical_id": res.canonical_id,
                "display_name": res.display_name,
                "title": res.title,
                "text": res.text,
                "schedule_ii": res.schedule_ii
            })

    return checks


def create_deterministic_fallback_plan(query: str) -> LegalQueryPlan:
    """
    Robust rule-based fallback if LLM planner fails or is unreachable.
    Leverages domain heuristics, anchor extraction, and query decomposition.
    """
    q_low = query.lower()
    anchors = extract_positive_query_anchors(query)
    decomposed = decompose_compound_legal_query(query)
    premise_checks = check_query_premises(query)
    premise_corrections = [c for c in premise_checks if c["status"] in ("CONFIRMED_ABSENT", "UNVERIFIED")]

    # 1. Detect province
    province = "Federal"
    if any(k in q_low for k in ["punjab", "lahore", "rawalpindi", "multan", "faisalabad", "prpa", "lhc"]):
        province = "Punjab"
    elif any(k in q_low for k in ["sindh", "karachi", "hyderabad", "sukkur", "srpo", "shc"]):
        province = "Sindh"
    elif any(k in q_low for k in ["khyber", "peshawar", "kpk", "kp", "abbottabad", "phc"]):
        province = "Khyber Pakhtunkhwa"
    elif any(k in q_low for k in ["balochistan", "baluchistan", "quetta", "bhc"]):
        province = "Balochistan"
    elif any(k in q_low for k in ["islamabad", "ict", "ihc"]):
        province = "Islamabad"

    binding_courts, persuasive_courts = resolve_jurisdiction_hierarchy(province)

    # 2. Detect matter_type and domains
    domains = []
    matter_type = []
    questions: List[str] = []
    if any(k in q_low for k in ["fir", "bail", "ppc", "crpc", "offence", "accused", "arrest", "police", "custody", "prosecute", "prosecution", "cheque", "dishonour", "dishonored", "bounced", "489"]):
        domains.append("criminal law")
        if "criminal" not in matter_type:
            matter_type.append("criminal")
        if any(k in q_low for k in ["cheque", "bounced", "dishonour", "489"]):
            domains.append("cheque dishonour")
    if any(k in q_low for k in ["director", "company", "shareholder", "board", "funds"]) and any(k in q_low for k in ["funds", "misappropriat", "breach of trust", "board", "shares", "fiduciary", "companies act"]):
        domains.append("corporate crime")
        if "corporate" not in matter_type:
            matter_type.append("corporate")
    if any(k in q_low for k in ["pre-arrest bail", "pre arrest bail", "anticipatory bail"]):
        domains.append("pre-arrest bail")
        if "criminal" not in matter_type:
            matter_type.append("criminal")
    elif any(k in q_low for k in ["post-arrest bail", "post arrest bail", "arrested", "custody", "in jail"]) and "bail" in q_low:
        domains.append("post-arrest bail")
        if "criminal" not in matter_type:
            matter_type.append("criminal")
    elif any(k in q_low for k in ["bail", "496", "497", "498"]):
        if any(k in q_low for k in ["arrested", "custody", "without a warrant", "without warrant"]):
            domains.append("post-arrest bail")
        else:
            domains.append("bail")
        if "criminal" not in matter_type:
            matter_type.append("criminal")
    if any(k in q_low for k in ["rent", "tenant", "landlord", "eviction", "evict", "ejectment", "prpa", "srpo", "tenancy", "commercial shop"]):
        domains.append("rent restriction")
        if "rent" not in matter_type:
            matter_type.append("rent")
    if any(k in q_low for k in ["adverse possession", "possession", "limitation act", "specific relief", "injunction", "order xxxix", "suit"]):
        domains.append("civil property")
        if "civil" not in matter_type:
            matter_type.append("civil")
    if any(k in q_low for k in ["sale deed", "agreement to sell", "specific performance", "advance money", "earnest money", "token money", "breach of contract"]) or (any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and any(k in q_low for k in ["sale", "deed", "refused", "money", "property"])):
        if "specific performance & contract" not in domains:
            domains.append("specific performance & contract")
        if "civil" not in matter_type:
            matter_type.append("civil")
    if any(k in q_low for k in ["family", "khula", "dower", "maintenance", "guardian", "custody of minor"]):
        domains.append("family law")
        if "family" not in matter_type:
            matter_type.append("family")
    if any(k in q_low for k in ["article 199", "writ", "fundamental right", "constitution"]):
        domains.append("constitutional law")
        if "constitutional" not in matter_type:
            matter_type.append("constitutional")
    if any(k in q_low for k in ["banking court", "bank", "financial institution", "recovery of finance", "fio"]) and any(k in q_low for k in ["decree", "appeal", "loan", "finance", "stay", "deposit", "leave to defend", "banking"]):
        domains.append("banking recovery")
        if "commercial" not in matter_type:
            matter_type.append("commercial")
    if not domains:
        domains.append("general civil law")
        matter_type.append("civil")

    # 3. Forum
    if "rent" in matter_type and "criminal" in matter_type:
        forum = "Rent Tribunal / Special Judge (Rent) (for eviction) & Judicial Magistrate 1st Class / Police (for Section 489-F PPC)"
    elif "rent" in matter_type:
        forum = "Rent Tribunal / Special Judge (Rent)"
    elif "criminal" in matter_type:
        forum = "Magistrate 1st Class / Sessions Court / High Court"
    elif "family" in matter_type:
        forum = "Family Court"
    elif "corporate" in matter_type:
        forum = "Special Court / High Court Company Bench"
    elif "banking recovery" in domains:
        forum = "Banking Court / High Court (Appellate Division)"
    elif "constitutional" in matter_type:
        forum = "High Court / Supreme Court"
    else:
        forum = "Civil Court / District Judge / High Court"

    # 4. Governing statutes
    statutes = []
    if any(k in q_low for k in ["cpc", "order xxxix", "civil procedure", "sec 9"]):
        statutes.append("Code of Civil Procedure, 1908")
    if any(k in q_low for k in ["limitation", "sec 28", "art 144", "art 149"]):
        statutes.append("Limitation Act, 1908")
    if any(k in q_low for k in ["specific relief", "injunction", "sec 42", "sec 9 sra"]):
        statutes.append("Specific Relief Act, 1877")
    if "rent" in matter_type or any(k in q_low for k in ["prpa", "punjab rented", "rent", "tenant", "evict", "eviction"]):
        if province == "Punjab":
            statutes.append("Punjab Rented Premises Act, 2009")
        elif province == "Sindh":
            statutes.append("Sindh Rented Premises Ordinance, 1979")
        else:
            statutes.append("Punjab Rented Premises Act, 2009")
    if "criminal" in matter_type or any(k in q_low for k in ["ppc", "penal code", "409", "420", "489", "cheque", "dishonour", "bounced", "prosecute"]):
        statutes.append("Pakistan Penal Code, 1860")
        statutes.append("Code of Criminal Procedure, 1898")
    if "banking recovery" in domains or any(k in q_low for k in ["banking court", "financial institution", "recovery of finance", "fio", "firo"]):
        statutes.append("Financial Institutions (Recovery of Finances) Ordinance, 2001")
    if "specific performance & contract" in domains or any(k in q_low for k in ["specific performance", "sale deed", "agreement to sell", "advance money"]):
        for sp_stat in ["Specific Relief Act, 1877", "Contract Act, 1872", "Transfer of Property Act, 1882", "Code of Civil Procedure, 1908", "Limitation Act, 1908"]:
            if sp_stat not in statutes:
                statutes.append(sp_stat)

    # 5. Identify standard provisions - FILTER ENACTMENT YEARS (Year-to-PPC bug fix)
    provisions = []

    # Priority 1: Ground truth canonical detection from unified statute currency
    try:
        from core.statute_currency import detect_statutory_provisions_in_query
        detected_cids = detect_statutory_provisions_in_query(query)
        for cid, act_c in detected_cids:
            m_sec = re.search(r'SEC_([0-9]+[A-Za-z]*)', cid)
            sec_n = m_sec.group(1) if m_sec else ""
            act_disp = act_c.replace('_', ' ')
            if "FIO" in act_c:
                act_disp = "Financial Institutions (Recovery of Finances) Ordinance 2001"
            elif "NI_ACT" in act_c:
                act_disp = "Negotiable Instruments Act, 1881"
            elif "CRPC" in act_c:
                act_disp = "CrPC"
            elif "PPC" in act_c:
                act_disp = "PPC"
            elif "CPC" in act_c:
                act_disp = "CPC"
            elif "SRA" in act_c:
                act_disp = "Specific Relief Act, 1877"
            elif "TPA" in act_c:
                act_disp = "Transfer of Property Act, 1882"

            p_label = f"Section {sec_n} {act_disp}".strip() if sec_n else cid
            if p_label not in provisions:
                provisions.append(p_label)
    except Exception:
        pass

    sec_matches = re.findall(r'(?:sections?|secs?\.?|ss\.?|s\.)\s*([0-9]+(?:-[a-z])?(?:\s*(?:and|&|,)\s*[0-9]+(?:-[a-z])?)*)\s*(ppc|crpc|cpc|qso|sra|fio)?', q_low)
    for m, statute in sec_matches:
        nums = re.findall(r'[0-9]+(?:-[a-z])?', m)
        for num in nums:
            clean_digit = re.sub(r'[^0-9]', '', num)
            if clean_digit and 1800 <= int(clean_digit) <= 2099:
                continue  # SKIP ENACTMENT YEARS!

            if statute:
                stat_suffix = statute.upper()
            else:
                num_int = int(clean_digit) if clean_digit else 0
                if num_int in [409, 420, 406, 489, 302, 376, 380, 468, 471, 324, 34, 109]:
                    stat_suffix = "PPC"
                elif num_int in [496, 497, 498, 561, 154, 161, 164, 173, 249, 265, 342, 54, 61]:
                    stat_suffix = "CrPC"
                elif num_int == 22 and any(k in q_low for k in ["justice of peace", "peace", "crpc", "fir", "police", "ex-officio"]):
                    stat_suffix = "CrPC"
                elif num_int in [115, 12, 151, 96, 100, 114]:
                    stat_suffix = "CPC"
                elif num_int in [9, 42, 8, 12, 39, 54]:
                    stat_suffix = "SRA"
                elif num_int in [28, 5, 14, 19]:
                    stat_suffix = "Limitation Act"
                elif "rent" in matter_type:
                    stat_suffix = "PRPA" if province == "Punjab" else "SRPO"
                elif any(k in q_low for k in ["banking", "bank", "financial institutions", "fio", "loan", "finance"]):
                    stat_suffix = "Financial Institutions (Recovery of Finances) Ordinance 2001"
                else:
                    stat_suffix = ""

            if stat_suffix == "PPC" and clean_digit and int(clean_digit) > 511:
                continue

            prov_str = f"Section {num} {stat_suffix}".strip() if stat_suffix else f"Section {num}"
            already_covered = any(f"section {num} " in p.lower() or p.lower() == f"section {num}" for p in provisions)
            if not already_covered and prov_str not in provisions:
                provisions.append(prov_str)

    # Doctrinal provision detection when query does not state section explicitly
    if any(k in q_low for k in ["banking court", "bank", "financial institution", "recovery of finance", "fio"]):
        if any(k in q_low for k in ["appeal", "stay", "deposit", "execution"]):
            p_label = "Section 22 Financial Institutions (Recovery of Finances) Ordinance 2001"
            if p_label not in provisions:
                provisions.append(p_label)
        elif any(k in q_low for k in ["leave to defend", "leave to appear"]):
            p_label = "Section 10 Financial Institutions (Recovery of Finances) Ordinance 2001"
            if p_label not in provisions:
                provisions.append(p_label)

    # Fallback to extracted anchors
    for a in anchors:
        m_yr = re.search(r'\b(18\d\d|19\d\d|20\d\d)\b', a)
        if m_yr:
            continue
        m_sec = re.search(r'\bsection\s*([0-9]+(?:-[a-z])?)\b', a.lower())
        if m_sec:
            sec_val = m_sec.group(1)
            if any(f"section {sec_val}" in p.lower() for p in provisions):
                continue
        if a.startswith("section ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())
        elif a.startswith("article ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())
        elif a.startswith("order ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())

    # Topic-specific mandatory provision inclusions
    if "bail" in q_low:
        if any(k in q_low for k in ["bailable", "non-bailable", "non bailable", "arrest", "which section", "custody"]):
            for bp in ["Section 496 CrPC", "Section 497 CrPC", "Section 498 CrPC"]:
                if not any(bp.split()[1] in p for p in provisions):
                    provisions.append(bp)
            if any(k in q_low for k in ["without warrant", "without a warrant", "arrest without"]):
                for ap in ["Section 54 CrPC", "Section 61 CrPC"]:
                    if not any(ap.split()[1] in p for p in provisions):
                        provisions.append(ap)

    if any(k in q_low for k in ["cheque", "bounced", "dishonour", "489-f", "489f"]):
        if not any("489" in p for p in provisions):
            provisions.append("Section 489-F PPC")

    if "adverse possession" in q_low or "limitation act" in q_low:
        for default_p in ["Section 28 Limitation Act", "Article 144 Limitation Act", "Article 149 Limitation Act"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)

    if "injunction" in q_low or "order xxxix" in q_low or "o.xxxix" in q_low or "o.39" in q_low:
        for default_p in ["Order XXXIX Rule 1 CPC", "Order XXXIX Rule 2 CPC", "Order XLIII Rule 1(r) CPC", "Section 115 CPC"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)

    if "rent" in matter_type or "eviction" in q_low or "tenant" in q_low:
        if province == "Punjab":
            for default_p in ["Section 4 PRPA 2009", "Section 15 PRPA 2009", "Section 34 PRPA 2009"]:
                if not any(default_p.split()[1] in p for p in provisions):
                    provisions.append(default_p)

    if any(k in q_low for k in ["banking court decree", "banking decree", "banking court judgment"]):
        if not any("fio" in p.lower() or "financial institutions" in p.lower() for p in provisions):
            provisions.append("Section 22 Financial Institutions (Recovery of Finances) Ordinance 2001")

    if "specific performance & contract" in domains or any(k in q_low for k in ["specific performance", "sale deed", "agreement to sell", "advance money"]):
        for sp_p in [
            "Section 12 Specific Relief Act, 1877",
            "Section 53A Transfer of Property Act, 1882",
            "Section 55 Transfer of Property Act, 1882",
            "Section 73 Contract Act, 1872",
            "Section 9 Code of Civil Procedure, 1908",
            "Order XXXIX Rule 1 CPC",
            "Article 113 Limitation Act, 1908"
        ]:
            if not any(sp_p.lower() == p.lower() for p in provisions):
                provisions.append(sp_p)

    # Premise correction routing
    for check in premise_checks:
        if check["status"] == "CONFIRMED_ABSENT":
            q_stat = str(check.get("queried_statute") or "")
            q_prov = str(check.get("queried_provision") or "")
            clean_sec = re.sub(r'[^0-9a-z]', '', q_prov.lower())
            # Filter out absent provision from provisions list
            provisions = [
                p for p in provisions 
                if not (q_prov.lower() == p.lower() or (clean_sec and clean_sec in re.sub(r'[^0-9a-z]', '', p.lower()) and any(k in p.lower() for k in ["ni", "negotiable", "ipc", "indian"])))
            ]
            if "138" in q_prov and ("ni" in q_stat.lower() or "negotiable" in q_stat.lower() or "cheque" in q_low or "bounced" in q_low):
                if not any("489-f" in p.lower() for p in provisions):
                    provisions.append("Section 489-F PPC")
                if not any("order xxxvii" in p.lower() for p in provisions):
                    provisions.append("Order XXXVII Rule 2 CPC")
                if not any("118" in p.lower() for p in provisions):
                    provisions.append("Section 118 Negotiable Instruments Act, 1881")
                if "Pakistan Penal Code, 1860" not in statutes:
                    statutes.append("Pakistan Penal Code, 1860")
                if "Code of Criminal Procedure, 1898" not in statutes:
                    statutes.append("Code of Criminal Procedure, 1898")
                if "Code of Civil Procedure, 1908" not in statutes:
                    statutes.append("Code of Civil Procedure, 1908")
                if "Negotiable Instruments Act, 1881" not in statutes:
                    statutes.append("Negotiable Instruments Act, 1881")
                if "cheque dishonour" not in domains:
                    domains.append("cheque dishonour")
                if "criminal" not in matter_type:
                    matter_type.append("criminal")
                forum = "Judicial Magistrate 1st Class (criminal) / District Judge (civil summary suit Order XXXVII)"
                questions.append("criminal punishment for cheque dishonour under Section 489-F PPC (up to 3 years imprisonment or fine or both)")
                questions.append("absence of Section 138 in Pakistan Negotiable Instruments Act 1881 and civil vs criminal remedies for bounced cheque")
            elif "420" in q_prov and ("indian" in q_stat.lower() or "ipc" in q_stat.lower()):
                if not any("420" in p.lower() and "ppc" in p.lower() for p in provisions):
                    provisions.append("Section 420 PPC")
                if not any("496" in p.lower() for p in provisions):
                    provisions.append("Section 496 CrPC")
                if "Pakistan Penal Code, 1860" not in statutes:
                    statutes.append("Pakistan Penal Code, 1860")
                if "Code of Criminal Procedure, 1898" not in statutes:
                    statutes.append("Code of Criminal Procedure, 1898")
                if "criminal" not in matter_type:
                    matter_type.append("criminal")
                forum = "Court of Session or Magistrate of the first class"
            elif "2a" in q_prov.lower() or "2-a" in q_prov.lower() or ("cpc" in q_stat.lower() and "2" in q_prov.lower()):
                if not any("rule 2a" in p.lower() for p in provisions):
                    provisions.append("Order XXXIX Rule 2A CPC")
                if not any("rule 2(3)" in p.lower() for p in provisions):
                    provisions.append("Order XXXIX Rule 2(3) CPC")
                if "Code of Civil Procedure, 1908" not in statutes:
                    statutes.append("Code of Civil Procedure, 1908")
                if "civil" not in matter_type:
                    matter_type.append("civil")
                forum = "Civil Court / Court granting injunction"
                questions.append("duration of ex-parte interim injunction under Order XXXIX Rule 2A CPC (15 days) and remedy for disobedience or breach under Order XXXIX Rule 2(3) CPC (attachment of property and detention in civil prison; 2006 YLR 2758)")

    forum_hierarchy = ["Civil Court", "District Judge", "High Court", "Supreme Court of Pakistan"]
    employee_status_branching = None

    if any(k in q_low for k in ["dismiss", "civil servant", "service tribunal", "peeda", "removal from service", "show cause"]):
        matter_type = ["constitutional", "service"]
        forum = "Service Tribunal / High Court (conditional)"
        forum_hierarchy = [
            "1. Departmental Appellate Authority (mandatory pre-condition under STA s.4)",
            "2. Federal or Provincial Service Tribunal (exclusive forum under Art. 212 for civil servants)",
            "3. High Court under Article 199 (competent ONLY for statutory body employees with statutory rules; strictly barred for civil servants)",
            "4. Supreme Court of Pakistan (Article 212(3) leave to appeal from Service Tribunal or Art. 185 appeal)"
        ]
        for default_p in ["Article 212 Constitution", "Section 4 Service Tribunals Act 1973", "Article 199(1) Constitution"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)
        questions.append("whether High Court writ under Article 199 is barred by Article 212 for civil servants")
        questions.append("exhaustion of departmental appeal under Section 4 Service Tribunals Act as mandatory pre-condition")
        questions.append("remedy for non-statutory or master-and-servant employees (ordinary civil suit vs writ)")
        
        employee_status_branching = {
            "requires_conditional_analysis": True,
            "civil_servant_branch": "Civil servant under Civil Servants Act: Article 212 bars High Court writ jurisdiction. Departmental appeal must be filed within 30 days. After rejection or expiry of 90 days, appeal lies before Service Tribunal under Section 4 Service Tribunals Act. Article 199 is unavailable.",
            "statutory_body_branch": "Statutory corporation/authority employee governed by statutory rules: Article 212 does not apply. If dismissed without hearing or in violation of statutory inquiry rules, Article 199 writ petition is maintainable before High Court.",
            "master_servant_branch": "Employee of corporation/private body without statutory rules: Governed by master-and-servant doctrine. Writ petition is not maintainable; remedy is ordinary civil suit for damages for wrongful termination.",
            "required_facts": [
                "1. Exact employment status: Whether appointed to a civil post in connection with affairs of Federation/Province or in an autonomous/corporate body.",
                "2. Nature of governing service rules: Whether framed under statutory authority with Government approval or internal administrative regulations.",
                "3. Stage of departmental remedies: Whether a departmental appeal/representation was filed and date thereof."
            ]
        }

    if any(k in q_low for k in ["civil", "criminal", "breach of trust", "loan"]):
        questions.append("civil dispute vs criminal breach of trust (dishonest intention at inception)")
    if any(k in q_low for k in ["409", "misappropriat"]) or ("director" in q_low and any(k in q_low for k in ["funds", "misappropriat", "breach of trust", "board", "shares", "fiduciary"])):
        questions.append("applicability of Section 409 PPC to company director managing corporate funds")
    if "bail" in q_low or any(k in q_low for k in ["496", "497", "498"]):
        if any(k in q_low for k in ["arrested", "in custody", "without a warrant", "without warrant", "post-arrest"]):
            questions.append("statutory distinction between bailable offences under Section 496 CrPC (mandatory right, no discretion to refuse) vs non-bailable offences under Section 497 CrPC (judicial discretion)")
            questions.append("scope of prohibitory clause (punishable with death, life, or 10+ years) vs non-prohibitory clause (bail is rule, refusal exception per Tariq Bashir PLD 1995 SC 34)")
            questions.append("forum hierarchy: Area Judicial Magistrate / SHO (S. 496/497) -> Court of Session (S. 497/498) -> High Court (S. 497/498 concurrent statutory jurisdiction, not Art. 199 writ)")
        else:
            questions.append("grounds for pre-arrest bail under Section 498 CrPC (demonstration of mala fide, ulterior motive, and apprehension of imminent arrest)")
    if any(k in q_low for k in ["adverse possession", "provincial government", "state land"]):
        questions.append("whether adverse possession can mature against Provincial Government under Section 28 Limitation Act")
        questions.append("statutory limitation period for Government recovery of land under Article 149 (60 years) vs Article 144")
    if any(k in q_low for k in ["injunction", "order xxxix"]):
        questions.append("mandatory tripartite test for interim injunction under Order XXXIX Rules 1 & 2 CPC")
        questions.append("appellate remedy under Order XLIII Rule 1(r) CPC against grant or refusal of injunction")
    if any(k in q_low for k in ["rent", "eviction", "commercial shop", "tenant"]):
        questions.append("exclusive jurisdiction of Rent Tribunal and bar on civil court suit under Section 34 PRPA 2009")
        questions.append("grounds for eviction for default in rent payment under Section 15 PRPA 2009")
    if any(k in q_low for k in ["cheque", "bounced", "dishonour", "489"]):
        questions.append("criminal prosecution under Section 489-F PPC for dishonour of cheque issued for rent arrears")
    if any(k in q_low for k in ["rent", "evict", "tenant"]) and any(k in q_low for k in ["cheque", "bounced", "prosecute", "489"]):
        questions.append("concurrent civil eviction and criminal proceedings: whether simultaneous proceedings are legally maintainable")
        questions.append("limitation period: absence of limitation for criminal complaint under CrPC vs eviction application under PRPA")
    if "specific performance & contract" in domains or any(k in q_low for k in ["sale deed", "specific performance", "agreement to sell", "advance money"]):
        questions.append("suit for specific performance of contract to sell immovable property under Section 12 Specific Relief Act 1877")
        questions.append("recovery of advance or earnest money and damages for breach of contract under Section 73 Contract Act 1872")
        questions.append("temporary injunction under Order XXXIX Rules 1 & 2 CPC restraining seller from creating third party interest or alienating property")
        questions.append("limitation period of three years under Article 113 Limitation Act 1908 for specific performance")

    if not questions:
        questions = [query[:200]]

    lanes = []
    for i, dq in enumerate(decomposed):
        lane_name = f"lane_{i+1}"
        dq_low = dq.lower()
        if "concurrent" in dq_low or "simultaneous" in dq_low:
            lane_name = "concurrent_civil_criminal_remedies"
        elif "rent" in dq_low or "eviction" in dq_low or "tenant" in dq_low or "prpa" in dq_low:
            lane_name = "rent_tribunal_eviction"
        elif "489" in dq_low or "cheque" in dq_low or "bounced" in dq_low or "dishonour" in dq_low or "138" in dq_low:
            lane_name = "cheque_dishonour_489f"
            # Anchor query to Pakistani Section 489-F PPC
            dq = "Section 489-F PPC cheque dishonour bounced cheque ingredients punishment dishonest issuance"
        elif "420" in dq_low and ("indian" in dq_low or "ipc" in dq_low):
            lane_name = "cheating_fraud_420ppc"
            dq = "Section 420 PPC cheating dishonestly inducing delivery of property ingredients punishment Schedule II"
        elif "rule 2a" in dq_low or "rule 2-a" in dq_low or "rule 2(3)" in dq_low or "disobedience" in dq_low:
            lane_name = "injunction_breach_rule_2_3"
            dq = "Order XXXIX Rule 2(3) CPC disobedience breach of injunction stay order attachment of property detention in civil prison"
        elif "409" in dq_low or "breach of trust" in dq_low:
            lane_name = "offence_ingredients"
        elif "civil dispute" in dq_low or "dishonest intention" in dq_low:
            lane_name = "civil_vs_criminal"
        elif "498" in dq_low or "bail" in dq_low:
            lane_name = "bail_doctrine"
        elif "adverse possession" in dq_low or "government" in dq_low:
            lane_name = "adverse_possession_doctrine"
        elif "injunction" in dq_low or "order xxxix" in dq_low:
            lane_name = "interim_injunction_remedy"
        elif any(k in dq_low for k in ["specific performance", "sale deed", "agreement to sell", "advance money"]):
            lane_name = "specific_performance_sale_deed"
            dq = "Section 12 Specific Relief Act 1877 suit for specific performance sale deed advance money refusal to execute agreement to sell"
        lanes.append({"lane": lane_name, "query": dq})

    # Add dedicated lanes for Specific Performance & Contract queries
    if "specific performance & contract" in domains or any(k in q_low for k in ["sale deed", "specific performance", "agreement to sell", "advance money"]):
        if not any(l["lane"] == "specific_performance_immovable_property" for l in lanes):
            lanes.insert(0, {
                "lane": "specific_performance_immovable_property",
                "query": "Section 12 Specific Relief Act 1877 suit for specific performance agreement to sell immovable property advance money"
            })
        if not any(l["lane"] == "recovery_advance_money_damages" for l in lanes):
            lanes.append({
                "lane": "recovery_advance_money_damages",
                "query": "Section 73 Contract Act 1872 recovery of earnest advance money damages breach of contract to sell"
            })
        if not any(l["lane"] == "temporary_injunction_restraining_alienation" for l in lanes):
            lanes.append({
                "lane": "temporary_injunction_restraining_alienation",
                "query": "Order XXXIX Rules 1 2 CPC temporary injunction restraining seller from alienating property creating third party interest"
            })

    # Add dedicated lanes if premise corrections were triggered
    for check in premise_checks:
        if check["status"] == "CONFIRMED_ABSENT" and "138" in str(check.get("queried_provision")):
            if not any(l["lane"] == "cheque_dishonour_489f" for l in lanes):
                lanes.insert(0, {
                    "lane": "cheque_dishonour_489f",
                    "query": "Section 489-F PPC dishonour of cheque ingredients punishment dishonest issuance"
                })
            if not any(l["lane"] == "cheque_civil_recovery" for l in lanes):
                lanes.append({
                    "lane": "cheque_civil_recovery",
                    "query": "Order XXXVII Rule 2 CPC summary suit dishonoured cheque Section 118 NI Act presumption"
                })
        elif check["status"] == "CONFIRMED_ABSENT" and "420" in str(check.get("queried_provision")):
            if not any(l["lane"] == "cheating_fraud_420ppc" for l in lanes):
                lanes.insert(0, {
                    "lane": "cheating_fraud_420ppc",
                    "query": "Section 420 PPC cheating dishonestly inducing delivery of property ingredients punishment"
                })
            if not any(l["lane"] == "crpc_bail_schedule_ii" for l in lanes):
                lanes.append({
                    "lane": "crpc_bail_schedule_ii",
                    "query": "Section 420 PPC Schedule II non-bailable cognizable Section 497 CrPC non-prohibitory clause bail as rule"
                })
        elif ("rule 2a" in str(check.get("queried_provision")).lower() or "rule 2-a" in str(check.get("queried_provision")).lower()):
            if not any(l["lane"] == "injunction_duration_rule_2a" for l in lanes):
                lanes.insert(0, {
                    "lane": "injunction_duration_rule_2a",
                    "query": "Order XXXIX Rule 2A CPC interim injunction duration fifteen days ex-parte defendant"
                })
            if not any(l["lane"] == "injunction_breach_rule_2_3" for l in lanes):
                lanes.append({
                    "lane": "injunction_breach_rule_2_3",
                    "query": "Order XXXIX Rule 2(3) CPC disobedience breach of injunction stay order attachment of property detention in civil prison"
                })

    # Dedicated lanes for Bail queries
    if "bail" in q_low and any(k in q_low for k in ["bailable", "non-bailable", "non bailable", "arrest", "which section"]):
        if not any(l["lane"] == "bail_bailable_s496" for l in lanes):
            lanes.insert(0, {
                "lane": "bail_bailable_s496",
                "query": "Section 496 CrPC bailable offence bail as matter of right not favor police station magistrate"
            })
        if not any(l["lane"] == "bail_non_bailable_s497" for l in lanes):
            lanes.insert(1, {
                "lane": "bail_non_bailable_s497",
                "query": "Section 497 CrPC non-bailable prohibitory clause Tariq Bashir PLD 1995 SC 34 concession grace judicial discretion"
            })
        if not any(l["lane"] == "bail_concurrent_jurisdiction_s498" for l in lanes):
            lanes.append({
                "lane": "bail_concurrent_jurisdiction_s498",
                "query": "Section 498 CrPC concurrent jurisdiction Court of Session High Court bail application"
            })

    return LegalQueryPlan(
        legal_domain=domains,
        provisions=provisions,
        legal_questions=questions,
        factual_matrix=[query[:250]],
        jurisdiction="Pakistan",
        required_authorities=["Supreme Court of Pakistan", "High Courts"],
        search_lanes=lanes,
        matter_type=matter_type,
        province=province,
        forum=forum,
        governing_statutes=statutes,
        issues=questions,
        binding_courts=binding_courts,
        persuasive_courts=persuasive_courts,
        forum_hierarchy=forum_hierarchy,
        employee_status_branching=employee_status_branching,
        premise_corrections=premise_corrections
    )


async def analyze_legal_query(query: str, ai_client_fn=None) -> LegalQueryPlan:
    """
    Analyzes user query and returns a structured LegalQueryPlan.
    Tries AI planner first; safely falls back to deterministic planner on any error or timeout.
    """
    if not query or len(query.strip()) < 10:
        return create_deterministic_fallback_plan(query)

    if ai_client_fn:
        try:
            user_msg = f"User Legal Query:\n\"\"\"{query}\"\"\""
            resp = await asyncio.wait_for(
                ai_client_fn(
                    system=PLANNER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                    temperature=0.0,
                    max_tokens=1500
                ),
                timeout=12.0
            )
            raw_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
            m_json = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                # Normalize provisions
                raw_provisions = data.get("provisions", [])
                provisions = []
                for p in raw_provisions:
                    p_str = str(p).strip()
                    # Filter out suspicious year provisions (e.g. Section 1908, Section 1898)
                    m_fake = re.search(r'section\s*(18\d\d|19\d\d|20\d\d)', p_str, re.IGNORECASE)
                    if m_fake:
                        continue
                    provisions.append(p_str)

                fallback = create_deterministic_fallback_plan(query)
                premise_corrections = fallback.premise_corrections
                search_lanes = data.get("search_lanes", [])

                # If premise corrections exist, ensure absent provisions are scrubbed and replaced with Pakistani equivalents
                if premise_corrections:
                    for pc in premise_corrections:
                        if pc.get("status") == "CONFIRMED_ABSENT":
                            absent_p = str(pc.get("queried_provision") or "").lower()
                            provisions = [p for p in provisions if absent_p not in p.lower()]
                            for fp in fallback.provisions:
                                if fp not in provisions:
                                    provisions.append(fp)
                            search_lanes = fallback.search_lanes

                if not provisions:
                    provisions = fallback.provisions

                if not search_lanes:
                    search_lanes = fallback.search_lanes

                province = data.get("province") or fallback.province
                binding_courts, persuasive_courts = resolve_jurisdiction_hierarchy(province)

                issues = data.get("issues") or data.get("legal_questions") or fallback.issues

                return LegalQueryPlan(
                    legal_domain=data.get("legal_domain") or fallback.legal_domain,
                    provisions=provisions,
                    legal_questions=data.get("legal_questions") or fallback.legal_questions,
                    factual_matrix=data.get("factual_matrix") or [query[:250]],
                    jurisdiction="Pakistan",
                    required_authorities=data.get("required_authorities", ["Supreme Court of Pakistan", "High Courts"]),
                    search_lanes=search_lanes,
                    matter_type=data.get("matter_type") or fallback.matter_type,
                    province=province,
                    forum=data.get("forum") or fallback.forum,
                    governing_statutes=data.get("governing_statutes") or fallback.governing_statutes,
                    issues=issues,
                    binding_courts=binding_courts,
                    persuasive_courts=persuasive_courts,
                    forum_hierarchy=fallback.forum_hierarchy,
                    employee_status_branching=fallback.employee_status_branching,
                    premise_corrections=premise_corrections
                )
        except Exception as err:
            import sys
            print(f"⚠️ analyze_legal_query exception: {err}", file=sys.stderr, flush=True)

    # Deterministic fallback
    return create_deterministic_fallback_plan(query)
