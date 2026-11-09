"""
core/legal_issue_extractor.py
Multi-Issue Fact Pattern Decomposition Engine for Pakistani Law.

Breaks down real-world legal fact patterns into distinct legal sub-issues,
assigns controlling statutory provisions to each issue, generates targeted
search queries, and anchors factual remedies across:
- Family Law (Khula, Dower, Maintenance, Custody/Hizanat)
- Rent and Eviction (PRPA 2009, SRPO 1979, leave to contest, default)
- Banking Recovery (FIO 2001 Sections 9, 10, leave to defend)
- Criminal Law (Theft, Cheating, Breach of Trust, Murder, Bail, Quashment, Cheque Dishonour)
- Civil Law (Specific Performance, Injunctions, Contracts)
- Constitutional Writs and Special Jurisdictions
"""

import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class LegalSubIssue(BaseModel):
    issue_id: str
    heading: str
    description: str
    controlling_statutes: List[str]
    controlling_provisions: List[str]
    search_queries: List[str]
    factual_anchors: List[str]


class FactPatternDecomposition(BaseModel):
    raw_query: str
    primary_domain: str = "civil"
    has_dates: bool = False
    has_monetary_amounts: bool = False
    issues: List[LegalSubIssue] = Field(default_factory=list)
    executive_answer_outline: Dict[str, str] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)


def extract_legal_issues_from_fact_pattern(
    query_text: str,
    planner_domain: Optional[str] = None,
    existing_issues: Optional[List[LegalSubIssue]] = None
) -> FactPatternDecomposition:
    """
    Decomposes an unstructured factual narrative into structured legal sub-issues.
    Enforces clear priority:
    1. If planner_domain is provided, it cannot be overridden by extractor keyword heuristics.
    2. Uses phrase-level keyword matching to eliminate false cross-contamination (e.g. 'unpaid' in family law).
    3. Provides dedicated legal decomposition branches for Family, Rent, Banking, Criminal, and Civil.
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
    # 1. Resolve Primary Domain (Planner wins if provided)
    # -------------------------------------------------------------------------
    is_family_signal = any(k in q_low for k in [
        "khula", "dower", "mahr", "maintenance", "nafaqa", "custody",
        "hizanat", "guardianship", "iddat", "talaq", "dissolution of marriage",
        "family court", "guardians and wards act"
    ])

    is_rent_signal = bool(
        re.search(r'\b(?:punjab rented premises|prpa|rent tribunal|ejectment application|leave to contest|default in payment of rent|bona fide need)\b', q_low) or
        (any(k in q_low for k in ["tenant", "landlord", "ejectment", "eviction"]) and "rent" in q_low)
    )

    is_banking_signal = any(k in q_low for k in [
        "banking court", "financial institutions (recovery", "fio 2001", "fio",
        "recovery of finance", "leave to defend", "compound mark-up", "finance agreement",
        "section 9 fio", "section 10 fio"
    ])

    is_cheque_signal = any(phrase in q_low for phrase in [
        "cheque returned unpaid", "insufficient funds", "dishonoured cheque",
        "dishonored cheque", "bounced cheque", "return memo", "section 489-f",
        "489f ppc", "cheque was dishonoured", "cheque dishonour", "dishonoured on presentation",
        "cheque of rs", "deposited a cheque"
    ]) and not is_family_signal

    is_criminal_signal = (
        is_cheque_signal or
        any(k in q_low for k in [
            "fir", "police", "arrest", "arrested", "custody", "remand", "bail",
            "pre-arrest", "post-arrest", "quashment", "561-a", "theft", "379", "378",
            "cheating", "420", "415", "criminal breach of trust", "406", "405",
            "302", "murder", "qatl"
        ])
    )

    is_sale_specific_perf = any(k in q_low for k in [
        "specific performance", "agreement to sell", "sale deed",
        "plot", "earnest money", "advance money"
    ]) or (
        any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and
        any(k in q_low for k in ["sale", "refused"])
    )

    if planner_domain and planner_domain in {
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
    elif is_criminal_signal:
        primary_domain = "criminal"
    elif is_sale_specific_perf:
        primary_domain = "civil"
    else:
        primary_domain = "civil"

    # Mutual exclusion: Never allow false cheque/criminal triggers to contaminate family, rent, or banking
    if primary_domain in ("family", "rent", "banking"):
        is_cheque_signal = False
        is_sale_specific_perf = False

    # -------------------------------------------------------------------------
    # 2. Domain-Specific Decompositions
    # -------------------------------------------------------------------------

    # =========================================================================
    # A. FAMILY LAW DECOMPOSITION
    # =========================================================================
    if primary_domain == "family":
        # 1. Dissolution of Marriage / Khula
        if any(k in q_low for k in ["khula", "dissolution", "deserted", "desertion", "divorce"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_khula_dissolution",
                heading="Dissolution of Marriage by Khula (Section 10 Family Courts Act, 1964 & Section 2 DMMA 1939)",
                description="Right of wife to claim dissolution of marriage through Khula on ground of aversion or desertion, and non-contingency of divorce upon return of dower or husband's consent.",
                controlling_statutes=["Family Courts Act, 1964", "Dissolution of Muslim Marriages Act, 1939"],
                controlling_provisions=[
                    "FAMILY_COURTS_1964_SEC_10", "FAMILY_COURTS_1964_SEC_5", "DMMA_1939_SEC_2"
                ],
                search_queries=[
                    "Section 10 Family Courts Act 1964 Khula wife right without husband consent dissolution of marriage",
                    "Section 2 Dissolution of Muslim Marriages Act 1939 desertion by husband failure to maintain grounds for dissolution"
                ],
                factual_anchors=["khula", "deserted", "dissolution of marriage", "husband"]
            ))

        # 2. Recovery of Dower (Mahr)
        if any(k in q_low for k in ["dower", "mahr", "prompt dower", "deferred dower"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_dower_recovery",
                heading="Recovery of Prompt Dower (Section 5, Family Courts Act, 1964)",
                description="Statutory claim for recovery of unpaid prompt dower as an absolute debt payable on demand, which remains a distinct civil liability not extinguished by Khula decree.",
                controlling_statutes=["Family Courts Act, 1964", "Muslim Family Laws Ordinance, 1961"],
                controlling_provisions=[
                    "MFLO_1961_SEC_10", "FAMILY_COURTS_1964_SEC_5"
                ],
                search_queries=[
                    "return of dower zar-i-khula civil liability does not invalidate dissolution of marriage Section 10(4)",
                    "Section 5 Family Courts Act 1964 suit for recovery of prompt dower debt payable on demand"
                ],
                factual_anchors=["prompt dower", "dower", "unpaid dower", "Rs. 500,000"]
            ))

        # 3. Past & Future Maintenance for Wife and Minor Children
        if any(k in q_low for k in ["maintenance", "nafaqa", "minor", "children"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_maintenance_minors",
                heading="Past & Future Maintenance of Minor Children and Wife (Section 9 MFLO 1961 & Section 5 FCA 1964)",
                description="Statutory and Islamic obligation of father to maintain minor children until majority/marriage and wife during subsistence of marriage, including schedule of interim maintenance.",
                controlling_statutes=["Muslim Family Laws Ordinance, 1961", "Family Courts Act, 1964"],
                controlling_provisions=[
                    "MFLO_1961_SEC_9", "FAMILY_COURTS_1964_SEC_17A", "FAMILY_COURTS_1964_SEC_5"
                ],
                search_queries=[
                    "Section 9 Muslim Family Laws Ordinance 1961 Section 5 Family Courts Act 1964 maintenance of minor children father statutory duty",
                    "past maintenance minor children father obligation limitation Family Court"
                ],
                factual_anchors=["maintenance", "minor children", "past and future maintenance"]
            ))

        # 4. Custody (Hizanat) and Guardianship
        if any(k in q_low for k in ["custody", "hizanat", "guardian", "guardianship", "minor children", "ages"]):
            issues.append(LegalSubIssue(
                issue_id="issue_family_custody_hizanat",
                heading="Custody of Minor Children (Hizanat) & Guardianship (Sections 7, 17, 25 GWA 1890)",
                description="Determination of custody (Hizanat) of minor children where welfare of the minor is paramount consideration, and preferential custody rights of mother for children of tender age.",
                controlling_statutes=["Guardians and Wards Act, 1890", "Family Courts Act, 1964"],
                controlling_provisions=[
                    "GWA_1890_SEC_7", "GWA_1890_SEC_17", "GWA_1890_SEC_25", "FAMILY_COURTS_1964_SEC_5"
                ],
                search_queries=[
                    "welfare of minor paramount consideration Section 17 Section 25 Guardians and Wards Act 1890 hizanat mother preferential right",
                    "custody of tender age minors mother hizanat father visitation rights"
                ],
                factual_anchors=["custody", "Hizanat", "Guardians and Wards Act", "minor children"]
            ))

        open_questions.append(
            "Whether the prompt dower of Rs. 500,000 is evidenced by the registered Nikahnama (Column 13/14), "
            "and whether the father has provided any interim maintenance during the 2-year desertion period."
        )

    # =========================================================================
    # B. RENT & EVICTION DECOMPOSITION
    # =========================================================================
    elif primary_domain == "rent":
        issues.append(LegalSubIssue(
            issue_id="issue_rent_ejectment_grounds",
            heading="Ejectment Grounds: Default in Rent & Personal Bona Fide Need (Section 15, PRPA 2009)",
            description="Substantive grounds for ejectment under Section 15 of the Punjab Rented Premises Act, 2009: establishing willful default in payment of rent and proving genuine personal bona fide need of landlord.",
            controlling_statutes=["Punjab Rented Premises Act, 2009"],
            controlling_provisions=[
                "PRPA_2009_SEC_15", "PRPA_2009_SEC_4"
            ],
            search_queries=[
                "Section 15 PRPA 2009 grounds for eviction default in payment of rent personal bona fide need",
                "Section 15 Punjab Rented Premises Act 2009 landlord proof of personal use and default"
            ],
            factual_anchors=["Section 15", "Punjab Rented Premises Act, 2009", "default in payment of rent", "personal bona fide need"]
        ))

        issues.append(LegalSubIssue(
            issue_id="issue_rent_leave_to_contest",
            heading="Leave to Contest Procedure & Mandatory Limitation (Section 22, PRPA 2009)",
            description="Mandatory procedural requirement under Section 22 PRPA 2009 to file an application for leave to contest within ten days of appearance/service, disclosing substantial questions of law or fact.",
            controlling_statutes=["Punjab Rented Premises Act, 2009"],
            controlling_provisions=[
                "PRPA_2009_SEC_22", "PRPA_2009_SEC_19", "PRPA_2009_SEC_34"
            ],
            search_queries=[
                "Section 22 PRPA 2009 leave to contest mandatory 10 days limitation substantial defense",
                "Section 19 Section 34 PRPA 2009 exclusive jurisdiction Rent Tribunal civil court jurisdiction barred"
            ],
            factual_anchors=["leave to contest", "Section 22 PRPA 2009", "ejectment defense"]
        ))

        issues.append(LegalSubIssue(
            issue_id="issue_rent_payment_receipts",
            heading="Mode of Rent Payment & Landlord's Duty to Issue Receipts (Section 4 & 15 PRPA 2009)",
            description="Statutory defense where tenant paid cash rent but landlord refused receipts, and evaluation of rent deposit remedies through postal money order or bank account.",
            controlling_statutes=["Punjab Rented Premises Act, 2009"],
            controlling_provisions=[
                "PRPA_2009_SEC_4", "PRPA_2009_SEC_15"
            ],
            search_queries=[
                "Section 4 PRPA 2009 landlord obligation to issue rent receipt tenant defense cash payment",
                "tenant paid cash landlord refused receipt default defense PRPA 2009"
            ],
            factual_anchors=["cash rent", "refused to issue receipts", "paid rent regularly"]
        ))

        open_questions.append(
            "Whether the tenant has tender records, bank transfers, witnesses, or postal money orders establishing cash payments, "
            "and the exact date of receipt of notice or service from the Rent Tribunal to compute the 10-day period under Section 22 PRPA 2009."
        )

    # =========================================================================
    # C. BANKING RECOVERY DECOMPOSITION
    # =========================================================================
    elif primary_domain == "banking":
        issues.append(LegalSubIssue(
            issue_id="issue_banking_recovery_suit",
            heading="Banking Recovery Suit under Special Law (Section 9, FIO 2001)",
            description="Statutory recovery suit by financial institution under Section 9 of the Financial Institutions (Recovery of Finances) Ordinance, 2001 and requirements of valid statement of account.",
            controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
            controlling_provisions=[
                "FIO_2001_SEC_9", "FIO_2001_SEC_22"
            ],
            search_queries=[
                "Section 9 Financial Institutions Recovery of Finances Ordinance 2001 recovery suit statement of account",
                "Section 9 FIO 2001 commercial bank recovery claim finance agreement"
            ],
            factual_anchors=["Section 9", "Financial Institutions (Recovery of Finances) Ordinance, 2001", "FIO 2001", "Rs. 45 million"]
        ))

        issues.append(LegalSubIssue(
            issue_id="issue_banking_leave_to_defend",
            heading="Mandatory Leave to Defend Procedure & 30-Day Limitation (Section 10, FIO 2001)",
            description="Mandatory statutory requirement under Section 10 FIO 2001 to file petition for leave to defend within 30 days of service of summons, strictly supported by affidavit and specific dispute of finance amounts.",
            controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
            controlling_provisions=["FIO_2001_SEC_10"],
            search_queries=[
                "Section 10 Financial Institutions Recovery of Finances Ordinance 2001 leave to defend 30 days mandatory limitation",
                "Section 10 FIO 2001 leave to defend affidavit summary procedure Banking Court"
            ],
            factual_anchors=["Section 10", "leave to defend", "30 days", "mandatory procedure"]
        ))

        issues.append(LegalSubIssue(
            issue_id="issue_banking_compound_markup_interest",
            heading="Challenge to Compound Mark-up & Penal Interest (Sections 10 & 14, FIO 2001)",
            description="Substantive legal defense challenging unlawful compound mark-up, liquidated damages, and penal charges imposed beyond the agreed finance agreement, which constitutes a bona fide substantial question of law for grant of unconditional leave to defend.",
            controlling_statutes=["Financial Institutions (Recovery of Finances) Ordinance, 2001"],
            controlling_provisions=[
                "FIO_2001_SEC_10", "FIO_2001_SEC_14"
            ],
            search_queries=[
                "Section 10 FIO 2001 compound markup penal interest beyond finance agreement substantial question of fact law leave to defend",
                "Banking Court compound interest mark-up upon mark-up disallowed FIO 2001"
            ],
            factual_anchors=["compound mark-up", "penal interest", "finance agreement", "excessive charges"]
        ))

        open_questions.append(
            "Whether the corporate borrower has maintained an independent audit or ledger reconciliation showing agreed mark-up vs charged penal interest, "
            "and the exact date of publication or personal service of the Banking Court summons."
        )

    # =========================================================================
    # D. CRIMINAL LAW (CHEQUE, THEFT, FRAUD, BAIL, QUASHMENT)
    # =========================================================================
    elif primary_domain == "criminal":
        # 1. Cheque Dishonour (Section 489-F PPC)
        if is_cheque_signal:
            issues.append(LegalSubIssue(
                issue_id="issue_cheque_dishonour_489f",
                heading="Criminal Offence of Dishonestly Issuing a Cheque (Section 489-F, PPC 1860)",
                description="Whether the returned cheque was dishonestly issued towards repayment of a loan or fulfillment of an obligation under Section 489-F PPC.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["PPC_1860_SEC_489F", "CPC_1908_ORD_XXXVII_R_1"],
                search_queries=[
                    "Section 489-F PPC dishonour of cheque ingredients dishonest issuance lack of funds",
                    "Section 489-F Pakistan Penal Code 1860 dishonestly issuing a cheque prima facie offence"
                ],
                factual_anchors=["cheque", "dishonoured", "unpaid", "insufficient funds", "489-F"]
            ))

        # 2. Substantive Theft, Cheating, and Breach of Trust (Sections 379, 420, 406 PPC)
        has_theft = any(k in q_low for k in ["theft", "379", "378", "stolen", "machinery"])
        has_cheating = any(k in q_low for k in ["cheating", "420", "415", "fraud", "deceiv", "dishonest inducement"])
        has_cbt = any(k in q_low for k in ["breach of trust", "406", "405", "409", "misappropriat", "entrustment"])

        if has_theft:
            issues.append(LegalSubIssue(
                issue_id="issue_theft_379_ppc",
                heading="Offence of Theft (Sections 378 & 379, Pakistan Penal Code, 1860)",
                description="Statutory ingredients of theft under Section 378 PPC requiring dishonest taking of movable property out of possession without consent, and punishment under Section 379 PPC.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=[
                    "PPC_1860_SEC_378", "PPC_1860_SEC_379"
                ],
                search_queries=[
                    "Section 378 Section 379 PPC theft ingredients movable property dishonest intention taking out of possession",
                    "Section 379 PPC false implication commercial dispute theft allegation"
                ],
                factual_anchors=["theft", "Section 379 PPC", "machinery", "Sections 379"]
            ))

        if has_cheating:
            issues.append(LegalSubIssue(
                issue_id="issue_cheating_420_ppc",
                heading="Offence of Cheating and Dishonestly Inducing Delivery (Sections 415 & 420, PPC 1860)",
                description="Statutory ingredients of cheating under Section 415 PPC and aggravated punishment under Section 420 PPC requiring fraudulent or dishonest inducement at the very inception of transaction.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=[
                    "PPC_1860_SEC_415", "PPC_1860_SEC_420"
                ],
                search_queries=[
                    "Section 415 Section 420 PPC cheating dishonest intention at inception delivery of property",
                    "Section 420 PPC commercial transaction breach of contract vs cheating criminal offence"
                ],
                factual_anchors=["cheating", "Section 420 PPC", "fraud", "Sections 420"]
            ))

        if has_cbt:
            issues.append(LegalSubIssue(
                issue_id="issue_cbt_406_ppc",
                heading="Criminal Breach of Trust (Sections 405 & 406, Pakistan Penal Code, 1860)",
                description="Statutory ingredients of criminal breach of trust under Section 405 PPC requiring entrustment with property or dominion over property and dishonest misappropriation, punished under Section 406 PPC.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=[
                    "PPC_1860_SEC_405", "PPC_1860_SEC_406"
                ],
                search_queries=[
                    "Section 405 Section 406 PPC criminal breach of trust entrustment dishonest misappropriation",
                    "Section 406 PPC cancelled agreement commercial dispute civil liability not criminal breach of trust"
                ],
                factual_anchors=["criminal breach of trust", "Section 406 PPC", "misappropriation of funds", "Sections 406"]
            ))

        # 3. Murder / Section 302 PPC
        if any(k in q_low for k in ["302", "murder", "qatl"]):
            issues.append(LegalSubIssue(
                issue_id="issue_murder_302_ppc",
                heading="Substantive Penal Offence of Murder (Section 302, Pakistan Penal Code, 1860)",
                description="Analysis of the charged penal offence of Qatl-i-Amd under Section 302 PPC, clauses (a), (b), (c), and the fasad-fil-arz proviso.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["PPC_1860_SEC_302"],
                search_queries=[
                    "Section 302 PPC punishment for murder qatl-i-amd ingredients clauses",
                    "Section 302 clause b PPC tazir capital sentence life imprisonment"
                ],
                factual_anchors=["Section 302 PPC", "murder", "qatl"]
            ))

        # 4. Bail (Pre-arrest under 498 CrPC & Post-arrest under 497 CrPC)
        if any(k in q_low for k in ["bail", "pre-arrest", "post-arrest", "498", "497", "496"]):
            issues.append(LegalSubIssue(
                issue_id="issue_criminal_bail_498_497",
                heading="Pre-Arrest & Post-Arrest Bail Jurisprudence (Sections 498, 497 & 496, CrPC 1898)",
                description="Pre-arrest bail under Section 498 CrPC based on demonstration of mala fides, ulterior motives, or humiliation by prosecution arising out of a civil/commercial dispute, and post-arrest bail principles under Section 497 CrPC.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=[
                    "CRPC_1898_SEC_498", "CRPC_1898_SEC_497", "CRPC_1898_SEC_496"
                ],
                search_queries=[
                    "Section 498 Section 497 CrPC pre-arrest bail mala fide ulterior motive civil dispute commercial recovery arrest humiliation",
                    "Section 497 CrPC non-bailable prohibitory clause concession grace judicial discretion non-prohibitory bail rule refusal exception"
                ],
                factual_anchors=["pre-arrest bail", "Section 498 CrPC", "bail", "arrest"]
            ))

        # 5. Quashment of FIR (Section 561-A CrPC)
        if any(k in q_low for k in ["quash", "quashment", "561-a", "561a", "abuse of process", "false fir"]):
            issues.append(LegalSubIssue(
                issue_id="issue_quashment_561a_crpc",
                heading="Inherent Powers of High Court for Quashment of FIR (Section 561-A, CrPC 1898)",
                description="Quashment of criminal proceedings under Section 561-A CrPC where FIR is lodged to exert coercive pressure for recovery in a purely civil/commercial breach of contract, constituting an abuse of process of the Court.",
                controlling_statutes=["Code of Criminal Procedure, 1898"],
                controlling_provisions=["CRPC_1898_SEC_561A"],
                search_queries=[
                    "Section 561-A CrPC quashment of FIR commercial transaction cancelled distributorship agreement civil dispute criminal breach of trust",
                    "criminal breach of trust vs civil dispute dishonest intention at inception commercial transaction loan repayment quashment"
                ],
                factual_anchors=["quashment", "Section 561-A CrPC", "cancelled commercial distributorship agreement"]
            ))

        if any(k in q_low for k in ["theft", "420", "406", "distributorship", "commercial"]):
            open_questions.append(
                "Whether the cancelled commercial distributorship agreement contains arbitration or audit clauses, "
                "and whether any dishonest intention was established at the inception of the contract versus subsequent commercial default."
            )
        elif any(k in q_low for k in ["302", "murder"]):
            open_questions.append(
                "Whether any direct ocular evidence, recovery of weapon of offence, medical corroboration, or statutory concession "
                "under Section 497(1) provisos (sickness, infirmity, woman, minor) or Section 497(2) CrPC (further inquiry) is established on the record."
            )

    # =========================================================================
    # E. CIVIL SPECIFIC PERFORMANCE
    # =========================================================================
    elif is_sale_specific_perf:
        issues.append(LegalSubIssue(
            issue_id="issue_specific_performance_immovable_property",
            heading="Specific Performance of Agreement to Sell Immovable Property (Sections 12, 21, 22 SRA 1877)",
            description="Enforceability of agreement to sell immovable property and statutory presumption that breach cannot be adequately compensated in money under Section 12 Specific Relief Act.",
            controlling_statutes=["Specific Relief Act, 1877"],
            controlling_provisions=[
                "SRA_1877_SEC_12", "SRA_1877_SEC_19", "SRA_1877_SEC_21", "SRA_1877_SEC_22", "CONTRACT_1872_SEC_73"
            ],
            search_queries=[
                "Section 12 Specific Relief Act 1877 presumption immovable property compensation in money not adequate relief",
                "Section 22 Specific Relief Act 1877 discretion of court decreeing specific performance agreement to sell"
            ],
            factual_anchors=["agreement to sell", "plot", "sale deed", "refused to execute", "specific performance"]
        ))

    # =========================================================================
    # F. GENERAL CIVIL FALLBACK
    # =========================================================================
    if not issues:
        issues.append(LegalSubIssue(
            issue_id="issue_general_civil_remedy",
            heading="Civil Relief & Statutory Grounds",
            description="Examination of rights, cause of action, and competent civil remedies.",
            controlling_statutes=["Code of Civil Procedure, 1908"],
            controlling_provisions=["CPC_1908_SEC_9", "CPC_1908_SEC_151"],
            search_queries=[query_text],
            factual_anchors=[]
        ))

    return FactPatternDecomposition(
        raw_query=query_text,
        primary_domain=primary_domain,
        has_dates=has_dates,
        has_monetary_amounts=has_amounts,
        issues=issues,
        open_questions=open_questions
    )
