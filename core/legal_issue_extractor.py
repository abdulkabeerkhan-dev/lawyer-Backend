"""
core/legal_issue_extractor.py
Multi-Issue Fact Pattern Decomposition Engine for Pakistani Law.

Deterministic decomposition across 10 Priority Domains:
1. Family Law (Khula, Dower, Maintenance, Custody/Hizanat, Talaq)
2. Rent and Eviction (PRPA 2009, SRPO 1979, leave to contest, rent receipts)
3. Banking Recovery (FIO 2001 Sec 9, 10, 14, 15, 22)
4. Criminal Law beyond murder (Theft, CBT, Cheating, Bail, 489-F PPC)
5. Constitutional Writs (Art 199 Certiorari, Mandamus, Habeas Corpus, Arts 4, 9, 10A, 24)
6. FIR Quashment & Abuse of Process (CrPC 561-A, 154, 249-A, 265-K, Art 199)
7. Service Tribunal (Civil Servants Act 1973 Sec 4, 8, 9, Art 212 bar)
8. Land & Property Revenue (Land Revenue Act 1967 Sec 42, 52, 135, 172, Illegal Dispossession 2005)
9. IP & Cybercrime (PECA 2016 Sec 3, 16, 21, Trademarks 2001 Sec 40, 46, Copyright 1962 Sec 56, 60)
10. Family Property & Inheritance (Shariat Act 1962, Partition Act 1893, CPC O.XX R.18, Women Property Rights 2020)
"""

import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class LegalSubIssue(BaseModel):
    issue_id: str
    heading: str
    description: str
    controlling_statutes: List[str] = Field(default_factory=list)
    controlling_provisions: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)
    factual_anchors: List[str] = Field(default_factory=list)


class FactPatternDecomposition(BaseModel):
    primary_domain: str
    secondary_domains: List[str] = Field(default_factory=list)
    issues: List[LegalSubIssue] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    named_statute_canonical_ids: List[str] = Field(default_factory=list)


def extract_named_statute_canonical_ids(query_text: str) -> List[str]:
    """
    Direct lookup extractor: When a query explicitly mentions a statute name or citation
    (e.g. 'PECA 2016', 'FIO 2001', 'Section X of the Y Act'), resolves that statute's
    canonical IDs directly without running search.
    """
    q_low = query_text.lower()
    admitted: List[str] = []

    # 1. Whole-statute direct mappings
    statute_canonical_map = {
        ("peca 2016", "peca", "prevention of electronic crimes act"): [
            "PECA_2016_SEC_20", "PECA_2016_SEC_21", "PECA_2016_SEC_10", "PECA_2016_SEC_3", "PECA_2016_SEC_16"
        ],
        ("fio 2001", "fio", "financial institutions ordinance", "financial institutions (recovery"): [
            "FIO_2001_SEC_9", "FIO_2001_SEC_10", "FIO_2001_SEC_22", "FIO_2001_SEC_2"
        ],
        ("fia act", "fia 1974", "federal investigation agency act"): [
            "FIA_1974_SEC_5", "FIA_1974_SEC_3"
        ],
        ("prpa 2009", "prpa", "punjab rented premises act"): [
            "PRPA_2009_SEC_15", "PRPA_2009_SEC_22", "PRPA_2009_SEC_4", "PRPA_2009_SEC_19"
        ],
        ("srpo 1979", "srpo", "sindh rented premises ordinance"): [
            "SRPO_1979_SEC_15", "SRPO_1979_SEC_16", "SRPO_1979_SEC_21"
        ],
        ("mflo 1961", "mflo", "muslim family laws ordinance"): [
            "MFLO_1961_SEC_7", "MFLO_1961_SEC_9", "MFLO_1961_SEC_10"
        ],
        ("family courts act 1964", "family courts act", "fca 1964"): [
            "FAMILY_COURTS_1964_SEC_5", "FAMILY_COURTS_1964_SEC_10", "FAMILY_COURTS_1964_SEC_14", "FAMILY_COURTS_1964_SEC_17A"
        ],
        ("specific relief act 1877", "specific relief act", "sra 1877"): [
            "SRA_1877_SEC_12", "SRA_1877_SEC_42", "SRA_1877_SEC_54", "SRA_1877_SEC_19"
        ],
        ("contract act 1872", "contract act"): [
            "CONTRACT_1872_SEC_73", "CONTRACT_1872_SEC_2"
        ],
        ("limitation act 1908", "limitation act"): [
            "LIMITATION_1908_SEC_3", "LIMITATION_1908_SEC_5", "LIMITATION_1908_SEC_14"
        ],
        ("arbitration act 1940", "arbitration act"): [
            "ARBITRATION_1940_SEC_34", "ARBITRATION_1940_SEC_20"
        ],
        ("qanun-e-shahadat order", "qanun-e-shahadat", "qso 1984", "qso"): [
            "QSO_1984_ART_2", "QSO_1984_ART_17", "QSO_1984_ART_129"
        ],
        ("trade marks ordinance 2001", "trade marks ordinance", "trademarks ordinance"): [
            "TRADEMARKS_2001_SEC_40", "TRADEMARKS_2001_SEC_46"
        ],
        ("copyright ordinance 1962", "copyright ordinance"): [
            "COPYRIGHT_1962_SEC_56", "COPYRIGHT_1962_SEC_60"
        ],
    }

    for keys, cids in statute_canonical_map.items():
        if any(k in q_low for k in keys):
            for c in cids:
                if c not in admitted:
                    admitted.append(c)

    # 2. Section X of [the] Y Act patterns
    statute_code_map = {
        "peca": "PECA_2016", "peca 2016": "PECA_2016",
        "fio": "FIO_2001", "fio 2001": "FIO_2001",
        "crpc": "CRPC_1898", "cr.p.c": "CRPC_1898", "cr.p.c.": "CRPC_1898",
        "ppc": "PPC_1860", "p.p.c": "PPC_1860", "p.p.c.": "PPC_1860",
        "cpc": "CPC_1908", "c.p.c": "CPC_1908", "c.p.c.": "CPC_1908",
        "constitution": "CONST_1973", "const": "CONST_1973",
        "fia": "FIA_1974", "fia act": "FIA_1974",
        "prpa": "PRPA_2009", "srpo": "SRPO_1979",
        "sra": "SRA_1877", "specific relief": "SRA_1877",
        "contract": "CONTRACT_1872", "contract act": "CONTRACT_1872",
        "limitation": "LIMITATION_1908", "limitation act": "LIMITATION_1908",
        "qso": "QSO_1984", "qanun-e-shahadat": "QSO_1984",
    }

    # Matches "Section 20 of PECA", "Section 498 of CrPC", "Section 10 of the FIO 2001", "Article 199 of the Constitution"
    sec_of_matches = re.finditer(
        r'(?:section|sec\.?|s\.|article|art\.?|order|ord\.?)\s*([0-9IVXLCDM]+[A-Za-z]?(?:\s*\([0-9]+\))?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z0-9\s,\-]+?(?:Act|Ordinance|Code|Order|Constitution|PPC|CrPC|CPC|PECA|FIO|PRPA|SRPO|MFLO|QSO|SRA|GWA|ATA|CNSA|BCO|FIA))',
        query_text,
        re.IGNORECASE
    )
    for m in sec_of_matches:
        sec_raw = m.group(1).strip()
        act_raw = m.group(2).strip().lower()
        matched_act = None
        for k, code in statute_code_map.items():
            if k in act_raw:
                matched_act = code
                break
        if matched_act:
            sec_num = re.sub(r'[\(\)\s]', '', sec_raw).upper()
            unit = "ART" if "art" in m.group(0).lower() or "CONST" in matched_act else "SEC"
            cid = f"{matched_act}_{unit}_{sec_num}"
            if cid not in admitted:
                admitted.append(cid)

    # Pattern: "Section 498 CrPC", "Section 20 PECA", "Section 489-F PPC"
    sec_prefix_matches = re.finditer(
        r'(?:section|sec\.?|s\.|article|art\.?)\s*([0-9IVXLCDM]+[A-Za-z]?(?:-[A-Za-z0-9]+)?)\s+([A-Za-z]{2,8})',
        query_text,
        re.IGNORECASE
    )
    for m in sec_prefix_matches:
        sec_raw = m.group(1).strip()
        act_raw = m.group(2).strip().lower()
        if act_raw in statute_code_map:
            matched_act = statute_code_map[act_raw]
            sec_num = re.sub(r'[\(\)\s\-]', '', sec_raw).upper()
            unit = "ART" if "art" in m.group(0).lower() or "CONST" in matched_act else "SEC"
            cid = f"{matched_act}_{unit}_{sec_num}"
            if cid not in admitted:
                admitted.append(cid)

    return admitted


def extract_legal_issues_from_fact_pattern(
    query_text: str,
    planner_domain: Optional[str] = None,
    existing_issues: Optional[List[LegalSubIssue]] = None
) -> FactPatternDecomposition:
    """
    Decomposes an unstructured factual narrative into structured legal sub-issues across 10 Priority Domains.
    Enforces clear priority:
    1. If planner_domain is provided, it cannot be overridden by extractor keyword heuristics.
    2. Uses phrase-level keyword matching to eliminate false cross-contamination (e.g. 'unpaid' in family law).
    3. Emits authoritative Canonical IDs only in controlling_provisions.
    """
    q_low = query_text.lower()
    issues: List[LegalSubIssue] = list(existing_issues or [])
    open_questions: List[str] = []

    has_dates = bool(
        re.search(r'\b(?:19|20)\d\d\b', q_low) or
        re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b', q_low)
    )
    has_amounts = bool(re.search(r'(?i)\b(?:rs\.?|pkr|lakh|crore|million)\b', q_low))

    # -------------------------------------------------------------------------
    # 1. Resolve Primary Domain Signals
    # -------------------------------------------------------------------------
    is_family_signal = any(k in q_low for k in [
        "khula", "dower", "mahr", "maintenance", "nafaqa", "custody",
        "hizanat", "guardianship", "iddat", "talaq", "dissolution of marriage",
        "family court", "guardians and wards act", "union council", "arbitration council"
    ]) and not any(k in q_low for k in ["inheritance", "inherited property", "legal heirs", "shariat application", "dwelling-house", "dwelling house", "benami"])

    is_rent_signal = bool(
        re.search(r'\b(?:punjab rented premises|prpa|rent tribunal|ejectment application|leave to contest|default in payment of rent|bona fide need|sindh rented premises|srpo|cantonment rent)\b', q_low) or
        (any(k in q_low for k in ["tenant", "landlord", "ejectment", "eviction", "subletting", "tentative rent"]) and "rent" in q_low)
    )

    is_banking_signal = any(k in q_low for k in [
        "banking court", "financial institutions (recovery", "fio 2001", "fio",
        "recovery of finance", "leave to defend", "compound mark-up", "finance agreement",
        "section 9 fio", "section 10 fio", "statement of account", "penal mark-up"
    ])

    is_service_signal = any(k in q_low for k in [
        "civil servant", "service tribunal", "seniority list", "superseded in promotion",
        "disciplinary inquiry", "compulsory retirement", "departmental appeal", "article 212",
        "civil servants act", "terms and conditions of service", "reversion"
    ])

    is_constitutional_signal = any(k in q_low for k in [
        "article 199", "writ petition", "writ of", "mandamus", "certiorari", "habeas corpus",
        "quo warranto", "fundamental rights", "article 10a", "article 24", "unlawful detention",
        "without lawful authority", "detenue"
    ]) and not is_service_signal

    is_quashment_signal = any(k in q_low for k in [
        "561-a", "561a", "quashment", "quash the fir", "quashing of fir", "abuse of process of the court",
        "abuse of process", "commercial dispute into criminal", "pure civil dispute", "second fir", "249-a", "249a", "265-k", "265k"
    ])

    is_land_revenue_signal = any(k in q_low for k in [
        "land revenue", "mutation", "intiqal", "record of rights", "jamabandi", "revenue officer",
        "patwari", "partition of agricultural", "section 42 land revenue", "section 135 land revenue",
        "section 172 land revenue", "illegal dispossession act", "land grabber", "illegal dispossession"
    ])

    peca_keywords = [
        "peca", "cybercrime", "cyber crime", "fia notice", "online defamation",
        "digital content", "electronic fraud", "unauthorized access", "cyberstalking",
        "cyber stalking"
    ]
    is_peca_signal = any(k in q_low for k in peca_keywords)

    is_cyber_ip_signal = is_peca_signal or any(k in q_low for k in [
        "peca", "cybercrime", "cyber crime", "hacking", "cyberstalking", "cyber stalking",
        "online harassment", "electronic crimes", "trademark", "trade mark", "passing off",
        "copyright", "software piracy", "infringement of trademark", "counterfeit goods"
    ])

    is_inheritance_signal = any(k in q_low for k in [
        "inheritance", "inherited property", "legal heirs", "shariat application",
        "muslim personal law (shariat)", "partition act", "order xx rule 18",
        "women's property rights", "sister's share", "deprived of inheritance", "benami",
        "deceased father's estate", "pre-emption of dwelling"
    ])

    is_civil_execution = (
        any(k in q_low for k in ["judgment debtor", "execution of decree", "money decree", "order xxi", "section 55", "warrant of arrest against judgment debtor", "civil prison", "executing court"])
        and not any(k in q_low for k in ["fir", "police station", "remand", "challan", "post-arrest bail", "pre-arrest bail"])
    )

    is_corporate_signal = (
        any(k in q_low for k in ["companies act", "company law", "section 286", "section 288", "oppression", "mismanagement", "minority shareholder", "company bench", "secp"]) or
        (any(k in q_low for k in ["director", "board of directors", "majority director", "managing director", "shareholder"]) and
         any(k in q_low for k in ["siphoning", "siphon", "allotment of shares", "issuing shares", "agm", "eogm", "company assets", "corporate assets"]))
    )

    is_cheque_signal = any(phrase in q_low for phrase in [
        "cheque returned unpaid", "insufficient funds", "dishonoured cheque",
        "dishonored cheque", "bounced cheque", "return memo", "section 489-f",
        "489f ppc", "cheque was dishonoured", "cheque dishonour", "dishonoured on presentation",
        "cheque of rs", "deposited a cheque"
    ]) and not (is_family_signal or is_inheritance_signal or is_service_signal or is_rent_signal or is_corporate_signal or is_civil_execution)

    is_criminal_signal = (
        (
            is_cheque_signal or
            is_quashment_signal or
            any(k in q_low for k in [
                "fir", "police", "pre-arrest", "post-arrest", "theft", "379", "378",
                "cheating", "420", "415", "criminal breach of trust", "406", "405",
                "302", "murder", "qatl", "stolen"
            ]) or
            (any(k in q_low for k in ["arrest", "arrested", "custody", "remand", "bail"]) and not (is_civil_execution or is_family_signal))
        )
        and not (is_civil_execution or is_land_revenue_signal or is_corporate_signal)
    )

    is_sale_specific_perf = (
        (
            any(k in q_low for k in [
                "specific performance", "agreement to sell", "sale deed",
                "plot", "earnest money", "advance money"
            ]) or (
                any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and
                any(k in q_low for k in ["sale", "refused"])
            )
        )
        and not (is_family_signal or is_rent_signal or is_banking_signal or is_service_signal or is_constitutional_signal or is_land_revenue_signal or is_cyber_ip_signal or is_corporate_signal or is_civil_execution)
    )

    if is_peca_signal:
        primary_domain = "cybercrime"
    elif planner_domain and planner_domain in {
        "civil", "criminal", "constitutional", "family", "corporate", "rent",
        "banking", "taxation", "service", "labour", "cybercrime",
        "intellectual_property", "environmental", "general_legal"
    }:
        primary_domain = planner_domain
    elif is_family_signal:
        primary_domain = "family"
    elif is_rent_signal:
        primary_domain = "rent"
    elif is_banking_signal:
        primary_domain = "banking"
    elif is_service_signal:
        primary_domain = "service"
    elif is_constitutional_signal:
        primary_domain = "constitutional"
    elif is_civil_execution:
        primary_domain = "civil"
    elif is_corporate_signal:
        primary_domain = "corporate"
    elif is_quashment_signal:
        primary_domain = "criminal"
    elif is_cyber_ip_signal:
        primary_domain = "cybercrime" if "peca" in q_low or "cyber" in q_low else "intellectual_property"
    elif is_land_revenue_signal:
        primary_domain = "civil"
    elif is_inheritance_signal:
        primary_domain = "civil"
    elif is_criminal_signal:
        primary_domain = "criminal"
    elif is_sale_specific_perf:
        primary_domain = "civil"
    else:
        primary_domain = "civil"

    # Mutual exclusion: Never allow false cheque/criminal triggers to contaminate isolated domains
    if primary_domain in ("family", "rent", "banking", "service", "constitutional"):
        is_cheque_signal = False
        is_sale_specific_perf = False

    # -------------------------------------------------------------------------
    # 2. Domain-Specific Decompositions (10 Priority Domains)
    # -------------------------------------------------------------------------

    # =========================================================================
    # 1. FAMILY LAW DECOMPOSITION
    # =========================================================================
    if primary_domain == "family":
        # Khula / Dissolution
        if any(k in q_low for k in ["khula", "dissolution", "deserted", "desertion", "divorce"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_khula_dissolution",
                heading="Dissolution of Marriage by Khula (Section 10 FCA 1964 & Section 2 DMMA 1939)",
                description="Right of wife to claim dissolution of marriage through Khula on ground of aversion or desertion.",
                controlling_statutes=["Family Courts Act, 1964", "Dissolution of Muslim Marriages Act, 1939"],
                controlling_provisions=["FAMILY_COURTS_1964_SEC_10", "FAMILY_COURTS_1964_SEC_5", "DMMA_1939_SEC_2"],
                search_queries=["Section 10 Family Courts Act 1964 Khula wife right without husband consent", "Section 2 DMMA 1939 desertion"],
                factual_anchors=["khula", "deserted", "dissolution of marriage"]
            ))

        # Recovery of Dower (Mahr)
        if any(k in q_low for k in ["dower", "mahr", "prompt dower", "deferred dower"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_dower_recovery",
                heading="Recovery of Prompt Dower (Section 5 FCA 1964 & Section 10 MFLO 1961)",
                description="Statutory claim for recovery of unpaid prompt dower as an absolute debt payable on demand.",
                controlling_statutes=["Family Courts Act, 1964", "Muslim Family Laws Ordinance, 1961"],
                controlling_provisions=["MFLO_1961_SEC_10", "FAMILY_COURTS_1964_SEC_5"],
                search_queries=["Section 10 MFLO 1961 dower debt payable on demand", "Section 5 Family Courts Act 1964 suit for dower"],
                factual_anchors=["prompt dower", "dower", "unpaid dower"]
            ))

        # Maintenance for Wife and Minors
        if any(k in q_low for k in ["maintenance", "nafaqa", "minor", "children"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_maintenance_minors",
                heading="Past & Future Maintenance of Minors and Wife (Section 9 MFLO 1961 & Section 17A FCA 1964)",
                description="Statutory obligation of father to maintain minor children and interim maintenance schedule.",
                controlling_statutes=["Muslim Family Laws Ordinance, 1961", "Family Courts Act, 1964"],
                controlling_provisions=["MFLO_1961_SEC_9", "FAMILY_COURTS_1964_SEC_17A", "FAMILY_COURTS_1964_SEC_5"],
                search_queries=["Section 9 MFLO 1961 Section 17A FCA 1964 interim maintenance minor children", "past maintenance minor father duty"],
                factual_anchors=["maintenance", "minor children", "interim maintenance"]
            ))

        # Custody (Hizanat) & Guardianship
        if any(k in q_low for k in ["custody", "hizanat", "guardian", "guardianship"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_custody_hizanat",
                heading="Custody of Minor Children (Hizanat) & Guardianship (Sections 7, 17, 25 GWA 1890)",
                description="Determination of custody (Hizanat) where welfare of the minor is paramount consideration.",
                controlling_statutes=["Guardians and Wards Act, 1890", "Family Courts Act, 1964"],
                controlling_provisions=["GWA_1890_SEC_7", "GWA_1890_SEC_17", "GWA_1890_SEC_25", "FAMILY_COURTS_1964_SEC_5"],
                search_queries=["welfare of minor paramount consideration Section 17 Section 25 GWA 1890 hizanat mother", "tender age custody"],
                factual_anchors=["custody", "Hizanat", "Guardians and Wards Act"]
            ))

        # Talaq Notice & 90-day Arbitration
        if any(k in q_low for k in ["talaq", "divorce notice", "union council", "arbitration council"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_talaq_notice",
                heading="Statutory Notice of Talaq & 90-Day Arbitration (Section 7 MFLO 1961)",
                description="Mandatory statutory requirement to give written notice of Talaq to Chairman Union Council.",
                controlling_statutes=["Muslim Family Laws Ordinance, 1961", "Family Courts Act, 1964"],
                controlling_provisions=["MFLO_1961_SEC_7", "MFLO_1961_SEC_8", "FAMILY_COURTS_1964_SEC_5"],
                search_queries=["Section 7 MFLO 1961 notice of talaq union council 90 days effectiveness", "failure to give notice of talaq"],
                factual_anchors=["talaq", "Union Council", "notice of talaq"]
            ))

        # Family Court Appeal
        if any(k in q_low for k in ["appeal", "decree", "appellate"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_court_appeal",
                heading="Appeals Against Family Court Decree (Section 14 Family Courts Act, 1964)",
                description="Statutory appeal against Family Court judgment/decree before District Judge within 30 days.",
                controlling_statutes=["Family Courts Act, 1964"],
                controlling_provisions=["FAMILY_COURTS_1964_SEC_14", "FAMILY_COURTS_1964_SEC_5"],
                search_queries=["Section 14 Family Courts Act 1964 appeal before District Judge 30 days limitation", "appealable family decrees"],
                factual_anchors=["appeal", "Family Court decree"]
            ))

        open_questions.append("Whether the prompt dower is evidenced by a registered Nikahnama and whether interim maintenance was awarded.")

    # =========================================================================
    # 2. RENT & EVICTION DECOMPOSITION
    # =========================================================================
    elif primary_domain == "rent":
        if "sindh" in q_low or "srpo" in q_low or "karachi" in q_low:
            issues.append(LegalSubIssue(
                issue_id="issue_rent_srpo_eviction",
                heading="Eviction under Sindh Rented Premises Ordinance, 1979 (Sections 15, 16, 21 SRPO)",
                description="Ejectment application under Section 15 SRPO 1979 on default or personal need, and tentative rent deposit under Section 16.",
                controlling_statutes=["Sindh Rented Premises Ordinance, 1979"],
                controlling_provisions=["SRPO_1979_SEC_15", "SRPO_1979_SEC_16", "SRPO_1979_SEC_21"],
                search_queries=["Section 15 Section 16 SRPO 1979 eviction default tentative rent deposit", "Sindh rent appeal Section 21"],
                factual_anchors=["Sindh Rented Premises Ordinance", "SRPO", "Section 15"]
            ))
        else:
            issues.append(LegalSubIssue(
                issue_id="issue_rent_ejectment_grounds",
                heading="Ejectment Grounds: Default in Rent & Personal Bona Fide Need (Section 15, PRPA 2009)",
                description="Substantive grounds for ejectment under Section 15 of PRPA 2009: willful default and personal bona fide need.",
                controlling_statutes=["Punjab Rented Premises Act, 2009"],
                controlling_provisions=["PRPA_2009_SEC_15", "PRPA_2009_SEC_4"],
                search_queries=["Section 15 PRPA 2009 grounds for eviction default personal bona fide need", "Section 4 PRPA 2009 tenancy agreement"],
                factual_anchors=["Section 15", "Punjab Rented Premises Act, 2009", "default in payment of rent"]
            ))

            issues.append(LegalSubIssue(
                issue_id="issue_rent_leave_to_contest",
                heading="Leave to Contest Procedure & Mandatory 10-Day Limitation (Section 22, PRPA 2009)",
                description="Mandatory requirement under Section 22 PRPA 2009 to file application for leave to contest within ten days.",
                controlling_statutes=["Punjab Rented Premises Act, 2009"],
                controlling_provisions=["PRPA_2009_SEC_22", "PRPA_2009_SEC_19", "PRPA_2009_SEC_34"],
                search_queries=["Section 22 PRPA 2009 leave to contest 10 days limitation", "Section 34 PRPA 2009 bar of jurisdiction"],
                factual_anchors=["leave to contest", "Section 22 PRPA 2009", "10 days"]
            ))

        if any(k in q_low for k in ["cash", "receipt", "receipts", "refused"]):
            issues.append(LegalSubIssue(
                issue_id="issue_rent_payment_receipts",
                heading="Mode of Rent Payment & Duty to Issue Receipts (Section 4 & 15 PRPA 2009)",
                description="Statutory defense where tenant paid cash rent but landlord refused receipts.",
                controlling_statutes=["Punjab Rented Premises Act, 2009"],
                controlling_provisions=["PRPA_2009_SEC_4", "PRPA_2009_SEC_15"],
                search_queries=["Section 4 PRPA 2009 landlord duty to issue receipt cash payment defense", "default proof"],
                factual_anchors=["cash rent", "refused to issue receipts"]
            ))

        open_questions.append("Whether the tenant has bank records or postal money orders establishing payment of rent.")

    # =========================================================================
    # 3. BANKING RECOVERY DECOMPOSITION
    # =========================================================================
    elif primary_domain == "banking":
        issues.append(LegalSubIssue(
            issue_id="issue_banking_recovery_suit",
            heading="Banking Recovery Suit under Special Law (Sections 2, 9, 22 FIO 2001)",
            description="Statutory recovery suit by financial institution under Section 9 FIO 2001 and requirement of valid statement of account.",
            controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
            controlling_provisions=["FIO_2001_SEC_9", "FIO_2001_SEC_2", "FIO_2001_SEC_22"],
            search_queries=["Section 9 FIO 2001 recovery suit statement of account financial institution", "Section 22 FIO 2001 appeal"],
            factual_anchors=["Section 9", "Financial Institutions (Recovery of Finances) Ordinance, 2001", "FIO 2001"]
        ))

        issues.append(LegalSubIssue(
            issue_id="issue_banking_leave_to_defend",
            heading="Mandatory Leave to Defend & 30-Day Limitation (Section 10 FIO 2001)",
            description="Mandatory requirement under Section 10 FIO 2001 to file leave to defend within 30 days of service of summons.",
            controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
            controlling_provisions=["FIO_2001_SEC_10"],
            search_queries=["Section 10 FIO 2001 leave to defend 30 days mandatory limitation affidavit", "substantial question of law"],
            factual_anchors=["Section 10", "leave to defend", "30 days"]
        ))

        if any(k in q_low for k in ["compound", "mark-up", "markup", "penal", "interest", "excessive"]):
            issues.append(LegalSubIssue(
                issue_id="issue_banking_compound_markup",
                heading="Challenge to Compound Mark-up & Penal Interest (Sections 10 & 14 FIO 2001)",
                description="Substantive legal defense challenging unlawful compound mark-up and penal charges beyond finance agreement.",
                controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
                controlling_provisions=["FIO_2001_SEC_10", "FIO_2001_SEC_14"],
                search_queries=["Section 10 Section 14 FIO 2001 compound markup penal interest disallowed", "unconditional leave to defend"],
                factual_anchors=["compound mark-up", "penal interest", "finance agreement"]
            ))

        if any(k in q_low for k in ["mortgage", "sale without court", "section 15"]):
            issues.append(LegalSubIssue(
                issue_id="issue_banking_mortgage_sale",
                heading="Extra-Judicial Sale of Mortgaged Property (Section 15 FIO 2001)",
                description="Challenge to bank proceeding for sale of mortgaged property without intervention of court under Section 15 FIO.",
                controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
                controlling_provisions=["FIO_2001_SEC_15", "FIO_2001_SEC_9"],
                search_queries=["Section 15 FIO 2001 sale of mortgaged property without court intervention challenge", "notice requirements"],
                factual_anchors=["Section 15 FIO 2001", "mortgaged property", "sale without intervention"]
            ))

        open_questions.append("Whether the borrower has an independent ledger reconciliation showing agreed finance vs charged penal interest.")

    # =========================================================================
    # 4. CONSTITUTIONAL WRITS DECOMPOSITION
    # =========================================================================
    elif primary_domain == "constitutional":
        # Certiorari / Ultra Vires
        if any(k in q_low for k in ["certiorari", "quash", "cancellation", "without lawful authority", "license", "order", "arbitrary"]):
            issues.append(LegalSubIssue(
                issue_id="issue_const_writ_certiorari",
                heading="Writ of Certiorari for Judicial Review of Public Action (Article 199(1)(a)(ii) Constitution 1973)",
                description="Constitutional challenge to executive orders passed without lawful authority or in violation of natural justice.",
                controlling_statutes=["Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CONST_1973_ART_199", "CONST_1973_ART_4", "CONST_1973_ART_10A"],
                search_queries=["Article 199(1)(a)(ii) Constitution 1973 writ of certiorari order without lawful authority", "principles of natural justice audi alteram partem"],
                factual_anchors=["Article 199", "without lawful authority", "certiorari"]
            ))

        # Mandamus
        if any(k in q_low for k in ["mandamus", "compel", "statutory duty", "refused to perform", "sanction", "public body"]):
            issues.append(LegalSubIssue(
                issue_id="issue_const_writ_mandamus",
                heading="Writ of Mandamus to Compel Public Duty (Article 199(1)(a)(i) Constitution 1973)",
                description="Constitutional remedy directing public authorities to perform statutory duties required by law.",
                controlling_statutes=["Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CONST_1973_ART_199", "CONST_1973_ART_4"],
                search_queries=["Article 199(1)(a)(i) Constitution 1973 writ of mandamus compel statutory duty public officer", "failure of public authority to act"],
                factual_anchors=["mandamus", "statutory duty", "compel"]
            ))

        # Habeas Corpus
        if any(k in q_low for k in ["habeas corpus", "unlawful detention", "police custody", "detenue", "missing", "illegal detention", "without production"]):
            issues.append(LegalSubIssue(
                issue_id="issue_const_writ_habeas_corpus",
                heading="Writ of Habeas Corpus Against Unlawful Detention (Article 199(1)(b)(i) & Section 61 CrPC)",
                description="Constitutional remedy to set at liberty any person held in unlawful custody by police or private parties.",
                controlling_statutes=["Constitution of the Islamic Republic of Pakistan, 1973", "Code of Criminal Procedure, 1898"],
                controlling_provisions=["CONST_1973_ART_199", "CONST_1973_ART_9", "CRPC_1898_SEC_61"],
                search_queries=["Article 199(1)(b)(i) Constitution 1973 writ of habeas corpus illegal detention police", "Section 61 CrPC detention over 24 hours"],
                factual_anchors=["habeas corpus", "unlawful detention", "detenue"]
            ))

        # Property Expropriation / Art 24
        if any(k in q_low for k in ["expropriat", "property rights", "acquisition", "taking possession", "article 24"]):
            issues.append(LegalSubIssue(
                issue_id="issue_const_property_protection",
                heading="Protection of Property Rights Against Compulsory Deprivation (Article 24 Constitution 1973)",
                description="Enforcement of fundamental right that no person shall be compulsorily deprived of property save by authority of law.",
                controlling_statutes=["Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CONST_1973_ART_199", "CONST_1973_ART_24", "CONST_1973_ART_4"],
                search_queries=["Article 24 Constitution 1973 compulsory acquisition compensation authority of law", "protection of property rights writ"],
                factual_anchors=["Article 24", "property rights", "acquisition without compensation"]
            ))

        if not issues:
            issues.append(LegalSubIssue(
                issue_id="issue_const_fundamental_rights",
                heading="Enforcement of Fundamental Rights & Due Process (Article 199 & Article 4 Constitution 1973)",
                description="Constitutional petition for protection of fundamental rights and procedural due process.",
                controlling_statutes=["Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CONST_1973_ART_199", "CONST_1973_ART_4", "CONST_1973_ART_10A"],
                search_queries=["Article 199 Constitution 1973 fundamental rights due process fair trial Article 10A"],
                factual_anchors=["Article 199", "fundamental rights"]
            ))

        open_questions.append("Whether an alternate adequate statutory remedy exists under the governing statute before invoking Article 199 writ jurisdiction.")

    # =========================================================================
    # 5. SERVICE TRIBUNAL & CIVIL SERVANTS DECOMPOSITION
    # =========================================================================
    elif primary_domain == "service":
        if any(k in q_low for k in ["seniority", "seniority list"]):
            issues.append(LegalSubIssue(
                issue_id="issue_service_seniority_dispute",
                heading="Civil Servant Seniority Dispute (Section 8 Civil Servants Act 1973 & Art 212 Constitution)",
                description="Determination of seniority of civil servants and legal remedies against altered seniority lists.",
                controlling_statutes=["Civil Servants Act, 1973", "Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CIVIL_SERVANTS_1973_SEC_8", "CONST_1973_ART_212"],
                search_queries=["Section 8 Civil Servants Act 1973 seniority list dispute Service Tribunal", "Article 212 Constitution bar"],
                factual_anchors=["seniority list", "Section 8 Civil Servants Act", "Article 212"]
            ))

        if any(k in q_low for k in ["promotion", "superseded", "supersession"]):
            issues.append(LegalSubIssue(
                issue_id="issue_service_promotion_eligibility",
                heading="Promotion Eligibility vs Vested Right (Section 9 Civil Servants Act 1973 & Art 212)",
                description="Legal right of civil servant to be considered for promotion in accordance with eligibility rules.",
                controlling_statutes=["Civil Servants Act, 1973", "Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CIVIL_SERVANTS_1973_SEC_9", "CONST_1973_ART_212"],
                search_queries=["Section 9 Civil Servants Act 1973 consideration for promotion eligibility Service Tribunal", "Article 212 bar"],
                factual_anchors=["promotion", "Section 9 Civil Servants Act"]
            ))

        if any(k in q_low for k in ["dismissal", "removal", "compulsory retirement", "inquiry", "disciplinary", "reversion", "tenure"]):
            issues.append(LegalSubIssue(
                issue_id="issue_service_disciplinary_removal",
                heading="Disciplinary Penalties & Terms of Service (Section 4 Civil Servants Act 1973 & Art 212)",
                description="Challenge to major penalties of dismissal, removal, or reversion, and mandatory departmental appeal.",
                controlling_statutes=["Civil Servants Act, 1973", "Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CIVIL_SERVANTS_1973_SEC_4", "CONST_1973_ART_212"],
                search_queries=["Section 4 Civil Servants Act 1973 terms of service tenure disciplinary inquiry removal Service Tribunal", "departmental appeal requirement"],
                factual_anchors=["dismissal", "removal", "Civil Servants Act", "Article 212"]
            ))

        if not issues:
            issues.append(LegalSubIssue(
                issue_id="issue_service_general_terms",
                heading="Civil Servant Terms and Conditions of Service (Civil Servants Act 1973 & Art 212)",
                description="Exclusive jurisdiction of Service Tribunal over terms and conditions of civil servants and bar under Article 212.",
                controlling_statutes=["Civil Servants Act, 1973", "Constitution of the Islamic Republic of Pakistan, 1973"],
                controlling_provisions=["CIVIL_SERVANTS_1973_SEC_4", "CONST_1973_ART_212"],
                search_queries=["Article 212 Constitution 1973 Service Tribunal exclusive jurisdiction civil servant terms of service"],
                factual_anchors=["Civil Servants Act", "Service Tribunal", "Article 212"]
            ))

        open_questions.append("Whether the civil servant has filed a timely departmental appeal and waited 90 days before invoking Service Tribunal jurisdiction.")

    # =========================================================================
    # 7. LAND & PROPERTY REVENUE DECOMPOSITION
    # =========================================================================
    elif is_land_revenue_signal or "land_revenue" in q_low:
        if any(k in q_low for k in ["mutation", "intiqal", "patwari", "section 42"]):
            issues.append(LegalSubIssue(
                issue_id="issue_revenue_mutation_challenge",
                heading="Challenge to Mutation of Agricultural Land (Section 42 & 52 Land Revenue Act 1967)",
                description="Sanctioning of mutation in Record of Rights and legal challenge to forged mutations.",
                controlling_statutes=["West Pakistan Land Revenue Act, 1967"],
                controlling_provisions=["LAND_REVENUE_1967_SEC_42", "LAND_REVENUE_1967_SEC_52"],
                search_queries=["Section 42 Land Revenue Act 1967 sanctioning of mutation procedure revenue officer", "forged mutation challenge"],
                factual_anchors=["mutation", "intiqal", "Section 42 Land Revenue Act"]
            ))

        if any(k in q_low for k in ["record of rights", "jamabandi", "presumption", "section 52"]):
            issues.append(LegalSubIssue(
                issue_id="issue_revenue_record_of_rights",
                heading="Presumption of Correctness of Record of Rights (Section 52 Land Revenue Act 1967)",
                description="Statutory presumption of correctness of entries in periodic Record of Rights (Jamabandi).",
                controlling_statutes=["West Pakistan Land Revenue Act, 1967"],
                controlling_provisions=["LAND_REVENUE_1967_SEC_52", "LAND_REVENUE_1967_SEC_42"],
                search_queries=["Section 52 Land Revenue Act 1967 presumption of truth entries Jamabandi Record of Rights", "rebuttal of presumption"],
                factual_anchors=["Record of Rights", "Jamabandi", "Section 52"]
            ))

        if any(k in q_low for k in ["partition", "section 135", "joint holding", "revenue partition"]):
            issues.append(LegalSubIssue(
                issue_id="issue_revenue_agricultural_partition",
                heading="Partition of Agricultural Land Holding (Section 135 & 172 Land Revenue Act 1967)",
                description="Partition of joint agricultural holding before Revenue Officer and exclusion of civil court jurisdiction under Section 172.",
                controlling_statutes=["West Pakistan Land Revenue Act, 1967"],
                controlling_provisions=["LAND_REVENUE_1967_SEC_135", "LAND_REVENUE_1967_SEC_172"],
                search_queries=["Section 135 Section 172 Land Revenue Act 1967 partition agricultural land Revenue Officer", "bar of civil court jurisdiction"],
                factual_anchors=["Section 135 Land Revenue Act", "partition of agricultural land", "Section 172"]
            ))

        if any(k in q_low for k in ["illegal dispossession", "land grabber"]):
            issues.append(LegalSubIssue(
                issue_id="issue_illegal_dispossession_remedy",
                heading="Restoration of Possession under Illegal Dispossession Act 2005 (Sections 3, 5, 8)",
                description="Special criminal complaint before Sessions Court for recovery of property from land grabbers.",
                controlling_statutes=["Illegal Dispossession Act, 2005"],
                controlling_provisions=["ILLEGAL_DISPOSSESSION_2005_SEC_3", "ILLEGAL_DISPOSSESSION_2005_SEC_5", "ILLEGAL_DISPOSSESSION_2005_SEC_8"],
                search_queries=["Section 3 Section 5 Section 8 Illegal Dispossession Act 2005 complaint Sessions Court", "restoration of possession"],
                factual_anchors=["Illegal Dispossession Act", "Section 3", "land grabbers"]
            ))

        if not issues:
            issues.append(LegalSubIssue(
                issue_id="issue_revenue_jurisdiction_bar",
                heading="Revenue Jurisdiction & Civil Court Bar (Section 172 Land Revenue Act 1967)",
                description="Exclusion of civil court jurisdiction in matters falling within exclusive competence of Revenue Officers.",
                controlling_statutes=["West Pakistan Land Revenue Act, 1967"],
                controlling_provisions=["LAND_REVENUE_1967_SEC_172", "LAND_REVENUE_1967_SEC_135"],
                search_queries=["Section 172 Land Revenue Act 1967 exclusion of civil court jurisdiction revenue matters"],
                factual_anchors=["Section 172 Land Revenue Act", "Revenue Officer"]
            ))

        open_questions.append("Whether an appeal or revision has been filed before the Collector or Commissioner under Section 161 of the Land Revenue Act.")

    # =========================================================================
    # 8. PECA CYBERCRIME DETERMINISTIC BRANCH & IP DECOMPOSITION
    # =========================================================================
    elif is_peca_signal or primary_domain == "cybercrime":
        # Sub-issue 1: Specific PECA Section Alleged (Dignity, Modesty, Fraud)
        issues.append(LegalSubIssue(
            issue_id="issue_peca_specific_section_alleged",
            heading="Specific PECA Section Alleged: Dignity, Modesty & Electronic Fraud (Sections 20, 21, 10 PECA 2016)",
            description="Identification of the specific substantive cybercrime offences alleged under PECA 2016: offences against dignity of natural person (Section 20), cyberstalking and modesty (Section 21), and electronic fraud / cyber-terrorism (Section 10).",
            controlling_statutes=["Prevention of Electronic Crimes Act, 2016"],
            controlling_provisions=["PECA_2016_SEC_20", "PECA_2016_SEC_21", "PECA_2016_SEC_10"] + (["PECA_2016_SEC_3"] if any(k in q_low for k in ["unauthorized access", "hacking"]) else []),
            search_queries=[
                "Section 20 Section 21 Section 10 PECA 2016 cybercrime dignity cyberstalking electronic fraud",
                "Section 20 PECA online defamation false information"
            ],
            factual_anchors=["PECA 2016", "online defamation", "cyberstalking", "electronic fraud"]
        ))

        # Sub-issue 2: Punishment & Prohibitory Clause Applicability
        issues.append(LegalSubIssue(
            issue_id="issue_peca_punishment_prohibitory_clause",
            heading="Punishment & Prohibitory Clause Applicability (Section 497 CrPC & Section 43 PECA 2016)",
            description="Examination of the maximum statutory punishment under the alleged PECA sections, determining whether offences fall outside the prohibitory clause of Section 497 CrPC (punishable with less than 10 years) and are bailable under Section 43 PECA 2016.",
            controlling_statutes=["Code of Criminal Procedure, 1898", "Prevention of Electronic Crimes Act, 2016"],
            controlling_provisions=["CRPC_1898_SEC_498", "CRPC_1898_SEC_497", "PECA_2016_SEC_20"],
            search_queries=[
                "Section 43 PECA bailable non-bailable offences prohibitory clause Section 497 CrPC",
                "punishment under Section 20 Section 21 PECA 2016"
            ],
            factual_anchors=["prohibitory clause", "punishment under PECA", "Section 43 PECA"]
        ))

        # Sub-issue 3: FIA procedure under PECA
        issues.append(LegalSubIssue(
            issue_id="issue_peca_fia_procedure",
            heading="FIA Notice, Inquiry & Investigation Procedure under PECA (Section 5 FIA Act 1974)",
            description="Procedural legality of FIA Cyber Crime Wing inquiry, call-up notice, registration of FIR, and statutory powers of investigation under Section 5 of the Federal Investigation Agency Act, 1974 read with PECA 2016.",
            controlling_statutes=["Federal Investigation Agency Act, 1974", "Prevention of Electronic Crimes Act, 2016"],
            controlling_provisions=["FIA_1974_SEC_5"],
            search_queries=[
                "Section 5 FIA Act 1974 inquiry call-up notice cyber crime wing powers investigation",
                "FIA procedure under PECA 2016 inquiry notice"
            ],
            factual_anchors=["FIA notice", "FIA Cyber Crime Wing", "Section 5 FIA Act 1974"]
        ))

        # Sub-issue 4: Pre-arrest bail under Section 498 CrPC
        issues.append(LegalSubIssue(
            issue_id="issue_peca_pre_arrest_bail",
            heading="Pre-Arrest Bail in Cybercrime Offences (Section 498 CrPC)",
            description="Entitlement to pre-arrest bail under Section 498 CrPC in respect of allegations under PECA 2016 on grounds of mala fides, ulterior motives, false implication, or absence of prima facie electronic evidence.",
            controlling_statutes=["Code of Criminal Procedure, 1898"],
            controlling_provisions=["CRPC_1898_SEC_498"],
            search_queries=[
                "Section 498 CrPC pre-arrest bail PECA 2016 cybercrime mala fides ulterior motive",
                "pre-arrest bail Section 20 PECA online defamation"
            ],
            factual_anchors=["pre-arrest bail", "Section 498 CrPC", "mala fides"]
        ))

        open_questions.append("Whether an FIR has been registered by the FIA Cyber Crime Wing or only a call-up notice / inquiry is pending.")
        open_questions.append("Whether the alleged digital material was publicly exhibited on an information system as required under Section 20 of PECA 2016.")

    elif is_cyber_ip_signal or primary_domain == "intellectual_property":
        if any(k in q_low for k in ["peca", "hacking", "unauthorized access", "cybercrime"]):
            issues.append(LegalSubIssue(
                issue_id="issue_cyber_unauthorized_access",
                heading="Offence of Unauthorized Access to Information System (Section 3 PECA 2016)",
                description="Criminal offence under Section 3 PECA 2016 for unauthorized access to data or information system.",
                controlling_statutes=["Prevention of Electronic Crimes Act, 2016"],
                controlling_provisions=["PECA_2016_SEC_3", "PECA_2016_SEC_10"],
                search_queries=["Section 3 PECA 2016 unauthorized access information system data cybercrime", "FIA cyber crime wing"],
                factual_anchors=["PECA 2016", "unauthorized access", "hacking"]
            ))

        if any(k in q_low for k in ["harassment", "cyberstalking", "cyber stalking", "blackmail", "modesty"]):
            issues.append(LegalSubIssue(
                issue_id="issue_cyber_harassment_modesty",
                heading="Cyber Harassment & Offences Against Modesty (Section 21 PECA 2016)",
                description="Offence of cyber stalking, blackmailing, and transmitting sexually explicit material or harassment online.",
                controlling_statutes=["Prevention of Electronic Crimes Act, 2016"],
                controlling_provisions=["PECA_2016_SEC_21", "PECA_2016_SEC_16"],
                search_queries=["Section 21 PECA 2016 cyber harassment offences against modesty natural person minor", "social media blackmail"],
                factual_anchors=["cyber harassment", "Section 21 PECA", "blackmail"]
            ))

        if any(k in q_low for k in ["impersonation", "identity theft", "fake account"]):
            issues.append(LegalSubIssue(
                issue_id="issue_cyber_identity_theft",
                heading="Unauthorized Use of Identity Information (Section 16 PECA 2016)",
                description="Criminal offence under Section 16 PECA 2016 for electronic impersonation and identity theft.",
                controlling_statutes=["Prevention of Electronic Crimes Act, 2016"],
                controlling_provisions=["PECA_2016_SEC_16", "PECA_2016_SEC_3"],
                search_queries=["Section 16 PECA 2016 unauthorized use identity information fake account impersonation", "electronic forgery"],
                factual_anchors=["Section 16 PECA", "fake account", "identity theft"]
            ))

        if any(k in q_low for k in ["trademark", "trade mark", "passing off", "counterfeit"]):
            issues.append(LegalSubIssue(
                issue_id="issue_ip_trademark_infringement",
                heading="Trademark Infringement & Action for Passing Off (Sections 40 & 46 Trade Marks Ordinance 2001)",
                description="Civil and injunctive remedy for unauthorized use of registered trademark and passing off counterfeit goods.",
                controlling_statutes=["Trade Marks Ordinance, 2001"],
                controlling_provisions=["TRADEMARKS_2001_SEC_40", "TRADEMARKS_2001_SEC_46"],
                search_queries=["Section 40 Section 46 Trade Marks Ordinance 2001 infringement passing off deceptively similar mark", "counterfeit goods injunction"],
                factual_anchors=["trademark infringement", "Trade Marks Ordinance 2001", "passing off"]
            ))

        if any(k in q_low for k in ["copyright", "software piracy", "pirated", "infringement of copyright"]):
            issues.append(LegalSubIssue(
                issue_id="issue_ip_copyright_infringement",
                heading="Copyright Infringement & Remedies (Sections 56 & 60 Copyright Ordinance 1962)",
                description="Statutory civil remedies and criminal penalties for reproduction of copyrighted works and software piracy.",
                controlling_statutes=["Copyright Ordinance, 1962"],
                controlling_provisions=["COPYRIGHT_1962_SEC_56", "COPYRIGHT_1962_SEC_60"],
                search_queries=["Section 56 Section 60 Copyright Ordinance 1962 copyright infringement software piracy civil remedies", "injunction damages"],
                factual_anchors=["copyright infringement", "Copyright Ordinance 1962", "software piracy"]
            ))

        open_questions.append("Whether a formal complaint has been lodged with the FIA Cyber Crime Wing or an infringement notice served.")

    # =========================================================================
    # 9. FAMILY PROPERTY & INHERITANCE DECOMPOSITION
    # =========================================================================
    elif is_inheritance_signal:
        issues.append(LegalSubIssue(
            issue_id="issue_inheritance_shariat_shares",
            heading="Muslim Personal Law Shariat Distribution of Inheritance (Sections 2 & 3 Shariat Act 1962)",
            description="Devolution of estate upon legal heirs in accordance with Islamic Shariat shares immediately upon death.",
            controlling_statutes=["West Pakistan Muslim Personal Law (Shariat) Application Act, 1962"],
            controlling_provisions=["SHARIAT_APPLICATION_1962_SEC_2", "SHARIAT_APPLICATION_1962_SEC_3"],
            search_queries=["Section 2 Section 3 West Pakistan Muslim Personal Law Shariat Application Act 1962 inheritance shares legal heirs", "Quranic sharers residuaries"],
            factual_anchors=["inheritance", "legal heirs", "Shariat Application Act 1962"]
        ))

        issues.append(LegalSubIssue(
            issue_id="issue_inheritance_partition_suit",
            heading="Partition of Joint Inherited Property (Order XX Rule 18 CPC & Sections 2, 4 Partition Act 1893)",
            description="Suit for partition of joint family property, appointment of local commissioner, and preliminary/final decree.",
            controlling_statutes=["Code of Civil Procedure, 1908", "Partition Act, 1893"],
            controlling_provisions=["CPC_1908_ORD_XX_R_18", "PARTITION_1893_SEC_2", "PARTITION_1893_SEC_4"],
            search_queries=["Order XX Rule 18 CPC suit for partition inherited property preliminary decree final decree", "Section 2 Section 4 Partition Act 1893 sale of property"],
            factual_anchors=["partition of inherited property", "Order XX Rule 18 CPC", "Partition Act 1893"]
        ))

        if any(k in q_low for k in ["sister", "women", "deprived", "female heir", "refusing sister"]):
            issues.append(LegalSubIssue(
                issue_id="issue_inheritance_women_deprivation",
                heading="Protection of Women's Property & Inheritance Rights (Sections 4 & 5 Women's Property Rights Act 2020 & 498-A PPC)",
                description="Statutory remedy before Ombudsperson and criminal prosecution under Section 498-A PPC against deprivation of female heirs.",
                controlling_statutes=["Enforcement of Women's Property Rights Act, 2020", "Pakistan Penal Code, 1860"],
                controlling_provisions=["WOMEN_PROPERTY_RIGHTS_2020_SEC_4", "WOMEN_PROPERTY_RIGHTS_2020_SEC_5", "PPC_1860_SEC_498A"],
                search_queries=["Section 4 Enforcement of Women Property Rights Act 2020 Ombudsperson complaint female inheritance", "Section 498-A PPC depriving woman of property"],
                factual_anchors=["sister's share", "Women's Property Rights Act 2020", "Section 498-A PPC"]
            ))

        if any(k in q_low for k in ["benami", "fictitious name"]):
            issues.append(LegalSubIssue(
                issue_id="issue_inheritance_benami_challenge",
                heading="Benami Property Challenge by Legal Heirs (Sections 3 & 4 Benami Act 2017)",
                description="Challenge to property purchased by deceased in the name of one child or family member as a benami holding.",
                controlling_statutes=["Benami Transactions (Prohibition) Act, 2017"],
                controlling_provisions=["BENAMI_2017_SEC_3", "BENAMI_2017_SEC_4"],
                search_queries=["Section 3 Section 4 Benami Transactions Prohibition Act 2017 property held in name of child estate of deceased", "source of funds ostensible owner"],
                factual_anchors=["benami", "Benami Act 2017", "legal heirs"]
            ))

        open_questions.append("Whether a Succession Certificate or Letter of Administration has been issued by NADRA or the competent Civil Court.")

    # =========================================================================
    # =========================================================================
    # CRIMINAL LAW (THEFT, CBT, CHEATING, MURDER, BAIL, QUASHMENT)
    # =========================================================================
    elif primary_domain == "criminal":
        if is_cheque_signal:
            issues.append(LegalSubIssue(
                issue_id="issue_cheque_dishonour_489f",
                heading="Criminal Offence of Dishonestly Issuing a Cheque (Section 489-F PPC & Order XXXVII CPC)",
                description="Prosecution for bounced cheque issued towards loan repayment or fulfillment of obligation under Section 489-F PPC.",
                controlling_statutes=["Pakistan Penal Code, 1860", "Code of Civil Procedure, 1908"],
                controlling_provisions=["PPC_1860_SEC_489F", "CPC_1908_ORD_XXXVII_R_1"],
                search_queries=["Section 489-F PPC dishonour of cheque dishonest issuance loan repayment", "Order XXXVII CPC summary recovery"],
                factual_anchors=["cheque", "dishonoured", "489-F PPC"]
            ))

        has_theft = any(k in q_low for k in ["theft", "379", "378", "stolen", "machinery"])
        has_cheating = any(k in q_low for k in ["cheating", "420", "415", "fraud", "deceiv", "dishonest inducement"])
        has_cbt = any(k in q_low for k in ["breach of trust", "406", "405", "409", "misappropriat", "entrustment"])

        if has_theft or any(k in q_low for k in ["stolen", "recovery of stolen", "recovery of vehicle", "411"]):
            issues.append(LegalSubIssue(
                issue_id="issue_theft_379_ppc",
                heading="Offence of Theft & Recovery of Stolen Property (Sections 379 & 411 PPC 1860, Section 103 CrPC)",
                description="Statutory ingredients of theft under Section 379 PPC, dishonestly receiving stolen property under Section 411 PPC, and recovery memo under Section 103 CrPC.",
                controlling_statutes=["Pakistan Penal Code, 1860", "Code of Criminal Procedure, 1898"],
                controlling_provisions=["PPC_1860_SEC_379", "PPC_1860_SEC_411", "CRPC_1898_SEC_103"],
                search_queries=["Section 379 Section 411 PPC theft receiving stolen property recovery memo Section 103 CrPC", "recovery of stolen vehicle independent witnesses"],
                factual_anchors=["theft", "stolen property", "Section 411 PPC", "Section 103 CrPC"]
            ))

        if has_cheating:
            issues.append(LegalSubIssue(
                issue_id="issue_cheating_420_ppc",
                heading="Offence of Cheating and Dishonestly Inducing Delivery (Sections 415 & 420 PPC 1860)",
                description="Statutory ingredients of cheating under Section 415 PPC requiring dishonest inducement at inception.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["PPC_1860_SEC_415", "PPC_1860_SEC_420"],
                search_queries=["Section 415 Section 420 PPC cheating dishonest intention at inception delivery of property", "breach of contract vs cheating"],
                factual_anchors=["cheating", "Section 420 PPC"]
            ))

        if has_cbt:
            issues.append(LegalSubIssue(
                issue_id="issue_cbt_406_ppc",
                heading="Criminal Breach of Trust (Sections 405 & 406 Pakistan Penal Code, 1860)",
                description="Statutory ingredients of criminal breach of trust under Section 405 PPC requiring entrustment and misappropriation.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["PPC_1860_SEC_405", "PPC_1860_SEC_406"],
                search_queries=["Section 405 Section 406 PPC criminal breach of trust entrustment dishonest misappropriation", "commercial dispute civil liability"],
                factual_anchors=["criminal breach of trust", "Section 406 PPC"]
            ))

        if any(k in q_low for k in ["302", "murder", "qatl"]):
            issues.append(LegalSubIssue(
                issue_id="issue_murder_302_ppc",
                heading="Substantive Penal Offence of Murder (Section 302 Pakistan Penal Code, 1860)",
                description="Offence of Qatl-i-Amd under Section 302 PPC clauses (a), (b), (c) and fasad-fil-arz proviso.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["PPC_1860_SEC_302"],
                search_queries=["Section 302 PPC punishment for murder qatl-i-amd ingredients clauses", "Section 302 clause b PPC tazir"],
                factual_anchors=["Section 302 PPC", "murder", "qatl"]
            ))

        if any(k in q_low for k in ["bail", "pre-arrest", "post-arrest", "498", "497", "496"]):
            issues.append(LegalSubIssue(
                issue_id="issue_criminal_bail_498_497",
                heading="Pre-Arrest & Post-Arrest Bail Jurisprudence (Sections 498, 497 & 496 CrPC 1898)",
                description="Pre-arrest bail under Section 498 CrPC based on mala fides or ulterior motives, and post-arrest bail under Section 497 CrPC.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_498", "CRPC_1898_SEC_497", "CRPC_1898_SEC_496"],
                search_queries=["Section 498 Section 497 CrPC pre-arrest bail mala fide ulterior motive arrest humiliation", "Section 497 CrPC non-bailable further inquiry"],
                factual_anchors=["pre-arrest bail", "Section 498 CrPC", "bail"]
            ))

        # Quashment of FIR & Abuse of Process
        if any(k in q_low for k in ["561-a", "561a", "quash", "quashment", "abuse of process", "second fir", "249-a", "249a", "265-k", "265k"]):
            issues.append(LegalSubIssue(
                issue_id="issue_quashment_561a_crpc",
                heading="Inherent Powers of High Court for Quashment of FIR (Section 561-A CrPC 1898)",
                description="Quashment of criminal proceedings where FIR is lodged to exert coercive pressure for commercial breach of contract.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_561A"],
                search_queries=["Section 561-A CrPC quashment of FIR commercial transaction cancelled agreement civil dispute", "abuse of process of court"],
                factual_anchors=["quashment", "Section 561-A CrPC", "FIR"]
            ))

        if any(k in q_low for k in ["second fir", "earlier inquiry"]):
            issues.append(LegalSubIssue(
                issue_id="issue_quashment_second_fir",
                heading="Bar on Second FIR on Same Transaction (Section 154 & 561-A CrPC)",
                description="Quashment of subsequent FIR registered on identical factual narrative.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_561A", "CRPC_1898_SEC_154"],
                search_queries=["Section 154 Section 561-A CrPC second FIR registration barred same transaction", "quashment second FIR"],
                factual_anchors=["second FIR", "Section 154 CrPC", "Section 561-A CrPC"]
            ))

        if any(k in q_low for k in ["249-a", "249a"]):
            issues.append(LegalSubIssue(
                issue_id="issue_magistrate_early_acquittal",
                heading="Early Acquittal by Magistrate (Section 249-A CrPC 1898)",
                description="Application before trial Magistrate for early acquittal where charge is groundless.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_249A", "CRPC_1898_SEC_561A"],
                search_queries=["Section 249-A CrPC early acquittal groundless charge Magistrate power any stage", "no probability of conviction"],
                factual_anchors=["Section 249-A CrPC", "early acquittal", "Magistrate"]
            ))

        if any(k in q_low for k in ["265-k", "265k"]):
            issues.append(LegalSubIssue(
                issue_id="issue_sessions_early_acquittal",
                heading="Early Acquittal by Court of Session (Section 265-K CrPC 1898)",
                description="Application before Sessions Court for acquittal at any stage of trial under Section 265-K CrPC.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_265K", "CRPC_1898_SEC_561A"],
                search_queries=["Section 265-K CrPC early acquittal Sessions Court no probability of conviction any stage"],
                factual_anchors=["Section 265-K CrPC", "Sessions Court", "early acquittal"]
            ))

        if not issues:
            issues.append(LegalSubIssue(
                issue_id="issue_criminal_fir_investigation",
                heading="Criminal FIR & Statutory Investigation (Sections 154, 156, 173 CrPC 1898)",
                description="Cognizable offence reporting under Section 154 CrPC and police report under Section 173 CrPC.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_154", "CRPC_1898_SEC_497"],
                search_queries=["Section 154 Section 173 CrPC cognizable offence FIR investigation challan"],
                factual_anchors=["FIR", "police investigation"]
            ))

        open_questions.append("Whether there is any recovery of property or documentary proof demonstrating fraudulent intent at the inception of the contract.")

    # =========================================================================
    # 10A. CORPORATE OPPRESSION & MISMANAGEMENT
    # =========================================================================
    elif primary_domain == "corporate":
        issues.append(LegalSubIssue(
            issue_id="issue_corporate_oppression_mismanagement",
            heading="Oppression and Mismanagement by Majority Directors (Sections 286-288 Companies Act 2017)",
            description="Petition before Company Bench against fraudulent diversion or siphoning of corporate assets and illegal share allotment.",
            controlling_statutes=["Companies Act, 2017"],
            controlling_provisions=["COMPANIES_2017_SEC_286", "COMPANIES_2017_SEC_287"],
            search_queries=[
                "Section 286 Companies Act 2017 oppression and mismanagement directors siphoning company assets",
                "Section 287 powers of company bench interim relief"
            ],
            factual_anchors=["directors", "siphoning", "shares", "Companies Act"]
        ))
        if any(k in q_low for k in ["409", "criminal breach of trust", "misappropriat"]):
            issues.append(LegalSubIssue(
                issue_id="issue_corporate_breach_of_trust_director",
                heading="Criminal Breach of Trust by Director (Section 409 PPC 1860)",
                description="Penal liability for criminal breach of trust committed by director or officer of company having dominion over corporate funds.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["PPC_1860_SEC_409"],
                search_queries=["Section 409 PPC criminal breach of trust director company funds dominion"],
                factual_anchors=["director", "misappropriation", "Section 409 PPC"]
            ))

    # =========================================================================
    # 10B. CIVIL EXECUTION & ARREST OF JUDGMENT DEBTOR
    # =========================================================================
    if is_civil_execution or any(k in q_low for k in ["judgment debtor", "execution of decree", "section 55 cpc", "arrest of judgment debtor", "order xxi"]):
        issues.append(LegalSubIssue(
            issue_id="issue_civil_execution_arrest_debtor",
            heading="Execution of Money Decree & Arrest of Judgment Debtor (Sections 51 & 55, Order XXI Rule 37 CPC)",
            description="Statutory procedure for execution of decree against person of judgment debtor; mandatory requirement of show-cause notice and proof of means before detention in civil prison.",
            controlling_statutes=["Code of Civil Procedure, 1908"],
            controlling_provisions=["CPC_1908_SEC_55", "CPC_1908_SEC_51", "CPC_1908_ORD_XXI_R_37"],
            search_queries=[
                "Section 55 CPC arrest detention judgment debtor civil prison execution money decree",
                "Order XXI Rule 37 CPC notice before arrest show cause means to pay"
            ],
            factual_anchors=["judgment debtor", "Section 55 CPC", "execution of decree", "warrant of arrest"]
        ))

    # =========================================================================
    # 11. CIVIL SPECIFIC PERFORMANCE
    # =========================================================================
    elif is_sale_specific_perf:
        issues.append(LegalSubIssue(
            issue_id="issue_specific_performance_immovable_property",
            heading="Specific Performance of Agreement to Sell Immovable Property (Sections 12, 19, 21, 22 SRA 1877)",
            description="Enforceability of agreement to sell immovable property under Section 12 SRA and compensation under Section 73 Contract Act.",
            controlling_statutes=["Specific Relief Act, 1877", "Contract Act, 1872"],
            controlling_provisions=["SRA_1877_SEC_12", "SRA_1877_SEC_19", "SRA_1877_SEC_21", "SRA_1877_SEC_22", "CONTRACT_1872_SEC_73"],
            search_queries=["Section 12 Specific Relief Act 1877 presumption immovable property agreement to sell", "Section 22 SRA discretion of court"],
            factual_anchors=["agreement to sell", "plot", "sale deed", "specific performance"]
        ))
        open_questions.append("Whether the vendee was always ready and willing to perform their reciprocal obligations.")

    # =========================================================================
    # 12. GENERAL CIVIL FALLBACK
    # =========================================================================
    if not issues:
        issues.append(LegalSubIssue(
            issue_id="issue_general_civil_remedy",
            heading="Civil Relief & Statutory Grounds (Sections 9 & 151 CPC 1908)",
            description="Examination of rights, cause of action, and competent civil remedies.",
            controlling_statutes=["Code of Civil Procedure, 1908"],
            controlling_provisions=["CPC_1908_SEC_9", "CPC_1908_SEC_151"],
            search_queries=[query_text],
            factual_anchors=[]
        ))

    named_cids = extract_named_statute_canonical_ids(query_text)
    return FactPatternDecomposition(
        primary_domain=primary_domain,
        issues=issues,
        open_questions=open_questions,
        named_statute_canonical_ids=named_cids
    )
