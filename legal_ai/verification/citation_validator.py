"""
legal_ai/verification/citation_validator.py

Canonical Citation Parser, OCR Normalizer, and Court Identity Validator
for Pakistani Legal Law Reporters (PLD, SCMR, CLC, PCrLJ, MLD, PTD, PLC, YLR, CLD, GBLR).
"""

import re
from typing import Dict, Any, Optional, Tuple


JOURNAL_HIERARCHY: Dict[str, str] = {
    "SCMR": "Supreme Court of Pakistan",
    "PLD": "Superior Courts of Pakistan",
    "CLC": "High Court",
    "PCRLJ": "High Court",
    "PCrLJ": "High Court",
    "MLD": "High Court",
    "YLR": "High Court",
    "CLD": "High Court",
    "PTD": "High Court",
    "PLC": "High Court",
    "PLC(CS)": "High Court",
    "GBLR": "Chief Court of Gilgit-Baltistan"
}


def repair_ocr_citation(citation: str) -> str:
    """Repairs common OCR errors in citation strings (e.g., 2O24 -> 2024, S.C.M.R. -> SCMR)."""
    if not citation:
        return ""
    c = str(citation).strip()
    # Repair letters masquerading as digits in year
    c = re.sub(r'\b2[O0o]2[0-9]\b', lambda m: m.group(0).replace('O', '0').replace('o', '0'), c)
    c = re.sub(r'\b19[O0o][0-9]\b', lambda m: m.group(0).replace('O', '0').replace('o', '0'), c)

    # Normalize journal dots
    c = re.sub(r'S\.?\s*C\.?\s*M\.?\s*R\.?', 'SCMR', c, flags=re.IGNORECASE)
    c = re.sub(r'P\.?\s*L\.?\s*D\.?', 'PLD', c, flags=re.IGNORECASE)
    c = re.sub(r'P\.?\s*Cr\.?\s*L\.?\s*J\.?', 'PCrLJ', c, flags=re.IGNORECASE)
    c = re.sub(r'C\.?\s*L\.?\s*C\.?', 'CLC', c, flags=re.IGNORECASE)
    c = re.sub(r'M\.?\s*L\.?\s*D\.?', 'MLD', c, flags=re.IGNORECASE)
    c = re.sub(r'Y\.?\s*L\.?\s*R\.?', 'YLR', c, flags=re.IGNORECASE)
    c = re.sub(r'C\.?\s*L\.?\s*D\.?', 'CLD', c, flags=re.IGNORECASE)
    c = re.sub(r'P\.?\s*T\.?\s*D\.?', 'PTD', c, flags=re.IGNORECASE)
    c = re.sub(r'P\.?\s*L\.?\s*C\.?', 'PLC', c, flags=re.IGNORECASE)

    # Clean multiple spaces
    c = re.sub(r'\s+', ' ', c).strip()
    return c


def parse_pakistan_citation(citation: str) -> Dict[str, Any]:
    """
    Parses a citation string into structured components:
    journal, year, page, court_inference, and canonical string.
    """
    clean = repair_ocr_citation(citation)
    m = re.search(
        r'\b(19\d{2}|20\d{2})\s+([A-Za-z]+(?:\s*\([A-Za-z]+\))?)\s+(\d+)\b',
        clean
    )
    if not m:
        # Check alternative format: PLD 1995 SC 34
        m_alt = re.search(
            r'\b([A-Za-z]+)\s+(19\d{2}|20\d{2})\s+([A-Za-z\s]+)?\s*(\d+)\b',
            clean
        )
        if m_alt:
            journal = m_alt.group(1).upper()
            year = int(m_alt.group(2))
            court_hint = (m_alt.group(3) or "").strip()
            page = int(m_alt.group(4))
            return {
                "raw": citation,
                "canonical": f"{journal} {year} {page}",
                "journal": journal,
                "year": year,
                "page": page,
                "court_inference": "Supreme Court of Pakistan" if "SC" in court_hint.upper() else JOURNAL_HIERARCHY.get(journal, "Superior Courts"),
                "is_valid": True
            }
        return {
            "raw": citation,
            "canonical": clean,
            "journal": None,
            "year": None,
            "page": None,
            "court_inference": "Unknown",
            "is_valid": False
        }

    year = int(m.group(1))
    journal = m.group(2).upper().replace(" ", "")
    page = int(m.group(3))

    court_infer = JOURNAL_HIERARCHY.get(journal, "High Court")
    if journal == "SCMR":
        court_infer = "Supreme Court of Pakistan"

    return {
        "raw": citation,
        "canonical": f"{year} {journal} {page}",
        "journal": journal,
        "year": year,
        "page": page,
        "court_inference": court_infer,
        "is_valid": True
    }
