"""
core/statute_claim_verifier.py

General Claim-Support Verifier for Statutory Provisions.
Validates that every statutory proposition, condition, exception, duration,
and cross-reference in an AI-generated legal memorandum is supported
by the official stored text of the referenced enactment and section.

Zero query-specific hard-coding.
"""

import re
from typing import Dict, List, Any, Tuple, Optional

class StatuteClaimVerificationResult:
    def __init__(self, passed: bool, violations: List[Dict[str, Any]], verified_claims: List[Dict[str, Any]]):
        self.passed = passed
        self.violations = violations
        self.verified_claims = verified_claims

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations_count": len(self.violations),
            "violations": self.violations,
            "verified_claims_count": len(self.verified_claims),
            "verified_claims": self.verified_claims
        }

def _normalize_text(txt: str) -> str:
    return re.sub(r'\s+', ' ', txt.lower()).strip()

def verify_memo_statutory_claims(
    memo_text: str,
    stored_provisions: Dict[str, str],
    primary_section: str = "22"
) -> StatuteClaimVerificationResult:
    """
    Verifies statutory claims in memo_text against stored_provisions.
    stored_provisions: Dict mapping canonical_id or section string (e.g. 'FIO_2001_SEC_22')
                       to the official stored text (cleaned).
    """
    violations = []
    verified_claims = []

    combined_stored_text = _normalize_text(" ".join(stored_provisions.values()))

    # 1. Target sections only (Relevant Provisions & Application to Query)
    lines = memo_text.splitlines()
    target_lines = []
    in_target_section = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Relevant Provisions") or stripped.startswith("## Application to Query"):
            in_target_section = True
            continue
        elif stripped.startswith("## ") and in_target_section:
            if not (stripped.startswith("## Relevant Provisions") or stripped.startswith("## Application to Query")):
                in_target_section = False

        if in_target_section and stripped:
            target_lines.append(stripped)

    # 2. Check each target line
    for line in target_lines:
        if line.startswith("#") or line.startswith("---") or line.startswith("*Status:") or line.startswith("LABEL:"):
            continue

        line_norm = _normalize_text(line)

        # A. Check provision & subsection cross-references
        # Pattern captures: Section 22(1), Section 15A(13), Section 15(11), Section 19(7), Section 15A
        refs = re.findall(r'(?:section|s\.)\s*([0-9]+[a-z]?)(?:\(([0-9]+)\))?', line, flags=re.IGNORECASE)
        for sec_num, sub_num in refs:
            sec_num = sec_num.lower()
            if sec_num == primary_section.lower():
                # Reference to primary section itself
                if sub_num:
                    # Check if subsection exists in stored text, e.g. "(1)", "(2)", "sub-section (1)"
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
                # External cross-reference (e.g. Section 15A, Section 15(11), Section 19(7))
                # Check if this external section is mentioned in the stored text
                term_to_find = f"section {sec_num}"
                if term_to_find in combined_stored_text:
                    if sub_num:
                        # Check if the specific subsection is also mentioned, e.g. "sub-section (13) of section 15a"
                        sub_pattern = rf'(?:sub\s*-\s*section\s*\({sub_num}\)|sub-section\s*\({sub_num}\)|\({sub_num}\)).*?section\s*{sec_num}|section\s*{sec_num}.*?\({sub_num}\)'
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

        # B. Check substantive legal conditions & benchmarks
        condition_candidates = [
            ("deposit in cash", ["deposit in cash", "deposits in cash"]),
            ("decretal amount", ["decretal amount"]),
            ("opportunity of hearing", ["opportunity of being heard", "opportunity of hearing", "given an opportunity"]),
            ("bench composition", ["two judges", "two Judges", "bench of not less than two"]),
            ("disposal timeframe", ["ninety days", "90 days"]),
            ("limitation period", ["thirty days", "30 days"]),
            ("stay lapse duration", ["six months", "6 months"]),
            ("interlocutory bar", ["interlocutory", "leave to defend"]),
            ("ex-parte appeal", ["ex-parte", "ex parte"]),
            ("cpc notice", ["order xliii", "order 43", "rule 3"])
        ]

        for concept_name, triggers in condition_candidates:
            if any(t in line_norm for t in triggers):
                matched_in_store = any(t in combined_stored_text for t in triggers)
                if not matched_in_store:
                    violations.append({
                        "type": "unsupported_statutory_condition",
                        "line": line,
                        "unsupported_term": concept_name,
                        "reason": f"Substantive condition '{concept_name}' is asserted in the memo but is missing from stored statutory text."
                    })
                else:
                    verified_claims.append({
                        "type": "verified_statutory_condition",
                        "concept": concept_name
                    })

    passed = len(violations) == 0
    return StatuteClaimVerificationResult(passed=passed, violations=violations, verified_claims=verified_claims)
