"""
core/ingestion_verification.py

Ingestion verification and provenance gate for Pakistani superior court judgments:
- Enforces strict rule: Never author case records, holdings, or quotations from model memory.
- Corpus entries MUST derive directly from source judgment text.
- Rejects records without provenance: source_url or file_path, fetch_date, content_hash, and source_type.
- Validates source_type in {'official', 'licensed', 'user upload'}.
- Rejects records whose full_text begins with an editorial marker from retrieval.
- Preserves headnote-only records (flagged), rejecting only records with no text.
- Uses fuzzy party-name matching and citation normalization.
- Rejects contradictory, ungrounded, or synthetic records at the ingestion boundary.
"""

import re
import hashlib
import difflib
import logging
from typing import Dict, Any, Tuple, List, Optional
from core.search_provider import is_shc_url, SindhHighCourtReproductionError

VALID_SOURCE_TYPES = {"official", "licensed", "user upload"}

EDITORIAL_MARKERS = (
    "[editorial",
    "[ai-authored",
    "[synthetic",
    "[unreviewed",
    "[placeholder",
    "[provisional summary",
    "[summary - unreviewed"
)

def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

def normalize_text_tokens(text: str) -> str:
    """Normalize text into clean lowercase alphanumeric space-delimited string."""
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()

def is_editorial_text(text: str) -> bool:
    """Check if text begins with an editorial or synthetic marker."""
    t_clean = (text or "").strip().lower()
    return any(t_clean.startswith(marker) for marker in EDITORIAL_MARKERS)

def normalize_citation_components(citation_str: str) -> Dict[str, Optional[str]]:
    """
    Extract (year, journal, page) robustly from various citation formats:
    '2019 SCMR 984', 'PLD 2020 SC 150', '2018 PCrLJ 858', 'PLD 1958 SC 533'
    """
    cit_upper = citation_str.strip().upper()
    known_journals = ["SCMR", "PCrLJ", "PLD", "YLR", "CLC", "MLD", "PTD", "CLD", "PLC", "PTCL", "GBLR"]
    found_journal = None
    for j in known_journals:
        if re.search(rf'\b{j}\b', cit_upper):
            found_journal = j
            break
            
    m_year = re.search(r'\b(19\d{2}|20\d{2})\b', cit_upper)
    found_year = m_year.group(1) if m_year else None
    
    page_tokens = re.findall(r'\b\d+\b', cit_upper)
    found_page = None
    if page_tokens:
        if found_year and page_tokens[0] == found_year and len(page_tokens) > 1:
            found_page = page_tokens[-1]
        elif found_year and page_tokens[-1] == found_year and len(page_tokens) > 1:
            found_page = page_tokens[0]
        else:
            found_page = page_tokens[-1]
            
    return {"year": found_year, "journal": found_journal, "page": found_page}

def fuzzy_party_match(party_token: str, header_text: str, threshold: float = 0.75) -> bool:
    """Check if party token matches words in header_text fuzzily or exactly."""
    if not party_token or len(party_token) < 3:
        return True
    
    tok_norm = party_token.lower()
    header_tokens = normalize_text_tokens(header_text).split()
    
    # 1. Exact token match
    if tok_norm in header_tokens:
        return True
    if tok_norm in header_text.lower():
        return True
        
    # 2. Fuzzy similarity against header tokens of similar length
    for htok in header_tokens:
        if abs(len(htok) - len(tok_norm)) <= 2:
            ratio = difflib.SequenceMatcher(None, tok_norm, htok).ratio()
            if ratio >= threshold:
                return True
                
    return False

def verify_provenance(record: Dict[str, Any]) -> Tuple[bool, str]:
    """Verify source_url/file_path, fetch_date, content_hash, and source_type."""
    source_url = record.get("source_url") or record.get("file_path") or record.get("provenance_source")
    if source_url and is_shc_url(source_url):
        raise SindhHighCourtReproductionError(
            f"Ingestion of Sindh High Court text from '{source_url}' is prohibited under SHC copyright terms. "
            "SHC materials are restricted strictly to LINK AND CITE ONLY."
        )
    if not source_url:
        return False, "Missing source_url or file_path."
        
    fetch_date = record.get("fetch_date") or record.get("retrieval_date") or record.get("ingest_date")
    if not fetch_date:
        return False, "Missing fetch_date."
        
    source_type = (record.get("source_type") or "").strip().lower()
    if source_type not in VALID_SOURCE_TYPES:
        return False, f"Invalid source_type '{source_type}'. Must be one of: {VALID_SOURCE_TYPES}"
        
    claimed_hash = record.get("content_hash")
    if not claimed_hash:
        return False, "Missing content_hash."
        
    full_text = (record.get("full_text") or record.get("text") or "").strip()
    actual_hash = compute_content_hash(full_text)
    if claimed_hash != actual_hash:
        return False, f"Content hash mismatch. Claimed: {claimed_hash[:12]}..., Computed: {actual_hash[:12]}..."
        
    return True, "Provenance valid."

def verify_case_record(
    record: Dict[str, Any],
    require_provenance: bool = False,
    max_header_chars: int = 5000
) -> Dict[str, Any]:
    """
    Comprehensive verification of a case record against its text:
    Returns dict:
      - valid (bool)
      - mismatches (list of failure reasons)
      - categories (list of mismatch categories: 'title', 'court', 'citation', 'year', 'missing_text', 'provenance')
      - is_headnote (bool)
      - retrievable (bool)
    """
    mismatches: List[str] = []
    categories: List[str] = []
    
    if not isinstance(record, dict):
        return {
            "valid": False,
            "mismatches": ["Record must be a dictionary."],
            "categories": ["missing_text"],
            "is_headnote": False,
            "retrievable": False
        }
        
    source_url = record.get("source_url") or record.get("file_path") or record.get("provenance_source") or ""
    if is_shc_url(source_url):
        raise SindhHighCourtReproductionError(
            f"Ingestion of Sindh High Court text from '{source_url}' is prohibited under SHC copyright terms. "
            "SHC materials are restricted strictly to LINK AND CITE ONLY."
        )

    full_text = (record.get("full_text") or record.get("text") or "").strip()
    
    # Detect headnote status
    is_headnote = bool(
        record.get("is_headnote") or
        record.get("headnote_only") or
        record.get("status") == "headnote_only" or
        record.get("effective_stored_type") == "headnote_only" or
        record.get("detected_type") == "headnote_only" or
        len(full_text.split()) < 300
    )
    
    # 1. Missing text check: reject only if text is completely empty or explicitly 'not available'
    if not full_text or full_text.lower() in ("not available", "none", "null") or len(full_text) < 15:
        mismatches.append("Source document text is missing, empty, or 'not available'.")
        categories.append("missing_text")
        return {
            "valid": False,
            "mismatches": mismatches,
            "categories": categories,
            "is_headnote": is_headnote,
            "retrievable": False
        }
        
    # Check editorial marker
    if is_editorial_text(full_text):
        mismatches.append("Text begins with an unreviewed editorial or AI-authored marker.")
        categories.append("editorial_marker")
        retrievable = False
    else:
        retrievable = True

    # 2. Provenance Check
    if require_provenance:
        prov_ok, prov_msg = verify_provenance(record)
        if not prov_ok:
            mismatches.append(f"Provenance verification failed: {prov_msg}")
            categories.append("provenance")

    # Header region for metadata matching
    header_text = full_text[:max_header_chars]
    header_norm = normalize_text_tokens(header_text)
    
    # 3. Case Title / Party Names (Fuzzy Matching)
    case_title = str(record.get("case_title") or record.get("title") or record.get("case_name") or "").strip()
    if case_title:
        # Strip tab-delimited reporter prefixes if present (e.g., '64\t2004 YLR 202\tBAKHT ZAMIN VS AMIN KHAN...')
        if "\t" in case_title:
            parts = case_title.split("\t")
            case_title = parts[2] if len(parts) >= 3 else parts[-1]
            
        # Clean judge/lawyer suffixes if present in title string
        case_title_clean = case_title.split(" - Honorable")[0].split(" - Justice")[0]
        parties = re.split(r'\s+(?:versus|v\.?|vs\.?)\s+', case_title_clean, flags=re.IGNORECASE)
        
        party_mismatch = False
        for party in parties:
            clean_party = re.sub(
                r'\b(?:mst|dr|mr|mrs|syed|mian|the|and\s+others?|others?|etc|govt|government|of|pakistan|province|federation)\b',
                ' ',
                party,
                flags=re.IGNORECASE
            )
            tokens = [tok for tok in normalize_text_tokens(clean_party).split() if len(tok) > 2]
            if tokens:
                matched_tokens = sum(1 for tok in tokens if fuzzy_party_match(tok, header_text))
                # Require at least 50% of significant party tokens to be found fuzzily in header
                if (matched_tokens / len(tokens)) < 0.5:
                    party_mismatch = True
                    break
        if party_mismatch:
            mismatches.append(f"Case title party token(s) from '{case_title_clean}' not found in source document header.")
            categories.append("title")

    # 4. Court Name Verification
    claimed_court = str(record.get("canonical_court_name") or record.get("court_name") or record.get("court") or "").strip().lower()
    if claimed_court:

        if "supreme court" in claimed_court:
            if not ("supreme court" in header_norm or "scmr" in header_norm or "apex court" in header_norm):
                mismatches.append(f"Claimed court '{claimed_court}' contradicts document header (Supreme Court not found).")
                categories.append("court")
        elif "federal shariat" in claimed_court or "shariat appellate" in claimed_court:
            if not ("federal shariat" in header_norm or "fsc" in header_norm or "shariat appellate" in header_norm):
                mismatches.append(f"Claimed court '{claimed_court}' contradicts document header (FSC not found).")
                categories.append("court")
        elif "high court" in claimed_court:
            # Check if header contains High Court or specific province/city
            hc_found = "high court" in header_norm or any(h in header_norm for h in ["lahore", "sindh", "peshawar", "balochistan", "islamabad"])
            if not hc_found:
                mismatches.append(f"Claimed court '{claimed_court}' contradicts document header (High Court not found).")
                categories.append("court")

    # 5. Citation Verification (Normalized) - Never infer citation/page from case_id
    citation = str(record.get("citation") or record.get("neutral_citation") or "").strip()
    if citation:
        cit_comp = normalize_citation_components(citation)
        if cit_comp["journal"] and cit_comp["page"]:
            j_norm = cit_comp["journal"].lower()
            p_norm = cit_comp["page"]
            # Both journal and page must appear in header
            if j_norm not in header_norm or p_norm not in header_norm:
                mismatches.append(f"Citation '{citation}' (journal '{j_norm}' or page '{p_norm}') not found in header.")
                categories.append("citation")

    # 6. Year Verification
    year = record.get("year") or record.get("decision_date")
    if year:
        year_str = str(year)[:4]
        if year_str.isdigit() and len(year_str) == 4:
            if year_str not in header_text:
                mismatches.append(f"Year '{year_str}' not found in document header.")
                categories.append("year")

    is_valid = len(mismatches) == 0
    return {
        "valid": is_valid,
        "mismatches": mismatches,
        "categories": categories,
        "is_headnote": is_headnote,
        "retrievable": retrievable and is_valid
    }

def verify_case_record_against_text(record: Dict[str, Any]) -> Tuple[bool, str]:
    """Backward compatibility wrapper returning (bool, message)."""
    res = verify_case_record(record, require_provenance=False)
    if not res["valid"]:
        return False, "; ".join(res["mismatches"])
    return True, "Record verified against source document header text."

def ingest_verified_record(record: Dict[str, Any], require_provenance: bool = True) -> Dict[str, Any]:
    """Ingestion gatekeeper: strictly raises ValueError if validation fails."""
    res = verify_case_record(record, require_provenance=require_provenance)
    if not res["valid"]:
        raise ValueError(f"Ingestion Verification Rejected: {res['mismatches']}")
    return record


logger = logging.getLogger("query_time_identity_guardrail")


def normalize_text_hyphens(s: str) -> str:
    """Normalize various unicode hyphens and non-breaking spaces into standard whitespace."""
    return re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\xa0]+', ' ', s or '')


def strip_metadata_preamble(text: str) -> str:
    """
    Skip key-value metadata preamble lines (e.g., CITATION:, TITLE:, COURT:, BENCH:, DOCKET:, DATE:)
    so that identity verification checks the actual judicial body/header text underneath.
    """
    lines = text.splitlines()
    i = 0
    preamble_keys = {
        'citation', 'title', 'court', 'bench', 'docket', 'date',
        'judges', 'judge', 'case no', 'case_id', 'case name'
    }
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if ':' in line:
            prefix = line.split(':', 1)[0].strip().lower()
            if prefix in preamble_keys:
                i += 1
                continue
        break
    return '\n'.join(lines[i:])


def normalize_party_tokens(s: str) -> set:
    """Extract significant party tokens (length >= 3, excluding stopwords and digits)."""
    norm = normalize_text_hyphens(s or "").lower()
    norm = re.sub(r'[^a-z0-9\s]+', ' ', norm)
    stop_words = {
        'the', 'and', 'for', 'with', 'versus', 'vs', 'v', 'state', 'federation',
        'pakistan', 'petitioners', 'appellants', 'respondents', 'applicant',
        'plaintiff', 'defendant', 'others', 'another', 'messrs', 'm', 's',
        'case', 'appeal', 'civil', 'criminal', 'petition', 'misc', 'before',
        'justice', 'judge', 'mr', 'mst', 'mrs', 'dr', 'advocate',
        # Portal / Chrome stopwords
        'latest', 'caselaws', 'caselaw', 'copyrights', 'oratier', 'technologies',
        'pvt', 'ltd', 'laws', 'pakistanlawsite', 'search', 'navigation', 'menu',
        # Common designations in comma-cut titles
        'assistant', 'manager', 'director', 'deputy', 'secretary', 'officer', 'widow',
        # Court / Jurisdiction stopwords
        'court', 'courts', 'high', 'supreme', 'karachi', 'lahore', 'peshawar',
        'quetta', 'islamabad', 'rawalpindi', 'sindh', 'punjab', 'balochistan',
        'tribunal', 'service', 'appellate', 'district', 'session', 'sessions',
        'chief', 'bench', 'circuit', 'division'
    }
    tokens = set()
    for tok in norm.split():
        if len(tok) >= 3 and tok not in stop_words and not tok.isdigit():
            tokens.add(tok)
    return tokens


def extract_header_parties(text: str) -> str:
    """Extract explicit judicial party adversarial strings from header text."""
    head = text[:2500]
    head_clean = normalize_text_hyphens(head)

    # Fast filter: if no adversarial marker is present, skip expensive processing
    lower_h = head_clean.lower()
    if 'versus' not in lower_h and ' vs ' not in lower_h and ' vs. ' not in lower_h and ' v. ' not in lower_h:
        return ""

    # Strip leading "Before ...", "Present: ..." lines
    cleaned_lines = []
    in_bench = False
    for l in head_clean.splitlines():
        ls = l.strip()
        if not ls:
            continue
        if re.match(r'^(?:Before|Present)\b', ls, re.I):
            in_bench = True
            continue
        if in_bench:
            if re.search(r'\b(?:J|JJ|C\.?J\.?|Judge|Judges|Chairman|Member)\b', ls):
                in_bench = False
                continue
        cleaned_lines.append(ls)
    clean_block = '\n'.join(cleaned_lines)

    # Locate 'versus' or 'vs' / 'vs.' in clean_block
    m = re.search(r'\b(?:versus|vs\.?)\b', clean_block, re.I)
    if not m:
        return ""

    start, end = m.start(), m.end()
    pre = clean_block[max(0, start - 250):start].strip()
    pre_lines = [l.strip().strip(',;.-— ') for l in pre.splitlines() if l.strip().strip(',;.-— ')]
    p1 = pre_lines[-1] if pre_lines else ""

    post = clean_block[end:min(len(clean_block), end + 250)].strip()
    post_lines = [l.strip().strip(',;.-— ') for l in post.splitlines() if l.strip().strip(',;.-— ')]
    p2 = post_lines[0] if post_lines else ""

    p1 = re.sub(r'[-—\.\s]*(?:Petitioner|Appellant|Applicant|Plaintiff)s?[-—\.\s]*$', '', p1, flags=re.I).strip()
    p2 = re.sub(r'^[-—\.\s]*(?:Respondent|Defendant|State)s?[-—\.\s]*', '', p2, flags=re.I).strip()
    p2 = re.sub(r'[-—\.\s]*(?:Respondent|Defendant|State)s?[-—\.\s]*$', '', p2, flags=re.I).strip()
    p2 = re.sub(r'\s+(?:Civil|Criminal|Appeal|Petition|decided|dated|Order|Judgment)\b.*$', '', p2, flags=re.I).strip()

    if p1 and p2 and len(p1) >= 3 and len(p2) >= 3:
        return f"{p1} v. {p2}"

    return ""


PLACEHOLDER_TITLE_PATTERN = re.compile(
    r'^(?:Case\s*#\s*\d+'
    r'|[A-Za-z0-9_\-\.]+\s*\(\d{4}\s+[A-Za-z]+\s+\d+\)'
    r'|\(?Applications?\s+for\s+impleadment'
    r'|\(?Civil\s+(?:Misc|Appeal|Petitions?)'
    r'|\(?Criminal\s+(?:Misc|Appeal|Petitions?)'
    r'|\(?C\.?M\.?\s*No'
    r'|\(?Cr\.?Misc'
    r'|\(?Petition\s+for\s+Special\s+Leave'
    r'|Held\b'
    r'|However\b'
    r'|\d{4}\b'
    r')',
    re.I
)


def verify_query_time_identity(record: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Query-time identity check: ensures retrieved record does NOT pair one case's metadata
    with another case's text.
    Returns:
      (True, "Identity verified...") if party names match, placeholder title is resolved
      from text header, or there is insufficient contrary party info.
      (False, reason) if text header parties contradict the metadata title, or document
      is empty / login-wall / portal chrome.
    """
    raw_full_text = (record.get('full_text') or record.get('text') or record.get('raw_text') or '').strip()
    if not raw_full_text or (len(raw_full_text) < 100 and len(raw_full_text.split()) < 15):
        record['title_source'] = None
        return False, "Excluded: Missing or empty document text."

    # Work on top 3500 chars for header identification
    raw_head = raw_full_text[:3500]

    # Detect subscriber wall / login / terms of use pages
    if re.search(r'\b(?:Subscription\s+Options|I\s+Agree\s+with\s+the\s+Terms|Terms\s+and\s+Conditions\s+of\s+Acceptable\s+Use)\b', raw_head, re.I) or (
        re.search(r'\bLOGIN\b', raw_head) and re.search(r'\b(?:About\s+Us|Contact\s+Us|Services)\b', raw_head, re.I)
    ):
        record['title_source'] = None
        return False, "Excluded: Login-wall / portal subscription text."

    # 1. Ignore / detect portal chrome (e.g., Latest Caselaws)
    if re.match(r'^\s*Latest\s+Caselaws\b', raw_head, re.I):
        if 'Latest from the Journal Section' in raw_head or 'Oratier Technologies' in raw_head:
            record['title_source'] = None
            return False, "Excluded: Document consists of portal chrome/sidebar text rather than judicial text."
        # If there is content after chrome, strip chrome prefix
        chrome_match = re.search(r'\n(?=(?:\[\w|P\s*L\s*D|\d{4}\s+[A-Z]|JUDGMENT|ORDER))', raw_head, re.I)
        if chrome_match:
            raw_head = raw_head[chrome_match.start():]
        else:
            record['title_source'] = None
            return False, "Excluded: Document consists of portal chrome/sidebar text rather than judicial text."

    # 2. Skip metadata preamble (CITATION: ... TITLE: ... COURT: ...)
    clean_text = strip_metadata_preamble(raw_head).strip()
    if not clean_text or (len(clean_text) < 50 and len(clean_text.split()) < 10):
        record['title_source'] = None
        return False, "Excluded: Document contains only metadata preamble without judicial body."

    case_title = str(record.get('case_title') or record.get('title') or record.get('case_name') or '').strip()
    if not case_title:
        record['title_source'] = 'unspecified'
        return True, "No stored metadata title to verify."

    # Strip tab-delimited reporter prefixes if present
    if "\t" in case_title:
        parts = case_title.split("\t")
        case_title = parts[2] if len(parts) >= 3 else parts[-1]
    case_title_clean = re.sub(r'[-—\s]+$', '', case_title.split(" - Honorable")[0].split(" - Justice")[0].strip())
    case_title_clean = re.sub(r'\s*-\s*.*?(?:Court|Tribunal|Board).*?$', '', case_title_clean, flags=re.I).strip()

    header_parties = extract_header_parties(clean_text)

    # Check for placeholder titles or truncated names
    is_placeholder = bool(PLACEHOLDER_TITLE_PATTERN.search(case_title_clean)) or (
        case_title_clean.endswith('...') or case_title_clean.endswith('…') or len(case_title_clean) <= 4 or len(case_title_clean.split()) <= 1
    )

    if is_placeholder and header_parties:
        record['title_source'] = 'text'
        record['resolved_title'] = header_parties
        return True, f"Identity verified (title resolved from text header: '{header_parties}')."

    m_toks = normalize_party_tokens(case_title_clean)

    if not header_parties:
        # Check if title tokens appear anywhere in top 2500 chars
        if len(m_toks) >= 2:
            head_norm = normalize_text_hyphens(clean_text[:2500]).lower()
            overlap = [t for t in m_toks if t in head_norm]
            if len(overlap) == 0:
                record['title_source'] = None
                return False, f"Excluded: Stored title '{case_title_clean}' tokens not found in text header."
        record['title_source'] = 'metadata'
        return True, "Identity verified (header parties unparsed, no contrary signal)."

    m_squash = re.sub(r'[^a-z]+', '', case_title_clean.lower())
    h_squash = re.sub(r'[^a-z]+', '', header_parties.lower())
    if len(m_squash) > 8 and (m_squash in h_squash or h_squash in m_squash):
        record['title_source'] = 'metadata'
        return True, "Identity verified (squashed match)."

    h_toks = normalize_party_tokens(header_parties)
    if len(m_toks) < 1 or len(h_toks) < 1:
        record['title_source'] = 'metadata'
        return True, "Identity verified (insufficient token count)."

    overlap = m_toks.intersection(h_toks)
    if len(overlap) > 0:
        record['title_source'] = 'metadata'
        return True, f"Identity verified (overlap: {overlap})."

    for mt in m_toks:
        for ht in h_toks:
            if len(mt) >= 4 and len(ht) >= 4 and (mt in ht or ht in mt):
                record['title_source'] = 'metadata'
                return True, f"Identity verified (substring: {mt} ~ {ht})."

    # Handle comma-cut title: check if plaintiff/defendant matched
    if ',' in case_title or ' v' not in case_title_clean.lower():
        for mt in m_toks:
            if any(mt in ht or ht in mt for ht in h_toks if len(ht) >= 4 and len(mt) >= 4):
                record['title_source'] = 'metadata'
                return True, f"Identity verified (comma-cut title match: {mt})."

    record['title_source'] = None
    return False, f"Excluded: Stored title '{case_title_clean}' contradicts text header parties '{header_parties}'."


def filter_retrieved_records_for_model(
    records: List[Dict[str, Any]],
    custom_logger: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Query-time filter: Every retrieved record must pass the title/text party match
    before being passed to the model prompt. Mismatches are excluded and logged.
    """
    valid_records: List[Dict[str, Any]] = []
    log_target = custom_logger or logger

    for rec in records:
        cid = rec.get("case_id") or rec.get("id") or "unknown_id"
        passed, reason = verify_query_time_identity(rec)
        if passed:
            valid_records.append(rec)
        else:
            log_target.warning(
                f"[QUERY_TIME_IDENTITY_EXCLUSION] Excluded mismatched record case_id={cid}: {reason}"
            )

    return valid_records




def verify_retrieval_trust_record(
    record: Dict[str, Any],
    allowed_statuses: Tuple[str, ...] = ("trusted", "verified", "legacy_verified", "verified_v2"),
    allow_dynamic_fallback: bool = False
) -> Tuple[bool, str]:
    """
    Runtime Trust Gate: Ensures candidate records are explicitly trusted
    before entering the LLM prompt context.
    Fail-closed: Missing, unknown, quarantined, rejected, and restricted records
    are strictly excluded by default.
    UNKNOWN TRUST STATE = BLOCK in production runtime.
    """
    r_status = record.get("retrieval_status")
    if not r_status or r_status not in allowed_statuses:
        if not allow_dynamic_fallback:
            return False, f"Excluded by trust gate: retrieval_status='{r_status}' (FAIL-CLOSED: missing or untrusted status)"
        # Migration / Offline tooling only:
        try:
            from scripts.classify_corpus_trust import classify_record_trust
            dyn_res = classify_record_trust(record)
            dyn_status = dyn_res["retrieval_status"]
            if dyn_status not in allowed_statuses:
                return False, f"Excluded by dynamic trust gate: retrieval_status='{dyn_status}' ({dyn_res['verification_reason']})"
            r_status = dyn_status
        except Exception as e:
            return False, f"Excluded by trust gate exception: {e}"

    id_valid, id_reason = verify_query_time_identity(record)
    if not id_valid:
        return False, f"Excluded by runtime identity check: {id_reason}"
    return True, f"Passed trust gate (status='{r_status}')"


def filter_trusted_retrieval_records(
    records: List[Dict[str, Any]],
    allowed_statuses: Tuple[str, ...] = ("trusted", "verified", "legacy_verified", "verified_v2"),
    custom_logger: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Filters retrieved records for LLM context, ensuring only trusted records pass.
    """
    trusted_records: List[Dict[str, Any]] = []
    log_target = custom_logger or logger

    for rec in records:
        cid = rec.get("case_id") or rec.get("id") or "unknown_id"
        passed, reason = verify_retrieval_trust_record(rec, allowed_statuses=allowed_statuses)
        if passed:
            trusted_records.append(rec)
        else:
            log_target.warning(
                f"[RETRIEVAL_TRUST_GATE_EXCLUSION] Excluded untrusted record case_id={cid}: {reason}"
            )

    return trusted_records


def classify_retrieval_authority_lane(
    record: Dict[str, Any],
    authority_policy: Optional[str] = None,
    allow_dynamic_fallback: bool = True
) -> Dict[str, Any]:
    """
    Mission 1.3 Production Refinement: Strict Conjunction for Courtroom-Grade Authority.
    Evaluates whether a candidate record qualifies as:
    1. COURTROOM_AUTHORITY (authoritative_evidence lane):
       - retrieval_status == "trusted"
       - identity_status == "verified"
       - citation_status == "verified"
       - title_status == "verified"
       - authority_policy == "FULL_AUTHORITY"
       - content_quality in {"full_text", "mixed", "order_text"}

    2. PROVISIONAL_LEAD (discovery_leads lane):
       - retrieval_status == "trusted"
       - identity_status == "probable"
       (Even with full_text content, cannot enter authoritative_evidence or support verified ratio)

    3. CAPTION_ONLY (discovery_leads lane):
       - content_quality == "caption_only"

    4. HEADNOTE_DISCOVERY (discovery_leads lane):
       - All other discovery leads (e.g. editorial headnotes)
    """
    r_status = record.get("retrieval_status")
    id_status = record.get("identity_status")
    cit_status = record.get("citation_status")
    tit_status = record.get("title_status")
    cq = record.get("content_quality")

    if (not r_status or not id_status) and allow_dynamic_fallback:
        try:
            from scripts.classify_corpus_trust import classify_record_trust
            dyn = classify_record_trust(record)
            r_status = r_status or dyn.get("retrieval_status")
            id_status = id_status or dyn.get("identity_status")
            cit_status = cit_status or dyn.get("citation_status")
            tit_status = tit_status or dyn.get("title_status")
            cq = cq or dyn.get("content_quality")
        except Exception:
            pass

    if not authority_policy:
        from core.legal_guardrails import get_authority_policy
        authority_policy = get_authority_policy(str(cq or ""))

    is_courtroom = (
        r_status == "trusted" and
        id_status == "verified" and
        cit_status == "verified" and
        tit_status == "verified" and
        authority_policy == "FULL_AUTHORITY" and
        cq in {"full_text", "mixed", "order_text"}
    )

    if is_courtroom:
        return {
            "lane": "authoritative_evidence",
            "verified_source": True,
            "authority_class": "FULL_AUTHORITY",
            "source_badge": "Verified Judicial Text",
            "is_courtroom_authority": True
        }
    elif r_status == "trusted" and id_status == "probable":
        return {
            "lane": "discovery_leads",
            "verified_source": False,
            "authority_class": "PROVISIONAL_LEAD",
            "source_badge": "Provisional Lead (Probable Identity)",
            "is_courtroom_authority": False
        }
    elif cq == "caption_only":
        return {
            "lane": "discovery_leads",
            "verified_source": False,
            "authority_class": "NON_AUTHORITY",
            "source_badge": "Caption Only",
            "is_courtroom_authority": False
        }
    else:
        return {
            "lane": "discovery_leads",
            "verified_source": False,
            "authority_class": "HEADNOTE_DISCOVERY",
            "source_badge": "Discovery Lead (Editorial Headnote)",
            "is_courtroom_authority": False
        }
