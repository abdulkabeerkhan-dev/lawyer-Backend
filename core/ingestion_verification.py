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
from typing import Dict, Any, Tuple, List, Optional

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
    claimed_court = str(record.get("court_name") or record.get("court") or "").strip().lower()
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

    # 5. Citation Verification (Normalized)
    citation = str(record.get("citation") or record.get("neutral_citation") or record.get("case_id") or "").strip()
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

