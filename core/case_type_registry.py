"""
Case Type Canonical Registry & Normalizer
Version: 1.0.0
Phase 4 Gate 3 Standard Component

Establishes deterministic, versioned mapping between raw court case type strings
and standardized canonical abbreviation codes for composite key deduplication.
"""

from typing import Optional, Tuple, Dict
import re

VERSION = "1.0.0"

# Versioned canonical lookup map per specification
CASE_TYPE_CANONICAL_MAP: Dict[str, str] = {
    # High Court & General Writs
    "writ petition": "WP",
    "w.p.": "WP",
    "wp(c)": "WP",
    "wp": "WP",
    "w.p": "WP",

    # Civil Petitions
    "civil petition": "CP",
    "c.p.": "CP",
    "cp": "CP",
    "c.p": "CP",
    "cpla": "CP",
    "c.p.l.a.": "CP",
    "c.p.l.a": "CP",
    "civil petition for leave to appeal": "CP",

    # Civil Appeals
    "civil appeal": "CA",
    "c.a.": "CA",
    "ca": "CA",
    "c.a": "CA",

    # Criminal Petitions
    "criminal petition": "CRP",
    "cr.p.": "CRP",
    "cr.p": "CRP",
    "crl.p.": "CRP",
    "crl.p": "CRP",
    "crp": "CRP",
    "crpla": "CRP",
    "cr.p.l.a.": "CRP",
    "criminal petition for leave to appeal": "CRP",

    # Criminal Appeals
    "criminal appeal": "CRA",
    "cr.a.": "CRA",
    "cr.a": "CRA",
    "crl.a.": "CRA",
    "crl.a": "CRA",
    "cra": "CRA",

    # Constitutional Petitions
    "constitution petition": "CONST.P",
    "const.p.": "CONST.P",
    "const.p": "CONST.P",
    "const petition": "CONST.P",
    "constitutional petition": "CONST.P",

    # Civil Revisions & Misc Applications
    "civil revision": "CR",
    "c.r.": "CR",
    "cr": "CR",
    "civil misc": "CM",
    "c.m.": "CM",
    "cm": "CM",
    "civil miscellaneous application": "CMA",
    "c.m.a.": "CMA",
    "cma": "CMA",

    # Appellate & High Court Specific
    "regular first appeal": "RFA",
    "r.f.a.": "RFA",
    "rfa": "RFA",
    "intra court appeal": "ICA",
    "i.c.a.": "ICA",
    "ica": "ICA",
    "first appeal from order": "FAO",
    "f.a.o.": "FAO",
    "fao": "FAO",

    # Federal Constitutional Court / Shariat
    "shariat petition": "SH.P",
    "sh.p.": "SH.P",
    "shariat appeal": "SH.A",
    "sh.a.": "SH.A"
}


def canonicalize_case_type(raw_type: Optional[str]) -> Optional[str]:
    """
    Normalizes a raw case type string into its canonical abbreviation code.
    Returns None if no canonical mapping is recognized.
    """
    if not raw_type:
        return None
    cleaned = raw_type.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    
    # 1. Direct dictionary lookup
    if cleaned in CASE_TYPE_CANONICAL_MAP:
        return CASE_TYPE_CANONICAL_MAP[cleaned]
    
    # 2. Lookup without trailing dots or 'no'
    stripped = re.sub(r"\bno\.?\b", "", cleaned).strip().rstrip(".:- ")
    if stripped in CASE_TYPE_CANONICAL_MAP:
        return CASE_TYPE_CANONICAL_MAP[stripped]

    # 3. Exact word boundary match
    for key, code in sorted(CASE_TYPE_CANONICAL_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(r"\b" + re.escape(key) + r"\b", stripped):
            return code

    return None


def extract_case_type_and_docket(raw_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses a raw case number/docket string into:
    (canonical_case_type_code, normalized_docket_number).
    
    Examples:
        "C.P.L.A. No. 88-P of 2022" -> ("CP", "88-P/2022")
        "Writ Petition No. 3278 of 2019" -> ("WP", "3278/2019")
        "Civil Appeal No. 2768-L/2022" -> ("CA", "2768-L/2022")
        "C.M. No.1969 of 2023 in Writ Petition No.3278 of 2019" -> ("WP", "3278/2019")
    """
    if not raw_str:
        return None, None

    text = raw_str.strip()
    if not re.search(r"\d", text):
        return canonicalize_case_type(text), None

    # If compound "in Writ Petition No. ...", prioritize substantive petition
    in_match = re.search(r"\bin\s+([A-Za-z\.\s]+(?:Petition|Appeal|Revision|Application)?\s*(?:No\.?)?\s*[\d\w\/\-]+(?:\s*(?:of|\/)\s*\d{4})?)", text, re.IGNORECASE)
    if in_match:
        text = in_match.group(1).strip()

    # Pattern 1: type + number + optional year
    m = re.search(r"^(?P<type>[A-Za-z\.\s\(\)]+?)(?:\s*(?:No\.?|Number|#)?\s*)(?P<num>\d+[\d\w\-\/]*)\s*(?:of|\/)?\s*(?P<year>\d{4})?$", text, re.IGNORECASE)
    if m:
        canon_type = canonicalize_case_type(m.group("type"))
        num = m.group("num").strip()
        year = m.group("year")
        docket_norm = f"{num}/{year}" if (year and year not in num) else num
        return canon_type, docket_norm

    # Pattern 2: type + number within longer text
    m2 = re.search(r"^(?P<type>[A-Za-z\.\s\(\)]+?)(?:\s*(?:No\.?|Number|#)?\s*)(?P<num>\d+[\d\w\-\/]*)", text, re.IGNORECASE)
    if m2:
        canon_type = canonicalize_case_type(m2.group("type"))
        num = m2.group("num").strip()
        rem = text[m2.end():].strip()
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", rem)
        year = year_match.group(1) if year_match else None
        docket_norm = f"{num}/{year}" if (year and year not in num) else num
        return canon_type, docket_norm

    return None, text
