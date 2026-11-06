"""
core/evidence_pack.py

Assembles the strict Stage 4 Evidence Pack for the Legal Research Pipeline.
The Evidence Pack assigns deterministic IDs (S1..Sn for statutes, C1..Cn for cases)
and serves as the EXCLUSIVE knowledge source provided to the drafting model.
"""

import re
from typing import Dict, List, Any, Optional
from core.case_integrity import sanitize_ratio_text, normalize_citation


class EvidencePack:
    """
    Container for verified statutes and judicial precedents admitted for a query.
    """
    def __init__(self):
        self.statutes: Dict[str, Dict[str, Any]] = {}  # S1, S2 -> {id, act, sec, text, ...}
        self.cases: Dict[str, Dict[str, Any]] = {}     # C1, C2 -> {id, citation, title, court, ratio, ...}
        self.statute_by_sec: Dict[str, str] = {}       # e.g. "BENAMI_2017_4" -> "S1"
        self.case_by_cit: Dict[str, str] = {}          # e.g. "2011 SCMR 1550" -> "C1"

    def add_statute(
        self,
        act_name: str,
        section_number: str,
        section_text: str,
        title: Optional[str] = None,
        year: Optional[int] = None,
        jurisdiction: Optional[str] = None,
        status: str = "in_force",
        amendment_history: Optional[str] = None
    ) -> str:
        """Adds a verified statute provision and assigns an S-id."""
        clean_text = (section_text or "").strip()
        if not clean_text:
            return ""

        lookup_key = f"{act_name.upper()}_{section_number.upper()}"
        if lookup_key in self.statute_by_sec:
            return self.statute_by_sec[lookup_key]

        s_id = f"S{len(self.statutes) + 1}"
        record = {
            "id": s_id,
            "act_name": act_name.strip(),
            "section_number": str(section_number).strip(),
            "title": (title or f"Section {section_number}").strip(),
            "text": clean_text,
            "year": year,
            "jurisdiction": jurisdiction or "Federal / Provincial",
            "status": status,
            "amendment_history": amendment_history or ""
        }
        self.statutes[s_id] = record
        self.statute_by_sec[lookup_key] = s_id
        return s_id

    def add_case(
        self,
        citation: str,
        case_title: str,
        court: str,
        ratio: str,
        year: Optional[int] = None,
        statutes_invoked: Optional[List[str]] = None,
        pdf_url: Optional[str] = None,
        full_text_available: bool = True
    ) -> str:
        """Adds a verified judicial precedent and assigns a C-id."""
        clean_cit = normalize_citation(citation)
        if not clean_cit:
            return ""

        clean_ratio = sanitize_ratio_text(ratio)
        if not clean_ratio:
            return ""

        if clean_cit in self.case_by_cit:
            return self.case_by_cit[clean_cit]

        c_id = f"C{len(self.cases) + 1}"
        record = {
            "id": c_id,
            "citation": clean_cit,
            "case_title": (case_title or "Untitled Judicial Precedent").strip(),
            "court": (court or "Supreme Court of Pakistan").strip(),
            "ratio": clean_ratio,
            "year": year,
            "statutes_invoked": statutes_invoked or [],
            "pdf_url": pdf_url or "",
            "full_text_available": full_text_available
        }
        self.cases[c_id] = record
        self.case_by_cit[clean_cit] = c_id
        return c_id

    def format_pack_for_llm(self) -> str:
        """
        Formats the evidence pack as a strictly structured prompt context block.
        """
        lines = [
            "================================================================================",
            "VERIFIED EVIDENCE PACK (EXCLUSIVE ADMISSIBLE SOURCES)",
            "CRITICAL: You may cite ONLY from this pack. No outside knowledge or citations.",
            "================================================================================",
            ""
        ]

        # Statutes Section
        lines.append("### STATUTORY PROVISIONS ON RECORD:")
        if not self.statutes:
            lines.append("No verified statutory provisions were admitted for this query.")
        else:
            for sid, s in self.statutes.items():
                lines.append(f"[{sid}] {s['act_name']}, Section {s['section_number']} ({s['title']}):")
                lines.append(f"Status: {s['status']} | Scope: {s['jurisdiction']}")
                lines.append(f"VERBATIM TEXT:\n\"\"\"\n{s['text']}\n\"\"\"")
                if s.get("amendment_history"):
                    lines.append(f"Amendment History: {s['amendment_history']}")
                lines.append("")

        # Cases Section
        lines.append("### JUDICIAL PRECEDENTS ON RECORD:")
        if not self.cases:
            lines.append("No verified judicial precedents were admitted for this query.")
        else:
            for cid, c in self.cases.items():
                lines.append(f"[{cid}] {c['citation']} - {c['case_title']}")
                lines.append(f"Court: {c['court']} | Year: {c.get('year') or 'N/A'}")
                if c.get("statutes_invoked"):
                    lines.append(f"Statutes Invoked: {', '.join(str(x) for x in c['statutes_invoked'])}")
                lines.append(f"RECORDED RATIO DECIDENDI:\n\"\"\"\n{c['ratio']}\n\"\"\"")
                lines.append("")

        lines.append("================================================================================")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Returns JSON serializable representation."""
        return {
            "statutes": self.statutes,
            "cases": self.cases
        }


def assemble_evidence_pack(
    statute_records: List[Dict[str, Any]],
    case_records: List[Dict[str, Any]]
) -> EvidencePack:
    """
    Assembles and hydrates an EvidencePack from raw retrieved records.
    """
    pack = EvidencePack()

    for s in statute_records:
        act = s.get("act_name") or s.get("act") or s.get("statute") or ""
        sec = s.get("section_number") or s.get("section") or s.get("sec") or ""
        txt = s.get("section_text") or s.get("text") or s.get("provision_text") or ""
        title = s.get("section_title") or s.get("title") or ""
        year = s.get("year")
        jurisdiction = s.get("jurisdiction") or s.get("province") or "Federal"
        status = s.get("status") or ("in_force" if not s.get("repealed") else "repealed")
        amend = s.get("amendment_history") or ""

        if act and sec and txt:
            pack.add_statute(
                act_name=act,
                section_number=str(sec),
                section_text=txt,
                title=title,
                year=year,
                jurisdiction=jurisdiction,
                status=status,
                amendment_history=amend
            )

    for c in case_records:
        cit = c.get("citation") or c.get("neutral_citation") or c.get("case_id") or ""
        title = c.get("case_title") or c.get("title") or c.get("case_name") or ""
        court = c.get("court_name") or c.get("court") or c.get("canonical_court_name") or ""
        ratio = c.get("ratio_decidendi") or c.get("holding") or c.get("ratio") or c.get("headnote") or ""
        year = c.get("year")
        invoked = c.get("statutes_invoked") or []
        pdf = c.get("pdf_url") or ""
        full_text = bool(c.get("full_text") or c.get("judgment_text"))

        if cit and ratio:
            pack.add_case(
                citation=cit,
                case_title=title,
                court=court,
                ratio=ratio,
                year=year,
                statutes_invoked=invoked,
                pdf_url=pdf,
                full_text_available=full_text
            )

    return pack
