"""
core/legal_issue_extractor.py
Multi-Issue Fact Pattern Decomposition Engine.

Breaks down real-world legal fact patterns into distinct legal sub-issues,
assigns controlling statutory provisions to each issue, generates targeted
search queries, and anchors factual remedies.
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


def extract_legal_issues_from_fact_pattern(query_text: str) -> FactPatternDecomposition:
    """
    Decomposes an unstructured factual narrative into structured legal sub-issues.
    """
    q_low = query_text.lower()
    issues: List[LegalSubIssue] = []
    
    # 1. Limitation & Time-Bar Issue
    has_dates = bool(re.search(r'\b(?:19|20)\d\d\b', q_low) or re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b', q_low))
    has_limitation_query = any(k in q_low for k in ["within time", "limitation", "time-barred", "time barred", "delay", "period", "expiry"])
    
    is_sale_specific_perf = any(k in q_low for k in ["specific performance", "agreement to sell", "sale deed", "plot", "earnest money", "advance money"]) or \
                            (any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and any(k in q_low for k in ["sale", "refused"]))

    if (has_dates and is_sale_specific_perf) or has_limitation_query:
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

    # 2. Specific Performance of Immovable Property
    if is_sale_specific_perf:
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
    has_money_paid = any(k in q_low for k in ["earnest money", "advance money", "paid rs", "token money", "down payment", "lakh", "crore"])
    has_remedies_query = any(k in q_low for k in ["what other remedies", "alternative remedies", "other relief", "remedies does my client have", "compensation", "damages"])
    if has_money_paid or has_remedies_query:
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
            factual_anchors=["earnest money", "rs 20 lakh", "rs 80 lakh", "other remedies", "damages", "compensation"]
        ))

    # Fallback if no specific issues triggered
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

    has_amounts = bool(re.search(r'(?i)\b(?:rs\.?|pkr|lakh|crore|million)\b', q_low))

    return FactPatternDecomposition(
        raw_query=query_text,
        primary_domain="civil",
        has_dates=has_dates,
        has_monetary_amounts=has_amounts,
        issues=issues
    )
