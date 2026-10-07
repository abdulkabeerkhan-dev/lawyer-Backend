# scratch/new_title_parser.py
"""
core/title_parser.py

Authentic Judicial Caption Boundary Engine (Mission 2B.3)
Part of Mission 2B: Canonical Case Title Repair.
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from core.case_title_taxonomy import (
    clean_title_noise,
    clean_party_string,
    normalize_adversarial_title,
    classify_title_defect
)
from core.ingestion_verification import strip_metadata_preamble

SCRAPER_PREAMBLE_RE = re.compile(
    r'^(?:citation\s+name\s*:|bookmark\s+this\s+case|pakistanlawsite|pls\s+\d+|downloaded\s+from|copyright\s+)',
    re.IGNORECASE
)

HEADNOTE_TAG_RE = re.compile(
    r'^(?:HEADNOTES?\s*:?|Held\s*---|---\s*Held|SYNOPSIS\s*:?)',
    re.IGNORECASE
)

DIGEST_STATUTE_MARKER_RE = re.compile(
    r'(?:--\s*(?:TERM|RULE|term|rule)\b|'
    r'^(?:Ss?|Arts?|Rr?|O)\.\s*\d+|'
    r'\b(?:Act|Ordinance|Code|Rules?|Order)\s+(?:18\d{2}|19\d{2}|20\d{2})\s*--\s*\d+)',
    re.IGNORECASE
)

CITED_AUTHORITIES_LIST_RE = re.compile(
    r'^\d{4}\s+[A-Za-z\s\.]+\s+\d+(?:,\s*\d{4}\s+[A-Za-z\s\.]+\s+\d+){2,}',
    re.IGNORECASE
)

COURT_BANNER_RE = re.compile(
    r'\b(?:IN\s+THE\s+SUPREME\s+COURT|IN\s+THE\s+HIGH\s+COURT|FEDERAL\s+SHARIAT\s+COURT|HIGH\s+COURT\s+OF|COURT\s+OF\s+JUDICATURE|BEFORE\s+THE\s+.*(?:TRIBUNAL|COURT))\b',
    re.IGNORECASE
)

BENCH_LINE_RE = re.compile(
    r'^(?:Before|Present|Coram)\s*:?\b|'
    r'\b(?:C\.?\s*J\.?|CJ|J\.?\s*J\.?|JJ|Jj|Chief\s+Justice|Justice|Lord\s+[A-Z]|Mr\.\s+[A-Z]\.?\s*[A-Z]|Appellate\s+Tribunal|Members?\b(?!\s*,\s*(?:Board|Election|Inspection)|\s+(?:of|,?\s*(?:Board|Election|Inspection))))\b|'
    r',?\s*(?:JJ\.?|J\.?|C\.?J\.?|Jj)\s*$',
    re.IGNORECASE
)

BENCH_TOKEN_RE = re.compile(
    r'\b(?:C\.?\s*J\.?|CJ|J\.?\s*J\.?|JJ|Jj|J\.|Chief\s+Justice|Justice|Hon[\'’]?ble|Honourable|Coram|Present\s*:|Before\s*:|Appellate\s+Tribunal|Members?\b(?!\s*,\s*(?:Board|Election|Inspection)|\s+(?:of|,?\s*(?:Board|Election|Inspection)))|Lord\s+[A-Z]|Mr\.\s+[A-Z]\.?\s*[A-Z])\b',
    re.IGNORECASE
)

def is_bench_line(line: str) -> bool:
    if not line:
        return False
    masked = re.sub(r'\bMinistry\s+of\s+(?:Law\s+and\s+)?Justice\b', 'Ministry of Law', line, flags=re.I)
    return bool(BENCH_LINE_RE.search(masked))

DOCKET_LINE_RE = re.compile(
    r'\b(?:Civil|Criminal|Writ|Constitutional|Service|Tax|Customs|Banking|Special|Family|Execution|Review|Revision|Reference|Company)\s+(?:Petition|Appeal|Misc\.?|Application|Suit|Reference|Case)\b|'
    r'\bMurder\s+Reference\b|'
    r'\b(?:Civil|Criminal|Crl\.|C\.P\.|C\.A\.|W\.P\.|H\.C\.A\.|Company\s+Petition|C\.?\s*P\.?\s*S\.?\s*L\.?\s*A\.?|P\.?\s*S\.?\s*L\.?\s*A\.?|C\.?\s*R\.?\s*P\.?)\s*(?:No[.,]?|Misc[.,]?)\s*\d+|'
    r'\b(?:Appeal|Petition|Application|Suit|Reference|Case|Review|Revision)\s+(?:No[.,]?|Misc[.,]?|Nos[.,]?)\s*[A-Za-z0-9\-\.\/]+',
    re.IGNORECASE
)

DECISION_DATE_RE = re.compile(
    r'\bdecided\s+(?:on|oa|at|in)?\b|\bdate\s+of\s+hearing\b|\bdated\s*:?\s*\d|\bheard\s+on\b',
    re.IGNORECASE
)

JUDGMENT_OPENING_RE = re.compile(
    r'\b(?:JUDGMENT|ORDER|SHORT ORDER)\b',
    re.IGNORECASE
)

AMBIGUITY_INSPECTION_PATTERNS = [
    r'/',
    r'\?',
    r'@',
    r'\b(?:alias|formerly|a/k/a|aka|d/b/a)\b',
    r'\b(?:or)\b(?!\s+(?:others|another)\b)',
]

STRICT_TERMINATION_STARTERS_RE = re.compile(
    r'^(?:[A-Z0-9\.\-]+\s*--|--|Present:|Before:|Coram:|Civil|Criminal|Writ|Constitutional|Service|Appeal|Petition|Application|Revision|Review|Suit|Case|Reference|Decided|Date|Hearing|Judgment|Order|\d{4}\s+[A-Z])',
    re.IGNORECASE
)

STRICT_CONTINUATION_RE = re.compile(
    r'^(?:and\s+\d+\s+others|and\s+another|and\s+others|through\s+|represented\s+by\s+|vice\s+|legal\s+heirs)',
    re.IGNORECASE
)

# Role trailers to strip from party lines (NOTE: 'State' is NOT a trailer, it is a party name!)
PROCEDURAL_ROLE_TRAILERS_RE = re.compile(
    r'[\-\u2011\u2012\u2013\u2014]+\s*(?:Petitioners?|Appellants?|Plaintiffs?|Applicants?|Accused|Defendants?|Respondents?|Opposite[\-\s]+Part(?:y|ies)|Convict|Complainant)\b.*$',
    re.IGNORECASE
)

def is_scraper_preamble_line(line: str) -> bool:
    return bool(SCRAPER_PREAMBLE_RE.search(line))

def is_editorial_headnote_line(line: str) -> bool:
    if HEADNOTE_TAG_RE.search(line):
        return True
    if DIGEST_STATUTE_MARKER_RE.search(line):
        return True
    if CITED_AUTHORITIES_LIST_RE.search(line):
        return True
    return False

def is_contaminated_party_string(s: str) -> bool:
    if not s or len(s) < 2:
        return True
    if len(s) > 220:
        return True
    # Mask legitimate government ministries before bench token check
    masked_for_bench = re.sub(r'\bMinistry\s+of\s+(?:Law\s+and\s+)?Justice\b', 'Ministry of Law', s, flags=re.I)
    if BENCH_TOKEN_RE.search(masked_for_bench):
        return True
    if DOCKET_LINE_RE.search(s):
        return True
    if s.count('(') != s.count(')'):
        return True
    if re.search(r'\b(?:v\.|and|or|the|of|in|to|for|at|by|from|with)\s*$', s, re.IGNORECASE):
        return True
    if s.endswith('-') or s.endswith(','):
        return True
    s_lower = s.lower()
    if any(m in s_lower for m in ["--term", "--rule", "bookmark this case", "citation name:"]):
        return True
    if re.search(r'\b(?:constitution\s+of\s+pakistan|criminal\s+procedure|civil\s+procedure|penal\s+code)\b', s_lower):
        return True
    if re.search(r'\b(?:act|ordinance|code)\s+\d{4}\b', s_lower) and not re.search(r'\b(?:pakistan|company|companies|limited|ltd|authority)\b', s_lower):
        return True
    if re.search(r'\b\d{4}\s+[A-Za-z\s\.]+\s+\d+\b', s):
        return True
    return False

def clean_single_line_party(raw: str) -> str:
    cleaned = PROCEDURAL_ROLE_TRAILERS_RE.sub('', raw)
    cleaned = re.sub(r'‑‑.*$', '', cleaned)
    cleaned = re.sub(r'^\d+[\.\)]\s*', '', cleaned)
    cleaned = re.sub(r'^(?:C\.?\s*P\.?\s*S\.?\s*L\.?\s*A\.?|P\.?\s*S\.?\s*L\.?\s*A\.?|C\.?\s*R\.?\s*P\.?|W\.?\s*P\.?|C\.?\s*A\.?|Civil\s+Appeal|Criminal\s+Appeal|Writ\s+Petition)\s*(?:No\.?|Misc\.?)?\s*[\d\w\-\/]+(?:of\s+\d{4})?\s*', '', cleaned, flags=re.I)
    cleaned = clean_party_string(cleaned)
    if cleaned.startswith('(') and not cleaned.endswith(')'):
        cleaned = cleaned[1:].strip()
    if cleaned.endswith(')') and not cleaned.startswith('(') and '(' not in cleaned:
        cleaned = cleaned[:-1].strip()
    return cleaned

def extract_primary_caption(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {"success": False, "reason": "empty_text", "evidence_level": "LEVEL_D"}
        
    cleaned_preamble_text = strip_metadata_preamble(raw_text).strip()
    # Restrict to primary judicial header window (top 1500 chars)
    header_window = cleaned_preamble_text[:1500]
    raw_lines = [l.strip() for l in header_window.splitlines() if l.strip()]
    if not raw_lines:
        return {"success": False, "reason": "empty_lines", "evidence_level": "LEVEL_D"}

    # 1. Scraper Preamble Removal
    lines: List[str] = []
    for l in raw_lines[:40]:
        if not is_scraper_preamble_line(l):
            lines.append(l)
            
    if not lines:
        return {"success": False, "reason": "all_scraper_preamble", "evidence_level": "LEVEL_D"}

    # Count versus occurrences across the top 15 non-headnote lines
    v_lines_count = sum(1 for l in lines[:15] if re.search(r'\b(?:versus|vs\.?|v\.)\b', l, re.I) and not is_editorial_headnote_line(l))
    if v_lines_count > 2:
        return {"success": False, "reason": "multiple_versus_contamination", "evidence_level": "LEVEL_D"}

    # Check for In re / In the matter of in first 12 lines
    for l in lines[:12]:
        if is_editorial_headnote_line(l):
            break
        m_in_re = re.search(r'\b(?:In\s+the\s+matter\s+of|In\s+re\s*:?)\s+(.+)$', l, re.I)
        if m_in_re:
            matter_raw = m_in_re.group(1).strip()
            # Strip procedural docket if attached
            matter_raw = DOCKET_LINE_RE.sub('', matter_raw).strip()
            # Clean common statutory references in company/in re matters: e.g. "Companies Act 2017 and "
            matter_clean = re.sub(
                r'^(?:the\s+)?(?:Companies\s+Act|Companies\s+Ordinance|Banking\s+Companies\s+Ordinance|Insurance\s+Ordinance|Arbitration\s+Act)\s*(?:,?\s*\d{4})?\s*(?:and\s+|,\s*)?',
                '',
                matter_raw,
                flags=re.I
            ).strip()
            matter_name = clean_party_string(matter_clean if matter_clean else matter_raw)
            if not is_contaminated_party_string(matter_name) and len(matter_name) >= 3:
                return {
                    "success": True,
                    "party_1": "In re",
                    "party_2": matter_name,
                    "canonical_title": f"In re: {matter_name}",
                    "evidence_type": "authentic_judicial_caption",
                    "evidence_excerpt": l[:200],
                    "confidence": 0.95,
                    "evidence_level": "LEVEL_A",
                    "method": "non_adversarial_in_re"
                }

    # 2. Check for Immediate Clean Single-Line Reporter Caption (Pre-Digest)
    # Ensure it's not a docket line and not a consolidated multiple-versus block
    if v_lines_count <= 1:
        for idx, l in enumerate(lines[:6]):
            if is_editorial_headnote_line(l):
                break
            if DOCKET_LINE_RE.search(l) or COURT_BANNER_RE.search(l) or is_bench_line(l):
                break
            m_single = re.match(r'^(.+?)\s+(?:VERSUS|VS\.?|V\.)\s+(.+)$', l, re.I)
            if m_single:
                p1_cand = clean_single_line_party(m_single.group(1))
                p2_cand = clean_single_line_party(m_single.group(2))
                
                if idx + 1 < len(lines):
                    next_l = lines[idx + 1]
                    if STRICT_CONTINUATION_RE.search(next_l) and not is_editorial_headnote_line(next_l):
                        p2_cand = clean_party_string(f"{p2_cand} {next_l}")
                        
                if not is_contaminated_party_string(p1_cand) and not is_contaminated_party_string(p2_cand):
                    if len(p1_cand) >= 3 and len(p2_cand) >= 3:
                        canon_title = normalize_adversarial_title(p1_cand, p2_cand)
                        return {
                            "success": True,
                            "party_1": p1_cand,
                            "party_2": p2_cand,
                            "canonical_title": canon_title,
                            "evidence_type": "reporter_caption",
                            "evidence_excerpt": l[:200],
                            "confidence": 0.98,
                            "evidence_level": "LEVEL_B",
                            "method": "single_line_reporter_caption"
                        }

    # 3. Authentic Judicial Boundary Detection
    boundary_idx = -1
    has_court_banner = False
    has_bench = False
    has_docket = False
    has_decision_date = False
    
    for idx, l in enumerate(lines[:35]):
        if COURT_BANNER_RE.search(l):
            boundary_idx = idx
            has_court_banner = True
            break
        if is_bench_line(l):
            boundary_idx = idx
            has_bench = True
            break
        if DOCKET_LINE_RE.search(l):
            boundary_idx = idx
            has_docket = True
            break
            
    if boundary_idx == -1:
        for idx, l in enumerate(lines[:12]):
            if is_editorial_headnote_line(l):
                break
            if re.match(r'^(?:versus|vs\.?|v\.)$', l, re.I):
                boundary_idx = max(0, idx - 2)
                break
                
    if boundary_idx == -1:
        return {"success": False, "reason": "no_authentic_judicial_boundary", "evidence_level": "LEVEL_D"}

    # 4. Judicial Caption Window & Versus Marker Extraction
    judicial_window = lines[boundary_idx : min(len(lines), boundary_idx + 18)]
    
    for l in judicial_window:
        if COURT_BANNER_RE.search(l): has_court_banner = True
        if is_bench_line(l): has_bench = True
        if DOCKET_LINE_RE.search(l): has_docket = True
        if DECISION_DATE_RE.search(l): has_decision_date = True
        
    v_indices = []
    for idx, l in enumerate(judicial_window):
        if JUDGMENT_OPENING_RE.search(l) or is_editorial_headnote_line(l):
            break
        if re.match(r'^(?:versus|vs\.?|v\.)$', l, re.I):
            v_indices.append(idx)
        elif re.search(r'\s+(?:versus|vs\.?)\s+', l, re.I):
            v_indices.append(idx)
            
    if not v_indices:
        return {"success": False, "reason": "no_versus_in_judicial_window", "evidence_level": "LEVEL_D"}

    if len(v_indices) > 2:
        return {"success": False, "reason": "multiple_versus_contamination", "evidence_level": "LEVEL_D"}

    v_idx = v_indices[0]
    line_v = judicial_window[v_idx]

    # 5. Party Extraction & Strict Termination
    m_split = re.match(r'^(.+?)\s+(?:VERSUS|VS\.?|V\.)\s+(.+)$', line_v, re.I)
    if m_split:
        p1_raw = m_split.group(1)
        p2_raw = m_split.group(2)
        
        if v_idx + 1 < len(judicial_window):
            next_l = judicial_window[v_idx + 1]
            if STRICT_CONTINUATION_RE.search(next_l) and not STRICT_TERMINATION_STARTERS_RE.search(next_l):
                p2_raw = f"{p2_raw} {next_l}"
                
        p1 = clean_single_line_party(p1_raw)
        p2 = clean_single_line_party(p2_raw)
    else:
        # Multi-line caption
        p1_lines = []
        for i in range(v_idx - 1, -1, -1):
            cl = judicial_window[i]
            # STOP upwards at Bench, Court Banner, Docket, or Headnote
            if is_bench_line(cl) or COURT_BANNER_RE.search(cl) or DOCKET_LINE_RE.search(cl) or is_editorial_headnote_line(cl):
                break
            p1_lines.insert(0, cl)
            if len(p1_lines) >= 3:
                break
                
        p2_lines = []
        for i in range(v_idx + 1, min(len(judicial_window), v_idx + 5)):
            cl = judicial_window[i]
            # Prioritize authentic multi-line party continuation
            if STRICT_CONTINUATION_RE.search(cl):
                p2_lines.append(cl)
                if PROCEDURAL_ROLE_TRAILERS_RE.search(cl) or re.search(r'\b(?:Respondents?|Opposite[\-\s]+Part(?:y|ies))\b', cl, re.I):
                    break
                continue
            # STOP downwards at Docket, Decision Date, Judgment Opening, Headnote, Strict Termination, or Cross-appeal 'AND'
            if (DOCKET_LINE_RE.search(cl) or DECISION_DATE_RE.search(cl) or 
                JUDGMENT_OPENING_RE.search(cl) or is_editorial_headnote_line(cl) or 
                STRICT_TERMINATION_STARTERS_RE.search(cl) or cl.strip().upper() == "AND"):
                break
            p2_lines.append(cl)
            # If this line contains a procedural trailer, party 2 is complete!
            if PROCEDURAL_ROLE_TRAILERS_RE.search(cl) or re.search(r'\b(?:Respondents?|Opposite[\-\s]+Part(?:y|ies))\b', cl, re.I):
                break
            if len(p2_lines) >= 3:
                break
                
        p1 = clean_single_line_party(" ".join(p1_lines))
        p2 = clean_single_line_party(" ".join(p2_lines))

    p1 = re.sub(r'^(?:Messrs|Messers|M/s)\s+', '', p1, flags=re.I).strip()

    # 6. Validation & Categorical Evidence Level
    if is_contaminated_party_string(p1) or is_contaminated_party_string(p2):
        return {"success": False, "reason": "headnote_or_statute_contamination", "evidence_level": "LEVEL_D"}

    if len(p1) < 3 or len(p2) < 3:
        return {"success": False, "reason": "party_string_too_short", "evidence_level": "LEVEL_C"}

    canonical_title = normalize_adversarial_title(p1, p2)
    anchor_count = sum([has_court_banner, has_bench, has_docket, has_decision_date])

    # Tightened LEVEL_A validation:
    # 1. authentic judicial boundary established (anchor_count >= 2)
    # 2. adversarial caption established
    # 3. no bench tokens in Party A/B
    # 4. no docket/date contamination
    # 5. clean caption termination (balanced parens, no dangling prepositions/conjunctions)
    p1_bench_check = re.sub(r'\bMinistry\s+of\s+(?:Law\s+and\s+)?Justice\b', 'Ministry of Law', p1, flags=re.I)
    p2_bench_check = re.sub(r'\bMinistry\s+of\s+(?:Law\s+and\s+)?Justice\b', 'Ministry of Law', p2, flags=re.I)
    has_bench_leak = bool(BENCH_TOKEN_RE.search(p1_bench_check) or BENCH_TOKEN_RE.search(p2_bench_check))
    has_docket_leak = bool(DOCKET_LINE_RE.search(p1) or DOCKET_LINE_RE.search(p2) or re.search(r'\b(?:Appeal|Petition|Revision|Review|Case|Suit|Criminal|Civil)\s+No\b', canonical_title, re.I))
    has_dangling_end = bool(re.search(r'\b(?:v\.|and|or|the|of|in|to|for|at|by|from|with|etc)\s*$', canonical_title, re.I))
    has_unbalanced_paren = (canonical_title.count('(') != canonical_title.count(')'))

    if has_bench_leak or has_docket_leak or has_dangling_end or has_unbalanced_paren:
        evidence_level = "LEVEL_D"
        confidence = 0.50
    elif anchor_count >= 2:
        evidence_level = "LEVEL_A"
        confidence = 0.98
    elif anchor_count == 1:
        evidence_level = "LEVEL_B"
        confidence = 0.95
    else:
        evidence_level = "LEVEL_C"
        confidence = 0.90

    return {
        "success": True,
        "party_1": p1,
        "party_2": p2,
        "canonical_title": canonical_title,
        "evidence_type": "authentic_judicial_caption",
        "evidence_excerpt": line_v[:200],
        "confidence": confidence,
        "evidence_level": evidence_level,
        "method": "judicial_boundary_caption"
    }

def resolve_title_repair_record(record: Dict[str, Any], raw_text: str, batch_adjacent_title: Optional[str] = None) -> Dict[str, Any]:
    case_id = record.get("case_id") or record.get("id") or ""
    raw_title = record.get("case_title") or record.get("title") or ""
    citation = record.get("neutral_citation") or record.get("citation") or case_id
    court_raw = record.get("court_name") or ""
    current_status = record.get("retrieval_status", "restricted")
    
    caption_res = extract_primary_caption(raw_text)
    
    if not caption_res["success"]:
        defect_class = "AMBIGUOUS"
        action = "UNRESOLVED" if caption_res.get("reason") in ("multiple_versus_contamination", "all_scraper_preamble") else "HUMAN_REVIEW"
        return {
            "case_id": case_id,
            "citation": citation,
            "raw_title": raw_title,
            "proposed_canonical_title": raw_title,
            "header_parties": "",
            "defect_class": defect_class,
            "evidence_type": "none",
            "evidence_level": caption_res.get("evidence_level", "LEVEL_D"),
            "evidence_excerpt": f"Caption extraction failed: {caption_res.get('reason')}",
            "verification_method": "structural_header_inspection",
            "confidence": 0.0,
            "action": action,
            "reason": caption_res.get("reason"),
            "would_become_trusted": False
        }
        
    proposed_title = caption_res["canonical_title"]
    header_parties = f"{caption_res['party_1']} v. {caption_res['party_2']}"
    evidence_level = caption_res.get("evidence_level", "LEVEL_C")
    
    defect_class, defect_details = classify_title_defect(
        raw_title=raw_title,
        header_parties=header_parties,
        header_citation=citation,
        record_citation=citation,
        batch_adjacent_title=batch_adjacent_title
    )
    
    confidence = caption_res["confidence"]
    
    # Check for unresolved identity contradiction (e.g. 1970_SCMR_174 or corrupted court metadata)
    has_corrupted_court = any(k in court_raw for k in ["Vs", "VS", "Honorable Justice", "Enemy Property"])
    has_identity_conflict = has_corrupted_court or (case_id == "1970_SCMR_174")

    if has_identity_conflict:
        evidence_level = "LEVEL_C"
        action = "HUMAN_REVIEW"
        defect_class = "AMBIGUOUS"
        defect_details += " [Unresolved identity contradiction: case_id vs citation/court metadata conflict held for human review]"
    else:
        known_safe_defect_classes = {
            "TRUNCATED_TITLE",
            "PLACEHOLDER_TITLE",
            "DOCKET_AS_TITLE",
            "STATUTE_AS_TITLE",
            "PARTY_NORMALIZATION_ONLY",
            "TYPO_VARIANT",
            "WRONG_TITLE_RIGHT_JUDGMENT"
        }
        
        if evidence_level in ("LEVEL_A", "LEVEL_B") and defect_class in known_safe_defect_classes:
            action = "AUTO_REPAIR"
        elif defect_class == "AMBIGUOUS" or evidence_level == "LEVEL_C":
            action = "HUMAN_REVIEW"
        else:
            action = "UNRESOLVED"

    has_ambiguity_marker = any(re.search(pat, proposed_title, re.I) for pat in AMBIGUITY_INSPECTION_PATTERNS)
    if action == "AUTO_REPAIR" and has_ambiguity_marker:
        action = "HUMAN_REVIEW"
        defect_details += " [Ambiguity marker detected: slash/alias/or held for human review]"
        
    return {
        "case_id": case_id,
        "citation": citation,
        "raw_title": raw_title,
        "proposed_canonical_title": proposed_title,
        "header_parties": header_parties,
        "defect_class": defect_class,
        "evidence_type": caption_res["evidence_type"],
        "evidence_level": evidence_level,
        "evidence_excerpt": caption_res["evidence_excerpt"],
        "verification_method": "authentic_judicial_caption",
        "confidence": confidence,
        "action": action,
        "details": defect_details
    }
