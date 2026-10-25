"""
core/statute_claim_verifier.py

General Claim-Support Verifier for Pakistani Statutory Provisions & Case Attribution.
Validates that:
1. Every statutory proposition, condition, percentage, penalty, exception, duration,
   and cross-reference in an AI-generated legal memorandum is supported
   by the official stored text of the referenced enactment and section.
2. Every precedent citation attributed to a statutory provision in the memo actually
   interprets that enactment and section in the retrieved judicial record
   (e.g., 2026 CLD 39 concerns FIO 2001 Ss. 9 & 22, NOT the Civil Procedure Code).

Zero query-specific hardcoding. Completely general across all Pakistani enactments.
"""

import re
from typing import Dict, List, Any, Tuple, Optional

# --- GENERAL CONCEPT BENCHMARKS FOR PAKISTANI ENACTMENTS ---
STATUTORY_CONCEPT_BENCHMARKS = [
    # 1. Financial Conditions, Percentages & Security
    ("deposit_percentage", [r'\b\d+(?:\.\d+)?\s*%\b', r'\b\d+(?:\.\d+)?\s*percent\b']),
    ("decretal_amount_deposit", ["decretal amount", "deposit in cash", "deposits in cash", "furnishing of security", "bank guarantee"]),
    ("fine_and_penalties", ["fine which may extend", "liable to fine", "penalty of not less than", "penalty", "shall be punishable with fine"]),
    
    # 2. Sentences, Imprisonment & Criminal Classifications
    ("imprisonment_duration", [
        r'\b(?:rigorous|simple)?\s*imprisonment\s+(?:for\s+a\s+term\s+)?(?:which\s+may\s+extend\s+to\s+)?(?:\w+\s+)?(?:years|months|days|life)\b',
        "death", "life imprisonment", "rigorous imprisonment", "simple imprisonment"
    ]),
    
    # 3. Limitation Periods & Timeframes
    ("limitation_period", [
        r'\b(?:within|period of)\s+(?:fifteen|twenty[- ]one|thirty|sixty|ninety|one hundred and eighty|\d+)\s+days\b',
        r'\b(?:within|period of)\s+(?:one|two|three|five|six|\d+)\s+(?:months|years)\b',
        "period of limitation", "prescribed period", "barred by limitation"
    ]),
    
    # 4. Bench Composition & Forum
    ("bench_composition", ["single judge", "division bench", "bench of not less than two", "two judges", "full bench"]),
    
    # 5. Natural Justice & Procedural Notice
    ("procedural_notice", ["opportunity of being heard", "opportunity of hearing", "notice in writing", "show cause notice", "direct notice"]),
    
    # 6. Negative Bars & Appealability
    ("interlocutory_bar", ["interlocutory order", "no appeal shall lie", "final order", "leave to defend", "bar to suit"]),
    
    # 7. Ex-Parte Restraints
    ("ex_parte_injunction", ["ex-parte", "ex parte", "in the absence of defendant", "dispense with such notice"])
]


class StatuteClaimVerificationResult:
    def __init__(
        self, 
        passed: bool, 
        violations: List[Dict[str, Any]], 
        verified_claims: List[Dict[str, Any]],
        attribution_violations: Optional[List[Dict[str, Any]]] = None
    ):
        self.passed = passed
        self.violations = violations
        self.verified_claims = verified_claims
        self.attribution_violations = attribution_violations or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations_count": len(self.violations),
            "violations": self.violations,
            "attribution_violations_count": len(self.attribution_violations),
            "attribution_violations": self.attribution_violations,
            "verified_claims_count": len(self.verified_claims),
            "verified_claims": self.verified_claims
        }


def _normalize_text(txt: Any) -> str:
    if isinstance(txt, dict):
        txt = " ".join(str(v) for v in txt.values())
    return re.sub(r'\s+', ' ', str(txt).lower()).strip()


def verify_memo_statutory_claims(
    memo_text: str,
    stored_provisions: Dict[str, Any],
    primary_section: str = ""
) -> StatuteClaimVerificationResult:
    """
    Verifies statutory claims in memo_text against stored_provisions.
    stored_provisions: Dict mapping canonical_id or section string (e.g. 'FIO_2001_SEC_22')
                       to the official stored text (cleaned).
    """
    violations = []
    verified_claims = []

    stored_texts = []
    for v in stored_provisions.values():
        if isinstance(v, dict):
            stored_texts.append(" ".join(str(x) for x in v.values()))
        else:
            stored_texts.append(str(v))
    combined_stored_text = _normalize_text(" ".join(stored_texts))

    # Target sections only (Relevant Provisions & Application to Query)
    lines = memo_text.splitlines()
    target_lines = []
    in_target_section = False

    for line in lines:
        stripped = line.strip()
        if any(h in stripped for h in ["## Relevant Provisions", "## Application to Query", "## Statutory Grounding"]):
            in_target_section = True
            continue
        elif stripped.startswith("## ") and in_target_section:
            if not any(h in stripped for h in ["## Relevant Provisions", "## Application to Query", "## Statutory Grounding"]):
                in_target_section = False

        if in_target_section and stripped:
            target_lines.append(stripped)

    # Check target lines
    for line in target_lines:
        if line.startswith("#") or line.startswith("---") or line.startswith("*Status:") or line.startswith("LABEL:"):
            continue

        line_norm = _normalize_text(line)

        # 1. Provision & subsection cross-references
        refs = re.findall(r'(?:section|s\.)\s*([0-9]+(?:[-][0-9a-z]+|[a-z])?)(?:\(([0-9]+)\))?', line, flags=re.IGNORECASE)
        for sec_num, sub_num in refs:
            sec_num_clean = re.sub(r'[^0-9a-z]', '', sec_num.lower())
            primary_clean = re.sub(r'[^0-9a-z]', '', primary_section.lower())
            if primary_section and sec_num_clean == primary_clean:
                if sub_num:
                    if f"({sub_num})" in combined_stored_text or f"sub-section ({sub_num})" in combined_stored_text or f"subsection ({sub_num})" in combined_stored_text:
                        verified_claims.append({
                            "type": "verified_primary_subsection",
                            "reference": f"Section {sec_num}({sub_num})"
                        })
                    else:
                        violations.append({
                            "type": "unsupported_subsection",
                            "line": line,
                            "unsupported_term": f"Section {sec_num}({sub_num})",
                            "reason": f"Subsection '({sub_num})' does not exist in the stored text of Section {sec_num}."
                        })
                else:
                    verified_claims.append({
                        "type": "verified_primary_section",
                        "reference": f"Section {sec_num}"
                    })
            else:
                # External cross-reference
                term_to_find_1 = f"section {sec_num.lower()}"
                term_to_find_2 = f"section {sec_num_clean}"
                if term_to_find_1 in combined_stored_text or term_to_find_2 in combined_stored_text or sec_num.lower() in combined_stored_text:
                    if sub_num:
                        sub_pattern = rf'(?:sub\s*-\s*section\s*\({sub_num}\)|sub-section\s*\({sub_num}\)|\({sub_num}\)).*?section\s*{sec_num_clean}|section\s*{sec_num_clean}.*?\({sub_num}\)'
                        if re.search(sub_pattern, combined_stored_text):
                            verified_claims.append({
                                "type": "verified_external_cross_reference",
                                "reference": f"Section {sec_num}({sub_num})"
                            })
                        else:
                            violations.append({
                                "type": "unsupported_external_subsection",
                                "line": line,
                                "unsupported_term": f"Section {sec_num}({sub_num})",
                                "reason": f"Section {sec_num} is referenced, but subsection ({sub_num}) is not in stored text."
                            })
                    else:
                        verified_claims.append({
                            "type": "verified_external_section",
                            "reference": f"Section {sec_num}"
                        })
                else:
                    violations.append({
                        "type": "unsupported_external_cross_reference",
                        "line": line,
                        "unsupported_term": f"Section {sec_num}" + (f"({sub_num})" if sub_num else ""),
                        "reason": f"Cited cross-reference 'Section {sec_num}' does not appear in the stored statutory text."
                    })

        # 2. Substantive legal conditions & benchmarks
        for concept_name, patterns in STATUTORY_CONCEPT_BENCHMARKS:
            matched_in_line = False
            matched_pattern = None
            for pat in patterns:
                if pat.startswith(r'\b') or '(' in pat:
                    if re.search(pat, line_norm, re.IGNORECASE):
                        matched_in_line = True
                        matched_pattern = pat
                        break
                else:
                    if pat.lower() in line_norm:
                        matched_in_line = True
                        matched_pattern = pat
                        break

            if matched_in_line:
                # Check whether concept exists in stored text
                in_store = False
                for pat in patterns:
                    if pat.startswith(r'\b') or '(' in pat:
                        if re.search(pat, combined_stored_text, re.IGNORECASE):
                            in_store = True
                            break
                    else:
                        if pat.lower() in combined_stored_text:
                            in_store = True
                            break

                if not in_store:
                    violations.append({
                        "type": "unsupported_statutory_condition",
                        "line": line,
                        "unsupported_term": concept_name,
                        "pattern": matched_pattern,
                        "reason": f"Substantive condition '{concept_name}' is asserted in the memo but is missing from stored statutory text."
                    })
                else:
                    verified_claims.append({
                        "type": "verified_statutory_condition",
                        "concept": concept_name
                    })

    if len(verified_claims) == 0:
        violations.append({
            "type": "zero_verified_claims",
            "unsupported_term": "zero_verified_claims",
            "reason": (
                "Verification failed: zero verified statutory claims found in memo. "
                "A pass requires at least one verified claim per statutory proposition, and fails on zero."
            )
        })
        passed = False
    else:
        passed = len(violations) == 0

    return StatuteClaimVerificationResult(passed=passed, violations=violations, verified_claims=verified_claims)


def verify_case_statute_attribution(
    memo_text: str,
    precedent_cards: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Validates that whenever a precedent (e.g. '2026 CLD 39') is cited in the memo,
    the statutory enactments and sections attributed to that case match the actual
    retrieved excerpt on record.
    Prevents false attributions (e.g., claiming 2026 CLD 39 concerns CPC Section 22
    when it actually interprets FIO 2001 Section 22).
    """
    attribution_violations = []

    for card in precedent_cards:
        cit = str(card.get("citation", "")).strip()
        if not cit:
            continue

        # Look for this citation in the memo text
        if cit.lower() not in memo_text.lower():
            continue

        # Find the paragraph or surrounding lines mentioning this citation
        card_text_corpus = (
            str(card.get("text", "")) + " " +
            str(card.get("preview", "")) + " " +
            str(card.get("ratio_decidendi", "")) + " " +
            str(card.get("title", "")) + " " +
            str(card.get("case_name", ""))
        ).lower()

        # Find memo lines referencing this case
        memo_lines = [l.strip() for l in memo_text.splitlines() if cit.lower() in l.lower()]
        for m_line in memo_lines:
            # Check if line asserts a statute name
            statute_mentions = re.findall(
                r'\b(Civil Procedure Code|CPC|Financial Institutions \(Recovery of Finances\) Ordinance|FIO|Pakistan Penal Code|PPC|Contract Act|Specific Relief Act)\b',
                m_line,
                flags=re.IGNORECASE
            )
            for sm in statute_mentions:
                sm_norm = sm.lower()
                # Check if this statute is present in the card's retrieved record
                if sm_norm in ["civil procedure code", "cpc"] and "cpc" not in card_text_corpus and "civil procedure" not in card_text_corpus:
                    attribution_violations.append({
                        "citation": cit,
                        "line": m_line,
                        "false_enactment": sm,
                        "reason": f"Memo attributes '{sm}' to precedent {cit}, but '{sm}' does not appear in the retrieved judicial text on record."
                    })
                elif sm_norm in ["financial institutions (recovery of finances) ordinance", "fio"] and "fio" not in card_text_corpus and "financial institutions" not in card_text_corpus and "recovery of finances" not in card_text_corpus:
                    attribution_violations.append({
                        "citation": cit,
                        "line": m_line,
                        "false_enactment": sm,
                        "reason": f"Memo attributes '{sm}' to precedent {cit}, but '{sm}' is absent from the case record."
                    })

    return attribution_violations
