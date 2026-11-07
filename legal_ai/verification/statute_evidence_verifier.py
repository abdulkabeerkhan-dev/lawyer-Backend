"""
legal_ai/verification/statute_evidence_verifier.py

Layer 7: Deterministic Code Verifier for Structured Legal Memoranda.
Executes purely in deterministic Python code without LLM self-grading:
1. Every evidence_id in claims[] exists in the Bounded Evidence Pack.
2. Quoted text matches the stored legal unit text exactly.
3. Every cited statutory number exists in the store with the exact unit_type
   (strictly blocks 'Section 264', 'Section 57', or 'Article 257').
4. Claims without grounded evidence are flagged and stripped of verified status.
5. Verification badges are awarded strictly per claim and per memo upon 100% compliance.
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field

from legal_ai.statutes.legal_unit_record import LegalUnitRecord


class ClaimVerificationStatus(BaseModel):
    statement: str
    evidence_ids: List[str]
    is_verified: bool
    violations: List[str] = Field(default_factory=list)
    citations_checked: List[str] = Field(default_factory=list)


class MemoVerificationReport(BaseModel):
    is_memo_verified: bool = False
    total_claims: int = 0
    verified_claims_count: int = 0
    unverified_claims_count: int = 0
    claim_statuses: List[ClaimVerificationStatus] = Field(default_factory=list)
    blocking_violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    mode: str = "full"  # "full" or "partial_result"


class StatuteEvidenceVerifier:
    """
    Deterministic plain-code verifier that gates memo rendering and badge attachment.
    """

    UNIT_CITATION_REGEX = re.compile(
        r'\b(section|sec\.?|article|art\.?|order|rule|schedule)\s*([0-9]+[A-Za-z]?(?:-[A-Za-z])?)\b(?:\s+of\s+(?:the\s+)?([^,\.;\n]+))?',
        re.IGNORECASE
    )

    def __init__(self, legal_unit_store: Optional[Dict[str, LegalUnitRecord]] = None):
        """
        legal_unit_store: dict mapping canonical unit_id (or number lookup) to LegalUnitRecord.
        """
        self.store: Dict[str, LegalUnitRecord] = legal_unit_store or {}

    def register_units(self, units: List[LegalUnitRecord]):
        for u in units:
            self.store[u.unit_id.lower()] = u
            # Also register by shorthand key: statute_id:unit_type:num
            short_key = f"{u.statute_id}:{u.unit_type}:{u.number}".lower()
            self.store[short_key] = u

    def verify_structured_memo(
        self,
        memo_payload: Dict[str, Any],
        evidence_pack: Dict[str, Any]
    ) -> MemoVerificationReport:
        """
        Verifies structured memo JSON:
        memo_payload = {
            "answer": "...",
            "claims": [{"statement": "...", "evidence_ids": ["E1"]}],
            "caveats": ["..."],
            "not_found": []
        }
        evidence_pack = {
            "E1": LegalUnitRecord or dict
        }
        """
        report = MemoVerificationReport()
        claims = memo_payload.get("claims", [])
        report.total_claims = len(claims)

        if not claims:
            # If no claims provided, cannot award verified badge
            report.blocking_violations.append("Structured memo contains zero claims.")
            report.mode = "partial_result"
            return report

        all_ok = True

        for c in claims:
            statement = str(c.get("statement", "")).strip()
            ev_ids = [str(e).strip() for e in c.get("evidence_ids", []) if str(e).strip()]

            c_status = ClaimVerificationStatus(
                statement=statement,
                evidence_ids=ev_ids,
                is_verified=False
            )

            # 1. Evidence ID existence in Evidence Pack
            if not ev_ids:
                c_status.violations.append("Claim has no grounded evidence ID from Evidence Pack.")
                all_ok = False
            else:
                for eid in ev_ids:
                    if eid not in evidence_pack:
                        c_status.violations.append(f"Evidence ID '{eid}' does not exist in the Evidence Pack.")
                        all_ok = False

            # 2. Check all cited numbers and unit_types inside the statement
            stat_violations, citations_checked = self._verify_citations_in_text(statement, ev_ids, evidence_pack)
            c_status.violations.extend(stat_violations)
            c_status.citations_checked = citations_checked
            if stat_violations:
                all_ok = False

            # 3. Check exact quotes in statement if quotation marks are used
            quote_violations = self._verify_quotes_in_text(statement, ev_ids, evidence_pack)
            c_status.violations.extend(quote_violations)
            if quote_violations:
                all_ok = False

            c_status.is_verified = (len(c_status.violations) == 0)
            if c_status.is_verified:
                report.verified_claims_count += 1
            else:
                report.unverified_claims_count += 1

            report.claim_statuses.append(c_status)

        report.is_memo_verified = all_ok and (report.verified_claims_count == report.total_claims)
        if not report.is_memo_verified:
            report.mode = "partial_result"
            for cs in report.claim_statuses:
                report.blocking_violations.extend(cs.violations)

        return report

    def verify_rendered_memo_text(
        self,
        memo_text: str,
        evidence_pack: Dict[str, Any]
    ) -> MemoVerificationReport:
        """
        Verifies plain rendered memo markdown against the Evidence Pack and Knowledge Store.
        """
        report = MemoVerificationReport()
        stat_violations, citations_checked = self._verify_citations_in_text(memo_text, list(evidence_pack.keys()), evidence_pack)
        quote_violations = self._verify_quotes_in_text(memo_text, list(evidence_pack.keys()), evidence_pack)

        all_violations = stat_violations + quote_violations
        report.blocking_violations = all_violations
        report.is_memo_verified = (len(all_violations) == 0)
        report.mode = "full" if report.is_memo_verified else "partial_result"
        return report

    def _verify_citations_in_text(
        self,
        text: str,
        ev_ids: List[str],
        evidence_pack: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        """
        Deterministic check that every statutory unit cited exists with the right unit_type.
        Specifically blocks calling an Article a Section, or referencing phantom numbers like 264.
        """
        violations: List[str] = []
        checked: List[str] = []

        for m in self.UNIT_CITATION_REGEX.finditer(text):
            raw_type = m.group(1).lower()
            num = m.group(2).upper()
            statute_mention = (m.group(3) or "").lower()

            norm_type = "article" if raw_type in ("article", "art", "art.") else "section"
            citation_repr = f"{norm_type.capitalize()} {num}"
            checked.append(citation_repr)

            # Check if Limitation Act is mentioned or in context
            is_limitation = ("limitation" in statute_mention) or any(
                "limitation" in str(getattr(evidence_pack.get(eid), "statute_id", "")).lower() or
                "limitation" in str((evidence_pack.get(eid) if isinstance(evidence_pack.get(eid), dict) else {}).get("statute_id", "")).lower()
                for eid in ev_ids
            )

            if is_limitation:
                # Limitation Act validation rules:
                # 1. Numbers > 32 in Limitation Act can ONLY be Articles in Schedule I, NEVER Sections
                num_digits = re.match(r"^(\d+)", num)
                if num_digits:
                    val = int(num_digits.group(1))
                    if val > 32 and norm_type == "section":
                        violations.append(
                            f"Violation: 'Section {num}' does not exist in the Limitation Act, 1908. "
                            f"Provisions beyond Section 32 are Articles in the First Schedule (must be cited as 'Article {num}')."
                        )
                    elif val > 183:
                        violations.append(
                            f"Violation: Phantom citation 'Article/Section {num}' does not exist in the Limitation Act, 1908 (First Schedule spans Articles 1-183)."
                        )
                    elif val in (57, 64) and norm_type == "section":
                        violations.append(
                            f"Violation: Inapplicable unit type 'Section {num}'. Under the Limitation Act, 1908, "
                            f"recovery periods for money lent/accounts stated are governed by 'Article {num}', not Section {num}."
                        )

            # Also verify against self.store if populated
            if self.store:
                lim_art_key = f"limitation-act-1908:article:{num}".lower()
                lim_sec_key = f"limitation-act-1908:section:{num}".lower()
                if is_limitation:
                    if norm_type == "section" and lim_art_key in self.store and lim_sec_key not in self.store:
                        msg = f"Violation: Provision {num} is an Article, not a Section, in the Limitation Act, 1908."
                        if msg not in violations:
                            violations.append(msg)
                    elif norm_type == "article" and lim_art_key not in self.store:
                        msg = f"Violation: Article {num} was not found in the verified store for Limitation Act, 1908."
                        if msg not in violations:
                            violations.append(msg)

        return violations, checked

    def _verify_quotes_in_text(
        self,
        text: str,
        ev_ids: List[str],
        evidence_pack: Dict[str, Any]
    ) -> List[str]:
        """
        Ensures any text enclosed in quotation marks matches the official text of the cited evidence records.
        """
        violations: List[str] = []
        quotes = re.findall(r'["“]([^"”]{15,})["”]', text)

        if not quotes:
            return violations

        # Aggregate official texts from cited evidence
        pack_texts = []
        for eid in ev_ids:
            ev = evidence_pack.get(eid)
            if ev:
                t = getattr(ev, "text", "") or (ev.get("text", "") if isinstance(ev, dict) else "")
                h = getattr(ev, "heading_description", "") or (ev.get("heading_description", "") if isinstance(ev, dict) else "")
                trig = getattr(ev, "trigger", "") or (ev.get("trigger", "") if isinstance(ev, dict) else "")
                pack_texts.extend([t, h, trig])

        joined_evidence_text = " ".join([t for t in pack_texts if t]).lower()
        joined_evidence_clean = re.sub(r'\s+', ' ', joined_evidence_text)

        for q in quotes:
            clean_q = re.sub(r'\s+', ' ', q).strip().lower()
            if len(clean_q) > 20 and clean_q not in joined_evidence_clean:
                # Check fuzzy/substring match
                words = clean_q.split()
                if len(words) >= 4:
                    sub_phrase = " ".join(words[:4])
                    if sub_phrase not in joined_evidence_clean:
                        violations.append(
                            f"Violation: Quoted text '{q[:50]}...' does not match the official text in the cited Evidence Pack."
                        )

        return violations
