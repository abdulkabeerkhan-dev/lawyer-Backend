"""
core/legal_query_planner.py

Production-grade Legal Query Understanding Engine for Pakistani Law.
Before any retrieval is executed, every user query is analyzed to extract:
- Legal domains (e.g. civil, criminal, constitutional, family, corporate, rent, banking, taxation, service, labour)
- Primary and secondary domains
- Specific subdomains and topic anchors
- Allowed domains filter for vector and database isolation
- Cross-domain relevance discriminator (distinguishes legitimate cross-domain authority from irrelevant noise)
- Ambiguity detection and multi-branch clarification
- Province and forum
- Binding courts (Article 189 apex, Article 201 provincial) and persuasive courts
- Statutory provisions (e.g. Order XX Rule 18 CPC, Section 406 PPC, Section 22 FIO 2001)
- Governing statutes
- Core legal questions / issues
- Procedural remedy
- Specialized multi-lane search queries
"""

import os
import re
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Literal, Set, Union
from pydantic import BaseModel, Field, model_validator

from core.legal_guardrails import (
    decompose_compound_legal_query,
    extract_positive_query_anchors
)

LegalDomainType = Literal[
    "civil", "criminal", "constitutional", "family",
    "corporate", "rent", "banking", "taxation", "service", "labour",
    "cybercrime", "intellectual_property", "environmental", "general_legal"
]

ALL_LEGAL_DOMAINS: Set[str] = {
    "civil", "criminal", "constitutional", "family",
    "corporate", "rent", "banking", "taxation", "service", "labour",
    "cybercrime", "intellectual_property", "environmental", "general_legal"
}

ProvinceType = Literal[
    "Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan", "Islamabad", "Federal"
]


class SearchLane(BaseModel):
    lane_id: str
    purpose: str = ""
    query: str
    target_engine: Literal["all", "dense", "sparse", "exact"] = "all"
    domain_override: Optional[LegalDomainType] = None

    @property
    def lane(self) -> str:
        return self.lane_id

    def __getitem__(self, item: str) -> Any:
        if item == "lane":
            return self.lane_id
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except (KeyError, AttributeError):
            return default


class PremiseCorrection(BaseModel):
    queried_statute: str
    queried_provision: str
    status: Literal[
        "VALID", "STATUTORILY_BARRED", "LEGALLY_INAPPLICABLE", "REPEALED",
        "CONFIRMED_ABSENT", "UNVERIFIED", "EXISTS",
        "LEGALLY_INAPPLICABLE_PREMISE", "STATUTORILY_BARRED_DEFENCE"
    ]
    mandatory_opening_thesis: str
    statutory_authority: str = ""
    is_foreign: Optional[bool] = None
    pakistani_equivalent: Optional[str] = None
    explanation: Optional[str] = None
    canonical_id: Optional[str] = None
    display_name: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    schedule_ii: Optional[Any] = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            return default


class StructuredLegalQueryPlan(BaseModel):
    query_text: str
    jurisdiction: str = "Pakistan"
    primary_domain: LegalDomainType = "civil"
    secondary_domains: List[LegalDomainType] = Field(default_factory=list)
    subdomains: List[str] = Field(default_factory=list)
    governing_statutes: List[str] = Field(default_factory=list)
    statutory_provisions: List[str] = Field(default_factory=list)
    core_legal_issues: List[str] = Field(default_factory=list)
    procedural_remedy: str = ""
    competent_forum: str = ""
    target_province: Optional[ProvinceType] = "Federal"
    search_lanes: List[Union[SearchLane, Dict[str, Any]]] = Field(default_factory=list)
    premise_corrections: List[Union[PremiseCorrection, Dict[str, Any]]] = Field(default_factory=list)
    allowed_domains_filter: List[str] = Field(default_factory=list)

    # Cross-domain synthesis & isolation controls
    is_cross_domain_relevant: bool = False
    cross_domain_reason: Optional[str] = None
    cross_domain_controlling_doctrines: List[str] = Field(default_factory=list)

    # Ambiguity detection & handling
    is_ambiguous: bool = False
    ambiguity_reasons: List[str] = Field(default_factory=list)
    clarification_options: List[Dict[str, Any]] = Field(default_factory=list)

    # Backward compatibility fields (synced with target fields)
    legal_domain: List[str] = Field(default_factory=list)
    provisions: List[str] = Field(default_factory=list)
    legal_questions: List[str] = Field(default_factory=list)
    factual_matrix: List[str] = Field(default_factory=list)
    required_authorities: List[str] = Field(default_factory=lambda: ["Supreme Court of Pakistan", "High Courts"])
    matter_type: List[str] = Field(default_factory=list)
    province: str = "Federal"
    forum: str = "Civil Court / High Court"
    issues: List[str] = Field(default_factory=list)
    binding_courts: List[str] = Field(default_factory=lambda: ["Supreme Court of Pakistan"])
    persuasive_courts: List[str] = Field(default_factory=list)
    forum_hierarchy: List[str] = Field(default_factory=list)
    employee_status_branching: Optional[Dict[str, Any]] = None
    raw_query: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_and_validate_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. Sync raw_query <-> query_text
        q_text = data.get("query_text") or data.get("raw_query") or ""
        data["query_text"] = q_text
        data["raw_query"] = q_text

        # 2. Sync provisions <-> statutory_provisions
        p_list = data.get("statutory_provisions") or data.get("provisions") or []
        data["statutory_provisions"] = list(p_list)
        data["provisions"] = list(p_list)

        # 3. Sync issues <-> legal_questions <-> core_legal_issues
        iss_list = data.get("core_legal_issues") or data.get("issues") or data.get("legal_questions") or []
        data["core_legal_issues"] = list(iss_list)
        data["issues"] = list(iss_list)
        data["legal_questions"] = list(iss_list)

        # 4. Sync province <-> target_province
        prov = data.get("target_province") or data.get("province") or "Federal"
        if prov not in ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan", "Islamabad", "Federal"]:
            prov = "Federal"
        data["target_province"] = prov
        data["province"] = prov

        # 5. Sync forum <-> competent_forum
        frm = data.get("competent_forum") or data.get("forum") or "Civil Court / High Court"
        data["competent_forum"] = frm
        data["forum"] = frm

        # 6. Resolve primary_domain if missing
        prim = data.get("primary_domain")
        if not prim:
            m_type = data.get("matter_type", [])
            l_dom = data.get("legal_domain", [])
            all_str = [str(x).lower() for x in m_type + l_dom]
            if any("criminal" in x for x in all_str):
                prim = "criminal"
            elif any("family" in x for x in all_str):
                prim = "family"
            elif any("rent" in x for x in all_str):
                prim = "rent"
            elif any("corporate" in x for x in all_str):
                prim = "corporate"
            elif any("service" in x for x in all_str):
                prim = "service"
            elif any("constitutional" in x for x in all_str):
                prim = "constitutional"
            elif any("banking" in x for x in all_str):
                prim = "banking"
            else:
                prim = "civil"
            data["primary_domain"] = prim

        # 7. Sync matter_type & legal_domain
        sec = data.get("secondary_domains", [])
        if not data.get("matter_type"):
            data["matter_type"] = [prim] + [s for s in sec if s != prim]
        if not data.get("legal_domain"):
            data["legal_domain"] = [prim] + data.get("subdomains", [])

        # 8. Ensure allowed_domains_filter is set and sound
        allowed = data.get("allowed_domains_filter", [])
        if not allowed:
            allowed_set = {prim}
            # Only add secondary domains if is_cross_domain_relevant or allowed synergies
            if data.get("is_cross_domain_relevant"):
                for s in sec:
                    allowed_set.add(s)
            elif prim in ("rent", "banking", "corporate"):
                allowed_set.add("civil")
            data["allowed_domains_filter"] = sorted(list(allowed_set))

        # 9. Sync binding and persuasive courts
        if not data.get("binding_courts") or not data.get("persuasive_courts"):
            b_courts, p_courts = resolve_jurisdiction_hierarchy(prov)
            if not data.get("binding_courts"):
                data["binding_courts"] = b_courts
            if not data.get("persuasive_courts"):
                data["persuasive_courts"] = p_courts

        return data


# Backward-compatibility alias
LegalQueryPlan = StructuredLegalQueryPlan


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

CRITICAL PAKISTANI JURISDICTIONAL INVARIANTS:
- CHEQUE DISHONOUR: In Pakistan, dishonour of a cheque is governed SOLELY by Section 489-F PPC (PPC_1860_SEC_489F) and Order XXXVII CPC (CPC_1908_ORD_XXXVII_R_1) for summary civil recovery.
  Sections 138, 139, 140, 141, 142 of the Negotiable Instruments Act are INDIAN provisions (inserted in India by Act 66 of 1988) and DO NOT EXIST in Pakistani law. Pakistan's Negotiable Instruments Act 1881 stops at Section 137. NEVER cite Section 138 or Section 139 NIA 1881 for Pakistan.
- BAIL: Pre-arrest bail is Section 498 CrPC (CRPC_1898_SEC_498). Post-arrest bail is Section 497 CrPC (CRPC_1898_SEC_497). Bailable offences is Section 496 CrPC (CRPC_1898_SEC_496). Quashment of FIR or criminal proceedings is Section 561-A CrPC (CRPC_1898_SEC_561A).
- SPECIFIC PERFORMANCE: Agreement to sell immovable property is governed by Section 12 SRA (SRA_1877_SEC_12), with compensation under Section 19 SRA (SRA_1877_SEC_19) and Section 73 Contract Act (CONTRACT_1872_SEC_73).
- FAMILY LAW: Khula is under Section 10 FCA (FAMILY_COURTS_1964_SEC_10) and Section 2 DMMA (DMMA_1939_SEC_2). Prompt/deferred dower is under Section 10 MFLO (MFLO_1961_SEC_10) and Section 5 FCA (FAMILY_COURTS_1964_SEC_5). Maintenance is under Section 9 MFLO (MFLO_1961_SEC_9) and Section 17A FCA (FAMILY_COURTS_1964_SEC_17A). Custody/Hizanat is under Section 17 and 25 GWA (GWA_1890_SEC_17, GWA_1890_SEC_25). Never cite criminal or SRA sections in pure family law matters.
- RENT: Eviction is governed by Section 15 PRPA (PRPA_2009_SEC_15). Leave to contest within 10 days is mandatory under Section 22 PRPA (PRPA_2009_SEC_22). Written tenancy agreement under Section 4 PRPA (PRPA_2009_SEC_4).
- BANKING: Recovery suits are instituted under Section 9 FIO 2001 (FIO_2001_SEC_9). Mandatory petition for leave to defend within 30 days is under Section 10 FIO 2001 (FIO_2001_SEC_10). Appeals under Section 22 FIO 2001 (FIO_2001_SEC_22).

CANONICAL ID MANDATE:
All statutory provisions returned in `statutory_provisions` and in `issues[i].controlling_provisions` MUST be Authoritative Canonical IDs from the Pakistani Statute Store.
DO NOT return free-form text strings (e.g. do NOT return 'Section 489-F PPC' or 'Order XXXVII Rule 1 CPC').
Return EXACT CANONICAL IDs ONLY.
Every canonical ID follows the syntax: [STATUTE]_[YEAR]_[UNIT]_[NUMBER]
Where UNIT is:
- SEC: Section (e.g. PPC_1860_SEC_379, CRPC_1898_SEC_498, FIO_2001_SEC_9, PRPA_2009_SEC_15, FAMILY_COURTS_1964_SEC_5, MFLO_1961_SEC_9, GWA_1890_SEC_17, DMMA_1939_SEC_2)
- ORD / RULE: CPC Orders and Rules (e.g. CPC_1908_ORD_XXXVII_R_1, CPC_1908_ORD_VII_R_11, CPC_1908_ORD_XXXIX_R_1)
- ART: Constitutional Articles, Limitation Act Articles, QSO Articles (e.g. CONST_1973_ART_199, LIMITATION_1908_ART_113, QSO_1984_ART_17)

CANONICAL ID LOOKUP REFERENCE TABLE:
1. Criminal (PPC 1860 & CrPC 1898):
   - Offence of Murder: PPC_1860_SEC_300, PPC_1860_SEC_301, PPC_1860_SEC_302, PPC_1860_SEC_324
   - Offences of Theft, CBT, Fraud: PPC_1860_SEC_378, PPC_1860_SEC_379, PPC_1860_SEC_380, PPC_1860_SEC_405, PPC_1860_SEC_406, PPC_1860_SEC_408, PPC_1860_SEC_409, PPC_1860_SEC_415, PPC_1860_SEC_420, PPC_1860_SEC_489F
   - FIR & Investigation: CRPC_1898_SEC_54, CRPC_1898_SEC_61, CRPC_1898_SEC_154, CRPC_1898_SEC_156, CRPC_1898_SEC_161, CRPC_1898_SEC_164, CRPC_1898_SEC_167, CRPC_1898_SEC_173
   - Bail & Quashment: CRPC_1898_SEC_496, CRPC_1898_SEC_497, CRPC_1898_SEC_498, CRPC_1898_SEC_561A
2. Civil & Commercial (CPC 1908, SRA 1877, Contract 1872, TPA 1882, Limitation 1908):
   - CPC: CPC_1908_SEC_9, CPC_1908_SEC_10, CPC_1908_SEC_11, CPC_1908_SEC_12, CPC_1908_SEC_96, CPC_1908_SEC_115, CPC_1908_SEC_151, CPC_1908_ORD_VI_R_17, CPC_1908_ORD_VII_R_11, CPC_1908_ORD_VIII_R_1, CPC_1908_ORD_XX_R_18, CPC_1908_ORD_XXXVII_R_1, CPC_1908_ORD_XXXVII_R_2, CPC_1908_ORD_XXXVII_R_3, CPC_1908_ORD_XXXIX_R_1, CPC_1908_ORD_XXXIX_R_2
   - Specific Relief: SRA_1877_SEC_8, SRA_1877_SEC_9, SRA_1877_SEC_12, SRA_1877_SEC_19, SRA_1877_SEC_21, SRA_1877_SEC_22, SRA_1877_SEC_42, SRA_1877_SEC_54, SRA_1877_SEC_56
   - Contract & Property: CONTRACT_1872_SEC_10, CONTRACT_1872_SEC_23, CONTRACT_1872_SEC_56, CONTRACT_1872_SEC_64, CONTRACT_1872_SEC_65, CONTRACT_1872_SEC_73, CONTRACT_1872_SEC_74, TPA_1882_SEC_52, TPA_1882_SEC_53A, TPA_1882_SEC_54
   - Limitation: LIMITATION_1908_SEC_3, LIMITATION_1908_SEC_5, LIMITATION_1908_SEC_12, LIMITATION_1908_SEC_14, LIMITATION_1908_ART_113, LIMITATION_1908_ART_144, LIMITATION_1908_ART_150, LIMITATION_1908_ART_181
3. Family Law:
   - Family Courts Act, 1964: FAMILY_COURTS_1964_SEC_5, FAMILY_COURTS_1964_SEC_7, FAMILY_COURTS_1964_SEC_10, FAMILY_COURTS_1964_SEC_12, FAMILY_COURTS_1964_SEC_14, FAMILY_COURTS_1964_SEC_17, FAMILY_COURTS_1964_SEC_17A, FAMILY_COURTS_1964_SEC_20
   - Muslim Family Laws Ordinance, 1961: MFLO_1961_SEC_6, MFLO_1961_SEC_7, MFLO_1961_SEC_8, MFLO_1961_SEC_9, MFLO_1961_SEC_10
   - Dissolution of Muslim Marriages Act, 1939: DMMA_1939_SEC_2
   - Guardians and Wards Act, 1890: GWA_1890_SEC_7, GWA_1890_SEC_9, GWA_1890_SEC_12, GWA_1890_SEC_17, GWA_1890_SEC_25
4. Rent & Eviction:
   - Punjab Rented Premises Act, 2009: PRPA_2009_SEC_4, PRPA_2009_SEC_15, PRPA_2009_SEC_19, PRPA_2009_SEC_22, PRPA_2009_SEC_24, PRPA_2009_SEC_27, PRPA_2009_SEC_28, PRPA_2009_SEC_34
   - Sindh Rented Premises Ordinance, 1979: SRPO_1979_SEC_15, SRPO_1979_SEC_16, SRPO_1979_SEC_21
5. Banking Recovery:
   - Financial Institutions (Recovery of Finances) Ordinance, 2001: FIO_2001_SEC_2, FIO_2001_SEC_9, FIO_2001_SEC_10, FIO_2001_SEC_11, FIO_2001_SEC_14, FIO_2001_SEC_15, FIO_2001_SEC_19, FIO_2001_SEC_22
6. Constitutional Law:
   - Constitution of Pakistan, 1973: CONST_1973_ART_4, CONST_1973_ART_9, CONST_1973_ART_10, CONST_1973_ART_10A, CONST_1973_ART_14, CONST_1973_ART_18, CONST_1973_ART_23, CONST_1973_ART_24, CONST_1973_ART_25, CONST_1973_ART_184, CONST_1973_ART_185, CONST_1973_ART_187, CONST_1973_ART_189, CONST_1973_ART_199, CONST_1973_ART_201, CONST_1973_ART_212

Output ONLY valid JSON matching this schema:
{
  "primary_domain": "family",
  "secondary_domains": [],
  "subdomains": ["khula", "dower", "maintenance", "custody"],
  "issues": [
    {
      "issue_id": "issue_1",
      "heading": "...",
      "description": "...",
      "controlling_statutes": ["Family Courts Act, 1964", "Dissolution of Muslim Marriages Act, 1939"],
      "controlling_provisions": [
        "FAMILY_COURTS_1964_SEC_5",
        "DMMA_1939_SEC_2"
      ],
      "search_queries": ["..."],
      "factual_anchors": ["..."]
    }
  ],
  "statutory_provisions": [
    "FAMILY_COURTS_1964_SEC_5",
    "DMMA_1939_SEC_2"
  ],
  "open_questions": ["..."],
  "procedural_remedy": "...",
  "competent_forum": "Family Court",
  "target_province": "Federal",
  "search_lanes": [
    {"lane_id": "lane_1", "purpose": "...", "query": "...", "target_engine": "all"}
  ],
  "is_cross_domain_relevant": false,
  "cross_domain_reason": null,
  "allowed_domains_filter": ["family"],
  "is_ambiguous": false
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
        # Check for Indian Negotiable Instruments Act Section 138 (Cheque dishonour)
        if any(k in str(statute_hint).lower() for k in ["negotiable", "ni act"]) and "138" in str(prov_str):
            checks.append({
                "queried_statute": "Negotiable Instruments Act, 1881",
                "queried_provision": "Section 138",
                "status": "CONFIRMED_ABSENT",
                "is_foreign": True,
                "pakistani_equivalent": "Section 489-F PPC (Pakistan Penal Code, 1860) and Order XXXVII CPC",
                "explanation": (
                    "The criminal offence of dishonouring a cheque under Section 138 of the Negotiable Instruments Act "
                    "is an Indian statutory provision (inserted in India by Act 66 of 1988) and does not exist in the "
                    "Pakistan Negotiable Instruments Act, 1881 (where Section 138 merely provides for the appointment "
                    "of Notaries Public). In Pakistan, criminal prosecution for dishonour of a cheque is governed exclusively "
                    "by Section 489-F of the Pakistan Penal Code, 1860, and summary civil recovery by Order XXXVII CPC."
                ),
                "mandatory_opening_thesis": (
                    "PREMISE CORRECTION: Section 138 of the Negotiable Instruments Act (criminal offence for bounced cheque) "
                    "does not apply in Pakistan. It is an Indian provision (Act 66 of 1988). "
                    "Controlling Pakistani law: Section 489-F PPC for criminal prosecution and Order XXXVII CPC for summary civil recovery."
                ),
                "schedule_ii": None
            })
            continue

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


def filter_provisions_by_domain(provisions: List[str], domain: str) -> List[str]:
    """
    Validation Gate: Ensures provisions added to the plan strictly align with primary_domain.
    Prevents cross-contamination across the 10 Priority Domains.
    """
    clean = []
    dom = (domain or "civil").lower()
    for p in provisions:
        p_str = str(p).strip()
        p_low = p_str.lower()
        if dom == "family":
            if any(bad in p_low for bad in ["ppc", "489-f", "489f", "crpc", "penal code", "criminal procedure", "sra", "specific relief", "order xxxvii"]):
                continue
        elif dom in ("rent", "banking"):
            if any(bad in p_low for bad in ["ppc", "489-f", "489f", "crpc", "penal code", "criminal procedure", "sra", "specific relief", "article 57", "article 58", "article 62", "article 64"]):
                continue
        elif dom == "corporate":
            if any(bad in p_low for bad in ["sra", "specific relief", "family courts", "mflo", "gwa", "prpa", "article 57", "article 58"]):
                continue
            if any(bad in p_low for bad in ["420", "415"]) and not any(k in p_low for k in ["409", "companies"]):
                continue
        elif dom == "service":
            if any(bad in p_low for bad in ["ppc", "489-f", "489f", "sra", "specific relief", "family courts", "mflo", "gwa", "prpa", "fio", "article 57", "article 58"]):
                continue
        elif dom == "constitutional":
            if any(bad in p_low for bad in ["489-f", "489f", "sra", "specific relief", "prpa", "fio", "family courts"]):
                continue
        elif dom in ("cybercrime", "intellectual_property"):
            if any(bad in p_low for bad in ["family courts", "mflo", "gwa", "prpa", "fio", "sra", "specific relief"]):
                continue
        elif dom == "criminal":
            if any(bad in p_low for bad in ["sra", "specific relief", "guardians and wards", "family courts act", "mflo", "prpa", "fio", "article 57", "article 58", "article 62", "article 64"]):
                continue
        elif dom == "civil":
            if any(bad in p_low for bad in ["crpc", "497", "498", "496", "489-f", "489f"]):
                continue
        clean.append(p_str)
    return clean


def create_deterministic_fallback_plan(query: str) -> StructuredLegalQueryPlan:
    """
    Robust rule-based fallback and classification engine.
    Extracts:
    - primary_domain, secondary_domains, subdomains
    - allowed_domains_filter for vector and PostgreSQL metadata quarantine
    - is_cross_domain_relevant, cross_domain_reason, cross_domain_controlling_doctrines
    - is_ambiguous, ambiguity_reasons, clarification_options
    - procedural_remedy, competent_forum, target_province
    - search_lanes, premise_corrections, statutory_provisions
    """
    q_low = query.lower()
    anchors = extract_positive_query_anchors(query)
    decomposed = decompose_compound_legal_query(query)
    premise_checks = check_query_premises(query)
    premise_corrections: List[Dict[str, Any]] = [
        c for c in premise_checks if c["status"] in ("CONFIRMED_ABSENT", "UNVERIFIED")
    ]

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

    # 2. Domain and Subdomain Identification
    primary_domain: LegalDomainType = "civil"
    secondary_domains: List[LegalDomainType] = []
    subdomains: List[str] = []
    legacy_domains: List[str] = []
    legacy_matter_type: List[str] = []
    questions: List[str] = []
    is_cross_domain_relevant = False
    cross_domain_reason: Optional[str] = None
    cross_domain_controlling_doctrines: List[str] = []
    is_ambiguous = False
    ambiguity_reasons: List[str] = []
    clarification_options: List[Dict[str, Any]] = []

    # Domain Flags
    is_civil_execution = (
        any(k in q_low for k in ["judgment debtor", "execution of decree", "money decree", "order xxi", "section 55", "warrant of arrest against judgment debtor", "civil prison", "executing court"])
        and not any(k in q_low for k in ["fir", "police station", "remand", "challan", "post-arrest bail", "pre-arrest bail"])
    )
    is_land_revenue = any(k in q_low for k in [
        "land revenue", "mutation", "intiqal", "record of rights", "jamabandi",
        "revenue officer", "patwari", "revenue court", "partition of agricultural",
        "section 42 land revenue", "section 135 land revenue", "section 172 land revenue",
        "illegal dispossession act", "land grabber", "illegal dispossession"
    ])
    is_partition = any(k in q_low for k in ["partition", "co-sharer", "co-owner", "hotchpot", "joint property", "joint ancestral", "order xx rule 18", "partition act", "order viii rule 6", "metes and bounds"])
    is_benami = any(k in q_low for k in ["benami", "ostensible owner", "benamidar", "advancement"])
    is_quashment = (
        any(k in q_low for k in ["quashment", "quash", "quashing", "561-a", "561a"])
        or (("fir" in q_low or "criminal" in q_low) and any(k in q_low for k in ["quash", "561"]))
    )
    is_bail = (
        (any(k in q_low for k in ["pre-arrest bail", "pre arrest bail", "post-arrest bail", "post arrest bail", "anticipatory bail"]) or ("bail" in q_low and any(k in q_low for k in ["496", "497", "498", "arrest", "custody", "fir", "non-bailable"])))
        and not is_civil_execution
    )
    is_corporate = (
        any(k in q_low for k in ["companies act", "company law", "section 286", "section 288", "oppression", "mismanagement", "minority shareholder", "company bench", "secp"])
        or (
            any(k in q_low for k in ["director", "board of directors", "majority director", "managing director", "shareholder"])
            and any(k in q_low for k in ["siphoning", "siphon", "allotment of shares", "issuing shares", "agm", "eogm", "company assets", "corporate assets"])
        )
    )
    is_commercial_crime = (
        any(k in q_low for k in ["405", "406", "409", "420", "breach of trust", "cheating", "misappropriat", "fiduciary", "entrustment", "forgery", "468", "471"])
        and any(k in q_low for k in ["contract", "commercial", "agreement", "loan", "civil dispute", "business", "power of attorney", "pending civil", "civil court", "civil suit", "recovery", "same agreement"])
        and not (is_land_revenue or is_corporate or is_civil_execution)
    )
    is_rent = bool(re.search(r'\b(?:rent|rented|tenan[ct]|landlord|evict|ejectment|tenancy|commercial shop|rent tribunal)\b', q_low) or any(k in q_low for k in ["prpa", "srpo"]))
    is_banking = any(k in q_low for k in ["banking court", "bank", "financial institution", "recovery of finance", "fio", "firo"]) and any(k in q_low for k in ["decree", "appeal", "loan", "finance", "stay", "deposit", "leave to defend", "banking", "section 22", "section 10"])
    is_habeas_corpus = any(k in q_low for k in ["habeas corpus", "unlawful detention", "illegal detention", "detenue", "without production"])
    is_cybercrime = any(k in q_low for k in ["peca", "cybercrime", "cyber crime", "hacking", "cyberstalking", "cyber stalking", "online harassment", "identity theft", "electronic crimes", "unauthorized access to secure"])
    is_ip = any(k in q_low for k in ["trademark", "trade mark", "passing off", "copyright", "software piracy", "pirated software"])
    is_service = any(k in q_low for k in ["civil servant", "service tribunal", "seniority list", "superseded in promotion", "promotion eligibility", "reversion", "civil servants act", "peeda", "removal from service", "dismissal from service", "article 212", "service tribunals act"])
    is_constitutional_general = any(k in q_low for k in ["article 199", "article 184", "article 189", "article 201", "writ petition", "writ of", "fundamental right", "mandamus", "certiorari", "public interest litigation"])
    is_family = (
        any(k in q_low for k in ["khula", "dower", "maintenance", "guardian", "custody of minor", "talaq", "mflo", "zar-i-khula", "family court", "hizanat", "guardians and wards"])
        or ("family" in q_low and not any(k in q_low for k in ["land", "property", "partition", "estate", "ancestral", "share", "heir"]))
    )
    is_female_inheritance = any(k in q_low for k in ["female heir", "female legal heir", "female co-heir", "sister", "daughter", "mother", "sister's share", "refusing sister"]) and any(k in q_low for k in ["inheritance", "tamleek", "relinquishment", "mutation", "shari share", "depriv", "estate", "women's property", "498-a", "498a"])
    is_cheque_dishonour = (
        (
            any(k in q_low for k in ["cheque", "check", "489-f", "489f"])
            and any(k in q_low for k in ["dishonour", "dishonored", "bounced", "unpaid", "return memo", "insufficient", "138"])
        )
        or any(k in q_low for k in ["dishonestly issuing a cheque", "bounced cheque", "dishonoured cheque", "dishonored cheque"])
    ) and not (is_family or is_service or is_rent or is_corporate or is_land_revenue or is_civil_execution)
    is_sec12_2 = (
        any(k in q_low for k in ["12(2)", "section 12(2)", "12 (2)", "decree obtained through fraud", "fraudulent decree", "setting aside decree", "set aside decree", "decree by fraud", "decree through fraud"])
        or (
            "decree" in q_low
            and any(k in q_low for k in ["fraud", "misrepresentation", "mis-representation", "collusion", "want of jurisdiction", "without jurisdiction", "void decree", "nullity"])
            and not (is_civil_execution or is_land_revenue or is_corporate)
        )
    )
    is_execution = any(k in q_low for k in ["order xxi", "execution of decree", "objection petition", "rule 97", "rule 103"]) or is_civil_execution
    is_specific_perf = (
        (
            any(k in q_low for k in ["sale deed", "agreement to sell", "specific performance", "advance money", "earnest money", "token money"])
            or (any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and any(k in q_low for k in ["sale", "deed", "refused", "money", "property"]))
        )
        and not (is_rent or is_banking or is_family or is_service or is_corporate or is_land_revenue or is_civil_execution)
    )
    is_adverse_possession = any(k in q_low for k in ["adverse possession", "hostile possession", "ouster", "extinguishment of title"]) or ("section 28" in q_low and "limitation" in q_low) or ("article 144" in q_low and "limitation" in q_low) or ("article 149" in q_low and "limitation" in q_low)
    is_money_recovery = (
        any(k in q_low for k in ["recovery of money", "money suit", "suit for money", "debt", "loan", "price of goods", "suit for recovery"])
        and not is_rent
        and not is_banking
        and not is_civil_execution
        and not any(k in q_low for k in [
            "recovery of possession", "possession from tenant", "recovery of stolen",
            "recovery of vehicle", "recovery of child", "custody", "arrears of pension",
            "pension", "dower", "unpaid dower", "arrears of rent"
        ])
    )

    # Classification Logic
    if is_habeas_corpus:
        primary_domain = "constitutional"
        secondary_domains = ["criminal"]
        subdomains = ["habeas_corpus", "illegal_detention", "article_199", "crpc_61"]
        legacy_domains = ["constitutional law", "criminal procedure"]
        legacy_matter_type = ["constitutional", "criminal"]
        allowed_domains_filter = ["constitutional", "criminal"]
        procedural_remedy = "Writ of Habeas Corpus under Article 199(1)(b)(i) Constitution 1973"
        competent_forum = "High Court"

    elif is_service:
        primary_domain = "service"
        secondary_domains = ["constitutional"]
        subdomains = ["service_tribunal", "civil_servant", "article_212_bar", "seniority_promotion"]
        legacy_domains = ["service law", "constitutional law"]
        legacy_matter_type = ["service", "constitutional"]
        is_cross_domain_relevant = True
        cross_domain_reason = "Service matters of civil servants fall under exclusive jurisdiction of Service Tribunal barred by Article 212 Constitution."
        allowed_domains_filter = ["service", "constitutional"]
        procedural_remedy = "Appeal before Service Tribunal under s.4 Service Tribunals Act 1973"
        competent_forum = "Federal Service Tribunal / Provincial Service Tribunal"

    elif is_cybercrime:
        primary_domain = "cybercrime"
        secondary_domains = ["criminal"]
        subdomains = ["peca", "cyber_offences", "unauthorized_access", "online_harassment"]
        legacy_domains = ["cybercrime", "criminal law"]
        legacy_matter_type = ["cybercrime", "criminal"]
        allowed_domains_filter = ["cybercrime", "criminal"]
        procedural_remedy = "Complaint before FIA Cyber Crime Wing / Special Court under PECA 2016"
        competent_forum = "Court of Session / Special Court (PECA)"

    elif is_ip:
        primary_domain = "intellectual_property"
        secondary_domains = ["civil"]
        subdomains = ["trademark_infringement", "passing_off", "copyright_piracy"]
        legacy_domains = ["intellectual property", "civil law"]
        legacy_matter_type = ["commercial", "civil"]
        allowed_domains_filter = ["intellectual_property", "civil"]
        procedural_remedy = "Suit for Infringement & Injunction under Trade Marks Ordinance 2001 / Copyright Ordinance 1962"
        competent_forum = "District Court / Intellectual Property Tribunal"

    elif is_civil_execution:
        primary_domain = "civil"
        subdomains = ["execution_of_decree", "arrest_of_judgment_debtor", "section_55_cpc", "order_xxi"]
        legacy_domains.append("general civil law / execution")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Show Cause Notice & Execution of Money Decree under Section 55 & Order XXI Rule 37 CPC"
        competent_forum = "Executing Court / Civil Court"

    elif is_land_revenue:
        primary_domain = "civil"
        secondary_domains = []
        subdomains = ["land_revenue", "mutation_challenge", "revenue_record", "section_42_land_revenue"]
        legacy_domains.extend(["civil property", "land revenue"])
        legacy_matter_type.extend(["civil", "land_revenue"])
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Suit for Declaration & Cancellation of Mutation (s.42 SRA 1877 / s.42 Land Revenue Act 1967)"
        competent_forum = "Civil Court / Revenue Officer (Collector / Commissioner)"

    elif is_quashment:
        primary_domain = "criminal"
        subdomains = ["quashment_of_fir", "inherent_powers_561a", "abuse_of_process"]
        has_civil_suit_aspect = any(k in q_low for k in ["pending civil", "civil suit", "civil court", "same agreement", "contractual dispute"])
        if has_civil_suit_aspect:
            secondary_domains = ["civil"]
            subdomains.extend(["civil_vs_criminal", "pending_civil_suit_quashment"])
            legacy_domains.extend(["criminal law", "civil dispute"])
            legacy_matter_type.extend(["criminal", "civil"])
            is_cross_domain_relevant = True
            cross_domain_reason = "Quashment of criminal proceedings under Section 561-A CrPC where civil proceedings/suit on the same subject matter are pending."
            cross_domain_controlling_doctrines = ["mens_rea_at_inception", "civil_dispute_quashment_406_420"]
            allowed_domains_filter = ["criminal", "civil"]
        else:
            secondary_domains = []
            if is_cheque_dishonour:
                subdomains.extend(["489f_quashment", "civil_nature_cheque"])
                legacy_domains.append("criminal quashment & cheque dishonour")
            else:
                legacy_domains.append("criminal quashment")
            legacy_matter_type.append("criminal")
            is_cross_domain_relevant = False
            allowed_domains_filter = ["criminal"]
        procedural_remedy = "Criminal Miscellaneous Petition for Quashment of FIR under Section 561-A Cr.P.C."
        competent_forum = "High Court"

    elif is_benami:
        primary_domain = "civil"
        subdomains = ["benami", "property", "ostensible_owner"]
        if is_partition:
            subdomains.extend(["partition", "co_ownership"])
            legacy_domains.append("partition & property")
        else:
            legacy_domains.append("benami & property")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Suit for Declaration of Title & Partition (Order XX Rule 18 CPC / s.42 SRA 1877)"
        competent_forum = "Civil Court / District Judge"

    elif is_partition:
        primary_domain = "civil"
        subdomains = ["property", "partition", "co_ownership"]
        legacy_domains.append("partition & property")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Suit for Partition and Separate Possession (Order XX Rule 18 CPC)"
        competent_forum = "Civil Court / District Judge"

    elif is_corporate:
        primary_domain = "corporate"
        subdomains = ["oppression_and_mismanagement", "minority_shareholders", "section_286"]
        legacy_domains.append("oppression & mismanagement")
        legacy_matter_type.append("corporate")
        if any(k in q_low for k in ["409", "misappropriat", "funds", "ppc", "crime", "siphon", "breach of trust", "embezzle", "forgery"]):
            secondary_domains = ["criminal", "civil"]
            is_cross_domain_relevant = True
            cross_domain_reason = "Oppression under Companies Act involving misappropriation of corporate funds/shares and criminal breach of trust under Section 409 PPC."
            allowed_domains_filter = ["corporate", "criminal", "civil"]
        else:
            secondary_domains = ["civil"]
            is_cross_domain_relevant = False
            allowed_domains_filter = ["corporate", "civil"]
        procedural_remedy = "Company Petition under Section 286 Companies Act 2017"
        competent_forum = "Special Court / High Court Company Bench"

    elif is_rent:
        primary_domain = "rent"
        subdomains = ["eviction", "default_in_rent", "leave_to_defend", "prpa"]
        legacy_domains.append("rent restriction")
        legacy_matter_type.append("rent")
        if any(k in q_low for k in ["cheque", "bounced", "dishonour", "489"]):
            secondary_domains = ["criminal", "civil"]
            is_cross_domain_relevant = True
            cross_domain_reason = "Concurrent civil eviction under PRPA 2009 and criminal prosecution under Section 489-F PPC for bounced rent cheques."
            allowed_domains_filter = ["rent", "criminal", "civil"]
        else:
            secondary_domains = ["civil"]
            is_cross_domain_relevant = False
            allowed_domains_filter = ["rent", "civil"]
        procedural_remedy = "Application for Eviction under Section 15 PRPA 2009"
        competent_forum = "Special Judge (Rent) / Rent Tribunal"

    elif is_commercial_crime:
        primary_domain = "criminal"
        secondary_domains = ["civil"]
        subdomains = ["commercial_fraud", "breach_of_trust", "contractual_breach"]
        legacy_domains.extend(["criminal law", "corporate crime" if "company" in q_low or "director" in q_low else "commercial fraud"])
        legacy_matter_type.extend(["criminal", "civil"])
        is_cross_domain_relevant = True
        cross_domain_reason = (
            "Superior court precedents on Sections 406/420 PPC and Section 561-A CrPC establish "
            "the legal boundary distinguishing mere civil breach of contract/debt from criminal "
            "fraudulent intention at inception. Authorities across both criminal quashment/bail "
            "and civil contract law are reciprocally relevant."
        )
        cross_domain_controlling_doctrines = [
            "mens_rea_at_inception",
            "civil_dispute_quashment_406_420",
            "fiduciary_entrustment"
        ]
        allowed_domains_filter = ["criminal", "civil"]
        procedural_remedy = "Pre-arrest Bail (s.498 CrPC) / Quashment of FIR (s.561-A CrPC)"
        competent_forum = "Sessions Court / High Court"

    elif is_cheque_dishonour:
        primary_domain = "criminal"
        if any(k in q_low for k in ["guarantee", "security deposit", "civil", "recovery", "summary suit", "order 37", "oxxxvii", "concurrent", "simultaneous", "both"]):
            secondary_domains = ["civil"]
            subdomains = ["cheque_dishonour", "489f", "summary_suit_oxxxvii"]
            legacy_domains.extend(["criminal law", "cheque dishonour", "civil recovery"])
            legacy_matter_type.extend(["criminal", "civil"])
            is_cross_domain_relevant = True
            cross_domain_reason = (
                "Dishonour of cheques in Pakistan engages concurrent remedies: criminal penal prosecution "
                "under Section 489-F PPC and civil summary recovery under Order XXXVII CPC / Section 118 NI Act. "
                "Superior courts affirm both remedies proceed simultaneously."
            )
            cross_domain_controlling_doctrines = [
                "concurrent_civil_criminal_remedies",
                "presumption_under_s118_ni_act",
                "obligation_incurred_for_consideration"
            ]
            allowed_domains_filter = ["criminal", "civil"]
            procedural_remedy = "FIR under Section 489-F PPC & Summary Suit under Order XXXVII CPC"
            competent_forum = "Judicial Magistrate 1st Class (criminal) / Civil Court (summary suit)"
        else:
            secondary_domains = []
            subdomains = ["cheque_dishonour", "489f"]
            legacy_domains.append("criminal law")
            legacy_matter_type.append("criminal")
            is_cross_domain_relevant = False
            allowed_domains_filter = ["criminal"]
            procedural_remedy = "Criminal Prosecution under Section 489-F PPC"
            competent_forum = "Judicial Magistrate 1st Class / Sessions Court"

    elif is_female_inheritance:
        primary_domain = "civil"
        secondary_domains = ["family"]
        subdomains = ["inheritance", "tamleek", "fraudulent_relinquishment", "female_heir_rights"]
        legacy_domains.extend(["general civil law", "family law"])
        legacy_matter_type.extend(["civil", "family"])
        is_cross_domain_relevant = True
        cross_domain_reason = (
            "Islamic personal law inheritance rights (shari shares) intersect with civil remedies "
            "under Specific Relief Act 1877 for declaration and cancellation of fraudulent instruments."
        )
        cross_domain_controlling_doctrines = [
            "protection_of_female_inheritance",
            "burden_of_proof_in_tamleek",
            "nullity_of_fraudulent_relinquishment"
        ]
        allowed_domains_filter = ["civil", "family"]
        procedural_remedy = "Suit for Declaration and Cancellation of Instrument (Sections 39 & 42 SRA 1877)"
        competent_forum = "Civil Court / District Judge"

    elif is_service or (is_constitutional_general and any(k in q_low for k in ["employee", "service", "dismissal", "tribunal"])):
        primary_domain = "constitutional"
        secondary_domains = ["service"]
        subdomains = ["service_tribunal", "civil_servant", "article_212_bar", "writ_maintainability"]
        legacy_domains.extend(["constitutional law", "service law"])
        legacy_matter_type.extend(["constitutional", "service"])
        is_cross_domain_relevant = True
        cross_domain_reason = (
            "Constitutional writ jurisdiction under Article 199 is barred by Article 212 for civil "
            "servants whose exclusive remedy is departmental appeal followed by appeal before the "
            "Service Tribunal under Section 4 Service Tribunals Act 1973."
        )
        cross_domain_controlling_doctrines = [
            "article_212_constitutional_ouster",
            "exhaustion_of_departmental_remedies",
            "master_and_servant_doctrine"
        ]
        allowed_domains_filter = ["constitutional", "service"]
        procedural_remedy = "Departmental Appeal -> Service Tribunal Appeal under s.4 STA / Constitutional Writ under Art. 199 (conditional)"
        competent_forum = "Service Tribunal / High Court"

    elif is_family:
        primary_domain = "family"
        subdomains = ["dissolution_of_marriage", "khula", "dower", "custody", "maintenance"]
        legacy_domains.append("family law")
        legacy_matter_type.append("family")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["family"]
        procedural_remedy = "Suit for Dissolution of Marriage (Khula) / Maintenance / Custody Petition"
        competent_forum = "Family Court / Guardian Judge"

    elif is_rent:
        primary_domain = "rent"
        subdomains = ["eviction", "default_in_rent", "leave_to_defend", "prpa"]
        legacy_domains.append("rent restriction")
        legacy_matter_type.append("rent")
        if any(k in q_low for k in ["cheque", "bounced", "489"]):
            secondary_domains = ["criminal", "civil"]
            is_cross_domain_relevant = True
            cross_domain_reason = "Concurrent civil eviction under PRPA 2009 and criminal prosecution under Section 489-F PPC for bounced rent cheques."
            allowed_domains_filter = ["rent", "criminal", "civil"]
        else:
            secondary_domains = ["civil"]
            is_cross_domain_relevant = False
            allowed_domains_filter = ["rent", "civil"]
        procedural_remedy = "Application for Eviction under Section 15 PRPA 2009"
        competent_forum = "Special Judge (Rent) / Rent Tribunal"

    elif is_banking:
        primary_domain = "banking"
        secondary_domains = ["civil"]
        subdomains = ["recovery_of_finances", "leave_to_defend", "section_22_appeal"]
        legacy_domains.append("banking recovery")
        legacy_matter_type.append("commercial")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["banking", "civil"]
        procedural_remedy = "Suit for Recovery under s.9 FIO 2001 / Appeal under s.22 FIO 2001"
        competent_forum = "Banking Court / High Court (Appellate Division)"

    elif is_corporate:
        primary_domain = "corporate"
        subdomains = ["oppression_and_mismanagement", "minority_shareholders", "section_286"]
        legacy_domains.append("oppression & mismanagement")
        legacy_matter_type.append("corporate")
        if any(k in q_low for k in ["409", "director", "misappropriat", "funds"]):
            secondary_domains = ["criminal", "civil"]
            is_cross_domain_relevant = True
            cross_domain_reason = "Oppression under s.286 Companies Act 2017 involving misappropriation of corporate funds and criminal breach of trust under s.409 PPC."
            allowed_domains_filter = ["corporate", "criminal", "civil"]
        else:
            secondary_domains = ["civil"]
            is_cross_domain_relevant = False
            allowed_domains_filter = ["corporate", "civil"]
        procedural_remedy = "Company Petition under Section 286 Companies Act 2017"
        competent_forum = "Special Court / High Court Company Bench"

    elif not is_civil_execution and (is_bail or any(k in q_low for k in ["fir", "arrest", "accused", "police", "custody", "murder", "302", "ppc", "crpc"])):
        primary_domain = "criminal"
        if "pre-arrest" in q_low or "pre arrest" in q_low or "anticipatory bail" in q_low:
            subdomains = ["bail", "pre_arrest_bail"]
            legacy_domains.extend(["criminal law", "pre-arrest bail"])
        elif any(k in q_low for k in ["post-arrest", "post arrest", "arrested", "in custody", "in jail", "without a warrant", "without warrant"]):
            subdomains = ["bail", "post_arrest_bail"]
            legacy_domains.extend(["criminal law", "post-arrest bail"])
        else:
            subdomains = ["bail", "criminal_procedure"]
            legacy_domains.extend(["criminal law", "bail"])
        legacy_matter_type.append("criminal")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["criminal"]
        procedural_remedy = "Bail Application under Section 497/498 CrPC"
        competent_forum = "Magistrate 1st Class / Sessions Court / High Court"

    elif is_constitutional_general:
        primary_domain = "constitutional"
        subdomains = ["judicial_precedent", "original_jurisdiction", "fundamental_rights", "writ_jurisdiction"]
        legacy_domains.append("constitutional law")
        legacy_matter_type.append("constitutional")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["constitutional"]
        procedural_remedy = "Constitutional Petition under Article 199 / 184(3)"
        competent_forum = "High Court / Supreme Court of Pakistan"

    elif is_sec12_2:
        primary_domain = "civil"
        subdomains = ["procedure", "section_12_2", "fraudulent_decree", "locus_standi"]
        legacy_domains.append("general civil law")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Application under Section 12(2) CPC"
        competent_forum = "Court which passed the final decree"

    elif is_execution:
        primary_domain = "civil"
        subdomains = ["execution", "order_xxi", "objection_petition", "third_party_rights"]
        legacy_domains.append("general civil law")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Objection Petition under Order XXI Rule 97/99 CPC"
        competent_forum = "Executing Court / Civil Court"

    elif is_specific_perf:
        primary_domain = "civil"
        subdomains = ["contract", "specific_performance", "sale_deed", "property"]
        legacy_domains.append("specific performance & contract")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Suit for Specific Performance of Agreement to Sell (s.12 SRA 1877)"
        competent_forum = "Civil Court / District Judge"

    elif is_adverse_possession:
        primary_domain = "civil"
        subdomains = ["property", "adverse_possession", "limitation"]
        legacy_domains.append("civil property")
        legacy_matter_type.append("civil")
        is_cross_domain_relevant = False
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Suit for Declaration of Title based on Adverse Possession"
        competent_forum = "Civil Court / District Judge"

    else:
        primary_domain = "civil"
        subdomains = ["general_civil"]
        legacy_domains.append("general civil law")
        legacy_matter_type.append("civil")
        allowed_domains_filter = ["civil"]
        procedural_remedy = "Civil Suit / Legal Notice"
        competent_forum = "Civil Court / District Judge"

    # Ambiguity Check
    if ("limitation period for filing an appeal" in q_low or ("limitation" in q_low and "appeal" in q_low and not any(k in q_low for k in ["cpc", "crpc", "fio", "prpa", "service", "banking", "rent", "financial institutions", "ordinance"]))):
        is_ambiguous = True
        ambiguity_reasons.append("Query does not specify whether the appeal arises from a civil suit, criminal conviction, banking court decree, rent tribunal eviction order, or service tribunal.")
        clarification_options = [
            {"branch": "Civil Appeal", "statute": "CPC 1908 (ss. 96, 100) / Limitation Act 1908", "forum": "District Court (30 days) / High Court (90 days)"},
            {"branch": "Criminal Appeal", "statute": "CrPC 1898 (ss. 417, 419)", "forum": "Court of Session (30 days) / High Court (30/60 days)"},
            {"branch": "Banking Appeal", "statute": "Section 22 FIO 2001", "forum": "High Court Appellate Division (30 days with mandatory 50% deposit)"},
            {"branch": "Rent Eviction Appeal", "statute": "Section 24 PRPA 2009", "forum": "District Judge / Appellate Court (30 days)"},
            {"branch": "Service Tribunal Appeal", "statute": "Section 4 Service Tribunals Act 1973", "forum": "Federal/Provincial Service Tribunal (30 days after departmental rejection)"}
        ]
        allowed_domains_filter = ["civil", "criminal", "banking", "rent", "service"]

    elif (("stay order" in q_low or "interim injunction" in q_low) and not any(k in q_low for k in ["cpc", "order xxxix", "39", "rent", "writ", "199", "suit", "property", "eviction"])):
        is_ambiguous = True
        ambiguity_reasons.append("Query does not specify the court or proceeding for the stay order (civil interim injunction Order XXXIX, criminal suspension under s.561-A, or High Court writ stay under Article 199).")
        clarification_options = [
            {"branch": "Civil Suit Temporary Injunction", "statute": "Order XXXIX Rules 1 & 2 CPC", "forum": "Civil Court"},
            {"branch": "Constitutional Writ Interim Stay", "statute": "Article 199 Constitution of Pakistan", "forum": "High Court"},
            {"branch": "Criminal Proceedings Stay", "statute": "Section 561-A CrPC", "forum": "High Court"}
        ]
        allowed_domains_filter = ["civil", "constitutional", "criminal"]

    elif ("court review its own" in q_low or "review its own decision" in q_low) and not any(k in q_low for k in ["cpc", "114", "47", "xlvii", "supreme court", "188", "crpc"]):
        is_ambiguous = True
        ambiguity_reasons.append("Query does not distinguish between Civil Court review under Section 114/Order XLVII CPC, Supreme Court constitutional review under Article 188, or Criminal Court bar on review under Section 369 CrPC.")
        clarification_options = [
            {"branch": "Civil Review", "statute": "Section 114 / Order XLVII Rule 1 CPC", "forum": "Civil / High Court"},
            {"branch": "Supreme Court Review", "statute": "Article 188 Constitution of Pakistan", "forum": "Supreme Court of Pakistan"},
            {"branch": "Criminal Law Review Bar", "statute": "Section 369 CrPC (Strict bar on review of judgment once signed)", "forum": "Criminal Courts"}
        ]
        allowed_domains_filter = ["civil", "constitutional", "criminal"]

    elif any(k in q_low for k in ["cheque bounce", "dishonoured cheque", "dishonored cheque", "bounced cheque"]) and not any(k in q_low for k in ["489", "order 37", "order xxxvii", "fio", "financial institution", "summary suit"]):
        is_ambiguous = True
        ambiguity_reasons.append("Query does not specify whether you are pursuing a criminal prosecution or a civil summary recovery for the dishonoured cheque.")
        clarification_options = [
            {"branch": "Criminal Prosecution", "statute": "Section 489-F Pakistan Penal Code, 1860", "forum": "Criminal Magistrate / Police FIR"},
            {"branch": "Summary Civil Suit on Negotiable Instrument", "statute": "Order XXXVII Rules 1 & 2 Code of Civil Procedure, 1908", "forum": "District Court / Civil Court"},
            {"branch": "Banking Recovery (Customer/Bank)", "statute": "Financial Institutions (Recovery of Finances) Ordinance, 2001", "forum": "Banking Court"}
        ]
        allowed_domains_filter = ["criminal", "civil", "banking"]

    # 3. Governing Statutes
    statutes: List[str] = []
    if any(k in q_low for k in ["cpc", "order xxxix", "civil procedure", "sec 9", "review its own", "court review", "order xxi", "12(2)", "order xx", "order viii"]):
        statutes.append("Code of Civil Procedure, 1908")
    if any(k in q_low for k in ["companies act", "company law", "section 286", "section 288", "oppression", "mismanagement", "minority shareholder"]):
        statutes.append("Companies Act, 2017")
        if any(k in q_low for k in ["1984", "ordinance", "predecessor"]):
            statutes.append("Companies Ordinance, 1984")
    if any(k in q_low for k in ["limitation", "sec 28", "art 144", "art 149", "article 113", "article 120"]):
        statutes.append("Limitation Act, 1908")
    if any(k in q_low for k in ["specific relief", "injunction", "sec 42", "sec 9 sra", "sra", "declaration"]):
        statutes.append("Specific Relief Act, 1877")
    if is_rent or any(k in q_low for k in ["prpa", "punjab rented", "rent", "tenant", "evict", "eviction"]):
        if province == "Punjab":
            statutes.append("Punjab Rented Premises Act, 2009")
        elif province == "Sindh":
            statutes.append("Sindh Rented Premises Ordinance, 1979")
        else:
            statutes.append("Punjab Rented Premises Act, 2009")
    if primary_domain == "criminal" or "criminal" in secondary_domains or any(k in q_low for k in ["ppc", "penal code", "409", "420", "406", "489", "cheque", "dishonour", "bounced", "prosecute", "murder"]):
        if "Pakistan Penal Code, 1860" not in statutes:
            statutes.append("Pakistan Penal Code, 1860")
        if "Code of Criminal Procedure, 1898" not in statutes:
            statutes.append("Code of Criminal Procedure, 1898")
    if is_banking or any(k in q_low for k in ["banking court", "financial institution", "recovery of finance", "fio", "firo"]):
        statutes.append("Financial Institutions (Recovery of Finances) Ordinance, 2001")
    if is_partition or is_benami:
        for part_s in ["Partition Act, 1893", "Code of Civil Procedure, 1908", "Specific Relief Act, 1877", "Benami Transactions (Prohibition) Act, 2017", "Transfer of Property Act, 1882", "Limitation Act, 1908"]:
            if part_s not in statutes:
                statutes.append(part_s)
    if is_specific_perf:
        for sp_stat in ["Specific Relief Act, 1877", "Contract Act, 1872", "Transfer of Property Act, 1882", "Code of Civil Procedure, 1908", "Limitation Act, 1908"]:
            if sp_stat not in statutes:
                statutes.append(sp_stat)
    if is_family:
        for fam_stat in ["Family Courts Act, 1964", "Muslim Family Laws Ordinance, 1961", "Guardians and Wards Act, 1890", "Dissolution of Muslim Marriages Act, 1939"]:
            if fam_stat not in statutes:
                statutes.append(fam_stat)
    if is_service or is_constitutional_general:
        if "Constitution of the Islamic Republic of Pakistan, 1973" not in statutes:
            statutes.append("Constitution of the Islamic Republic of Pakistan, 1973")
        if is_service and "Service Tribunals Act, 1973" not in statutes:
            statutes.append("Service Tribunals Act, 1973")
    if any(k in q_low for k in ["qso", "qanun-e-shahadat", "evidence", "proof", "presumption", "tamleek", "benami"]):
        if "Qanun-e-Shahadat Order, 1984" not in statutes:
            statutes.append("Qanun-e-Shahadat Order, 1984")

    # 4. Provisions Identification
    provisions: List[str] = []

    # Priority 1: Canonical detection from unified statute currency
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

    # Priority 2: Regex extraction
    sec_matches = re.findall(r'(?<![a-zA-Z0-9])(?:sections?|secs?\.?|ss\.?|s\.)\s*([0-9]+(?:-[a-z])?(?:\s*(?:and|&|,)\s*[0-9]+(?:-[a-z])?)*)\s*(ppc|crpc|cpc|qso|sra|fio)?', q_low)
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
                if num_int in [405, 406, 409, 420, 489, 302, 376, 380, 468, 471, 324, 34, 109]:
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
                elif is_rent:
                    stat_suffix = "PRPA" if province == "Punjab" else "SRPO"
                elif is_banking:
                    stat_suffix = "Financial Institutions (Recovery of Finances) Ordinance 2001"
                else:
                    stat_suffix = ""

            if stat_suffix == "PPC" and clean_digit and int(clean_digit) > 511:
                continue

            prov_str = f"Section {num} {stat_suffix}".strip() if stat_suffix else f"Section {num}"
            already_covered = any(f"section {num} " in p.lower() or p.lower() == f"section {num}" for p in provisions)
            if not already_covered and prov_str not in provisions:
                provisions.append(prov_str)

    # Doctrinal provision detection
    if is_banking:
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
        m_yr = re.search(r'(18\d\d|19\d\d|20\d\d)', a)
        if m_yr:
            continue
        m_sec = re.search(r'section\s*([0-9]+(?:-[a-z])?)', a.lower())
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

    # Mandatory provision inclusions per domain
    if is_bail:
        for bp in ["Section 496 CrPC", "Section 497 CrPC", "Section 498 CrPC"]:
            if not any(bp.split()[1] in p for p in provisions):
                provisions.append(bp)
        if any(k in q_low for k in ["without warrant", "without a warrant", "arrest without"]):
            for ap in ["Section 54 CrPC", "Section 61 CrPC"]:
                if not any(ap.split()[1] in p for p in provisions):
                    provisions.append(ap)

    if is_quashment:
        if not any("561" in p for p in provisions):
            provisions.insert(0, "Section 561A CrPC")
        if is_cheque_dishonour and not any("489" in p for p in provisions):
            provisions.append("Section 489-F PPC")

    elif is_cheque_dishonour:
        if not any("489" in p for p in provisions):
            provisions.append("Section 489-F PPC")

    if is_money_recovery:
        for default_p in [
            "Article 57 Limitation Act",
            "Article 58 Limitation Act",
            "Article 64A Limitation Act",
            "Article 115 Limitation Act",
            "Article 62 Limitation Act",
            "Article 120 Limitation Act",
            "Section 3 Limitation Act"
        ]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)
        # Section 5 Limitation Act applies only to appeals/applications, NOT original suits
        if not any(k in q_low for k in ["appeal", "revision", "review", "condonation", "sufficient cause"]):
            provisions = [p for p in provisions if not ("section 5" in p.lower() and "limitation" in p.lower())]

    if is_adverse_possession:
        for default_p in ["Section 28 Limitation Act", "Article 144 Limitation Act", "Article 149 Limitation Act"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)

    if "review" in q_low and any(k in q_low for k in ["cpc", "civil procedure", "court review its own", "review its own decision", "review of judgment", "order xlvii", "order 47", "own decision"]):
        if not any("114" in p for p in provisions):
            provisions.append("Section 114 CPC")
        if not any("xlvii" in p.lower() or "47" in p for p in provisions):
            provisions.append("Order XLVII Rule 1 CPC")

    if is_corporate:
        for cp in ["Section 286 Companies Act 2017", "Section 287 Companies Act 2017", "Section 288 Companies Act 2017"]:
            if not any(cp.split()[1] in p for p in provisions):
                provisions.append(cp)

    if any(k in q_low for k in ["injunction", "order xxxix", "o.xxxix", "o.39"]):
        for default_p in ["Order XXXIX Rule 1 CPC", "Order XXXIX Rule 2 CPC", "Order XLIII Rule 1(r) CPC", "Section 115 CPC"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)

    if is_rent:
        if province == "Punjab":
            for default_p in ["Section 4 PRPA 2009", "Section 15 PRPA 2009", "Section 22 PRPA 2009", "Section 34 PRPA 2009"]:
                if not any(default_p.split()[1] in p for p in provisions):
                    provisions.append(default_p)

    if is_specific_perf:
        for sp_p in [
            "Section 12 Specific Relief Act, 1877",
            "Section 53A Transfer of Property Act, 1882",
            "Section 73 Contract Act, 1872",
            "Order XXXIX Rule 1 CPC",
            "Article 113 Limitation Act, 1908"
        ]:
            if not any(sp_p.lower() == p.lower() for p in provisions):
                provisions.append(sp_p)

    if is_partition or is_benami:
        for part_p in [
            "Order XX Rule 18 CPC",
            "Order VIII Rule 6 CPC",
            "Order VIII Rule 6-A CPC",
            "Section 4 Partition Act, 1893",
            "Section 42 Specific Relief Act, 1877",
            "Section 66 Transfer of Property Act, 1882",
            "Order XXVI Rule 13 CPC",
            "Article 120 Limitation Act, 1908"
        ]:
            if not any(part_p.lower() == p.lower() for p in provisions):
                provisions.append(part_p)

    if is_benami:
        if not any("section 4" in p.lower() and "benami" in p.lower() for p in provisions):
            provisions.append("Section 4 Benami Transactions (Prohibition) Act, 2017")

    if is_family:
        for fam_p in [
            "Section 5 Family Courts Act, 1964",
            "Section 10 Family Courts Act, 1964",
            "Section 9 Muslim Family Laws Ordinance, 1961"
        ]:
            if not any(fam_p.lower() == p.lower() for p in provisions):
                provisions.append(fam_p)

    if is_service:
        for default_p in ["Article 212 Constitution", "Section 4 Service Tribunals Act 1973", "Article 199(1) Constitution"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)

    if is_sec12_2:
        if not any("12(2)" in p for p in provisions):
            provisions.append("Section 12(2) CPC")
        if not any("181" in p for p in provisions):
            provisions.append("Article 181 Limitation Act, 1908")
        if "appeal" in q_low and not any("96" in p for p in provisions):
            provisions.append("Section 96 CPC")

    if is_execution:
        for ex_p in ["Order XXI Rule 97 CPC", "Order XXI Rule 103 CPC"]:
            if not any(ex_p.lower() in p.lower() for p in provisions):
                provisions.append(ex_p)

    # Premise correction routing
    for check in premise_checks:
        if check["status"] == "CONFIRMED_ABSENT":
            q_stat = str(check.get("queried_statute") or "")
            q_prov = str(check.get("queried_provision") or "")
            clean_sec = re.sub(r'[^0-9a-z]', '', q_prov.lower())
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

            elif "2a" in q_prov.lower() or "2-a" in q_prov.lower() or ("cpc" in q_stat.lower() and "2" in q_prov.lower()):
                if not any("rule 2a" in p.lower() for p in provisions):
                    provisions.append("Order XXXIX Rule 2A CPC")
                if not any("rule 2(3)" in p.lower() for p in provisions):
                    provisions.append("Order XXXIX Rule 2(3) CPC")
                if "Code of Civil Procedure, 1908" not in statutes:
                    statutes.append("Code of Civil Procedure, 1908")

    if is_partition or is_benami:
        if any(k in q_low for k in ["set off", "set-off", "claim"]):
            premise_corrections.append({
                "queried_statute": "Code of Civil Procedure, 1908",
                "queried_provision": "Order VIII, Rule 6 & Rule 6-A",
                "status": "LEGALLY_INAPPLICABLE_PREMISE",
                "explanation": "Under Order VIII, Rule 6 CPC, legal set-off is restricted to suits for recovery of an ascertained sum of money. A claim of title or benami ownership cannot be pleaded as a mere money set-off. However, where plaintiff claims mesne profits (an ascertainable money sum), joint property maintenance/preservation expenses may legitimately be set off under Rule 6. Furthermore, under Order VIII Rule 6-A CPC, counter-claims are NOT restricted to money and may determine title in the suit property as an independent cross-suit. A partition court (Order XX Rule 18 CPC) has full competence to try questions of title before passing a preliminary decree."
            })
            if not any("order viii rule 6" in p.lower() for p in provisions):
                provisions.append("Order VIII Rule 6 CPC")
            if not any("order viii rule 6-a" in p.lower() for p in provisions):
                provisions.append("Order VIII Rule 6-A CPC")
            if not any("order xx rule 18" in p.lower() for p in provisions):
                provisions.append("Order XX Rule 18 CPC")
            questions.append("distinction between Order VIII Rule 6 money set-off and Order VIII Rule 6-A title counter-claim in partition proceedings")
            questions.append("jurisdiction of partition court under Order XX Rule 18 CPC to adjudicate disputed title before preliminary decree")

        if is_benami:
            premise_corrections.append({
                "queried_statute": "Benami Transactions (Prohibition) Act, 2017",
                "queried_provision": "Section 4(1), 4(2) & 4(3)",
                "status": "STATUTORILY_BARRED_DEFENCE",
                "explanation": "Under Section 4(1) of the Benami Transactions (Prohibition) Act, 2017, suits by real owners are barred, and under Section 4(2) defences by claimant real owners are barred, subject to Section 4(3) fiduciary/trustee exceptions. Crucially, the 2017 Act is strictly prospective under Supreme Court jurisprudence. For pre-2017 transactions, classic benami law applies: the onus probandi is strictly upon the party alleging benami (e.g. 2011 SCMR 1550, 2015 CLC 973, 2025 SCMR 2087), requiring affirmative proof of 4 ingredients: (1) source of consideration, (2) custody of title deeds, (3) possession, and (4) motive (Section 66 TPA). Any affirmative claim of title is also subject to the Limitation Act 1908 (Article 120)."
            })
            if not any("section 4" in p.lower() and "benami" in p.lower() for p in provisions):
                provisions.append("Section 4 Benami Transactions (Prohibition) Act, 2017")
            if not any("section 66" in p.lower() for p in provisions):
                provisions.append("Section 66 Transfer of Property Act, 1882")
            questions.append("prospective application of Benami Act 2017 vs classic 4-factor burden of proof on party alleging benami")
            questions.append("fiduciary capacity exception under Section 4(3) Benami Act 2017")
            questions.append("limitation under Article 120 Limitation Act 1908 for declaration of benami title")

    forum_hierarchy = ["Civil Court", "District Judge", "High Court", "Supreme Court of Pakistan"]
    employee_status_branching = None

    if is_service:
        forum_hierarchy = [
            "1. Departmental Appellate Authority (mandatory pre-condition under STA s.4)",
            "2. Federal or Provincial Service Tribunal (exclusive forum under Art. 212 for civil servants)",
            "3. High Court under Article 199 (competent ONLY for statutory body employees with statutory rules; strictly barred for civil servants)",
            "4. Supreme Court of Pakistan (Article 212(3) leave to appeal from Service Tribunal or Art. 185 appeal)"
        ]
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

    # Questions Generation
    if is_commercial_crime or any(k in q_low for k in ["civil", "criminal", "breach of trust", "loan"]):
        questions.append("civil dispute vs criminal breach of trust (dishonest intention at inception)")
    if any(k in q_low for k in ["409", "misappropriat"]) or ("director" in q_low and any(k in q_low for k in ["funds", "misappropriat", "breach of trust", "board", "shares", "fiduciary"])):
        questions.append("applicability of Section 409 PPC to company director managing corporate funds")
    if is_bail:
        if any(k in q_low for k in ["arrested", "in custody", "without a warrant", "without warrant", "post-arrest"]):
            questions.append("statutory distinction between bailable offences under Section 496 CrPC (mandatory right) vs non-bailable offences under Section 497 CrPC (judicial discretion)")
            questions.append("scope of prohibitory clause (punishable with death, life, or 10+ years) vs non-prohibitory clause (bail is rule, refusal exception per settled Supreme Court jurisprudence)")
        else:
            questions.append("grounds for pre-arrest bail under Section 498 CrPC (demonstration of mala fide, ulterior motive, and apprehension of imminent arrest)")
    if is_money_recovery:
        for default_p in ["Section 3 Limitation Act", "Article 62 Limitation Act", "Article 120 Limitation Act"]:
            if not any(default_p.split()[1] in p for p in provisions):
                provisions.append(default_p)

    if is_adverse_possession:
        questions.append("whether adverse possession can mature against Provincial Government under Section 28 Limitation Act")
        questions.append("statutory limitation period for Government recovery of land under Article 149 (60 years) vs Article 144")
    if is_sec12_2:
        questions.append("remedy under Section 12(2) CPC for setting aside decree obtained by fraud, misrepresentation, or want of jurisdiction")
        questions.append("limitation period under Article 181 Limitation Act 1908 (three years from discovery of fraud / accrual of right to apply)")
        if "appeal" in q_low:
            questions.append("distinction between Section 12(2) CPC application to decree-passing court vs regular appeal under Section 96 CPC")

    if "review" in q_low and any(k in q_low for k in ["cpc", "civil procedure", "court review its own", "review its own decision", "order xlvii", "own decision"]):
        questions.append("substantive power of civil court to review its own decree or order under Section 114 CPC")
        questions.append("statutory grounds for review under Order XLVII Rule 1 CPC (discovery of new and important matter or evidence, error apparent on face of record)")
    if is_corporate:
        questions.append("statutory qualification threshold and scope of relief under Section 286 Companies Act 2017")
        questions.append("interlocutory power under Section 288 Companies Act 2017 to regulate company affairs on just and equitable terms")
    if is_rent:
        questions.append("exclusive jurisdiction of Rent Tribunal and bar on civil court suit under Section 34 PRPA 2009")
        questions.append("grounds for eviction for default in rent payment under Section 15 PRPA 2009")
    if is_cheque_dishonour:
        questions.append("criminal prosecution under Section 489-F PPC for dishonour of cheque")

    if not questions:
        questions = [query[:200]]

    # 5. Search Lanes Construction
    raw_lanes: List[Dict[str, Any]] = []
    for i, dq in enumerate(decomposed):
        lane_name = f"lane_{i+1}"
        dq_low = dq.lower()
        if "concurrent" in dq_low or "simultaneous" in dq_low:
            lane_name = "concurrent_civil_criminal_remedies"
        elif "rent" in dq_low or "eviction" in dq_low or "tenant" in dq_low or "prpa" in dq_low:
            lane_name = "rent_tribunal_eviction"
        elif "489" in dq_low or "cheque" in dq_low or "bounced" in dq_low or "dishonour" in dq_low or "138" in dq_low:
            if is_quashment or "quash" in dq_low or "561" in dq_low:
                lane_name = "quashment_561a_cheque"
                dq = "Section 561-A CrPC quashment of FIR Section 489-F PPC cheque dishonour civil dispute abuse of process"
            elif "bail" in dq_low or "497" in dq_low or "498" in dq_low:
                lane_name = "bail_489f_cheque"
                dq = "Section 489-F PPC cheque dishonour pre-arrest bail post-arrest bail Section 497 CrPC Section 498 CrPC"
            else:
                lane_name = "cheque_dishonour_489f"
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
        raw_lanes.append({"lane": lane_name, "query": dq})

    if is_sec12_2:
        if not any(l["lane"] == "sec12_2_decree_fraud" for l in raw_lanes):
            raw_lanes.insert(0, {
                "lane": "sec12_2_decree_fraud",
                "query": "Section 12(2) CPC application to set aside decree obtained by fraud misrepresentation want of jurisdiction"
            })
        if not any(l["lane"] == "sec12_2_limitation_art181" for l in raw_lanes):
            raw_lanes.append({
                "lane": "sec12_2_limitation_art181",
                "query": "Section 12(2) CPC Article 181 Limitation Act three years from accrual of right to apply discovery of fraud"
            })
        if "appeal" in q_low and not any(l["lane"] == "sec12_2_vs_appeal_s96" for l in raw_lanes):
            raw_lanes.append({
                "lane": "sec12_2_vs_appeal_s96",
                "query": "Section 12(2) CPC application distinguished from appeal Section 96 CPC separate suit barred"
            })

    if is_specific_perf:
        if not any(l["lane"] == "specific_performance_immovable_property" for l in raw_lanes):
            raw_lanes.insert(0, {
                "lane": "specific_performance_immovable_property",
                "query": "Section 12 Specific Relief Act 1877 suit for specific performance agreement to sell immovable property advance money"
            })
        if not any(l["lane"] == "recovery_advance_money_damages" for l in raw_lanes):
            raw_lanes.append({
                "lane": "recovery_advance_money_damages",
                "query": "Section 73 Contract Act 1872 recovery of earnest advance money damages breach of contract to sell"
            })

    for check in premise_checks:
        if check["status"] == "CONFIRMED_ABSENT" and "138" in str(check.get("queried_provision")):
            if not any(l["lane"] == "cheque_dishonour_489f" for l in raw_lanes):
                raw_lanes.insert(0, {
                    "lane": "cheque_dishonour_489f",
                    "query": "Section 489-F PPC dishonour of cheque ingredients punishment dishonest issuance"
                })
            if not is_quashment and not is_bail and not any(l["lane"] == "cheque_civil_recovery" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "cheque_civil_recovery",
                    "query": "Order XXXVII Rule 2 CPC summary suit dishonoured cheque Section 118 NI Act presumption"
                })
        elif check["status"] == "CONFIRMED_ABSENT" and "420" in str(check.get("queried_provision")):
            if not any(l["lane"] == "cheating_fraud_420ppc" for l in raw_lanes):
                raw_lanes.insert(0, {
                    "lane": "cheating_fraud_420ppc",
                    "query": "Section 420 PPC cheating dishonestly inducing delivery of property ingredients punishment"
                })
        elif ("rule 2a" in str(check.get("queried_provision")).lower() or "rule 2-a" in str(check.get("queried_provision")).lower()):
            if not any(l["lane"] == "injunction_duration_rule_2a" for l in raw_lanes):
                raw_lanes.insert(0, {
                    "lane": "injunction_duration_rule_2a",
                    "query": "Order XXXIX Rule 2A CPC interim injunction duration fifteen days ex-parte defendant"
                })

    if "review" in q_low and any(k in q_low for k in ["cpc", "civil procedure", "court review its own", "review its own decision", "order xlvii", "own decision"]):
        if not any(l["lane"] == "cpc_review_sec114_oxlvii" for l in raw_lanes):
            raw_lanes.insert(0, {
                "lane": "cpc_review_sec114_oxlvii",
                "query": "Section 114 Order XLVII Rule 1 CPC review of judgment decree mistake error apparent on face of record discovery new evidence"
            })

    if is_corporate:
        if not any(l["lane"] == "company_interim_relief_s288" for l in raw_lanes):
            raw_lanes.insert(0, {
                "lane": "company_interim_relief_s288",
                "query": "Section 286 Section 288 Companies Act 2017 Section 290 Section 292 interim relief freeze bank accounts operational solvent company"
            })

    if is_bail and any(k in q_low for k in ["bailable", "non-bailable", "non bailable", "arrest", "which section"]):
        if not any(l["lane"] == "bail_bailable_s496" for l in raw_lanes):
            raw_lanes.insert(0, {
                "lane": "bail_bailable_s496",
                "query": "Section 496 CrPC bailable offence bail as matter of right not favor police station magistrate"
            })
        if not any(l["lane"] == "bail_non_bailable_s497" for l in raw_lanes):
            raw_lanes.insert(1, {
                "lane": "bail_non_bailable_s497",
                "query": "Section 497 CrPC non-bailable prohibitory clause concession grace judicial discretion non-prohibitory bail rule refusal exception"
            })

    if is_partition or is_benami:
        if any(k in q_low for k in ["set off", "set-off", "claim", "defence", "defense"]):
            if not any(l["lane"] == "partition_set_off_inapplicability" for l in raw_lanes):
                raw_lanes.insert(0, {
                    "lane": "partition_set_off_inapplicability",
                    "query": "Order VIII Rule 6 CPC set off maintainable only in money suit partition suit immovable property not maintainable"
                })
            if not any(l["lane"] == "partition_counter_claim_cross_suit" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "partition_counter_claim_cross_suit",
                    "query": "suit for partition co-sharers properties in name of other persons proper remedy independent suit counter claim Khawaja Nayyar Qayyum 2006 YLR 2059"
                })
        if is_partition:
            if not any(l["lane"] == "partition_order20_rule18_partial_partition" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "partition_order20_rule18_partial_partition",
                    "query": "suit for partition preliminary decree co-sharer Order XX Rule 18 CPC partial partition ancestral estate Shahbaz Khan 2026 SCMR 941"
                })
        if is_benami:
            if not any(l["lane"] == "benami_statutory_bar_section4" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "benami_statutory_bar_section4",
                    "query": "Section 4 Benami Transactions Prohibition Act 2017 bar on defence real owner burden of proof"
                })

    if is_family:
        if any(k in q_low for k in ["khula", "consent", "dissolution of marriage", "zar-i-khula"]):
            if not any(l["lane"] == "khula_without_consent" for l in raw_lanes):
                raw_lanes.insert(0, {
                    "lane": "khula_without_consent",
                    "query": "Section 10 Family Courts Act 1964 Khula wife right without husband consent dissolution of marriage"
                })
            if not any(l["lane"] == "khula_dower_zar_i_khula" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "khula_dower_zar_i_khula",
                    "query": "return of dower zar-i-khula civil liability does not invalidate dissolution of marriage Section 10(4)"
                })
        if any(k in q_low for k in ["maintenance", "minor", "child", "children"]):
            if not any(l["lane"] == "maintenance_family_s9" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "maintenance_family_s9",
                    "query": "Section 9 Muslim Family Laws Ordinance 1961 Section 5 Family Courts Act 1964 maintenance of minor children father statutory duty"
                })
        if any(k in q_low for k in ["custody", "guardian", "hizanat"]):
            if not any(l["lane"] == "custody_welfare_of_minor" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "custody_welfare_of_minor",
                    "query": "welfare of minor paramount consideration Section 17 Section 25 Guardians and Wards Act 1890 hizanat mother preferential right"
                })

    if is_rent:
        if not any(l["lane"] == "rent_tribunal_exclusive_jurisdiction" for l in raw_lanes):
            raw_lanes.insert(0, {
                "lane": "rent_tribunal_exclusive_jurisdiction",
                "query": "Section 19 Section 34 PRPA 2009 exclusive jurisdiction Rent Tribunal civil court jurisdiction barred"
            })
        if not any(l["lane"] == "rent_default_eviction_s15" for l in raw_lanes):
            raw_lanes.append({
                "lane": "rent_default_eviction_s15",
                "query": "Section 15 PRPA 2009 grounds for eviction default in payment of rent tenancy agreement expiry"
            })
        if not any(l["lane"] == "rent_leave_to_defend_s22" for l in raw_lanes):
            raw_lanes.append({
                "lane": "rent_leave_to_defend_s22",
                "query": "Section 22 PRPA 2009 leave to defend mandatory requirement substantial questions of law fact"
            })

    if is_banking:
        if any(k in q_low for k in ["leave to defend", "leave to appear", "condonation", "delay", "time barred"]):
            if not any(l["lane"] == "fio_leave_to_defend_s10" for l in raw_lanes):
                raw_lanes.insert(0, {
                    "lane": "fio_leave_to_defend_s10",
                    "query": "Section 10 Financial Institutions Recovery of Finances Ordinance 2001 leave to defend 30 days mandatory limitation"
                })
        if any(k in q_low for k in ["appeal", "stay", "deposit", "execution"]):
            if not any(l["lane"] == "fio_appeal_deposit_s22" for l in raw_lanes):
                raw_lanes.append({
                    "lane": "fio_appeal_deposit_s22",
                    "query": "Section 22 Financial Institutions Recovery of Finances Ordinance 2001 appeal mandatory statutory deposit 50 percent"
                })

    # Wrap into SearchLane objects
    search_lanes: List[Union[SearchLane, Dict[str, Any]]] = []
    for l in raw_lanes:
        lid = l.get("lane") or l.get("lane_id") or "lane"
        lq = l.get("query") or ""
        search_lanes.append(SearchLane(
            lane_id=lid,
            purpose=lid.replace("_", " ").title(),
            query=lq,
            target_engine=l.get("target_engine", "all"),
            domain_override=l.get("domain_override")
        ))

    # Wrap into PremiseCorrection objects
    typed_premise_corrections: List[Union[PremiseCorrection, Dict[str, Any]]] = []
    for pc in premise_corrections:
        typed_premise_corrections.append(PremiseCorrection(
            queried_statute=pc.get("queried_statute") or "",
            queried_provision=pc.get("queried_provision") or "",
            status=pc.get("status") or "EXISTS",
            mandatory_opening_thesis=pc.get("mandatory_opening_thesis") or "",
            statutory_authority=pc.get("statutory_authority") or "",
            is_foreign=pc.get("is_foreign"),
            pakistani_equivalent=pc.get("pakistani_equivalent"),
            explanation=pc.get("explanation"),
            canonical_id=pc.get("canonical_id"),
            display_name=pc.get("display_name"),
            title=pc.get("title"),
            text=pc.get("text"),
            schedule_ii=pc.get("schedule_ii")
        ))

    # Multi-Issue Fact Pattern Decomposition Integration
    try:
        from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern
        decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=primary_domain)
        if decomp and decomp.issues:
            for issue in decomp.issues:
                for cs in issue.controlling_statutes:
                    if cs not in statutes:
                        statutes.append(cs)
                for cp in issue.controlling_provisions:
                    if not any(cp.lower() in p.lower() or p.lower() in cp.lower() for p in provisions):
                        provisions.append(cp)
                for sq in issue.search_queries:
                    if not any(l.get("query") == sq for l in raw_lanes):
                        raw_lanes.append({"lane": issue.issue_id, "query": sq})
                if issue.heading not in questions:
                    questions.append(issue.heading)
            if hasattr(decomp, "open_questions") and decomp.open_questions:
                for oq in decomp.open_questions:
                    if oq not in questions:
                        questions.append(oq)
    except Exception as e:
        logger.warning(f"Fact pattern decomposition error in planner: {e}")

    # Prune inapplicable provisions for specific performance (possession/injunction bars)
    if is_specific_perf:
        provisions = [
            p for p in provisions
            if not any(bad in p.lower() for bad in [
                "section 8 specific", "section 9 specific", "section 56 specific",
                "sra 8", "sra 9", "sra 56", "section 8 sra", "section 9 sra", "section 56 sra"
            ])
        ]

    # Ensure unique lists and enforce domain isolation
    raw_clean_provisions = filter_provisions_by_domain(list(dict.fromkeys(provisions)), primary_domain)
    from core.evidence_pipeline import normalize_provision_string_to_canonical_id
    from core.unified_statute_store import get_unified_statute_store
    store = get_unified_statute_store()
    canonical_provisions = []
    for p in raw_clean_provisions:
        cid = normalize_provision_string_to_canonical_id(p)
        if cid and store.get_by_canonical_id(cid):
            if cid not in canonical_provisions:
                canonical_provisions.append(cid)
    clean_provisions = filter_provisions_by_domain(canonical_provisions, primary_domain) if canonical_provisions else raw_clean_provisions
    clean_statutes = list(dict.fromkeys(statutes))
    clean_legacy_domains = list(dict.fromkeys(legacy_domains))
    clean_legacy_matter = list(dict.fromkeys(legacy_matter_type))

    return StructuredLegalQueryPlan(
        query_text=query,
        raw_query=query,
        jurisdiction="Pakistan",
        primary_domain=primary_domain,
        secondary_domains=secondary_domains,
        subdomains=subdomains,
        governing_statutes=clean_statutes,
        statutory_provisions=clean_provisions,
        core_legal_issues=questions,
        procedural_remedy=procedural_remedy,
        competent_forum=competent_forum,
        target_province=province,
        search_lanes=search_lanes,
        premise_corrections=typed_premise_corrections,
        allowed_domains_filter=allowed_domains_filter,
        is_cross_domain_relevant=is_cross_domain_relevant,
        cross_domain_reason=cross_domain_reason,
        cross_domain_controlling_doctrines=cross_domain_controlling_doctrines,
        is_ambiguous=is_ambiguous,
        ambiguity_reasons=ambiguity_reasons,
        clarification_options=clarification_options,
        legal_domain=clean_legacy_domains,
        provisions=clean_provisions,
        legal_questions=questions,
        factual_matrix=[query],
        required_authorities=["Supreme Court of Pakistan", "High Courts"],
        matter_type=clean_legacy_matter if clean_legacy_matter else [primary_domain],
        province=province,
        forum=competent_forum,
        issues=questions,
        binding_courts=binding_courts,
        persuasive_courts=persuasive_courts,
        forum_hierarchy=forum_hierarchy,
        employee_status_branching=employee_status_branching
    )


def log_planner_audit_event(
    query: str,
    path_taken: str,
    plan: StructuredLegalQueryPlan,
    fallback_reason: Optional[str] = None
) -> None:
    """
    Logs every planner query decision to persistent logs/planner_query_audit.jsonl
    and emits an audit log line to stderr. Records the execution path, primary domain,
    provisions returned, and verification status against UnifiedStatuteStore.
    """
    try:
        from core.unified_statute_store import get_unified_statute_store

        store = get_unified_statute_store()
        provisions = list(plan.statutory_provisions or plan.provisions or [])
        verified_status: Dict[str, bool] = {}

        act_map = {
            'ppc': 'PPC_1860', 'penal code': 'PPC_1860',
            'crpc': 'CRPC_1898', 'criminal procedure': 'CRPC_1898',
            'cpc': 'CPC_1908', 'civil procedure': 'CPC_1908',
            'sra': 'SRA_1877', 'specific relief': 'SRA_1877',
            'prpa': 'PRPA_2009', 'rented premises': 'PRPA_2009',
            'fio': 'FIO_2001', 'financial institutions': 'FIO_2001',
            'limitation': 'LIMITATION_1908',
            'family courts': 'FAMILY_COURTS_1964', 'fca': 'FAMILY_COURTS_1964',
            'muslim family': 'MFLO_1961', 'mflo': 'MFLO_1961',
            'guardians': 'GWA_1890', 'gwa': 'GWA_1890',
            'contract': 'CONTRACT_1872',
            'negotiable': 'NI_ACT_1881', 'ni act': 'NI_ACT_1881',
            'qanun': 'QSO_1984', 'qso': 'QSO_1984',
            'constitution': 'CONST_1973', 'const': 'CONST_1973',
            'registration': 'REGISTRATION_1908',
            'stamp': 'STAMP_1899'
        }

        for p in provisions:
            p_str = str(p).strip()
            exists = False
            if store.get_by_canonical_id(p_str):
                exists = True
            else:
                m_sec = re.search(r'(?:sections?|sec\.?|articles?|art\.?|rules?|orders?|o\.|r\.)\s*([0-9]+[a-z]?(?:\s*\([0-9a-z]+\))?)', p_str, re.IGNORECASE)
                num = m_sec.group(1).replace(' ', '') if m_sec else ''
                low = p_str.lower()
                for kw, act in act_map.items():
                    if kw in low:
                        if num and store.get_provision(act, num):
                            exists = True
                            break
                        m_base = re.match(r'([0-9]+[a-z]?)', num)
                        if m_base and store.get_provision(act, m_base.group(1)):
                            exists = True
                            break
            verified_status[p_str] = exists

        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "path_taken": path_taken,
            "fallback_reason": fallback_reason,
            "primary_domain": plan.primary_domain,
            "controlling_provisions": provisions,
            "provisions_in_unified_store": verified_status,
            "all_provisions_verified": all(verified_status.values()) if verified_status else True
        }

        # Stderr / logger output
        import sys
        reason_str = f" fallback_reason={fallback_reason}" if fallback_reason else ""
        verified_count = sum(1 for v in verified_status.values() if v)
        sys.stderr.write(
            f"[PLANNER_QUERY_AUDIT] path={path_taken} domain={plan.primary_domain} "
            f"provisions={len(provisions)} verified={verified_count}/{len(provisions)}{reason_str}\n"
        )
        sys.stderr.flush()

        # Append to logs/planner_query_audit.jsonl
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "planner_query_audit.jsonl")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    except Exception as audit_err:
        import sys
        sys.stderr.write(f"[PLANNER_QUERY_AUDIT_ERROR] Failed to record audit log: {audit_err}\n")
        sys.stderr.flush()


async def analyze_legal_query(query: str, ai_client_fn=None) -> StructuredLegalQueryPlan:
    """
    Analyzes user query and returns a StructuredLegalQueryPlan.
    Tries AI planner first; safely falls back to deterministic planner on any error or timeout.
    Every query path decision is audited to logs/planner_query_audit.jsonl.
    """
    if not query or len(query.strip()) < 10:
        plan = create_deterministic_fallback_plan(query)
        log_planner_audit_event(query, path_taken="deterministic_fallback", plan=plan, fallback_reason="query_too_short")
        return plan

    fallback_reason: Optional[str] = None
    if ai_client_fn:
        try:
            user_msg = f'User Legal Query:\n\"\"\"{query}\"\"\"'
            resp = await asyncio.wait_for(
                ai_client_fn(
                    system=PLANNER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                    max_tokens=4096
                ),
                timeout=45.0
            )
            raw_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
            m_json = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                fallback = create_deterministic_fallback_plan(query)

                # Normalize provisions & gather from decomposition issues
                raw_provisions = data.get("statutory_provisions") or data.get("controlling_provisions") or data.get("provisions") or []
                raw_issues = data.get("issues") or []
                if isinstance(raw_issues, list):
                    for iss in raw_issues:
                        if isinstance(iss, dict):
                            for cp in iss.get("controlling_provisions") or []:
                                if cp not in raw_provisions:
                                    raw_provisions.append(cp)

                from core.evidence_pipeline import normalize_provision_string_to_canonical_id
                from core.unified_statute_store import get_unified_statute_store
                store = get_unified_statute_store()

                provisions = []
                for p in raw_provisions:
                    p_str = str(p).strip()
                    m_fake = re.search(r'section\s*(18\d\d|19\d\d|20\d\d)', p_str, re.IGNORECASE)
                    if m_fake:
                        continue
                    if any(k in p_str.lower() for k in ["138", "139"]) and any(k in p_str.lower() for k in ["ni", "negotiable", "nia"]):
                        continue
                    cid = normalize_provision_string_to_canonical_id(p_str)
                    if cid and store.get_by_canonical_id(cid):
                        if cid not in provisions:
                            provisions.append(cid)

                premise_corrections = fallback.premise_corrections
                search_lanes = data.get("search_lanes") or fallback.search_lanes

                if premise_corrections:
                    for pc in premise_corrections:
                        pc_status = pc.get("status") if isinstance(pc, dict) else getattr(pc, "status", "")
                        if pc_status in ("CONFIRMED_ABSENT", "LEGALLY_INAPPLICABLE_PREMISE", "STATUTORILY_BARRED_DEFENCE"):
                            absent_p = str(pc.get("queried_provision") if isinstance(pc, dict) else getattr(pc, "queried_provision", "")).lower()
                            provisions = [p for p in provisions if absent_p not in p.lower()]
                            for fp in fallback.statutory_provisions:
                                if fp not in provisions:
                                    provisions.append(fp)
                            search_lanes = fallback.search_lanes

                if not provisions:
                    provisions = fallback.statutory_provisions
                elif fallback.statutory_provisions:
                    for fp in fallback.statutory_provisions:
                        if not any(fp.lower() in p.lower() or p.lower() in fp.lower() for p in provisions):
                            provisions.append(fp)

                if any(k in query.lower() for k in ["specific performance", "agreement to sell"]):
                    provisions = [
                        p for p in provisions
                        if not any(bad in p.lower() for bad in [
                            "section 8 specific", "section 9 specific", "section 56 specific",
                            "sra 8", "sra 9", "sra 56", "section 8 sra", "section 9 sra", "section 56 sra"
                        ])
                    ]

                province = data.get("target_province") or data.get("province") or fallback.target_province
                binding_courts, persuasive_courts = resolve_jurisdiction_hierarchy(province)
                issues = data.get("core_legal_issues") or data.get("issues") or data.get("legal_questions") or fallback.core_legal_issues
                if isinstance(issues, list):
                    clean_issues = []
                    for iss in issues:
                        iss_str = str(iss).strip()
                        if ("139" in iss_str or "138" in iss_str) and any(k in iss_str.lower() for k in ["ni", "negotiable", "nia"]):
                            clean_issues.append("Burden and standard of proof of dishonest issuance and lack of funds under Section 489-F PPC")
                        else:
                            clean_issues.append(iss_str)
                    issues = clean_issues

                primary_domain = data.get("primary_domain") or fallback.primary_domain
                if primary_domain not in ALL_LEGAL_DOMAINS:
                    primary_domain = fallback.primary_domain

                # Validation Gate: Ensure all provisions strictly align with primary_domain
                provisions = filter_provisions_by_domain(provisions, primary_domain)
                if not provisions:
                    provisions = filter_provisions_by_domain(fallback.statutory_provisions, primary_domain)

                secondary_domains = data.get("secondary_domains") or fallback.secondary_domains
                subdomains = data.get("subdomains") or fallback.subdomains
                allowed_domains_filter = data.get("allowed_domains_filter") or fallback.allowed_domains_filter
                is_cross_domain = data.get("is_cross_domain_relevant", fallback.is_cross_domain_relevant)
                cross_reason = data.get("cross_domain_reason") or fallback.cross_domain_reason
                is_ambig = data.get("is_ambiguous", fallback.is_ambiguous)

                plan = StructuredLegalQueryPlan(
                    query_text=query,
                    raw_query=query,
                    jurisdiction="Pakistan",
                    primary_domain=primary_domain,
                    secondary_domains=secondary_domains,
                    subdomains=subdomains,
                    governing_statutes=data.get("governing_statutes") or fallback.governing_statutes,
                    statutory_provisions=provisions,
                    core_legal_issues=issues,
                    procedural_remedy=data.get("procedural_remedy") or fallback.procedural_remedy,
                    competent_forum=data.get("competent_forum") or fallback.competent_forum,
                    target_province=province,
                    search_lanes=search_lanes,
                    premise_corrections=premise_corrections,
                    allowed_domains_filter=allowed_domains_filter,
                    is_cross_domain_relevant=is_cross_domain,
                    cross_domain_reason=cross_reason,
                    cross_domain_controlling_doctrines=fallback.cross_domain_controlling_doctrines,
                    is_ambiguous=is_ambig,
                    ambiguity_reasons=fallback.ambiguity_reasons,
                    clarification_options=fallback.clarification_options,
                    legal_domain=fallback.legal_domain,
                    provisions=provisions,
                    legal_questions=issues,
                    factual_matrix=data.get("factual_matrix") or [query],
                    required_authorities=data.get("required_authorities", ["Supreme Court of Pakistan", "High Courts"]),
                    matter_type=fallback.matter_type,
                    province=province,
                    forum=data.get("competent_forum") or fallback.competent_forum,
                    issues=issues,
                    binding_courts=binding_courts,
                    persuasive_courts=persuasive_courts,
                    forum_hierarchy=fallback.forum_hierarchy,
                    employee_status_branching=fallback.employee_status_branching
                )
                log_planner_audit_event(query, path_taken="llm_planner", plan=plan)
                return plan
            else:
                fallback_reason = "ai_client_no_json_returned"
        except asyncio.TimeoutError:
            fallback_reason = "ai_client_timeout"
            import sys
            print(f"⚠️ analyze_legal_query timeout after 45s", file=sys.stderr, flush=True)
        except Exception as err:
            fallback_reason = f"ai_client_exception: {type(err).__name__} - {err}"
            import sys
            print(f"⚠️ analyze_legal_query exception: {err}", file=sys.stderr, flush=True)
    else:
        fallback_reason = "no_ai_client_provided"

    # Deterministic fallback
    plan = create_deterministic_fallback_plan(query)
    log_planner_audit_event(query, path_taken="deterministic_fallback", plan=plan, fallback_reason=fallback_reason)
    return plan
