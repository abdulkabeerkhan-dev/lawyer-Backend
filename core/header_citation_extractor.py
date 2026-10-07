"""
core/header_citation_extractor.py

Unit-tested extractor for Pakistani judgment headers:
- Restricts extraction strictly to the true header region (before adversarial/versus or docket lines).
- Never extracts cited precedents from the judgment body as case headers.
- Rejects portal chrome, customer care boilerplate, and login paywalls as 'no_header'.
- Treats PLC and PLC(CS) as equivalent journals.
"""

import re
from typing import Tuple, Optional

JOURNAL_PAT = r'(?:P\s*L\s*D|S\s*C\s*M\s*R|M\s*L\s*D|Y\s*L\s*R|C\s*L\s*C|P\s*C\s*r\s*L\s*J|P\s*T\s*D|P\s*L\s*C(?:\s*\(\s*C\s*\.?\s*S\s*\.?\s*\))?|C\s*L\s*D|G\s*B\s*L\s*R|R\s*L\s*D)'

CHROME_PATTERNS = [
    re.compile(r'^\s*#\s*Citation\s+Title\s+Court', re.I),
    re.compile(r'^\s*Latest\s+Caselaws\b', re.I),
    re.compile(r'^\s*My\s+Account\b', re.I),
    re.compile(r'^\s*Customer\s+Care\s+Office\b', re.I),
    re.compile(r'^\s*PLD\s+Publishers\b', re.I),
    re.compile(r'\b(?:Subscription\s+Options|I\s+Agree\s+with\s+the\s+Terms|Terms\s+and\s+Conditions)\b', re.I),
    re.compile(r'\bLOGIN\b.*?\b(?:About\s+Us|Contact\s+Us|Services)\b', re.I | re.DOTALL),
]

def is_chrome_or_login(text: str) -> bool:
    """Check if header text begins with or contains portal paywall / chrome boilerplate."""
    head = text[:500].strip()
    for cp in CHROME_PATTERNS:
        if cp.search(head):
            return True
    return False

def normalize_journal(j: Optional[str]) -> str:
    """Normalize journal abbreviations; treats PLC and PLC(CS) as identical."""
    if not j:
        return ""
    j_clean = re.sub(r'[^A-Z]+', '', j.upper())
    if j_clean.startswith('PLCC') or j_clean == 'PLCCS':
        return 'PLC'
    if j_clean == 'RLD':
        return 'PLD'
    return j_clean

def get_header_region(raw_text: str) -> Optional[str]:
    """
    Extract strictly the header region of the judgment:
    before the first party adversarial marker ('versus', 'vs.', 'vs', 'v.')
    or docket marker, or at most the first 350 characters.
    """
    if not raw_text:
        return None
    clean_top = raw_text[:1500].strip()
    
    # Check for Citation Name line at top:
    # e.g., Citation Name: 2025 MLD 1668 KARACHI-HIGH-COURT-SINDH
    m_cn = re.search(r'^\s*Citation\s+Name:\s*([^\r\n]+)', clean_top, re.I)
    if m_cn:
        return m_cn.group(0)

    # Check for CITATION: preamble at top:
    m_prem = re.search(r'^\s*CITATION:\s*([^\r\n]+)', clean_top, re.I)
    if m_prem:
        # If followed by portal login chrome, reject as paywall
        if is_chrome_or_login(clean_top):
            return None
        return m_prem.group(0)

    # Check for portal chrome
    if is_chrome_or_login(clean_top):
        return None

    # Cut at versus / vs / v.
    m_vs = re.search(r'\b(?:versus|vs\.?|v\.)\b', clean_top, re.I)
    if m_vs:
        return clean_top[:m_vs.start()]
        
    # Cut at docket marker
    m_dock = re.search(r'\b(?:Writ\s+Petition|Civil\s+Appeal|Criminal\s+Appeal|C\.?M\.?\s*No|Appeal\s+No)\b', clean_top, re.I)
    if m_dock:
        return clean_top[:m_dock.start()]

    return clean_top[:350]

def extract_header_citation_fixed(raw_text: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    Extract (year, journal, page, description) strictly from judgment header region.
    Returns (None, None, None, 'no_header' | 'unparsed') if no authentic header citation found.
    """
    region = get_header_region(raw_text)
    if not region:
        return None, None, None, "no_header"

    clean = re.sub(r'[\r\n\xa0]+', ' ', region).strip()

    # 1. Citation Name: 1994 MLD 424
    m_cn = re.search(r'Citation\s+Name:\s*(\d{4})\s+([A-Za-z]+(?:\([A-Za-z\.]+\))?)\s+(\d+)', clean, re.IGNORECASE)
    if m_cn:
        y, j, p = m_cn.group(1), normalize_journal(m_cn.group(2)), m_cn.group(3)
        return y, j, p, f"Citation Name: {y} {j} {p}"

    # 2. CITATION: 1980 SCMR 963
    m_prem = re.search(r'CITATION:\s*(\d{4})\s+([A-Za-z]+(?:\([A-Za-z\.]+\))?)\s+(\d+)', clean, re.IGNORECASE)
    if m_prem:
        y, j, p = m_prem.group(1), normalize_journal(m_prem.group(2)), m_prem.group(3)
        return y, j, p, f"CITATION: {y} {j} {p}"

    # 3. Traditional Format B: Year Journal [Court] Page
    # e.g., 1988 S C M R 1899, 1997 M L D 1236, 1984 S C M R 712, 1991 P L D Lahore 33
    m_trad_b = re.search(rf'\b(\d{{4}})\s+({JOURNAL_PAT})(?:\s+([A-Za-z\s\.\(\)\-]{{1,35}}?))?\s+(\d{{1,5}})\b', clean, re.IGNORECASE)
    if m_trad_b:
        y = m_trad_b.group(1)
        j = normalize_journal(m_trad_b.group(2))
        p = m_trad_b.group(4)
        return y, j, p, f"{y} {j} page {p}"

    # 4. Traditional Format A: Journal Year [Court] Page
    # e.g., P L D 1969 Lahore 374
    m_trad_a = re.search(rf'\b({JOURNAL_PAT})\s+(\d{{4}})(?:\s+([A-Za-z\s\.\(\)\-]{{1,35}}?))?\s+(\d{{1,5}})\b', clean, re.IGNORECASE)
    if m_trad_a:
        j = normalize_journal(m_trad_a.group(1))
        y = m_trad_a.group(2)
        p = m_trad_a.group(4)
        return y, j, p, f"{j} {y} page {p}"

    return None, None, None, "unparsed"
