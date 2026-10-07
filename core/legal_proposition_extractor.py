"""
core/legal_proposition_extractor.py

Legal Proposition Extraction Engine for Pakistani Jurisprudence.
Transforms raw judgment text into structured, advocate-grade legal propositions:
- Specific Legal Issue
- Court Holding / Ratio Decidendi
- Paragraph / Page Reference
- Why this authority matters to the client's case
- Tactical Application in Pleadings
"""

import re
from typing import Dict, List, Any, Optional
from core.legal_query_planner import LegalQueryPlan
from core.case_title_taxonomy import get_effective_title


def extract_paragraph_reference(text: str) -> Optional[str]:
    """Extracts paragraph or page number references from judgment text if present."""
    m_para = re.search(r'\b(?:para(?:graph)?|paragraph\s+no\.?|para\s+no\.?)\s*([0-9]+)\b', text, re.IGNORECASE)
    if m_para:
        return f"Para {m_para.group(1)}"
    m_page = re.search(r'\b(?:at\s+page|p\.\s*|page\s+no\.?)\s*([0-9]+)\b', text, re.IGNORECASE)
    if m_page:
        return f"Page {m_page.group(1)}"
    return None


def derive_why_matters_to_case(
    holding: str,
    title: str,
    query_plan: LegalQueryPlan
) -> str:
    """
    Synthesizes why this specific judicial authority matters to the client's fact pattern.
    """
    h_low = f"{holding} {title}".lower()
    facts_str = " ".join(query_plan.factual_matrix or []).lower()

    if "pre-arrest bail" in h_low or "498" in h_low or "bail" in h_low:
        if "dismiss" in h_low and "stay" in h_low:
            return "Critical procedural authority establishing that petition filing before the Supreme Court does not operate as an automatic stay of arrest following High Court bail dismissal."
        return "Directly establishes pre-arrest bail standards (Section 498 CrPC), protecting the client from police arrest and humiliation where criminal machinery is used to enforce civil recovery."

    if "director" in h_low or "company" in h_low or "fiduciary" in h_low or "agent" in h_low:
        return "Directly governs the liability of company directors managing corporate funds under Section 409 PPC, delineating statutory entrustment from intra-corporate accounting disputes."

    if "dishonest intention" in h_low or "civil dispute" in h_low or "breach of contract" in h_low or "420" in h_low:
        return "Provides the controlling doctrine distinguishing civil liability from criminal fraud, requiring proof of fraudulent deception at the inception of the transaction."

    if "489-f" in h_low or "cheque" in h_low:
        return "Directly analyzes the statutory ingredients of dishonest cheque issuance versus civil dispute or security transaction."

    return "Serves as governing superior court precedent on the legal ingredients and evidentiary thresholds applicable to the client's matter."


def extract_legal_propositions(
    authorities: List[Dict[str, Any]],
    query_plan: LegalQueryPlan
) -> List[Dict[str, Any]]:
    """
    Extracts structured legal propositions from top ranked authorities.
    """
    propositions = []

    for auth in authorities:
        meta = auth.get("metadata") if isinstance(auth.get("metadata"), dict) else auth
        title = get_effective_title(meta) or auth.get("title") or auth.get("case_name") or meta.get("title") or meta.get("case_title") or "Reported Precedent"
        citation = str(auth.get("citation") or auth.get("neutral_citation") or meta.get("citation") or meta.get("neutral_citation") or "Neutral Citation").strip()
        court = str(auth.get("court") or auth.get("court_name") or meta.get("court") or meta.get("court_name") or "Superior Court of Pakistan").strip()
        year = str(auth.get("year") or auth.get("decision_date") or meta.get("year") or meta.get("decision_date") or "2024").strip()

        raw_text = str(auth.get("preview") or auth.get("full_text") or auth.get("holding") or auth.get("snippet") or meta.get("full_text") or meta.get("text") or "").strip()
        para_ref = extract_paragraph_reference(raw_text)

        # Determine legal issue
        issue = str(auth.get("issue") or "").strip()
        if not issue or len(issue) < 15:
            if "409" in raw_text or "criminal breach of trust" in raw_text.lower():
                issue = "Criminal breach of trust by director/agent (Section 409 PPC)"
            elif "420" in raw_text or "cheating" in raw_text.lower():
                issue = "Dishonest inducement and cheating at transaction inception (Section 420 PPC)"
            elif "498" in raw_text or "pre-arrest bail" in raw_text.lower():
                issue = "Grounds and judicial discretion for pre-arrest bail (Section 498 CrPC)"
            else:
                issue = "Substantive penal liability and procedural relief"

        # Determine holding / ratio
        holding = str(auth.get("holding") or auth.get("ratio") or "").strip()
        if not holding or len(holding) < 20:
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw_text) if len(s.strip()) > 30]
            holding = sentences[0] if sentences else raw_text[:250]

        why_matters = derive_why_matters_to_case(holding, title, query_plan)

        # Tactical application
        application = (
            "Deploy in initial bail petition and quashment arguments to demonstrate that "
            "the dispute is civil in character and lacks criminal mens rea."
        )
        if "pre-arrest bail" in issue.lower():
            application = (
                "Cite as primary ratio before the Sessions Court / High Court under Section 498 CrPC "
                "to secure interim protective bail and establish mala fide prosecution."
            )

        prop_entry = {
            "case_id": auth.get("case_id") or auth.get("id") or citation,
            "case_name": title,
            "citation": citation,
            "court": court,
            "year": year,
            "legal_issue": issue,
            "court_holding": holding,
            "paragraph_reference": para_ref,
            "why_matters_to_case": why_matters,
            "application": application,
            "verbatim_extract": raw_text[:500] if len(raw_text) > 500 else raw_text,
            "authority_score": auth.get("authority_score", 0.0),
            "is_headnote_only": bool(auth.get("is_headnote_only") or auth.get("content_type") == "headnote_only")
        }
        propositions.append(prop_entry)

    return propositions


def format_propositions_for_memorandum(propositions: List[Dict[str, Any]]) -> str:
    """
    Renders structured legal propositions for injection into memorandum context.
    """
    if not propositions:
        return "No superior court propositions extracted."

    blocks = ["=== STRUCTURED SUPERIOR COURT PROPOSITIONS & HOLDINGS ==="]
    for i, p in enumerate(propositions, start=1):
        b = [
            f"--- AUTHORITY #{i}: {p['case_name']} ({p['citation']}) ---",
            f"COURT: {p['court']} | YEAR: {p['year']}",
            f"LEGAL ISSUE: {p['legal_issue']}",
            f"COURT HOLDING / RATIO: {p['court_holding']}",
        ]
        if p.get("paragraph_reference"):
            b.append(f"PINPOINT REFERENCE: {p['paragraph_reference']}")
        b.append(f"WHY THIS AUTHORITY MATTERS: {p['why_matters_to_case']}")
        b.append(f"TACTICAL APPLICATION: {p['application']}")
        if p.get("verbatim_extract"):
            b.append(f"RELEVANT EXTRACT:\n\"{p['verbatim_extract'].strip()}\"")
        blocks.append("\n".join(b))

    return "\n\n".join(blocks)
