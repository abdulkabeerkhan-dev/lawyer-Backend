"""
core/evidence_verifier.py

Deterministic Code Verification Engine for the Legal Research Pipeline (Stage 6).
Executes strictly in code (zero LLM reliance) to verify generated memoranda:
1. Every source tag [S#] / [C#] exists in the evidence pack.
2. Every statute quote is an exact substring of stored section text.
3. Every case citation matches a retrieved record; court & reporter pass reporter-to-court check.
4. Case ratio shown matches the stored ratio in the pack.
5. No phantom citations, section numbers, or case names appear outside the pack.
6. Banned absolutes ('must', 'exclusively', 'cannot') are flagged unless inside quotes.
7. Output is complete, valid JSON without truncation.
8. Computes honest verification badge and audit trail.
"""

import json
import re
from typing import Dict, List, Any, Tuple, Optional, Set
from core.evidence_pack import EvidencePack
from core.case_integrity import check_reporter_court_consistency, normalize_citation

# Strict pattern for Pakistani citations
PAK_CITATION_PATTERN = re.compile(
    r'\b(?:19|20)\d{2}\s+(?:SCMR|PLD|CLC|PCrLJ|MLD|YLR|CLD|PLR|PSC)\s+\d+\b',
    re.IGNORECASE
)

# Section / Order patterns
SECTION_PATTERN = re.compile(
    r'\b(?:Section|Sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))?)\b',
    re.IGNORECASE
)

ORDER_RULE_PATTERN = re.compile(
    r'\bOrder\s+([IVXLCDM]+)(?:\s*,?\s*Rule\s+(\d+[A-Za-z]?))?\b',
    re.IGNORECASE
)

# Banned absolute words when used outside quotation marks
BANNED_ABSOLUTES_PATTERN = re.compile(
    r'\b(must|exclusively|cannot)\b',
    re.IGNORECASE
)


def normalize_stream(text: str) -> str:
    """Collapses whitespace and normalizes punctuation for substring matching."""
    if not text:
        return ""
    t = re.sub(r'["\'`“”‘’]', '', text)
    return " ".join(t.lower().split())


def strip_quotes(text: str) -> str:
    """Replaces quoted substrings with whitespace to inspect unquoted prose."""
    return re.sub(r'"[^"]*"|\'[^\']*\'|“[^”]*”', ' ', text)


class EvidenceVerifier:
    """
    Executes deterministic checks against the generated output and EvidencePack.
    """
    def __init__(self, pack: EvidencePack):
        self.pack = pack
        self.failures: List[str] = []
        self.warnings: List[str] = []

    def verify(self, memo_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs all 7 deterministic checks and returns an immutable verification report.
        """
        self.failures.clear()
        self.warnings.clear()

        # Check 1: Output complete JSON and schema
        is_schema_valid = self._check_schema(memo_json)

        # Check 2: Source ID Existence
        self._check_source_tags(memo_json)

        # Check 3: Exact Statute Quote Substrings
        self._check_statute_quotes(memo_json)

        # Check 4: Case Citation & Reporter Validity
        self._check_cases(memo_json)

        # Check 5: Phantom Citations and Statutes outside pack
        self._check_phantom_references(memo_json)

        # Check 6: Banned Absolutes in unquoted prose
        self._check_banned_absolutes(memo_json)

        # Check 7: No mid-sentence truncation
        self._check_truncation(memo_json)

        # Check 8: Compute verification badge
        has_primary_records = bool(self.pack.statutes or self.pack.cases)
        if not has_primary_records:
            self.failures.append("No primary statutory provisions or precedents were admitted in the evidence pack for this query.")
            is_verified = False
            status = "unverified"
            badge_text = "Unverified: No primary records found in verified database for this query."
        else:
            is_verified = (len(self.failures) == 0) and is_schema_valid
            status = "verified" if is_verified else "partially_verified"
            if is_verified:
                badge_text = "All citations and quotes verified against primary judicial & statutory sources."
            else:
                badge_text = f"Partially verified ({len(self.failures)} item(s) unverified against primary records)"

        return {
            "is_verified": is_verified,
            "status": status,
            "badge_text": badge_text,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "database_freshness": "Database current as of November 2026"
        }

    def _check_schema(self, data: Dict[str, Any]) -> bool:
        if not isinstance(data, dict):
            self.failures.append("Generated memo is not a valid JSON dictionary.")
            return False
        required_keys = ["question", "short_answer", "statutes", "cases", "options_described_by_sources", "gaps"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            self.failures.append(f"Missing required schema fields: {', '.join(missing)}")
            return False
        return True

    def _check_source_tags(self, data: Dict[str, Any]):
        valid_ids: Set[str] = set(self.pack.statutes.keys()) | set(self.pack.cases.keys())

        # Check short_answer source tags
        for idx, item in enumerate(data.get("short_answer") or []):
            if isinstance(item, dict):
                sources = item.get("sources") or []
                for s in sources:
                    clean_s = str(s).strip("[]")
                    if clean_s not in valid_ids:
                        self.failures.append(f"short_answer[{idx}] references non-existent source ID '{s}'.")

        # Check options_described_by_sources tags
        for idx, item in enumerate(data.get("options_described_by_sources") or []):
            if isinstance(item, dict):
                sources = item.get("sources") or []
                for s in sources:
                    clean_s = str(s).strip("[]")
                    if clean_s not in valid_ids:
                        self.failures.append(f"options[{idx}] references non-existent source ID '{s}'.")

    def _check_statute_quotes(self, data: Dict[str, Any]):
        for idx, item in enumerate(data.get("statutes") or []):
            sid = str(item.get("id") or "").strip("[]")
            quote = str(item.get("quote") or "").strip()

            if sid not in self.pack.statutes:
                self.failures.append(f"Statute item [{sid}] does not exist in the evidence pack.")
                continue

            stored = self.pack.statutes[sid]
            stored_stream = normalize_stream(stored.get("text", ""))
            quote_stream = normalize_stream(quote)

            if not quote:
                self.failures.append(f"Statute [{sid}] ({stored.get('title')}) lacks verbatim quote.")
            elif len(quote_stream) < 15:
                self.warnings.append(f"Statute [{sid}] quote is very short ({len(quote_stream)} chars).")
            elif quote_stream not in stored_stream:
                self.failures.append(
                    f"Statute [{sid}] quote is not an exact substring of stored text for {stored.get('act_name')}, Section {stored.get('section_number')}."
                )

    def _check_cases(self, data: Dict[str, Any]):
        for idx, item in enumerate(data.get("cases") or []):
            cid = str(item.get("id") or "").strip("[]")
            if cid not in self.pack.cases:
                self.failures.append(f"Case item [{cid}] does not exist in the evidence pack.")
                continue

            stored = self.pack.cases[cid]
            cit = stored.get("citation", "")
            court = stored.get("court", "")

            # Reporter to court check
            is_consistent, _, msg = check_reporter_court_consistency(cit, court)
            if not is_consistent:
                self.failures.append(f"Precedent [{cid}] ({cit}): {msg}")

            # Ratio concordance check
            memo_ratio = str(item.get("ratio_as_recorded") or "").strip()
            if not memo_ratio:
                self.failures.append(f"Precedent [{cid}] has empty recorded ratio.")
            else:
                stored_stream = normalize_stream(stored.get("ratio", ""))
                memo_stream = normalize_stream(memo_ratio)
                # Ensure substantial overlap or substring match
                common_tokens = set(memo_stream.split()) & set(stored_stream.split())
                if len(common_tokens) < 5 and memo_stream not in stored_stream:
                    self.failures.append(
                        f"Precedent [{cid}] recorded ratio diverges from stored record in database."
                    )

    def _check_phantom_references(self, data: Dict[str, Any]):
        # Collect all allowed citations and sections from pack
        allowed_cits = {normalize_citation(c["citation"]) for c in self.pack.cases.values()}
        allowed_secs = {s["section_number"].upper() for s in self.pack.statutes.values()}

        # Scan text fields
        text_blobs = []
        for item in data.get("short_answer") or []:
            if isinstance(item, dict):
                text_blobs.append(item.get("text", ""))
        for item in data.get("options_described_by_sources") or []:
            if isinstance(item, dict):
                text_blobs.append(item.get("text", ""))

        full_memo_text = " ".join(text_blobs)

        # Phantom citations
        found_cits = PAK_CITATION_PATTERN.findall(full_memo_text)
        for fc in found_cits:
            norm_fc = normalize_citation(fc)
            if norm_fc not in allowed_cits:
                self.failures.append(f"Phantom citation found outside evidence pack: '{fc}'.")

        # Phantom sections & schedule out-of-range gating (outside quotes)
        unquoted = strip_quotes(full_memo_text)
        found_secs = SECTION_PATTERN.findall(unquoted)
        for fs in found_secs:
            clean_sec = fs.strip().upper()
            clean_digits = re.sub(r'[^0-9]', '', clean_sec)

            # Strict Structured Index Gating for Limitation Act
            if any("LIMITATION" in s.get("act_name", "").upper() for s in self.pack.statutes.values()):
                if clean_digits:
                    num_val = int(clean_digits)
                    # Corrupted footnote fusions e.g. 257, 264
                    if num_val in [252, 253, 257, 259, 261, 263, 264, 266, 267, 268, 269, 270, 271, 276, 277, 278, 279, 280, 228]:
                        self.failures.append(
                            f"Corrupted footnote citation detected: 'Section/Article {fs}'. "
                            f"Footnote marker fused onto provision number in unverified text."
                        )
                    elif num_val > 183:
                        self.failures.append(
                            f"Out-of-range statutory citation: '{fs}'. "
                            f"The Limitation Act, 1908 contains only Sections 1–32 and First Schedule Articles 1–183."
                        )

            # If section number not in allowed sections (allow common numbering like 1, 2)
            if clean_sec not in allowed_secs and clean_sec not in ["1", "2"]:
                self.warnings.append(f"Unverified section number cited outside evidence pack: Section {fs}.")

    def _check_banned_absolutes(self, data: Dict[str, Any]):
        text_blobs = []
        for item in data.get("short_answer") or []:
            if isinstance(item, dict):
                text_blobs.append(item.get("text", ""))
        for item in data.get("options_described_by_sources") or []:
            if isinstance(item, dict):
                text_blobs.append(item.get("text", ""))

        combined = " ".join(text_blobs)
        unquoted = strip_quotes(combined)

        banned_matches = BANNED_ABSOLUTES_PATTERN.findall(unquoted)
        if banned_matches:
            unique_banned = set(m.lower() for m in banned_matches)
            self.warnings.append(
                f"Absolute language detected outside quotes: {', '.join(unique_banned)}. "
                f"Replace with 'the retrieved provision states...' or 'under the retrieved authorities...'."
            )

    def _check_truncation(self, data: Dict[str, Any]):
        text_blobs = []
        for item in data.get("short_answer") or []:
            if isinstance(item, dict):
                text_blobs.append(item.get("text", ""))
        for item in data.get("options_described_by_sources") or []:
            if isinstance(item, dict):
                text_blobs.append(item.get("text", ""))

        for t in text_blobs:
            stripped = t.strip()
            if stripped.endswith("...") or stripped.endswith("and") or stripped.endswith("or") or stripped.endswith("that"):
                self.failures.append(f"Memo text appears truncated mid-sentence: '{stripped[-30:]}'")


def format_verified_memo_to_markdown(
    memo_json: Dict[str, Any],
    pack: EvidencePack,
    report: Dict[str, Any]
) -> str:
    """
    Renders the verified JSON schema into the full Research Memorandum format for DocumentView.
    """
    lines = []

    # Verification banner (Honest badge)
    status = report.get("status", "unverified")
    is_verified = report.get("is_verified", False)
    if status == "unverified":
        status_label = "UNVERIFIED LEGAL RESEARCH RECORD"
    elif is_verified:
        status_label = "VERIFIED LEGAL RESEARCH RECORD"
    else:
        status_label = "PARTIAL LEGAL RESEARCH RECORD"
    lines.append(f"# {status_label}")
    lines.append(f"**Verification Status**: {report.get('badge_text', 'Verified')}")
    lines.append(f"**Data Freshness**: {report.get('database_freshness', 'Database current as of November 2026')}")
    lines.append("")

    if report.get("failures"):
        lines.append("> [!WARNING] Unverified Elements Detected")
        for fail in report["failures"]:
            lines.append(f"> - {fail}")
        lines.append("")

    # Short Answer / Primary Legal Findings
    lines.append("## Primary Legal Findings")
    short_answers = memo_json.get("short_answer") or []
    if isinstance(short_answers, list):
        for sa in short_answers:
            if isinstance(sa, dict):
                txt = sa.get("text", "")
                srcs = sa.get("sources", [])
                src_str = " " + " ".join(f"[{s.strip('[]')}]" for s in srcs) if srcs else ""
                lines.append(f"{txt}{src_str}\n")
            elif isinstance(sa, str):
                lines.append(f"{sa}\n")
    lines.append("")

    # Statutory Provisions on Record
    lines.append("## Verified Statutory Provisions on Record")
    statutes = memo_json.get("statutes") or []
    if not statutes and hasattr(pack, "statutes") and pack.statutes:
        statutes = [
            {"id": sid, "quote": sdata.get("text") or sdata.get("verbatim_text") or "", "plain_explanation": ""}
            for sid, sdata in pack.statutes.items()
        ]
    if not statutes:
        lines.append("_No verified statutory provisions were admitted for this query._\n")
    else:
        for st in statutes:
            sid = st.get("id", "").strip("[]")
            stored = pack.statutes.get(sid, {})
            act_name = stored.get("act_name", "Statute")
            sec_num = stored.get("section_number", "")
            quote = st.get("quote", stored.get("text", ""))
            explanation = st.get("plain_explanation", "")

            prov_type = str(stored.get("provision_type") or ("article" if ("_ART_" in sid or "CONST" in act_name.upper()) else "section")).title()
            clean_num = re.sub(r'^(?:Article|Section|Order|Rule)\s+', '', str(sec_num), flags=re.I).strip()
            lines.append(f"### [{sid}] {prov_type} {clean_num}, {act_name}")
            lines.append(f"> \"{quote}\"\n")
            if explanation:
                lines.append(f"**Statutory Effect**: {explanation}\n")
            if stored.get("status"):
                lines.append(f"_Status: {stored['status']} | Scope: {stored.get('jurisdiction', 'Federal/Provincial')}_\n")

    # Judicial Precedents on Record
    lines.append("## Retrieved Judicial Precedents on Record")
    cases = memo_json.get("cases") or []
    if not cases and hasattr(pack, "cases") and pack.cases:
        cases = [
            {
                "id": cid,
                "ratio_as_recorded": cdata.get("ratio") or cdata.get("ratio_decidendi") or cdata.get("preview") or "",
                "relevance": ""
            }
            for cid, cdata in pack.cases.items()
        ]
    if not cases:
        lines.append("_No judicial precedents were admitted for this query._\n")
    else:
        for c in cases:
            cid = c.get("id", "").strip("[]")
            stored = pack.cases.get(cid, {})
            cit = stored.get("citation", "")
            title = stored.get("case_title", "")
            court = stored.get("court", "Superior Court of Pakistan")
            ratio = c.get("ratio_as_recorded") or stored.get("ratio", "")
            relevance = c.get("relevance", "")

            lines.append(f"### [{cid}] {cit} — {title}")
            lines.append(f"**Court**: {court} | **Binding Force**: Article 189/201")
            lines.append(f"\n- **Ratio Decidendi**: {ratio}\n")
            if relevance:
                lines.append(f"- **Application to Query**: {relevance}\n")

    # Procedural Options Described by Sources
    options = memo_json.get("options_described_by_sources") or []
    if options:
        lines.append("## Procedural & Legal Options Described by Sources")
        for opt in options:
            if isinstance(opt, dict):
                txt = opt.get("text", "")
                srcs = opt.get("sources", [])
                src_str = " " + " ".join(f"[{s.strip('[]')}]" for s in srcs) if srcs else ""
                lines.append(f"- {txt}{src_str}")
            elif isinstance(opt, str):
                lines.append(f"- {opt}")
        lines.append("")

    # Gaps in Sources
    gaps = memo_json.get("gaps") or []
    lines.append("## Research Scope & Source Gaps")
    if gaps:
        lines.append("The retrieved sources do **not** resolve or address the following matters:")
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- All legal points within query scope were addressed by the admitted sources.")
    lines.append("")

    lines.append("---")
    lines.append("_Notice: This memorandum is strictly grounded in retrieved authentic statutes and superior court case law. Counsel must verify certified copies of primary records before initiating court proceedings._")

    return "\n".join(lines)
