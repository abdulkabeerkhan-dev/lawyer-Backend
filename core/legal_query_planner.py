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
6. provisions: Exact canonical statutory provisions mentioned or directly engaged (e.g. "Section 409 PPC", "Order XXXIX Rule 1 CPC", "Section 28 Limitation Act", "Article 144 Limitation Act", "Article 149 Limitation Act").
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


def create_deterministic_fallback_plan(query: str) -> LegalQueryPlan:
    """
    Robust rule-based fallback if LLM planner fails or is unreachable.
    Leverages domain heuristics, anchor extraction, and query decomposition.
    """
    q_low = query.lower()
    anchors = extract_positive_query_anchors(query)
    decomposed = decompose_compound_legal_query(query)

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
    if any(k in q_low for k in ["pre-arrest bail", "bail", "498", "497"]):
        domains.append("pre-arrest bail")
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
    if any(k in q_low for k in ["family", "khula", "dower", "maintenance", "guardian", "custody of minor"]):
        domains.append("family law")
        if "family" not in matter_type:
            matter_type.append("family")
    if any(k in q_low for k in ["article 199", "writ", "fundamental right", "constitution"]):
        domains.append("constitutional law")
        if "constitutional" not in matter_type:
            matter_type.append("constitutional")
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

    # 5. Identify standard provisions - FILTER ENACTMENT YEARS (Year-to-PPC bug fix)
    provisions = []
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
                elif num_int in [497, 498, 561, 154, 161, 164, 173, 249, 265, 342]:
                    stat_suffix = "CrPC"
                elif num_int in [115, 12, 151, 96, 100, 114]:
                    stat_suffix = "CPC"
                elif num_int in [9, 42, 8, 12, 39, 54]:
                    stat_suffix = "SRA"
                elif num_int in [28, 5, 14, 19]:
                    stat_suffix = "Limitation Act"
                elif "rent" in matter_type:
                    stat_suffix = "PRPA" if province == "Punjab" else "SRPO"
                else:
                    stat_suffix = ""

            if stat_suffix == "PPC" and clean_digit and int(clean_digit) > 511:
                continue

            prov_str = f"Section {num} {stat_suffix}".strip() if stat_suffix else f"Section {num}"
            if prov_str not in provisions:
                provisions.append(prov_str)

    # Fallback to extracted anchors
    for a in anchors:
        m_yr = re.search(r'\b(18\d\d|19\d\d|20\d\d)\b', a)
        if m_yr:
            continue
        if a.startswith("section ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())
        elif a.startswith("article ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())
        elif a.startswith("order ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())

    # Topic-specific mandatory provision inclusions
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

    questions = []
    if any(k in q_low for k in ["civil", "criminal", "breach of trust", "loan"]):
        questions.append("civil dispute vs criminal breach of trust (dishonest intention at inception)")
    if any(k in q_low for k in ["409", "misappropriat"]) or ("director" in q_low and any(k in q_low for k in ["funds", "misappropriat", "breach of trust", "board", "shares", "fiduciary"])):
        questions.append("applicability of Section 409 PPC to company director managing corporate funds")
    if any(k in q_low for k in ["bail", "498", "arrest"]):
        questions.append("grounds for pre-arrest bail under Section 498 CrPC (mala fide and ulterior motive)")
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
        elif "489" in dq_low or "cheque" in dq_low or "bounced" in dq_low or "dishonour" in dq_low:
            lane_name = "cheque_dishonour_489f"
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
        lanes.append({"lane": lane_name, "query": dq})

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
        employee_status_branching=employee_status_branching
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
                if not provisions:
                    provisions = fallback.provisions

                search_lanes = data.get("search_lanes", [])
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
                    persuasive_courts=persuasive_courts
                )
        except Exception:
            # Fallback cleanly without stopping execution
            pass

    # Deterministic fallback
    return create_deterministic_fallback_plan(query)
