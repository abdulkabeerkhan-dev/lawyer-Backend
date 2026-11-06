"""
core/case_integrity.py

Deterministic Case Record Integrity Engine.
Enforces Section: Legal Research Pipeline Fix Spec rules:
1. Rejects known contaminated/corrupted case records (e.g. 1989 SCMR 868 spliced text).
2. Enforces deterministic reporter-to-court taxonomy (SCMR/PSC -> Supreme Court only, CLC/PCrLJ/MLD/YLR -> High Court only).
3. Detects domain/party contradictions (e.g. Establishment Division/Service Tribunal in private property dispute).
4. Sanitizes and validates ratio text (no raw scraper headers, no pasted reporter strings, non-empty substantive ratio).
"""

import re
from typing import Dict, Any, Tuple, Optional, List

# Known contaminated or corrupted citations in raw scraper databases
# Maps citation -> dict of reasons and domain restrictions
KNOWN_CORRUPTED_CASES: Dict[str, Dict[str, Any]] = {
    "1989 SCMR 868": {
        "reason": "Title is Iqbal Ahmad Khan v. Secretary, Establishment Division (civil service), but scraped body was contaminated with specific performance text.",
        "allowed_domains": ["service", "labour", "constitutional"],
        "forbidden_topics": ["specific performance", "agreement to sell", "earnest money", "property", "partition"]
    }
}

# Supreme Court reporters: exclusively Supreme Court of Pakistan
SC_REPORTER_PATTERN = re.compile(r'\b(SCMR|PSC)\b|\bPLD\b.*\b(SC|SUPREME)\b', re.IGNORECASE)

# High Court reporters: exclusively High Courts
HC_REPORTER_PATTERN = re.compile(r'\b(CLC|PCRLJ|MLD|YLR|CLD|PLR)\b|\bPLD\b.*\b(LAH|KAR|PESH|QUETTA|SIND|BALOCH)\b', re.IGNORECASE)

# Scraper garbage / raw ratio markers to scrub
RATIO_HEADER_PATTERN = re.compile(
    r'^(?:RATIO\s+DECIDENDI\s*(?:&|AND)?\s*JUDICIAL\s*HOLDING\s*:?|COURT\s*HELD\s*:?|HOLDING\s*:?|RATIO\s*:?)\s*',
    re.IGNORECASE
)

PASTED_CITATIONS_PATTERN = re.compile(
    r'\b(?:19|20)\d{2}\s+(?:SCMR|PLD|CLC|PCrLJ|MLD|YLR|CLD|PLR|PSC)\s+\d+\b(?:\s*,\s*(?:19|20)\d{2}\s+(?:SCMR|PLD|CLC|PCrLJ|MLD|YLR|CLD|PLR|PSC)\s+\d+)*',
    re.IGNORECASE
)


def normalize_citation(citation: Optional[str]) -> str:
    """Normalizes citation string for consistent lookups."""
    if not citation:
        return ""
    cit = re.sub(r'[\s_]+', ' ', str(citation).strip().upper())
    return cit


def check_reporter_court_consistency(citation: str, court_name: str) -> Tuple[bool, str, str]:
    """
    Validates that the court name is consistent with the citation's law reporter.
    Returns: (is_consistent, canonical_court, diagnostic_message)
    """
    norm_cit = normalize_citation(citation)
    norm_court = (court_name or "").strip()
    upper_court = norm_court.upper()

    if SC_REPORTER_PATTERN.search(norm_cit):
        # Must be Supreme Court
        if "HIGH COURT" in upper_court and "SUPREME" not in upper_court:
            return False, "Supreme Court of Pakistan", f"Reporter '{norm_cit}' is Supreme Court only; court was labeled '{norm_court}'"
        return True, "Supreme Court of Pakistan", "Consistent with Supreme Court reporter"

    if HC_REPORTER_PATTERN.search(norm_cit):
        # Must be High Court, never Supreme Court
        if "SUPREME COURT" in upper_court:
            return False, "High Court", f"Reporter '{norm_cit}' is High Court only; court was labeled '{norm_court}'"
        return True, norm_court or "High Court", "Consistent with High Court reporter"

    return True, norm_court, "Neutral reporter"


def sanitize_ratio_text(raw_ratio: Optional[str]) -> str:
    """
    Cleans ratio text:
    - Strips raw scraper headers like 'RATIO DECIDENDI & JUDICIAL HOLDING:'
    - Cleans out trailing boilerplate and scrap metadata
    - Strips standalone lists of raw citations pasted into ratio
    """
    if not raw_ratio:
        return ""
    text = str(raw_ratio).strip()

    # Strip repeated headers
    text = RATIO_HEADER_PATTERN.sub('', text).strip()

    # Strip trailing copyright / site banners
    text = re.sub(r'Copyrights?\s*©?.*?(?:Oratier|Technologies|Pvt).*$', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
    text = re.sub(r'This site is developed & maintained.*?$', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
    text = re.sub(r'Bookmark this Case.*$', '', text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Strip trailing or leading raw reporter list if entire line is just citations
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    cleaned_lines = []
    for line in lines:
        if RATIO_HEADER_PATTERN.match(line):
            line = RATIO_HEADER_PATTERN.sub('', line).strip()
        # If line is only comma-separated citations without verbs, skip
        if PASTED_CITATIONS_PATTERN.fullmatch(line) and not any(w in line.lower() for w in ['held', 'ruled', 'court', 'that', 'observed']):
            continue
        if line:
            cleaned_lines.append(line)

    return "\n\n".join(cleaned_lines).strip()


def verify_case_integrity(
    record: Dict[str, Any],
    query_domain: Optional[str] = None,
    sub_topic: Optional[str] = None,
    query_text: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validates a retrieved case record against pipeline integrity rules.

    Returns:
        (is_valid, failure_reason, sanitized_record)
    """
    sanitized = dict(record)
    citation = normalize_citation(
        sanitized.get("citation") or sanitized.get("neutral_citation") or sanitized.get("case_id") or ""
    )
    title = str(
        sanitized.get("case_title") or sanitized.get("title") or sanitized.get("case_name") or ""
    ).strip()
    court = str(
        sanitized.get("court_name") or sanitized.get("court") or sanitized.get("canonical_court_name") or ""
    ).strip()
    raw_ratio = (
        sanitized.get("ratio_decidendi") or
        sanitized.get("holding") or
        sanitized.get("ratio") or
        sanitized.get("headnote") or
        ""
    )

    # 1. Check known corrupted cases
    for corrupted_cit, details in KNOWN_CORRUPTED_CASES.items():
        if corrupted_cit in citation:
            # Check forbidden topics or query text
            combined_context = f"{query_domain or ''} {sub_topic or ''} {query_text or ''}".lower()
            if any(forbidden in combined_context for forbidden in details.get("forbidden_topics", [])):
                return False, f"Known corrupted record '{citation}': {details.get('reason')}", sanitized

    # 2. Check title / domain contradiction (e.g. civil service vs private property)
    upper_title = title.upper()
    upper_context = f"{query_domain or ''} {sub_topic or ''} {query_text or ''}".upper()

    is_property_or_private_suit = any(term in upper_context for term in [
        "SPECIFIC PERFORMANCE", "AGREEMENT TO SELL", "PARTITION", "BENAMI", "EARNEST MONEY", "LANDLORD", "TENANT"
    ])

    if is_property_or_private_suit:
        # If title clearly indicates a civil service / government service tribunal case
        if "ESTABLISHMENT DIVISION" in upper_title or "FEDERAL SERVICE TRIBUNAL" in upper_title or "CIVIL SERVANTS ACT" in upper_title:
            return False, f"Title-to-domain mismatch: '{title}' is an administrative/service dispute, incompatible with private property/contract claim.", sanitized

    # 3. Reporter-to-Court Taxonomy Check
    is_consistent, canonical_court, diag = check_reporter_court_consistency(citation, court)
    if not is_consistent:
        # If the reporter is SCMR and court was labeled High Court, auto-correct if unambiguous
        if SC_REPORTER_PATTERN.search(citation):
            sanitized["court_name"] = "Supreme Court of Pakistan"
            sanitized["court"] = "Supreme Court of Pakistan"
        elif HC_REPORTER_PATTERN.search(citation):
            sanitized["court_name"] = canonical_court or "High Court"
            sanitized["court"] = canonical_court or "High Court"
        else:
            return False, f"Court/Reporter integrity check failed: {diag}", sanitized

    # 4. Ratio text sanitization & check
    clean_ratio = sanitize_ratio_text(raw_ratio)
    if not clean_ratio:
        # If raw full text exists, try to extract ratio or mark empty
        full_txt = str(sanitized.get("judgment_text") or sanitized.get("full_text") or "")
        if full_txt and len(full_txt) > 200:
            clean_ratio = ""  # Mark ratio empty; full text exists for tab
        else:
            return False, f"Case record '{citation}' has neither substantive ratio nor order text.", sanitized

    sanitized["ratio_decidendi"] = clean_ratio
    sanitized["holding"] = clean_ratio
    sanitized["citation"] = citation

    return True, "", sanitized
