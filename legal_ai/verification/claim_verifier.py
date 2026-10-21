"""
legal_ai/verification/claim_verifier.py

Claim-to-Source Verification Engine for Pakistani Legal Research Assistant.
Extracts:
1. Statutory propositions and numeric figures (sentence lengths, fines, notice periods, days).
2. Case citations and their attributed holdings.
Verifies each claim against retrieved passages and bare-act tables.
Unsupported claims are corrected or marked as 'not established in retrieved sources'.
"""

import re
from typing import Dict, List, Any, Tuple, Optional


class ClaimVerificationResult:
    def __init__(self, cleaned_text: str, verified_claims: List[Dict[str, Any]], violations: List[Dict[str, Any]]):
        self.cleaned_text = cleaned_text
        self.verified_claims = verified_claims
        self.violations = violations

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0


def verify_and_scrub_memo_claims(
    memo_text: str,
    retrieved_precedents: Optional[List[Dict[str, Any]]] = None,
    statutory_context: str = "",
    query_text: str = ""
) -> ClaimVerificationResult:
    """
    Executes claim-to-source verification across:
    (a) Foreign cheque dishonour numbers (2 years, twice the cheque amount, 30 days notice).
    (b) Misattributed case holdings (e.g. security cheque attributed to PLD 2026 SC 75).
    (c) False non-existence claims (Rule 2A CPC).
    (d) Schedule II bail mismatches (Section 420 PPC bailable vs non-bailable).
    """
    if not memo_text:
        return ClaimVerificationResult("", [], [])

    cleaned = memo_text
    violations: List[Dict[str, Any]] = []
    verified_claims: List[Dict[str, Any]] = []

    retrieved = retrieved_precedents or []
    # Build citation-to-text map
    retrieved_map: Dict[str, str] = {}
    for c in retrieved:
        cit = str(c.get("citation") or c.get("case_id") or "").strip()
        norm_c = re.sub(r'[\s_\-]+', ' ', cit).lower()
        txt = str(c.get("preview") or c.get("holding") or c.get("full_text") or c.get("ratio_decidendi") or "").lower()
        if norm_c:
            retrieved_map[norm_c] = txt

    # 1. Foreign Section 138 NI Act numbers in Pakistan cheque query
    # (2 years imprisonment, fine up to twice cheque amount, 30 days notice)
    foreign_patterns = [
        (
            r'\b(?:imprisonment\s+(?:up\s+to|for|extending\s+to)\s+two\s+years|two\s+years\s+imprisonment)\b',
            "Foreign 2-year imprisonment penalty from Indian Section 138 NI Act; Pakistani Section 489-F PPC prescribes up to 3 years",
            "imprisonment which may extend to three years"
        ),
        (
            r'\bfine\s+(?:which\s+may\s+extend\s+to\s+)?twice\s+the\s+(?:amount\s+of\s+the\s+)?cheque\b',
            "Foreign penalty ('fine up to twice the cheque amount') from Indian NI Act; Section 489-F PPC prescribes fine without multiplier",
            "fine or both"
        ),
        (
            r'\b(?:within\s+30\s+days\s+of\s+(?:receipt\s+of\s+)?notice|30-?day\s+legal\s+notice\s+of\s+dishonour)\b',
            "30-day statutory notice is an Indian NI Act requirement; Pakistani Section 489-F PPC does not prescribe a mandatory 30-day notice period",
            "demand for payment"
        )
    ]

    for pat, desc, replacement in foreign_patterns:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m:
            violations.append({
                "type": "FOREIGN_STATUTORY_REGIME_LEAKAGE",
                "matched": m.group(0),
                "description": desc,
                "replacement": replacement
            })
            cleaned = re.sub(pat, replacement, cleaned, flags=re.IGNORECASE)

    # 1b. Bail and procedural statute hallucination patterns
    procedural_patterns = [
        (
            r'\barticle\s*12\s*(?:of\s+(?:the\s+)?)?cr\.?p\.?c\.?|\bcr\.?p\.?c\.?\s*article\s*12\b',
            "Hallucinated Article 12 Cr.P.C.; Cr.P.C. has sections (Section 12 is for Special Magistrates, Sessions Courts are established under Section 9, bail under Sections 497/498)",
            "Section 9 and Sections 497/498 Cr.P.C."
        ),
        (
            r'\bbailable\s+offences?\s*\((?:under\s+)?section\s*497\(1\)\)',
            "Bailable offences are governed exclusively by Section 496 Cr.P.C. (mandatory right), not Section 497(1)",
            "bailable offences (Section 496 Cr.P.C.)"
        ),
        (
            r'\b(?:under\s+)?section\s*497\(1\)\s*(?:for|governs?|applies\s+to)\s+bailable\s+offences?\b',
            "Bailable offences are governed exclusively by Section 496 Cr.P.C.",
            "Section 496 Cr.P.C. for bailable offences"
        ),
        (
            r'\bappeal\s+lies\s+to\s+the\s+High\s+Court\s+under\s+Section\s+561-A\s+Cr\.?P\.?C\.?\s+or\s+Article\s+199\b',
            "Routine bail refusal is not appealed under Article 199 or 561-A; direct statutory petition lies under Section 498 Cr.P.C. before the High Court",
            "post-arrest bail petition lies before the High Court under Section 498 Cr.P.C. (concurrent statutory jurisdiction)"
        ),
        (
            r'\b(?:file|filing)\s+(?:an?\s+)?article\s*199\s+(?:writ\s+)?petition\s+for\s+bail\b',
            "Article 199 writ is barred where direct statutory bail remedies exist under Section 497/498 Cr.P.C.",
            "filing a bail petition before the High Court under Section 498 Cr.P.C."
        )
    ]
    for pat, desc, replacement in procedural_patterns:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m:
            violations.append({
                "type": "PROCEDURAL_STATUTE_HALLUCINATION",
                "matched": m.group(0),
                "description": desc,
                "replacement": replacement
            })
            cleaned = re.sub(pat, replacement, cleaned, flags=re.IGNORECASE)

    # 2. General Claim-to-Headnote Verification
    # For every retrieved precedent cited in the memo, check if the asserted holding
    # is grounded in the retrieved candidate's holding / headnote / text.
    for c in retrieved:
        cit = str(c.get("citation") or c.get("case_id") or "").strip()
        if not cit:
            continue
        c_text = str(c.get("holding") or c.get("preview") or c.get("headnote") or c.get("full_text") or c.get("ratio_decidendi") or "").lower()
        if not c_text:
            continue

        # Look for claims asserting what this citation held or decided
        cit_pattern = re.compile(
            rf'(?:(?:in\s+)?{re.escape(cit)}[^.\n]*?\b(?:held|decided|ruled|laid\s+down)\b|(?:held|decided|ruled|laid\s+down)\s+(?:in|by)\s+{re.escape(cit)})\s+(?:that\s+)?([^.\n]+)',
            re.IGNORECASE
        )
        for m_claim in cit_pattern.finditer(cleaned):
            claimed_holding = m_claim.group(1).strip()
            # Extract distinctive legal topic words
            stop_words = {
                "that", "this", "court", "supreme", "high", "judgment", "held", "case", "order",
                "under", "section", "article", "provision", "petitioner", "respondent", "appeal",
                "rules", "rule", "pakistan", "bench", "matter", "parties", "cannot", "about",
                "definitively", "authoritative", "precedent"
            }
            tokens = [w.lower() for w in re.findall(r'[a-zA-Z0-9_\-]+', claimed_holding) if len(w) >= 4 and w.lower() not in stop_words]
            if len(tokens) >= 2:
                matching_tokens = [t for t in tokens if t in c_text]
                if len(matching_tokens) == 0 or (len(matching_tokens) / len(tokens) < 0.35):
                    violations.append({
                        "type": "UNGROUNDED_CASE_HOLDING",
                        "citation": cit,
                        "description": f"Holding attributed to {cit} ('{claimed_holding[:80]}') is ungrounded in the retrieved case text."
                    })
                    actual_desc = c.get("holding") or c.get("preview") or "a distinct factual dispute"
                    replacement_context = f"{cit} (which concerned {actual_desc}, rather than {claimed_holding})"
                    full_match_text = m_claim.group(0)
                    cleaned = cleaned.replace(full_match_text, replacement_context)

    # 3. Order XXXIX Rule 2A CPC Foreign Provision Correction
    # Rule 2A is an Indian CPC amendment (Act 104 of 1976); in Pakistan disobedience is governed by Order XXXIX Rule 2(3) CPC (2006 YLR 2758).
    r2a_match = re.search(
        r'(?i)\b(?:Order\s*XXXIX\s*Rule\s*2-?[aA]|Rule\s*2-?[aA])\b',
        cleaned
    )
    if r2a_match and not re.search(r'(?i)\bRule\s*2\(3\)\b', cleaned):
        violations.append({
            "type": "O39_R2A_INDIAN_IMPORT",
            "matched": r2a_match.group(0),
            "description": "Order XXXIX Rule 2A CPC is an Indian amendment (Act 104 of 1976). In Pakistan, disobedience or breach of injunction is governed by Order XXXIX Rule 2(3) CPC (2006 YLR 2758)."
        })
        cleaned = re.sub(
            r'(?i)\b(?:Order\s*XXXIX\s*Rule\s*2-?[aA]|Rule\s*2-?[aA])\b',
            'Order XXXIX Rule 2(3) CPC (providing for attachment of property and detention in civil prison; see 2006 YLR 2758)',
            cleaned
        )

    # 4. Schedule II bail status check for Section 420 PPC
    # Under Schedule II, Section 420 is non-bailable, falling under s.497 non-prohibitory clause
    s420_bail_mismatch = re.search(
        r'(?i)\b(?:Section\s*420|s\.\s*420)\b[^.\n]{0,60}(?:bailable\s+as\s+of\s+right|governed\s+by\s+section\s*496|within\s+the\s+prohibitory\s+clause)',
        cleaned
    )
    if s420_bail_mismatch:
        violations.append({
            "type": "SCHEDULE_II_MISMATCH",
            "matched": s420_bail_mismatch.group(0),
            "description": "Section 420 PPC is non-bailable under Cr.P.C. Schedule II; it falls outside the prohibitory clause of Section 497 Cr.P.C."
        })

    # 5. Check Court Metadata Consistency
    # High Court law reports: YLR, CLC, PCrLJ, MLD report High Court judgments, not Supreme Court
    high_court_reporters = [r'\b\d{4}\s+YLR\s+\d+\b', r'\b\d{4}\s+CLC\s+\d+\b', r'\b\d{4}\s+PCrLJ\s+\d+\b', r'\b\d{4}\s+MLD\s+\d+\b']
    for hc_pat in high_court_reporters:
        for match in re.finditer(hc_pat, cleaned, re.IGNORECASE):
            cit_str = match.group(0)
            # Check if surrounding text (150 chars before or after) erroneously calls it Supreme Court
            start_pos = max(0, match.start() - 150)
            end_pos = min(len(cleaned), match.end() + 150)
            window = cleaned[start_pos:end_pos]
            if re.search(r'\bSupreme\s+Court\b', window, re.IGNORECASE):
                violations.append({
                    "type": "COURT_METADATA_MISMATCH",
                    "citation": cit_str,
                    "description": f"Citation '{cit_str}' is from a High Court law report but was labeled or associated with the Supreme Court."
                })
                # If there's an explicit '**Court**: Supreme Court' or 'Supreme Court of Pakistan in [cit]'
                cleaned_window = re.sub(r'(\*\*Court\*\*:\s*)Supreme Court(?: of Pakistan)?', r'\1High Court', window, flags=re.IGNORECASE)
                cleaned_window = re.sub(r'\bSupreme\s+Court(?: of Pakistan)?\s+(?:in|held\s+in)\s+' + re.escape(cit_str), f"High Court in {cit_str}", cleaned_window, flags=re.IGNORECASE)
                cleaned = cleaned[:start_pos] + cleaned_window + cleaned[end_pos:]

    # 6. General Negative / Unlocated Holding Query Enforcement
    # When query specifically requests a judgment or authority holding a specific proposition:
    m_seek = re.search(r'\b(?:judgment|case|authority|ruling)\b[^\n.]{0,80}\b(?:holding|holds|held)\b\s+(?:that\s+)?([^.\n\?]+)', query_text, re.IGNORECASE)
    if not m_seek:
        m_seek = re.search(r'\b(?:holding|holds|held)\b\s+(?:that\s+)?([^.\n\?]+)', query_text, re.IGNORECASE)

    if m_seek:
        sought_prop = m_seek.group(1).strip().lower()
        sought_terms = [w for w in re.findall(r'[a-zA-Z0-9_\-]+', sought_prop) if len(w) >= 4 and w not in {"that", "this", "court", "supreme", "judgment", "under", "section", "cannot", "does", "have"}]
        if sought_terms:
            squarely_found = any(
                all(t in str(c.get("holding") or c.get("preview") or c.get("ratio_decidendi") or "").lower() for t in sought_terms)
                for c in retrieved
            )
            if not squarely_found and "squarely holds" not in cleaned.lower():
                disclaimer = "I did not find a case that squarely holds this. The closest retrieved authorities are discussed below as related authorities, but do not squarely establish this proposition.\n\n"
                if "## Judicial Authorities" in cleaned:
                    cleaned = cleaned.replace("## Judicial Authorities", disclaimer + "## Judicial Authorities", 1)
                else:
                    cleaned = disclaimer + cleaned
                violations.append({
                    "type": "NEGATIVE_AUTHORITY_UNLOCATED",
                    "description": "Query sought specific holding not squarely found in retrieved precedents; injected required disclaimer."
                })

    # 7. Strip Banned Superlatives ("definitively", "landmark", "authoritative shield")
    superlatives = [
        (r'\bdefinitively\s+held\b', "held"),
        (r'\blandmark\s+(?:precedent|judgment|authority|ruling)\b', "precedent"),
        (r'\bauthoritative\s+shield\b', "defence"),
    ]
    for sup_pat, sup_repl in superlatives:
        if re.search(sup_pat, cleaned, re.IGNORECASE):
            violations.append({
                "type": "INFLATED_AUTHORITY_SUPERLATIVE",
                "matched": sup_pat,
                "replacement": sup_repl
            })
            cleaned = re.sub(sup_pat, sup_repl, cleaned, flags=re.IGNORECASE)

    # 8. Check Truncated Precedent Text (e.g. 2024 SCMR 1719)
    for c in retrieved:
        cit = str(c.get("citation") or c.get("case_id") or "").strip()
        txt = str(c.get("preview") or c.get("headnote") or "").strip()
        if cit and (txt.endswith("...") or c.get("truncated")):
            # If memo cites this case and claims a full ratio beyond available headnote
            if re.search(re.escape(cit) + r'[^.\n]{0,80}\b(?:conclusively|full\s+text|entire\s+ratio)\b', cleaned, re.IGNORECASE):
                violations.append({
                    "type": "TRUNCATED_HEADNOTE_OVERCLAIM",
                    "citation": cit,
                    "description": f"Precedent {cit} has only a truncated headnote; cannot claim exhaustive textual holding."
                })

    # 9. Scrub Residual Artificial Certification / Word Count Artefacts
    cert_artefacts = [
        r"(?i)Counsel'?s\s+Certification[^\n]*",
        r"(?i)Prepared\s+by\s+Senior\s+Counsel[^\n]*",
        r"(?i)\[Current Date\]",
        r"(?i)Word\s+Count\s*:\s*\d+[^\n]*",
        r"(?i)All\s+8\s+Sections\s+Completed[^\n]*",
        r"(?i)all\s+citations\s+verified\s+active\s+status[^\n]*"
    ]
    for cart in cert_artefacts:
        if re.search(cart, cleaned):
            cleaned = re.sub(cart, "", cleaned)

    # 10. Check all cited authorities against retrieved_map
    from legal_ai.verification.statute_matcher import find_citations
    found_cits = find_citations(cleaned)
    for raw_cit, start, end in found_cits:
        norm_raw = re.sub(r'[\s_\-]+', ' ', raw_cit).lower()
        if retrieved_map:
            is_in_retrieved = any(norm_raw in r_key or r_key in norm_raw for r_key in retrieved_map)
            if is_in_retrieved:
                verified_claims.append({
                    "citation": raw_cit,
                    "status": "RETRIEVED_AND_VERIFIED"
                })
            else:
                violations.append({
                    "type": "UNRETRIEVED_CASE_CITATION",
                    "citation": raw_cit,
                    "description": f"Citation '{raw_cit}' was not in the retrieved precedent set."
                })

    # 11. Limitation Article 181 Misapplication on Promissory Notes
    q_low = str(query_text or "").lower()
    if any(k in q_low for k in ["promissory", "promissory note", "negotiable instrument"]):
        art181_match = re.search(r'(?i)\b(?:Article\s*181|Art\.?\s*181)\b[^.\n]{0,80}(?:promissory|recovery\s+of\s+money|suit)', cleaned)
        if art181_match:
            violations.append({
                "type": "ARTICLE_181_PROMISSORY_NOTE_MISAPPLICATION",
                "matched": art181_match.group(0),
                "description": "Article 181 is a residual article for applications under the CPC and does not govern suits on promissory notes (governed by Articles 73 and 80)."
            })
            cleaned = re.sub(
                r'(?i)\b(?:Article\s*181|Art\.?\s*181)\b',
                'Article 73 / Article 80 (Article 181 is a residual article for applications and inapplicable to suits on promissory notes)',
                cleaned
            )

    # 12. Statute Quotation Verifier: No quotation marks unless matching injected bare-act text
    stat_context_lower = str(statutory_context or "").lower()
    quotes = list(re.finditer(r'"([^"\n]{15,})"', cleaned))
    for q_match in quotes:
        q_text = q_match.group(1).strip()
        q_text_low = q_text.lower()
        statutory_indicators = [
            "shall be punished", "imprisonment", "fine", "commits criminal breach",
            "period of limitation", "time from which", "payable on demand",
            "contract", "specific performance", "injunction", "suit for",
            "valuable security", "dishonestly"
        ]
        is_statutory_quote = any(ind in q_text_low for ind in statutory_indicators)
        if is_statutory_quote:
            if q_text_low not in stat_context_lower:
                q_norm = " ".join(q_text_low.split())
                ctx_norm = " ".join(stat_context_lower.split())
                if q_norm not in ctx_norm:
                    violations.append({
                        "type": "UNGROUNDED_STATUTE_QUOTATION",
                        "matched": q_text,
                        "description": f"Quotation '{q_text[:50]}' does not match injected bare-act text verbatim; stripped quotation marks."
                    })
                    cleaned = cleaned.replace(f'"{q_text}"', q_text)

    # 13. Spurious "Statutory text unavailable" Warning Scrubber
    if "Verbatim Bare-Act Text in Force:" in statutory_context:
        spurious_warning = re.search(r'(?i)>\s*Statutory\s+text\s+unavailable\s+in\s+retrieved\s+sources\.[^\n]*', cleaned)
        if spurious_warning:
            if "[Statutory text not found in verified database]" not in statutory_context:
                violations.append({
                    "type": "SPURIOUS_STATUTE_UNAVAILABLE_WARNING",
                    "matched": spurious_warning.group(0),
                    "description": "Statutory text was provided in the framework; stripped spurious unavailability warning."
                })
                cleaned = re.sub(r'(?i)>\s*Statutory\s+text\s+unavailable\s+in\s+retrieved\s+sources\.[^\n]*\n*', '', cleaned)

    # 14. Section 406 PPC Penalty Grounding (subs. by Ord. XXXIII of 1981 to 7 years)
    if "406" in cleaned or "406" in q_low:
        m_406_3yr = re.search(r'(?i)\bSection\s*406\b[^.\n]{0,80}\b(?:three|3)\s+years\b', cleaned)
        if m_406_3yr and "seven" not in m_406_3yr.group(0).lower() and "7" not in m_406_3yr.group(0).lower():
            violations.append({
                "type": "PPC_406_PENALTY_MISMATCH",
                "matched": m_406_3yr.group(0),
                "description": "Section 406 PPC penalty was amended to up to seven years by Ord. XXXIII of 1981; corrected."
            })
            cleaned = cleaned.replace(
                m_406_3yr.group(0),
                f"{m_406_3yr.group(0)} (amended to up to seven years under Pakistan Penal Code bare act text by Ordinance XXXIII of 1981, s. 2)"
            )
        m_mand_fine = re.search(r'(?i)\bmandatory\s+fine\b', cleaned)
        if m_mand_fine:
            violations.append({
                "type": "FALSE_MANDATORY_FINE_CLAIM",
                "matched": m_mand_fine.group(0),
                "description": "Statute states 'liable to fine' or 'or with fine, or with both', not a mandatory fine."
            })
            cleaned = re.sub(r'(?i)\bmandatory\s+fine\b', 'fine', cleaned)

    return ClaimVerificationResult(cleaned, verified_claims, violations)
