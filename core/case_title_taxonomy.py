"""
core/case_title_taxonomy.py

Taxonomy, normalization, and classification engine for Canonical Case Title Repair.
Part of Mission 2B: Canonical Case Title Repair.

Guarantees:
1. get_effective_title resolves canonical_case_title over legacy case_title/title.
2. Conservative normalization: preserves legally meaningful designations ('through legal heirs',
   'through Secretary', 'Federation of Pakistan', 'Province of Punjab', 'and others', corporate names,
   and representative capacities) while standardizing 'v.' and title casing.
3. Defect classification into 9 standard classes:
   - WRONG_TITLE_RIGHT_JUDGMENT
   - PLACEHOLDER_TITLE
   - TRUNCATED_TITLE
   - TYPO_VARIANT
   - ADJACENT_ROW_TITLE_SHIFT
   - STATUTE_AS_TITLE
   - DOCKET_AS_TITLE
   - PARTY_NORMALIZATION_ONLY
   - AMBIGUOUS
"""

import re
from typing import Dict, Any, Optional, Tuple, List, Set

# Statutory markers in titles
STATUTE_TITLE_PATTERNS = [
    r'\b(?:section|sec\.?|s\.)\s+\d+',
    r'\bcr\.?\s*p\.?\s*c\b',
    r'\bc\.?\s*p\.?\s*c\b',
    r'\bconstitution\s+of\s+pakistan\b',
    r'\bincome\s+tax\s+ordinance\b',
    r'\bpenal\s+code\b',
    r'\bcustoms\s+act\b',
    r'\bcompanies\s+act\b',
    r'\bfinancial\s+institutions\b',
    r'\banti[- ]terrorism\s+act\b',
    r'\bcontrol\s+of\s+narcotic\b',
    r'\bspecified\s+articles?\b',
    r'\border\s+[ivxlcdm]+\b'
]
STATUTE_RE = re.compile('|'.join(STATUTE_TITLE_PATTERNS), re.IGNORECASE)

# Docket markers in titles
DOCKET_TITLE_PATTERNS = [
    r'^(?:civil|criminal|writ|constitutional|service|tax|customs|banking|special|family|execution|review|revision)\s+(?:petition|appeal|misc\.?|application|suit|review|revision|reference|case)\s*(?:no\.?|#)?\s*\d+',
    r'^(?:c\.?p\.?|c\.?a\.?|w\.?p\.?|cr\.?p\.?|cr\.?a\.?|c\.?m\.?|c\.?r\.?|h\.?c\.?a\.?)\s*(?:no\.?|#)?\s*\d+',
    r'^(?:petition|appeal|suit|case)\s*(?:no\.?|#)?\s*\d+'
]
DOCKET_RE = re.compile('|'.join(DOCKET_TITLE_PATTERNS), re.IGNORECASE)

# Placeholder markers in titles
PLACEHOLDER_TITLE_PATTERNS = [
    r'^(?:case\s*#\s*\d+|case\s+no\b)',
    r'^(?:precedent\s+record|judgment\s+record)',
    r'^(?:undergoing\s+index|full\s+judgment\s+record)',
    r'^(?:held\b|however\b|furthermore\b|per\s+curiam\b)',
    r'^(?:in\s+the\s+matter\s+of\s*:\s*$|in\s+re\s*:\s*$)',
    r'^\d{4}\s+[a-z]+\s+\d+$', # pure citation as title
    r'^\d{4}\b' # pure year
]
PLACEHOLDER_RE = re.compile('|'.join(PLACEHOLDER_TITLE_PATTERNS), re.IGNORECASE)

# Preserved legal phrases during title-casing
LEGAL_PRESERVED_WORDS = {
    "v.", "vs.", "and", "or", "of", "in", "the", "for", "on", "at", "to", "by", "with", "from",
    "through", "under", "re", "legal",
}

LEGAL_TITLES_PRESERVED = {
    "mst.": "Mst.",
    "mst": "Mst.",
    "mrs.": "Mrs.",
    "mr.": "Mr.",
    "syed": "Syed",
    "begum": "Begum",
    "raja": "Raja",
    "mian": "Mian",
    "malik": "Malik",
    "sardar": "Sardar",
    "chaudhry": "Chaudhry",
    "ch.": "Ch.",
    "haji": "Haji",
    "dr.": "Dr.",
    "prof.": "Prof.",
    "justice": "Justice",
    "col.": "Col.",
    "lt.": "Lt.",
    "lt.-col.": "Lt.-Col.",
    "maj.": "Maj.",
    "major": "Major",
    "gen.": "Gen.",
    "general": "General",
    "brig.": "Brig.",
    "brigadier": "Brigadier",
    "capt.": "Capt.",
    "captain": "Captain",
    "messrs": "Messrs",
    "m/s": "M/s",
    "co.": "Co.",
    "co": "Co.",
    "ltd.": "Ltd.",
    "ltd": "Ltd.",
    "pvt.": "Pvt.",
    "pvt": "Pvt.",
    "inc.": "Inc.",
    "corp.": "Corp.",
    "plc": "PLC",
    "llc": "LLC",
    "bank": "Bank",
    "federation": "Federation",
    "pakistan": "Pakistan",
    "province": "Province",
    "punjab": "Punjab",
    "sindh": "Sindh",
    "balochistan": "Balochistan",
    "khyber": "Khyber",
    "pakhtunkhwa": "Pakhtunkhwa",
    "state": "State",
    "others": "others",
    "another": "another",
    "heirs": "heirs",
    "secretary": "Secretary"
}

def get_effective_title(record: Dict[str, Any]) -> Optional[str]:
    """
    Returns canonical_case_title if present and non-empty,
    otherwise falls back to case_title, then title.
    Preserves raw case_title as immutable evidentiary lineage.
    """
    if not record or not isinstance(record, dict):
        return None
    return (
        record.get("canonical_case_title")
        or record.get("case_title")
        or record.get("title")
    )

def clean_title_noise(raw_title: str) -> str:
    """Strip scraped tab characters, court trailing tags, and trailing punctuation."""
    if not raw_title:
        return ""
    t = raw_title.strip()
    # Strip trailing court tags like "- \tSUPREME-COURT", "--SUPREME COURT", "- LAHORE-HIGH-COURT"
    t = re.sub(r'[\s\-—–]+(?:\t|\s+)*(?:SUPREME[- ]COURT|LAHORE[- ]HIGH[- ]COURT|HIGH[- ]COURT|SINDH[- ]HIGH[- ]COURT|PESHAWAR[- ]HIGH[- ]COURT|BALOCHISTAN[- ]HIGH[- ]COURT|FEDERAL[- ]SHARIAT[- ]COURT|ISLAMABAD[- ]HIGH[- ]COURT)[\s\-—–]*$', '', t, flags=re.I)
    # Strip judge tags like "- Honorable Justice..."
    t = re.sub(r'[\s\-—–]+Honorable\s+Justice\b.*$', '', t, flags=re.I)
    # Strip tabs and multiple spaces
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def conservative_title_case_word(w: str, is_first: bool = False, is_last: bool = False) -> str:
    """Capitalize a single token while preserving special acronyms and legal titles."""
    m_lead = re.match(r'^[()\[\],;.:"\'`]+', w)
    lead = m_lead.group(0) if m_lead else ""
    m_trail = re.search(r'[()\[\],;.:"\'`]+$', w)
    trail = m_trail.group(0) if m_trail else ""
    
    core = w[len(lead):len(w)-len(trail)] if trail else w[len(lead):]
    lower = core.lower()
    
    # Check legal titles map
    if lower in LEGAL_TITLES_PRESERVED:
        canon = LEGAL_TITLES_PRESERVED[lower]
        if canon.endswith('.'):
            trail = trail.lstrip('.')
        return f"{lead}{canon}{trail}"
        
    # Check lowercase joiners
    if lower in LEGAL_PRESERVED_WORDS and not is_first and not is_last:
        return f"{lead}{lower}{trail}"
        
    # Check known acronyms (e.g. WAPDA, PTCL, FBR, NAB, FIA, OGRA, PEMRA, HEC, CDA, LDA, KDA)
    if lower in {"wapda", "ptcl", "fbr", "nab", "fia", "ogra", "pemra", "hec", "cda", "lda", "kda", "sngpl", "ssgc", "pia", "pso", "sui"}:
        return f"{lead}{lower.upper()}{trail}"
        
    # Check dotted initialisms/abbreviations (e.g. A.D., N.W.F.P., U.S.A., C.J.)
    if re.match(r'^(?:[A-Za-z]\.)+[A-Za-z]?\.?$', core):
        return f"{lead}{core.upper()}{trail}"
        
    # Standard Title Case for normal words
    return f"{lead}{lower.capitalize()}{trail}"

def conservative_title_case(text: str) -> str:
    """Conservatively convert text to title case while respecting legal conventions."""
    if not text:
        return ""
    # Split by whitespace
    words = text.split()
    if not words:
        return ""
    out_words = []
    n = len(words)
    for i, w in enumerate(words):
        is_first = (i == 0)
        is_last = (i == n - 1)
        out_words.append(conservative_title_case_word(w, is_first, is_last))
    return " ".join(out_words)

def normalize_adversarial_title(p1: str, p2: str) -> str:
    """Format party 1 and party 2 into standard 'Party A v. Party B' title."""
    p1_clean = clean_party_string(p1)
    p2_clean = clean_party_string(p2)
    
    p1_tc = conservative_title_case(p1_clean)
    p2_tc = conservative_title_case(p2_clean)
    
    if p1_tc and p2_tc:
        return f"{p1_tc} v. {p2_tc}"
    elif p1_tc:
        return p1_tc
    return ""

DASH_PUNCT = r'\s\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\.\(\),;:—–\xa0'

def clean_party_string(p: str) -> str:
    """Remove procedural role designations and clean party string."""
    if not p:
        return ""
    s = p.strip()
    # Strip role suffixes
    s = re.sub(r'[' + DASH_PUNCT + r']*(?:Petitioner|Appellant|Applicant|Plaintiff|Complainant|Claimant|Accused)s?[' + DASH_PUNCT + r']*$', '', s, flags=re.I)
    s = re.sub(r'[' + DASH_PUNCT + r']*(?:Respondent|Defendant|Opposite\s+Party)s?[' + DASH_PUNCT + r']*$', '', s, flags=re.I)
    # Strip leading roles
    s = re.sub(r'^[' + DASH_PUNCT + r']*(?:Petitioner|Appellant|Applicant|Plaintiff|Respondent|Defendant)s?[' + DASH_PUNCT + r']*', '', s, flags=re.I)
    # Strip trailing and leading punctuation/dashes
    s = re.sub(r'^[' + DASH_PUNCT + r']+', '', s)
    s = re.sub(r'[' + DASH_PUNCT + r']+$', '', s)
    # Normalize missing space before parenthesis e.g. Co.(Pak) -> Co. (Pak)
    s = re.sub(r'([A-Za-z0-9\.])\(([^)]+)\)', r'\1 (\2)', s)
    # Normalize internal spaces
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def classify_title_defect(
    raw_title: str,
    header_parties: str,
    header_citation: str,
    record_citation: str,
    batch_adjacent_title: Optional[str] = None
) -> Tuple[str, str]:
    """
    Classifies title defect into one of 9 standard defect classes.
    Returns (defect_class, details).
    """
    cleaned_raw = clean_title_noise(raw_title)
    adversarial_marker_re = re.compile(r'(?:\b(?:versus|vs|v)\b|\bv\.)', re.I)
    
    # 1. Check Placeholder title
    if not cleaned_raw or len(cleaned_raw) < 5 or PLACEHOLDER_RE.search(cleaned_raw):
        return "PLACEHOLDER_TITLE", f"Title is procedural placeholder or extremely short: '{cleaned_raw[:50]}'"
        
    # 2. Check Docket as title
    if DOCKET_RE.search(cleaned_raw) and not adversarial_marker_re.search(cleaned_raw):
        return "DOCKET_AS_TITLE", f"Title is appeal or petition docket string: '{cleaned_raw[:50]}'"
        
    # 3. Check Statute as title
    if STATUTE_RE.search(cleaned_raw) and not adversarial_marker_re.search(cleaned_raw):
        return "STATUTE_AS_TITLE", f"Title is statutory section reference: '{cleaned_raw[:50]}'"
        
    # 4. Check Adjacent Row Title Shift
    if batch_adjacent_title and cleaned_raw.lower() == clean_title_noise(batch_adjacent_title).lower():
        return "ADJACENT_ROW_TITLE_SHIFT", "Title matches adjacent case in volume sequence"
        
    # Check adversarial structure in raw title
    m_raw = adversarial_marker_re.search(cleaned_raw)
    
    # 5. Check Truncated title on prefix/suffix cues
    if m_raw:
        pre = cleaned_raw[:m_raw.start()].strip()
        post = cleaned_raw[m_raw.end():].strip()
        # party A truncated to 1-3 letters like "CO", "LTD", "R", "VS"
        if len(pre) <= 3 or pre.upper() in {"CO", "LTD", "R", "SONS", "PAK", "PVT", "INC", "MR", "DR"}:
            return "TRUNCATED_TITLE", f"Party A in title is truncated prefix: '{pre}'"
        if len(post) <= 3:
            return "TRUNCATED_TITLE", f"Party B in title is truncated suffix: '{post}'"
            
    # Check against header parties if available
    if header_parties and adversarial_marker_re.search(header_parties):
        from core.ingestion_verification import normalize_party_tokens
        t_tokens = normalize_party_tokens(cleaned_raw)
        h_tokens = normalize_party_tokens(header_parties)
        overlap = len(t_tokens & h_tokens)
        
        # Check subset relationships
        if t_tokens and len(t_tokens) >= 2 and t_tokens.issubset(h_tokens) and len(t_tokens) < len(h_tokens):
            return "TRUNCATED_TITLE", "Stored title is a truncated subset of authentic judicial caption"
            
        if h_tokens and len(h_tokens) >= 2 and h_tokens.issubset(t_tokens) and len(h_tokens) < len(t_tokens):
            return "PARTY_NORMALIZATION_ONLY", "Stored title contains authentic parties with extra procedural tokens"
            
        # 6. Party Normalization Only
        if overlap >= 2 and len(t_tokens) >= 2 and abs(len(t_tokens) - len(h_tokens)) <= 1:
            return "PARTY_NORMALIZATION_ONLY", "Stored title contains matching parties but requires casing/formatting normalization"
            
        # 7. Typo Variant
        if overlap >= 1 and len(t_tokens) >= 2 and overlap / max(len(t_tokens), 1) >= 0.5:
            return "TYPO_VARIANT", "Minor spelling variation or partial token match with authentic caption"
            
        # 8. Wrong Title / Right Judgment
        if len(t_tokens) >= 2 and overlap == 0:
            return "WRONG_TITLE_RIGHT_JUDGMENT", "Stored title completely contradicts authentic judicial caption"
            
        if len(t_tokens) >= 2 and (overlap / max(len(t_tokens), 1)) < 0.35:
            return "WRONG_TITLE_RIGHT_JUDGMENT", "Stored title has negligible overlap with authentic caption"
            
    # Default fallback
    return "AMBIGUOUS", "Insufficient signals to unambiguously classify defect"
