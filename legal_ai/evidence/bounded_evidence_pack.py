"""
legal_ai/evidence/bounded_evidence_pack.py

Layer 5: Bounded Evidence Pack for the Structured Statute Knowledge Engine.
Design Invariants:
1. Retrieval produces a fixed, numbered pack: [E1], [E2], [E3], ...
2. The model only sees this pack. Nothing outside it can be cited.
3. Schedule tables are parsed row-by-row (description, period, trigger never separate).
4. Linked records (e.g., Punjab Loans Limitation Act, 1904 caveat to Article 57)
   are automatically pulled and bound into dedicated numbered evidence items.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from legal_ai.statutes.legal_unit_record import LegalUnitRecord


class EvidenceItem(BaseModel):
    """
    A single atomic admissible evidence item in the Bounded Pack.
    """
    id: str = Field(..., description="Evidence ID, e.g. 'E1', 'E2'")
    item_type: str = Field(..., description="'statute_unit', 'linked_caveat', or 'judicial_precedent'")
    
    # Statutory fields
    statute_id: Optional[str] = None
    statute_title: Optional[str] = None
    unit_type: Optional[str] = None  # 'article', 'section', 'order', 'rule'
    number: Optional[str] = None
    parent: Optional[str] = None
    heading_description: Optional[str] = None
    period: Optional[str] = None
    trigger: Optional[str] = None
    text: str = ""
    quote_verified: bool = False
    verification_label: Optional[str] = None
    footnotes: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    jurisdiction: str = "federal"
    amended_to: Optional[str] = None
    checksum: Optional[str] = None
    source_url: Optional[str] = None
    
    # Precedent fields (when item_type == 'judicial_precedent')
    citation: Optional[str] = None
    case_title: Optional[str] = None
    court: Optional[str] = None
    ratio: Optional[str] = None
    year: Optional[int] = None
    statutes_invoked: List[str] = Field(default_factory=list)
    pdf_url: Optional[str] = None


class BoundedEvidencePack:
    """
    Bounded container holding the exclusive universe of legal units and authorities
    admitted for an advocate's query.
    """

    def __init__(self):
        self.items: Dict[str, EvidenceItem] = {}
        self.item_by_unit_key: Dict[str, str] = {}
        self.item_by_citation: Dict[str, str] = {}
        self.query_text: str = ""

    def add_legal_unit(self, unit: LegalUnitRecord, pull_linked_caveats: bool = True) -> str:
        """
        Adds an atomic LegalUnitRecord to the evidence pack and assigns an E-ID.
        If the unit contains caveats or footnotes referencing provincial overrides
        (e.g., Punjab Loans Limitation Act, 1904 on Article 57), automatically
        creates and binds linked evidence records.
        """
        unit_key = f"{unit.statute_id}:{unit.unit_type}:{unit.number}".lower()
        if unit_key in self.item_by_unit_key:
            return self.item_by_unit_key[unit_key]

        e_id = f"E{len(self.items) + 1}"
        item = EvidenceItem(
            id=e_id,
            item_type="statute_unit",
            statute_id=unit.statute_id,
            statute_title=unit.statute_title,
            unit_type=unit.unit_type,
            number=unit.number,
            parent=unit.parent,
            heading_description=unit.heading_description,
            period=unit.period,
            trigger=unit.trigger,
            text=unit.text,
            quote_verified=unit.quote_verified,
            verification_label=unit.verification_label,
            footnotes=list(unit.footnotes),
            caveats=list(unit.caveats),
            jurisdiction=unit.jurisdiction,
            amended_to=unit.amended_to,
            checksum=unit.checksum,
            source_url=unit.source_url
        )
        self.items[e_id] = item
        self.item_by_unit_key[unit_key] = e_id

        # Layer 4 Invariant: Pull linked records automatically
        if pull_linked_caveats:
            for cav in unit.caveats:
                cav_key = f"caveat:{unit_key}:{cav[:40]}".lower()
                if cav_key not in self.item_by_unit_key:
                    cav_eid = f"E{len(self.items) + 1}"
                    cav_item = EvidenceItem(
                        id=cav_eid,
                        item_type="linked_caveat",
                        statute_id=unit.statute_id,
                        statute_title=unit.statute_title,
                        unit_type=unit.unit_type,
                        number=unit.number,
                        heading_description=f"Jurisdictional Caveat / Provincial Override to {unit.unit_type.capitalize()} {unit.number}",
                        text=cav,
                        jurisdiction="punjab" if "punjab" in cav.lower() else unit.jurisdiction,
                        parent=f"Linked to {unit.statute_title}, {unit.unit_type.capitalize()} {unit.number}"
                    )
                    self.items[cav_eid] = cav_item
                    self.item_by_unit_key[cav_key] = cav_eid

            # Check footnotes for statutory references not already extracted as caveats
            for fn in unit.footnotes:
                if any(k in fn.lower() for k in ["punjab loans limitation act", "override", "amended by"]):
                    fn_key = f"fn_override:{unit_key}:{fn[:40]}".lower()
                    if fn_key not in self.item_by_unit_key and not any(fn in c for c in unit.caveats):
                        fn_eid = f"E{len(self.items) + 1}"
                        fn_item = EvidenceItem(
                            id=fn_eid,
                            item_type="linked_caveat",
                            statute_id=unit.statute_id,
                            statute_title=unit.statute_title,
                            unit_type=unit.unit_type,
                            number=unit.number,
                            heading_description=f"Statutory Note to {unit.unit_type.capitalize()} {unit.number}",
                            text=fn,
                            jurisdiction="punjab" if "punjab" in fn.lower() else unit.jurisdiction,
                            parent=f"Linked footnote to {unit.unit_type.capitalize()} {unit.number}"
                        )
                        self.items[fn_eid] = fn_item
                        self.item_by_unit_key[fn_key] = fn_eid

        return e_id

    def add_case_precedent(
        self,
        citation: str,
        case_title: str,
        court: str,
        ratio: str,
        year: Optional[int] = None,
        statutes_invoked: Optional[List[str]] = None,
        pdf_url: Optional[str] = None
    ) -> str:
        """
        Adds an authentic superior court precedent to the bounded evidence pack.
        """
        clean_cit = citation.strip()
        if not clean_cit or not ratio.strip():
            return ""

        lookup_key = clean_cit.lower()
        if lookup_key in self.item_by_citation:
            return self.item_by_citation[lookup_key]

        e_id = f"E{len(self.items) + 1}"
        item = EvidenceItem(
            id=e_id,
            item_type="judicial_precedent",
            citation=clean_cit,
            case_title=case_title.strip() or "Judicial Precedent",
            court=court.strip() or "Supreme Court of Pakistan",
            ratio=ratio.strip(),
            text=f"Citation: {clean_cit}\nCourt: {court}\nRatio: {ratio}",
            year=year,
            statutes_invoked=statutes_invoked or [],
            pdf_url=pdf_url or ""
        )
        self.items[e_id] = item
        self.item_by_citation[lookup_key] = e_id
        return e_id

    def format_pack_for_llm(self) -> str:
        """
        Formats the bounded evidence pack as a strict, impenetrable context block.
        The prompt rule: every claim cites evidence IDs, no law from memory.
        """
        lines = [
            "================================================================================",
            "BOUNDED EVIDENCE PACK (EXCLUSIVE ADMISSIBLE LAW & SOURCES)",
            "CRITICAL INVARIANTS:",
            "1. The model NEVER supplies law from memory. You may cite ONLY from this pack.",
            "2. Every single claim MUST carry an evidence ID tag, e.g. [E1] or [E2].",
            "3. Use EXACT unit types ('Article 57', NOT 'Section 57' or 'Section 264').",
            "4. If the pack does not answer the question, state so explicitly under 'not_found'.",
            "================================================================================",
            ""
        ]

        statute_items = [it for it in self.items.values() if it.item_type in ("statute_unit", "linked_caveat")]
        case_items = [it for it in self.items.values() if it.item_type == "judicial_precedent"]

        lines.append("### STATUTORY PROVISIONS & LINKED CAVEATS ON RECORD:")
        if not statute_items:
            lines.append("No statutory provisions admitted for this query.")
        else:
            for item in statute_items:
                if item.item_type == "linked_caveat":
                    lines.append(f"[{item.id}] CAVEAT / LOCAL OVERRIDE: {item.heading_description}")
                    lines.append(f"Jurisdiction: {item.jurisdiction.capitalize()} | {item.parent}")
                    lines.append(f"OPERATIONAL CAVEAT:\n\"\"\"\n{item.text}\n\"\"\"")
                    lines.append("")
                else:
                    unit_label = (item.unit_type or "provision").capitalize()
                    lines.append(f"[{item.id}] {item.statute_title} — {unit_label} {item.number}")
                    if item.parent:
                        lines.append(f"Schedule / Part: {item.parent}")
                    lines.append(f"Description of Suit: {item.heading_description}")
                    if item.period:
                        lines.append(f"Period of Limitation: {item.period}")
                    if item.trigger:
                        lines.append(f"Time from which Period begins to run: {item.trigger}")
                    lines.append(f"VERBATIM TEXT:\n\"\"\"\n{item.text}\n\"\"\"")
                    if item.footnotes:
                        lines.append(f"Footnotes / Statutory Annotations: {'; '.join(item.footnotes)}")
                    if item.caveats:
                        lines.append(f"Linked Overrides: {'; '.join(item.caveats)}")
                    lines.append("")

        lines.append("### JUDICIAL PRECEDENTS ON RECORD:")
        if not case_items:
            lines.append("No judicial precedents admitted for this query.")
        else:
            for item in case_items:
                lines.append(f"[{item.id}] {item.citation} — {item.case_title}")
                lines.append(f"Court: {item.court} | Year: {item.year or 'N/A'}")
                if item.statutes_invoked:
                    lines.append(f"Statutes Invoked: {', '.join(item.statutes_invoked)}")
                lines.append(f"RECORDED RATIO DECIDENDI:\n\"\"\"\n{item.ratio}\n\"\"\"")
                lines.append("")

        lines.append("================================================================================")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes pack to dictionary keyed by E-ID."""
        return {eid: item.model_dump() for eid, item in self.items.items()}
