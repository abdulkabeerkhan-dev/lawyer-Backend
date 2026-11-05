"""
core/court_derivation.py

Authoritative court, year, and title cleaner per Remediation Spec Phase 3:
- SCMR and PLD SC imply Supreme Court of Pakistan.
- YLR, MLD, CLC, PCrLJ, PTD, PLC imply High Court (with province derived from bench in title).
- Ambiguous PLD alone resolves from bench name or returns UNKNOWN.
- Never default to Supreme Court of Pakistan.
- Year parsed from citation; never defaulted to 2024.
- Titles cleaned by removing leading serial numbers, judge names, and city suffixes.
"""

import re
from typing import Any, Dict, Optional, Tuple

def clean_judgment_title(raw_title: str) -> str:
    """
    Cleans title by stripping leading serial numbers and trailing judge/bench suffixes.
    Example: '317 2013 YLR 1198 MOIZ ALY MANJI VS State - Honorable Justice ... LAHORE'
    -> 'MOIZ ALY MANJI VS State'
    """
    if not raw_title:
        return ""
    t = str(raw_title).strip()
    
    # Strip leading serial number e.g. "317 "
    t = re.sub(r'^\d+\s+', '', t)
    
    # Strip citation prefix in title if present e.g. "2013 YLR 1198 "
    t = re.sub(r'^(?:19\d{2}|20\d{2})\s+[A-Za-z]+(?:\s*\([A-Za-z]+\))?\s+\d+\s+', '', t, flags=re.IGNORECASE)
    
    # Strip trailing judge/bench information e.g. " - Honorable Justice..." or " -- Mr. Justice..."
    t = re.split(r'\s*(?:[-–—]{1,2}|\|)\s*(?:Hon[\'a-z]*\s+Justice|Mr\.?\s+Justice|Justice\b|Bench\b|BEFORE:?)', t, flags=re.IGNORECASE)[0]
    
    # Strip trailing city if preceded by hyphen or dash
    t = re.sub(r'\s*[-–—]\s*(?:LAHORE|KARACHI|ISLAMABAD|PESHAWAR|QUETTA|RAWALPINDI|BAHAWALPUR|MULTAN)\s*$', '', t, flags=re.IGNORECASE)
    
    return t.strip()

def derive_court_and_year(
    citation: Optional[str] = None,
    meta_court: Optional[str] = None,
    meta_year: Optional[Any] = None,
    case_title: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Tuple[str, str, Optional[int]]:
    """
    Derives (court, court_source, year) with zero false defaults.
    
    Returns:
        court: Canonical court name or 'UNKNOWN'
        court_source: 'citation_prefix' | 'bench_in_title' | 'metadata' | 'unknown'
        year: Integer year or None
    """
    comb_cit = f"{citation or ''} {case_id or ''}".upper()
    comb_title = f"{case_title or ''} {meta_court or ''}".lower()
    
    # 1. Year Derivation from Citation
    year: Optional[int] = None
    m_yr = re.search(r'\b(19\d{2}|20\d{2})\b', comb_cit)
    if m_yr:
        year = int(m_yr.group(1))
    elif meta_year:
        try:
            val = int(str(meta_year)[:4])
            if 1900 <= val <= 2030:
                year = val
        except (ValueError, TypeError):
            pass

    # 2. Court Derivation
    # A. Apex Court: SCMR or PLD SC / PLD Supreme Court
    if "SCMR" in comb_cit or re.search(r'\bPLD\s+(?:19\d{2}|20\d{2})\s+(?:SC|SUPREME\s+COURT)\b', comb_cit):
        return ("Supreme Court of Pakistan", "citation_prefix", year)
    
    # B. Explicit High Court Reporters: YLR, MLD, CLC, PCrLJ, PTD, PLC
    is_hc_reporter = any(rep in comb_cit for rep in ["YLR", "MLD", "CLC", "PCRLJ", "PTD", "PLC", "GBLR"])
    
    # Determine province / bench from title or metadata
    bench_found = None
    if any(k in comb_title for k in ["lahore", "multan", "rawalpindi", "bahawalpur"]):
        bench_found = "Lahore High Court"
    elif any(k in comb_title for k in ["sindh", "karachi", "sukkur", "hyderabad"]):
        bench_found = "High Court of Sindh"
    elif any(k in comb_title for k in ["peshawar", "abbottabad", "mingora", "deraismailkhan", "d.i. khan"]):
        bench_found = "Peshawar High Court"
    elif any(k in comb_title for k in ["balochistan", "quetta", "sibi", "turbat"]):
        bench_found = "High Court of Balochistan"
    elif "islamabad" in comb_title:
        bench_found = "Islamabad High Court"
    elif any(k in comb_title for k in ["federal shariat court", "fsc"]):
        bench_found = "Federal Shariat Court"
        
    if is_hc_reporter:
        if bench_found:
            return (bench_found, "bench_in_title", year)
        return ("High Court", "citation_prefix", year)
    
    # C. Ambiguous PLD alone (without SC)
    if "PLD" in comb_cit:
        if bench_found:
            return (bench_found, "bench_in_title", year)
        return ("UNKNOWN", "unknown", year)
    
    # D. Metadata verification if clean (not old canned default)
    if meta_court and meta_court not in ("Supreme Court of Pakistan", "Supreme Court", "UNKNOWN", ""):
        return (meta_court, "metadata", year)
        
    if "supreme court" in comb_title:
        return ("Supreme Court of Pakistan", "bench_in_title", year)
        
    return ("UNKNOWN", "unknown", year)
