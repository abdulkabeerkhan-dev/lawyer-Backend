"""
core/legal_issue_extractor.py
Multi-Issue Fact Pattern Decomposition Engine.

Breaks down real-world legal fact patterns into distinct legal sub-issues,
assigns controlling statutory provisions to each issue, generates targeted
search queries, and anchors factual remedies across Civil, Criminal,
Procedural, and Commercial jurisdictions.
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


def extract_legal_issues_from_fact_pattern(query_text: str) -> FactPatternDecomposition:
    """
    Decomposes an unstructured factual narrative into structured legal sub-issues.
    Accurately isolates criminal offences (cheque dishonour, murder, arrest/bail)
    from civil specific performance and commercial contracts.
    """
    q_low = query_text.lower()
    issues: List[LegalSubIssue] = []
    open_questions: List[str] = []
    primary_domain = "civil"

    has_dates = bool(re.search(r'\b(?:19|20)\d\d\b', q_low) or re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b', q_low))
    has_amounts = bool(re.search(r'(?i)\b(?:rs\.?|pkr|lakh|crore|million)\b', q_low))

    # Detect domain signals
    is_cheque_dishonour = any(k in q_low for k in [
        "cheque", "check", "dishonour", "dishonored", "bounced",
        "unpaid", "insufficient funds", "lack of funds", "return memo",
        "489-f", "489f"
    ])
    
    is_criminal_arrest_bail = any(k in q_low for k in [
        "arrest", "arrested", "custody", "remand", "bail",
        "pre-arrest", "post-arrest", "bailable", "non-bailable",
        "fir", "police", "302", "murder", "qatl"
    ])

    is_sale_specific_perf = any(k in q_low for k in [
        "specific performance", "agreement to sell", "sale deed",
        "plot", "earnest money", "advance money"
    ]) or (
        any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and
        any(k in q_low for k in ["sale", "refused"])
    )

    # =========================================================================
    # A. CHEQUE DISHONOUR & SECTION 489-F PPC FACT PATTERN DECOMPOSITION
    # =========================================================================
    if is_cheque_dishonour:
        primary_domain = "criminal"

        # 1. Substantive Criminal Offence (Section 489-F PPC)
        issues.append(LegalSubIssue(
            issue_id="issue_cheque_dishonour_489f",
            heading="Criminal Offence of Dishonestly Issuing a Cheque (Section 489-F, Pakistan Penal Code, 1860)",
            description="Whether the issuance of the returned cheque for Rs. 15 lakh constitutes a cognizable penal offence under Section 489-F PPC, requiring proof of dishonest issuance towards repayment of a loan or fulfillment of an obligation.",
            controlling_statutes=["Pakistan Penal Code, 1860"],
            controlling_provisions=["Section 489-F PPC"],
            search_queries=[
                "Section 489-F PPC dishonour of cheque ingredients dishonest issuance lack of funds",
                "Section 489-F Pakistan Penal Code 1860 dishonestly issuing a cheque prima facie offence",
                "Section 489-F PPC repayment of loan fulfillment of obligation dishonest intent"
            ],
            factual_anchors=["cheque", "dishonoured", "unpaid", "insufficient funds", "Rs. 15 lakh", "489-F"]
        ))

        # 2. Criminal Procedure: FIR vs Direct Complaint under CrPC
        issues.append(LegalSubIssue(
            issue_id="issue_cheque_criminal_procedure",
            heading="Procedural Remedy: Registration of FIR or Direct Complaint (Sections 154, 190, 200, 202, 204 CrPC)",
            description="Procedural mechanism to initiate criminal proceedings: lodging an FIR under Section 154 CrPC at the local police station or instituting a private complaint before the Judicial Magistrate under Section 200 CrPC.",
            controlling_statutes=["Code of Criminal Procedure, 1898"],
            controlling_provisions=[
                "Section 154 CrPC",
                "Section 190 CrPC",
                "Section 200 CrPC",
                "Section 202 CrPC",
                "Section 204 CrPC"
            ],
            search_queries=[
                "Section 200 CrPC private complaint magistrate examination of complainant dishonoured cheque",
                "Section 154 CrPC registration of FIR cognizable offence Section 489-F PPC",
                "Section 190 CrPC cognizance of offences by Magistrate on complaint police report"
            ],
            factual_anchors=["criminal proceedings", "procedure", "initiate", "complaint", "magistrate", "FIR"]
        ))

        # 3. Limitation in Criminal Law & Concurrent Civil Summary Remedy
        issues.append(LegalSubIssue(
            issue_id="issue_cheque_limitation_and_civil_remedy",
            heading="Statutory Limitation in Criminal Law & Concurrent Civil Summary Recovery (Inapplicability of Limitation Act to FIRs / Order XXXVII CPC)",
            description="Whether criminal proceedings under Section 489-F PPC are subject to a statutory limitation period. Under settled Pakistani Supreme Court jurisprudence (PLD 1999 SC 1063, 2005 SCMR 404, 2021 SCMR 1602), the Limitation Act, 1908 applies strictly to civil suits, appeals, and applications; no statutory limitation period bars lodging an FIR or private complaint under the CrPC, though promptness is critical to establish bona fides. Concurrently, a civil summary suit under Order XXXVII CPC carries a 3-year limitation period under Article 64-A of the First Schedule to the Limitation Act, 1908.",
            controlling_statutes=["Limitation Act, 1908", "Code of Civil Procedure, 1908"],
            controlling_provisions=[
                "Section 3 Limitation Act, 1908",
                "Article 64-A Limitation Act, 1908"
            ],
            search_queries=[
                "limitation for criminal complaint FIR Section 489-F PPC Limitation Act not applicable",
                "Article 64-A Limitation Act 1908 Order XXXVII CPC summary suit negotiable instruments three years",
                "delay in lodging FIR Section 489-F PPC evidentiary value credibility"
            ],
            factual_anchors=["limitation", "limitation period", "within time", "delay", "Order XXXVII CPC"]
        ))

        open_questions.append(
            "Whether the cheque of Rs. 15 lakh was issued towards repayment of an existing loan or fulfillment of an obligation "
            "(a mandatory statutory ingredient under Section 489-F PPC) versus as an advance, investment, or security guarantee without an underlying debt."
        )

    # =========================================================================
    # B. CRIMINAL ARREST, CUSTODY, & BAIL FACT PATTERN DECOMPOSITION
    # =========================================================================
    elif is_criminal_arrest_bail:
        primary_domain = "criminal"

        # 1. Substantive Offence (e.g. Section 302 PPC murder)
        if any(k in q_low for k in ["302", "murder", "qatl"]):
            issues.append(LegalSubIssue(
                issue_id="issue_substantive_offence_302",
                heading="Substantive Penal Offence (Section 302, Pakistan Penal Code, 1860)",
                description="Analysis of the charged penal offence of Qatl-i-Amd under Section 302 PPC, its statutory ingredients, clauses (a), (b), (c), and the fasad-fil-arz proviso.",
                controlling_statutes=["Pakistan Penal Code, 1860"],
                controlling_provisions=["Section 302 PPC"],
                search_queries=[
                    "Section 302 PPC punishment for murder qatl-i-amd ingredients clauses",
                    "Section 302 clause b PPC tazir capital sentence life imprisonment"
                ],
                factual_anchors=["Section 302 PPC", "murder", "arrested"]
            ))

        # 2. Procedural Bail Law (Sections 497 & 498 CrPC)
        issues.append(LegalSubIssue(
            issue_id="issue_criminal_bail_procedure",
            heading="Post-Arrest & Pre-Arrest Bail Jurisprudence (Sections 496, 497, 498 CrPC)",
            description="Statutory principles governing grant or refusal of bail: Section 497 CrPC for post-arrest bail (prohibitory clause exception, further inquiry under subsection (2), and sickness/infirmity/minority provisos) and Section 498 CrPC for pre-arrest bail (demonstration of mala fides, ulterior motives, or humiliation by prosecution).",
            controlling_statutes=["Code of Criminal Procedure, 1898"],
            controlling_provisions=[
                "Section 497 CrPC",
                "Section 498 CrPC",
                "Section 496 CrPC"
            ],
            search_queries=[
                "Section 497 CrPC post arrest bail non-bailable offence prohibitory clause further inquiry",
                "Section 498 CrPC pre-arrest bail apprehension of arrest mala fide ulterior motive",
                "Section 497 subsection 2 CrPC further inquiry reasonable grounds accused not guilty"
            ],
            factual_anchors=["bail", "arrested", "custody", "grounds for bail", "non-bailable"]
        ))

        # 3. Investigation, Statements, & Challan (Sections 161, 164, 173 CrPC)
        issues.append(LegalSubIssue(
            issue_id="issue_criminal_investigation_safeguards",
            heading="Evidentiary & Procedural Safeguards (Sections 161, 164, 173 CrPC)",
            description="Procedural safeguards during police investigation, including examination of witnesses under Section 161 CrPC, recording of magisterial confessions/statements under Section 164 CrPC, and submission of the final police report/challan under Section 173 CrPC.",
            controlling_statutes=["Code of Criminal Procedure, 1898"],
            controlling_provisions=[
                "Section 161 CrPC",
                "Section 164 CrPC",
                "Section 173 CrPC"
            ],
            search_queries=[
                "Section 161 CrPC police statements evidentiary value criminal trial",
                "Section 173 CrPC report of police officer challan submission magistrate",
                "Section 164 CrPC confession recording magistrate voluntary certificate"
            ],
            factual_anchors=["investigation", "challan", "police statement", "custody"]
        ))

        open_questions.append(
            "Whether any direct ocular evidence, recovery of weapon of offence, medical corroboration, or statutory concession "
            "under Section 497(1) provisos (sickness, infirmity, woman, minor) or Section 497(2) CrPC (further inquiry) is established on the record."
        )

    # =========================================================================
    # C. CIVIL SPECIFIC PERFORMANCE FACT PATTERN DECOMPOSITION
    # =========================================================================
    elif is_sale_specific_perf:
        primary_domain = "civil"

        # 1. Limitation & Time-Bar Issue (Article 113, Limitation Act, 1908)
        has_limitation_query = any(k in q_low for k in ["within time", "limitation", "time-barred", "time barred", "delay", "period", "expiry"])
        if has_dates or has_limitation_query:
            issues.append(LegalSubIssue(
                issue_id="issue_limitation_specific_performance",
                heading="Statutory Limitation & Bar of Suit (Article 113, Limitation Act, 1908)",
                description="Whether the suit for specific performance is barred by limitation under Article 113 of the First Schedule to the Limitation Act, 1908.",
                controlling_statutes=["Limitation Act, 1908"],
                controlling_provisions=[
                    "Article 113 Limitation Act, 1908",
                    "Section 3 Limitation Act, 1908",
                    "Section 19 Limitation Act, 1908",
                    "Section 20 Limitation Act, 1908"
                ],
                search_queries=[
                    "Article 113 Limitation Act 1908 suit for specific performance date fixed for performance three years",
                    "Section 3 Limitation Act 1908 dismissal of suit barred by limitation without defense",
                    "Section 19 Limitation Act 1908 written acknowledgment of liability agreement to sell"
                ],
                factual_anchors=["completion date", "fixed date", "limitation", "time barred", "within time"]
            ))

        # 1b. Standing Open Question: Time as Essence of Contract (Section 55 Contract Act, 1872)
        has_fixed_completion_date = has_dates or any(k in q_low for k in ["completion date", "fixed date", "agreed date", "time limit", "date fixed", "deadline"])
        if has_fixed_completion_date:
            time_essence_inquiry = (
                "Whether time was made of the essence of the contract by express stipulation, notice, or conduct under "
                "Section 55 of the Contract Act, 1872 (in the absence of which the settled Supreme Court presumption under "
                "PLD 2002 SC 229 and 1987 SCMR 1005 is that time is not of the essence in contracts for the sale of immovable property)."
            )
            open_questions.append(time_essence_inquiry)
            issues.append(LegalSubIssue(
                issue_id="issue_time_as_essence_contract",
                heading="Time as Essence of Contract in Immovable Property (Section 55, Contract Act, 1872)",
                description="Whether time was specifically made of the essence of the contract by express stipulation, notice, or conduct under Section 55 of the Contract Act, 1872.",
                controlling_statutes=["Contract Act, 1872"],
                controlling_provisions=[
                    "Section 55 Contract Act, 1872"
                ],
                search_queries=[
                    "Section 55 Contract Act 1872 time is not of the essence sale of immovable property",
                    "time of essence agreement to sell immovable property intention notice PLD 2002 SC 229",
                    "Section 55 Contract Act 1872 extension of time waiver specific performance"
                ],
                factual_anchors=["completion date", "time of the essence", "fixed date", "delay in completion", "stipulated time"]
            ))

        # 2. Specific Performance of Immovable Property
        issues.append(LegalSubIssue(
            issue_id="issue_specific_performance_immovable_property",
            heading="Specific Performance of Agreement to Sell Immovable Property (Sections 12, 21, 22 SRA 1877)",
            description="Enforceability of the registered agreement to sell immovable property and the statutory presumption that breach cannot be adequately compensated in money.",
            controlling_statutes=["Specific Relief Act, 1877"],
            controlling_provisions=[
                "Section 12 Specific Relief Act, 1877",
                "Section 21 Specific Relief Act, 1877",
                "Section 22 Specific Relief Act, 1877"
            ],
            search_queries=[
                "Section 12 Specific Relief Act 1877 presumption immovable property compensation in money not adequate relief",
                "Section 22 Specific Relief Act 1877 discretion of court decreeing specific performance agreement to sell",
                "readiness and willingness plaintiff specific performance agreement to sell"
            ],
            factual_anchors=["agreement to sell", "plot", "sale deed", "refused to execute", "specific performance"]
        ))

        # 3. Subsequent Transferee / Third-Party Purchaser
        has_third_party = any(k in q_low for k in ["third party", "subsequent purchaser", "sold the plot to", "sold to another", "transferred to", "subsequent transferee", "another buyer"])
        if has_third_party:
            issues.append(LegalSubIssue(
                issue_id="issue_subsequent_transferee_rights",
                heading="Remedy Against Subsequent Purchaser / Transferee (Section 27(b) SRA & Section 52 TPA)",
                description="Enforceability of the agreement against the subsequent purchaser and the defense of bona fide purchaser for value without notice under Section 27(b) Specific Relief Act.",
                controlling_statutes=["Specific Relief Act, 1877", "Transfer of Property Act, 1882"],
                controlling_provisions=[
                    "Section 27 Specific Relief Act, 1877",
                    "Section 52 Transfer of Property Act, 1882"
                ],
                search_queries=[
                    "Section 27 clause b Specific Relief Act 1877 transferee for value paid money in good faith without notice original contract bona fide purchaser",
                    "burden of proof subsequent purchaser bona fide purchaser for value without notice agreement to sell",
                    "Section 52 Transfer of Property Act 1882 doctrine of lis pendens transfer during pendency of suit"
                ],
                factual_anchors=["sold to a third party", "subsequent purchaser", "third party", "transferee"]
            ))

        # 4. Alternative Remedies: Refund of Earnest Money & Damages
        has_earnest_or_remedies = any(k in q_low for k in ["earnest money", "advance money", "token money", "down payment", "what other remedies", "alternative remedies", "other relief", "remedies does my client have", "compensation", "damages"])
        if has_earnest_or_remedies:
            issues.append(LegalSubIssue(
                issue_id="issue_refund_earnest_money_and_damages",
                heading="Alternative Remedies: Refund of Earnest Money & Damages for Breach (Section 19 SRA & Sections 64, 65, 73 Contract Act)",
                description="Entitlement to recovery and refund of earnest money (restitution) and compensation/damages in addition to or in substitution for specific performance.",
                controlling_statutes=["Specific Relief Act, 1877", "Contract Act, 1872"],
                controlling_provisions=[
                    "Section 19 Specific Relief Act, 1877",
                    "Section 64 Contract Act, 1872",
                    "Section 65 Contract Act, 1872",
                    "Section 73 Contract Act, 1872",
                    "Section 74 Contract Act, 1872"
                ],
                search_queries=[
                    "Section 19 Specific Relief Act 1877 compensation in addition to or in substitution for specific performance",
                    "Section 65 Contract Act 1872 advantage received under void agreement refund of earnest advance money",
                    "Section 73 Contract Act 1872 compensation for loss or damage caused by breach of contract to sell"
                ],
                factual_anchors=["earnest money", "advance money", "other remedies", "damages", "compensation"]
            ))

    # =========================================================================
    # D. FALLBACK DEFAULT
    # =========================================================================
    if not issues:
        issues.append(LegalSubIssue(
            issue_id="issue_general_civil_remedy",
            heading="Civil Relief & Statutory Grounds",
            description="Examination of rights, cause of action, and competent civil remedies.",
            controlling_statutes=["Specific Relief Act, 1877", "Code of Civil Procedure, 1908"],
            controlling_provisions=["Section 12 Specific Relief Act, 1877"],
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
