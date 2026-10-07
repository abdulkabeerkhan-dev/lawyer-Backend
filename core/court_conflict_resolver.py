"""
core/court_conflict_resolver.py

Deterministic resolution engine for Pakistani Superior Court identity conflicts.
Adheres strictly to Mission 2A Court Evidence Hierarchy:
1. Explicit judicial header in authentic judgment body (highest)
2. Official/source document heading
3. Reporter court/location caption
4. Reliable structured source metadata
5. Existing Supabase court metadata (baseline)

Strict Non-Evidentiary Rules:
- Counsel titles ("Advocate Supreme Court", "ASC", etc.) MUST NOT justify repair.
- Party titles (e.g. "Supreme Court Housing Society") MUST NOT justify repair.
- Case-title keywords / petition designations MUST NOT justify repair.
- Pinecone vector metadata must NEVER serve as legal authoritative evidence.
- LLM inference must NEVER be used.
- Historical institutions must NEVER be modernized incorrectly.
- Temporal bounds (court existence dates) must be strictly enforced.
"""

import re
from typing import Dict, Any, List, Optional, Tuple, Set

from core.court_taxonomy import (
    CANONICAL_COURTS,
    HISTORICAL_COURT_NAMES,
    resolve_canonical_court,
    validate_court_temporal_bounds,
    is_historical_court,
    normalize_text_key,
    is_cross_jurisdiction_or_historical_boundary
)
from core.header_citation_extractor import (
    get_header_region,
    extract_header_citation_fixed,
    JOURNAL_PAT
)

# Negative lookbehinds and patterns to reject false matches from counsel / party titles
COUNSEL_PATTERNS = [
    re.compile(r'\b(?:Advocate|Senior\s+Advocate|ASC|A\.S\.C\.|AOR|A\.O\.R\.|Counsel|Barrister)\s+(?:Supreme\s+Court|High\s+Court)\b', re.IGNORECASE),
    re.compile(r'\bfor\s+the\s+(?:Petitioner|Appellant|Respondent|State|Complainant)\b', re.IGNORECASE),
]

# Explicit judicial header patterns (Institutional banners)
JUDICIAL_HEADER_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Supreme Court of Pakistan (including OCR apostrophes and brackets)
    (re.compile(r'\[\s*SUPREME\s+COURT\s+OF[\'\s]+PAKISTAN\s*\]', re.IGNORECASE), "Supreme Court of Pakistan"),
    (re.compile(r'\b(?:IN\s+THE\s+)?SUPREME\s+COURT\s+OF[\'\s]+PAKISTAN\b', re.IGNORECASE), "Supreme Court of Pakistan"),
    (re.compile(r'^\s*SUPREME\s+COURT\s+OF[\'\s]+PAKISTAN\b', re.IGNORECASE | re.MULTILINE), "Supreme Court of Pakistan"),
    # Federal Shariat Court
    (re.compile(r'\[\s*FEDERAL\s+SHARIAT\s+COURT(?:\s+OF\s+PAKISTAN)?\s*\]', re.IGNORECASE), "Federal Shariat Court"),
    (re.compile(r'\b(?:IN\s+THE\s+)?FEDERAL\s+SHARIAT\s+COURT(?:\s+OF\s+PAKISTAN)?\b', re.IGNORECASE), "Federal Shariat Court"),
    # Lahore High Court
    (re.compile(r'\[\s*LAHORE\s+HIGH\s+COURT\s*\]', re.IGNORECASE), "Lahore High Court"),
    (re.compile(r'^\s*LAHORE\s+HIGH\s+COURT(?:\s*,\s*LAHORE|\s+LAHORE|\s*\(.*?\))?\b', re.IGNORECASE | re.MULTILINE), "Lahore High Court"),
    (re.compile(r'\b(?:IN\s+THE|BEFORE\s+THE)\s+LAHORE\s+HIGH\s+COURT(?:\s*,\s*LAHORE|\s+LAHORE|\s*\(.*?\))?\b', re.IGNORECASE), "Lahore High Court"),
    (re.compile(r'^\s*HIGH\s+COURT\s+OF\s+LAHORE\b', re.IGNORECASE | re.MULTILINE), "Lahore High Court"),
    # Sindh High Court
    (re.compile(r'\[\s*(?:HIGH\s+COURT\s+OF\s+SINDH|SINDH\s+HIGH\s+COURT)\s*\]', re.IGNORECASE), "High Court of Sindh"),
    (re.compile(r'^\s*(?:HIGH\s+COURT\s+OF\s+SINDH|SINDH\s+HIGH\s+COURT)(?:\s*,\s*KARACHI|\s+KARACHI|\s*\(.*?\))?\b', re.IGNORECASE | re.MULTILINE), "High Court of Sindh"),
    (re.compile(r'\b(?:IN\s+THE|BEFORE\s+THE)\s+(?:HIGH\s+COURT\s+OF\s+SINDH|SINDH\s+HIGH\s+COURT)(?:\s*,\s*KARACHI|\s+KARACHI|\s*\(.*?\))?\b', re.IGNORECASE), "High Court of Sindh"),
    # Peshawar High Court
    (re.compile(r'\[\s*PESHAWAR\s+HIGH\s+COURT\s*\]', re.IGNORECASE), "Peshawar High Court"),
    (re.compile(r'^\s*PESHAWAR\s+HIGH\s+COURT(?:\s*,\s*PESHAWAR|\s+PESHAWAR)?\b', re.IGNORECASE | re.MULTILINE), "Peshawar High Court"),
    (re.compile(r'\b(?:IN\s+THE|BEFORE\s+THE)\s+PESHAWAR\s+HIGH\s+COURT(?:\s*,\s*PESHAWAR|\s+PESHAWAR)?\b', re.IGNORECASE), "Peshawar High Court"),
    # Balochistan High Court
    (re.compile(r'\[\s*(?:HIGH\s+COURT\s+OF\s+BALOCHISTAN|BALOCHISTAN\s+HIGH\s+COURT)\s*\]', re.IGNORECASE), "High Court of Balochistan"),
    (re.compile(r'^\s*(?:HIGH\s+COURT\s+OF\s+BALOCHISTAN|BALOCHISTAN\s+HIGH\s+COURT)(?:\s*,\s*QUETTA|\s+QUETTA)?\b', re.IGNORECASE | re.MULTILINE), "High Court of Balochistan"),
    (re.compile(r'\b(?:IN\s+THE|BEFORE\s+THE)\s+(?:HIGH\s+COURT\s+OF\s+BALOCHISTAN|BALOCHISTAN\s+HIGH\s+COURT)\b', re.IGNORECASE), "High Court of Balochistan"),
    # Islamabad High Court
    (re.compile(r'\[\s*ISLAMABAD\s+HIGH\s+COURT\s*\]', re.IGNORECASE), "Islamabad High Court"),
    (re.compile(r'^\s*ISLAMABAD\s+HIGH\s+COURT(?:\s*,\s*ISLAMABAD|\s+ISLAMABAD)?\b', re.IGNORECASE | re.MULTILINE), "Islamabad High Court"),
    (re.compile(r'\b(?:IN\s+THE|BEFORE\s+THE)\s+ISLAMABAD\s+HIGH\s+COURT(?:\s*,\s*ISLAMABAD|\s+ISLAMABAD)?\b', re.IGNORECASE), "Islamabad High Court"),

    # AJK Courts
    (re.compile(r'\[\s*(?:SUPREME\s+COURT\s+OF\s+AZAD\s+JAMMU\s+(?:&|AND)\s+KASHMIR|SUPREME\s+COURT\s+AZAD\s+KASHMIR)\s*\]', re.IGNORECASE), "Supreme Court of Azad Jammu and Kashmir"),
    (re.compile(r'\b(?:IN\s+THE\s+)?SUPREME\s+COURT\s+OF\s+AZAD\s+(?:JAMMU\s+(?:&|AND)\s+)?KASHMIR\b', re.IGNORECASE), "Supreme Court of Azad Jammu and Kashmir"),
    (re.compile(r'\b(?:IN\s+THE\s+)?AZAD\s+(?:JAMMU\s+(?:&|AND)\s+)?KASHMIR\s+SUPREME\s+COURT\b', re.IGNORECASE), "Supreme Court of Azad Jammu and Kashmir"),
    (re.compile(r'\[\s*(?:HIGH\s+COURT\s+OF\s+AZAD\s+JAMMU\s+(?:&|AND)\s+KASHMIR|HIGH\s+COURT\s+AZAD\s+KASHMIR)\s*\]', re.IGNORECASE), "High Court of Azad Jammu and Kashmir"),
    (re.compile(r'\b(?:IN\s+THE\s+)?HIGH\s+COURT\s+OF\s+AZAD\s+(?:JAMMU\s+(?:&|AND)\s+)?KASHMIR\b', re.IGNORECASE), "High Court of Azad Jammu and Kashmir"),
    (re.compile(r'\b(?:IN\s+THE\s+)?AZAD\s+(?:JAMMU\s+(?:&|AND)\s+)?KASHMIR\s+HIGH\s+COURT\b', re.IGNORECASE), "High Court of Azad Jammu and Kashmir"),
    # Foreign Apex Courts (Historical Comparative Precedent)
    (re.compile(r'\[\s*SUPREME\s+COURT\s+OF\s+INDIA\s*\]', re.IGNORECASE), "Supreme Court of India"),
    (re.compile(r'\b(?:IN\s+THE\s+)?SUPREME\s+COURT\s+OF\s+INDIA\b', re.IGNORECASE), "Supreme Court of India"),
    (re.compile(r'^\s*SUPREME\s+COURT\s+OF\s+INDIA\b', re.IGNORECASE | re.MULTILINE), "Supreme Court of India"),
    # Gilgit-Baltistan Courts
    (re.compile(r'\b(?:IN\s+THE\s+)?SUPREME\s+APPELLATE\s+COURT\s+GILGIT[\s\-]+BALTISTAN\b', re.IGNORECASE), "Supreme Appellate Court Gilgit-Baltistan"),
    (re.compile(r'\b(?:IN\s+THE\s+)?CHIEF\s+COURT\s+GILGIT[\s\-]+BALTISTAN\b', re.IGNORECASE), "Chief Court Gilgit-Baltistan"),
    # Tribunals
    (re.compile(r'\b(?:IN\s+THE\s+)?FEDERAL\s+SERVICE\s+TRIBUNAL\b', re.IGNORECASE), "Federal Service Tribunal"),
    (re.compile(r'\b(?:IN\s+THE\s+)?PUNJAB\s+SERVICE\s+TRIBUNAL\b', re.IGNORECASE), "Punjab Service Tribunal"),
    (re.compile(r'\b(?:IN\s+THE\s+)?SINDH\s+SERVICE\s+TRIBUNAL\b', re.IGNORECASE), "Sindh Service Tribunal"),
    # Historical Courts
    (re.compile(r'\b(?:IN\s+THE\s+)?HIGH\s+COURT\s+OF\s+WEST\s+PAKISTAN\b', re.IGNORECASE), "High Court of West Pakistan"),
    (re.compile(r'\b(?:IN\s+THE\s+)?WEST\s+PAKISTAN\s+HIGH\s+COURT\b', re.IGNORECASE), "High Court of West Pakistan"),
    (re.compile(r'\b(?:IN\s+THE\s+)?(?:DHAKA|DACCA)\s+HIGH\s+COURT\b', re.IGNORECASE), "Dhaka High Court"),
    (re.compile(r'\b(?:IN\s+THE\s+)?HIGH\s+COURT\s+OF\s+(?:DACCA|EAST\s+PAKISTAN)\b', re.IGNORECASE), "Dhaka High Court"),
    (re.compile(r'\b(?:IN\s+THE\s+)?FEDERAL\s+COURT\s+OF\s+PAKISTAN\b', re.IGNORECASE), "Federal Court of Pakistan"),
    (re.compile(r'^\s*FEDERAL\s+COURT\s+OF\s+PAKISTAN\b', re.IGNORECASE | re.MULTILINE), "Federal Court of Pakistan"),
    (re.compile(r'\b(?:IN\s+THE\s+)?CHIEF\s+COURT\s+OF\s+SIND(?:H)?\b', re.IGNORECASE), "Chief Court of Sind"),
    (re.compile(r'\b(?:BEFORE\s+THE\s+)?JUDICIAL\s+COMMITTEE\s+OF\s+THE\s+PRIVY\s+COUNCIL\b', re.IGNORECASE), "Privy Council"),
]

# Reporter caption patterns in citations or captions (Hierarchy Level 3)
REPORTER_LOCATION_MAP: Dict[str, str] = {
    "sc": "Supreme Court of Pakistan",
    "supreme court": "Supreme Court of Pakistan",
    "lahore": "Lahore High Court",
    "lah": "Lahore High Court",
    "karachi": "High Court of Sindh",
    "kar": "High Court of Sindh",
    "sindh": "High Court of Sindh",
    "peshawar": "Peshawar High Court",
    "pesh": "Peshawar High Court",
    "quetta": "High Court of Balochistan",
    "qta": "High Court of Balochistan",
    "balochistan": "High Court of Balochistan",
    "islamabad": "Islamabad High Court",
    "ihc": "Islamabad High Court",
    "fsc": "Federal Shariat Court",
    "dacca": "Dhaka High Court",
    "dhaka": "Dhaka High Court",
    "wp lahore": "High Court of West Pakistan",
    "wp karachi": "High Court of West Pakistan",
    "wp peshawar": "High Court of West Pakistan",
    "fc": "Federal Court of Pakistan",
    "pc": "Privy Council",
    "aj&k": "High Court of Azad Jammu and Kashmir",
    "ajk": "High Court of Azad Jammu and Kashmir",
    "aj&k sc": "Supreme Court of Azad Jammu and Kashmir",
    "ajk sc": "Supreme Court of Azad Jammu and Kashmir",
    "sc (aj&k)": "Supreme Court of Azad Jammu and Kashmir",
    "ind": "Supreme Court of India",
    "india": "Supreme Court of India",
    "sc (ind)": "Supreme Court of India",
    "sc ind": "Supreme Court of India",
}

def extract_reporter_caption_court(citation_str: str, raw_text: str) -> Optional[Tuple[str, str]]:
    """
    Extract court implied by reporter caption / journal.
    Returns (canonical_court, excerpt) or None.
    """
    # 1. SCMR journal is strictly Supreme Court of Pakistan
    if re.search(r'\b(?:S\s*C\s*M\s*R|SCMR)\b', citation_str, re.IGNORECASE):
        return "Supreme Court of Pakistan", "Reporter SCMR exclusively covers Supreme Court of Pakistan"
    
    # 2. Check traditional citation pattern e.g., PLD 1969 Lahore 374, PLD 1985 SC 533
    combined = citation_str + " " + raw_text[:600]
    m_cap = re.search(rf'\b({JOURNAL_PAT})\s+(\d{{4}})\s+([A-Za-z\s\.\(\)\-]{{1,30}}?)\s+(\d{{1,5}})\b', combined, re.IGNORECASE)
    if m_cap:
        loc = m_cap.group(3).strip().lower()
        loc_clean = re.sub(r'[^a-z\s\&]', '', loc).strip()
        for k, court in REPORTER_LOCATION_MAP.items():
            if loc_clean == k or loc == k:
                return court, f"Citation reporter caption '{m_cap.group(0)}'"
                
    m_cap2 = re.search(rf'\b(\d{{4}})\s+({JOURNAL_PAT})\s+([A-Za-z\s\.\(\)\-]{{1,30}}?)\s+(\d{{1,5}})\b', combined, re.IGNORECASE)
    if m_cap2:
        loc = m_cap2.group(3).strip().lower()
        loc_clean = re.sub(r'[^a-z\s\&]', '', loc).strip()
        for k, court in REPORTER_LOCATION_MAP.items():
            if loc_clean == k or loc == k:
                return court, f"Citation reporter caption '{m_cap2.group(0)}'"
                
    return None

def extract_document_heading_court(raw_text: str) -> Optional[Tuple[str, str]]:
    """
    Extract official source document heading (Hierarchy Level 2).
    E.g. 'Citation Name: 2025 MLD 1668 KARACHI-HIGH-COURT-SINDH'
    or '... - LAHORE-HIGH-COURT-LAHORE'
    """
    top = raw_text[:1200]
    
    # 1. Citation Name line
    m_cn = re.search(r'Citation\s+Name:\s*[^\r\n]+?([A-Z\-]{5,40})', top, re.IGNORECASE)
    if m_cn:
        token = m_cn.group(1).replace('-', ' ').strip()
        resolved = resolve_canonical_court(token)
        if resolved:
            return resolved, f"Document heading '{m_cn.group(0).strip()}'"
            
    # 2. End-of-title dash court marker: e.g. "VS State - LAHORE-HIGH-COURT-LAHORE"
    m_dash = re.search(r'[\-\t]\s*([A-Z\-]{5,40}(?:HIGH-COURT|SUPREME-COURT|FEDERAL-COURT)[A-Z\-]*)', top, re.IGNORECASE)
    if m_dash:
        token = m_dash.group(1).replace('-', ' ').strip()
        resolved = resolve_canonical_court(token)
        if resolved:
            return resolved, f"Source title court banner '{m_dash.group(0).strip()}'"
            
    return None

def extract_explicit_judicial_header(raw_text: str) -> Optional[Tuple[str, str]]:
    """
    Extract explicit judicial header from authentic judgment body (Hierarchy Level 1).
    Scans the judgment preamble before judge names or adversarial markers.
    """
    # Restrict to header region or first 2500 characters
    head = raw_text[:2500]
    
    # Exclude obvious counsel mention contexts
    for pattern, court in JUDICIAL_HEADER_PATTERNS:
        for match in pattern.finditer(head):
            start = match.start()
            end = match.end()
            line_before = head[max(0, start - 100):start]
            line_after = head[end:min(len(head), end + 100)]
            context = head[max(0, start - 50):min(len(head), end + 50)]
            
            # Check if this match is disqualified as counsel or party description
            disqualified = False
            for cp in COUNSEL_PATTERNS:
                if cp.search(context):
                    disqualified = True
                    break
            if disqualified:
                continue
                
            # Disqualify if immediately preceded by "Advocate" or "Advocate on Record"
            if re.search(r'\b(?:Advocate|Senior\s+Advocate|AOR|ASC)\s*$', line_before, re.I):
                continue
            # Disqualify if lower appealed court mention e.g. "(On appeal from the judgment of High Court...)"
            if re.search(r'\b(?:on\s+appeal\s+from|from\s+(?:the|a)\s+(?:order|judgment|decree)|impugned\s+(?:order|judgment)|against\s+the\s+order|Full\s+Bench\s+of\s+the|Division\s+Bench\s+of\s+the|single\s+judge\s+of\s+the|decision\s+of\s+the)\b', line_before, re.I):
                continue
            # Disqualify if precedent citation, rule citation, or judicial reference
            if re.search(r'\b(?:rules\s+and\s+orders|rules\s+of|ruling\s+of|view\s+of|held\s+by|decided\s+by|moved\s+the|dealt\s+with|relied\s+upon|referred\s+to|cited\s+in|followed\s+in|distinguished\s+in|overruled\s+by|letters\s+patent|clause\s+\d+|orders\s*,|judge\s*,?\s*of|decree\s+of|judgment\s+of|order\s+of|decision\s+of|of\s+the)\b', line_before, re.I):
                continue
            # Disqualify if comparative phrase e.g. "between the Lahore High Court and..."
            if re.search(r'\bbetween\s+the\b', line_before, re.I):
                continue

            # Disqualify if followed by "Employees Co-operative" or "Society" (Party name)
            if re.search(r'^\s*(?:Employees|Society|Cooperative|Bar\s+Association)\b', line_after, re.I):
                continue
                
            # Valid explicit judicial header
            excerpt = head[max(0, start - 20):min(len(head), end + 30)].strip()
            return court, excerpt
            
    return None

def resolve_court_conflict_record(
    record: Dict[str, Any],
    raw_text: str
) -> Dict[str, Any]:
    """
    Evaluates a candidate record with court conflict and determines canonical court,
    evidence, action, confidence, and secondary issues.
    
    Returns structured resolution dict matching user specifications:
    - case_id
    - citation
    - current_court
    - proposed_canonical_court
    - judicial_header_court
    - evidence_source
    - evidence_excerpt
    - verification_method
    - confidence
    - action: AUTO_REPAIR | HUMAN_REVIEW | NO_CHANGE | UNRESOLVED
    - historical_court_flag: bool
    - secondary_issues: List[str]
    """
    case_id = record.get("case_id", "")
    citation = record.get("citation", record.get("neutral_citation", ""))
    current_court_raw = record.get("supabase_court", record.get("court_name", ""))
    current_court = resolve_canonical_court(current_court_raw) or current_court_raw
    year_str = str(record.get("year", record.get("decision_date", "")))[:4]
    decision_year = int(year_str) if year_str.isdigit() else None
    
    secondary_issues: List[str] = []
    
    # Secondary issue checks:
    # 1. Citation validity check
    y, j, p, desc = extract_header_citation_fixed(raw_text)
    if desc == "unparsed" or desc == "no_header":
        secondary_issues.append(f"citation_defect_{desc}")
        
    # 2. Check title presence
    case_title = record.get("title", record.get("case_title", ""))
    if not case_title or len(case_title.strip()) < 5:
        secondary_issues.append("missing_case_title")
    elif "\t" in case_title:
        secondary_issues.append("corrupted_title_tabs")
        
    # Evidence Extraction along Hierarchy
    level_1 = extract_explicit_judicial_header(raw_text)
    level_2 = extract_document_heading_court(raw_text)
    level_3 = extract_reporter_caption_court(citation, raw_text)
    
    proposed_court: Optional[str] = None
    evidence_source: str = "none"
    evidence_excerpt: str = ""
    verification_method: str = "none"
    confidence: float = 0.0
    action: str = "UNRESOLVED"
    historical_flag: bool = False
    
    if level_1:
        proposed_court, evidence_excerpt = level_1
        evidence_source = "judicial_header"
        verification_method = "explicit_body_header"
        confidence = 0.98
    elif level_2:
        proposed_court, evidence_excerpt = level_2
        evidence_source = "document_heading"
        verification_method = "official_source_heading"
        confidence = 0.92
    elif level_3:
        proposed_court, evidence_excerpt = level_3
        evidence_source = "reporter_caption"
        verification_method = "reporter_citation_caption"
        confidence = 0.85
    else:
        # Fall back to existing current court if already canonical
        if current_court and current_court in CANONICAL_COURTS:
            proposed_court = current_court
            evidence_source = "legacy_metadata"
            evidence_excerpt = f"Existing canonical: '{current_court}'"
            verification_method = "legacy_verified"
            confidence = 0.60
            
    # Check for historical court
    if proposed_court and is_historical_court(proposed_court):
        historical_flag = True
        
    # Check temporal bounds
    temporal_valid = True
    temporal_reason = None
    if proposed_court and decision_year:
        temporal_valid, temporal_reason = validate_court_temporal_bounds(proposed_court, decision_year)
        if not temporal_valid:
            secondary_issues.append(f"temporal_conflict_{temporal_reason}")
            
    # Action Determination
    if not proposed_court:
        action = "UNRESOLVED"
    elif not temporal_valid:
        action = "HUMAN_REVIEW"
        confidence = 0.30
        evidence_excerpt += f" | {temporal_reason}"
    elif proposed_court == current_court:
        action = "NO_CHANGE"
        confidence = 1.00
    elif is_cross_jurisdiction_or_historical_boundary(current_court, proposed_court):
        # HARD INVARIANT: Zero automatic canonicalization across jurisdictional boundaries
        # (e.g. AJK, India) or historical institutions (e.g. Federal Court, Privy Council, Dacca).
        action = "HUMAN_REVIEW"
        confidence = min(confidence, 0.40)
        evidence_excerpt += f" | Cross-jurisdiction/historical boundary: '{current_court}' -> '{proposed_court}' requires human review"
    elif evidence_source in ("judicial_header", "document_heading"):
        # Explicit evidence beats legacy metadata
        # Ensure no blatant contradiction with reporter caption
        if level_3 and level_3[0] != proposed_court:
            # Level 1 or 2 disagrees with reporter caption -> Requires human inspection
            action = "HUMAN_REVIEW"
            evidence_excerpt += f" | Contradicts reporter caption: '{level_3[0]}'"
            confidence = 0.65
        else:
            action = "AUTO_REPAIR"
    elif evidence_source == "reporter_caption":
        # SCMR has exclusive jurisdiction -> AUTO_REPAIR if no contradictory header
        if "SCMR" in citation.upper() and proposed_court == "Supreme Court of Pakistan":
            action = "AUTO_REPAIR"
            confidence = 0.95
        else:
            # High Court reporter caption alone is human review unless verified
            action = "HUMAN_REVIEW"
    else:
        action = "HUMAN_REVIEW"
        
    return {
        "case_id": case_id,
        "citation": citation,
        "current_court": current_court_raw,
        "proposed_canonical_court": proposed_court or "UNRESOLVED",
        "judicial_header_court": level_1[0] if level_1 else (level_2[0] if level_2 else "none"),
        "evidence_source": evidence_source,
        "evidence_excerpt": evidence_excerpt,
        "verification_method": verification_method,
        "confidence": round(confidence, 3),
        "action": action,
        "historical_court_flag": historical_flag,
        "secondary_issues": secondary_issues,
        "decision_year": decision_year,
    }
