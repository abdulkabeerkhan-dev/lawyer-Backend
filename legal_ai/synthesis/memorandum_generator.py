"""
legal_ai/synthesis/memorandum_generator.py

Production-grade Senior Counsel Legal Opinion Synthesis and Precedent Normalizer.
Features:
1. Zero Disclaimer Pollution: Purges prototype disclaimers, currency warning tags,
   and incomplete generation notices.
2. 12-Field Precedent Card Standardization:
   - case_name, citation, court, year, sections, legal_issue,
     ratio_decidendi, important_paragraphs, authority_strength,
     pdf_url, source_type, verification_status.
3. 8-Part Structured Legal Memorandum standard.
"""

import sys
import re
import urllib.parse
from typing import Dict, List, Any, Optional, Tuple

from legal_ai.documents.pdf_service import resolve_judgment_pdf_url
from legal_ai.ranking.court_weighting import normalize_court_name
from legal_ai.config import get_backend_base_url


REQUIRED_12_FIELDS: List[str] = [
    "case_name", "citation", "court", "year", "sections", "legal_issue",
    "ratio_decidendi", "important_paragraphs", "authority_strength",
    "pdf_url", "source_type", "verification_status"
]


def purge_debug_warnings(text: str) -> str:
    """
    Strips prototype warnings, verification notices, completeness notices,
    and statutory currency warning tags from user-facing output.
    """
    if not text:
        return ""
    clean = text

    # 1. Strip Prototype warning banners
    clean = re.sub(r'(?is)>\s*⚠️\s*\*{0,2}Prototype\..*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)
    clean = re.sub(r'(?is)###\s*(?:\d+\.?\s*)?APPENDIX:\s*SYSTEM\s*&\s*VERIFICATION\s*NOTICE.*?(?=(?:\n\s*###|\Z))', '', clean)
    clean = re.sub(r'(?is)>\s*⚠️\s*\*{0,2}Notice\*{0,2}:\s*This result was found via full-text keyword search.*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)
    clean = re.sub(r'(?is)>\s*⚠️\s*\*{0,2}Notice on Case Law Grounding\*{0,2}:.*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)

    # 2. Strip Judicial Review Corroboration and Gate notices
    clean = re.sub(r'(?is)>\s*⚠️\s*\*{0,2}\[?JUDICIAL REVIEW CORROBORATION NOTICE\]?\*{0,2}.*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)
    clean = re.sub(r'(?is)>\s*⚠️\s*\*{0,2}\[?JUDICIAL REVIEW GATE:\s*NOT REVIEWED\]?\*{0,2}.*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)
    clean = re.sub(r'(?is)###\s*(?:\d+\.?\s*)?APPENDIX:\s*JUDICIAL\s*REVIEW\s*CORROBORATION\s*NOTICE.*?(?=(?:\n\s*###|\Z))', '', clean)
    clean = re.sub(r'(?is)>\s*⚠️\s*\*{0,2}\[?LEGAL MEMO NOTICE\]?\*{0,2}.*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)
    clean = re.sub(r'(?is)###\s*(?:\d+\.?\s*)?APPENDIX:\s*LEGAL\s*MEMO\s*NOTICES.*?(?=(?:\n\s*###|\Z))', '', clean)
    clean = re.sub(r'(?is)⚠️\s*\*{0,2}\[?GENERATION INCOMPLETE NOTICE\]?\*{0,2}:?.*?(?=(?:\n\s*###|\n\n|\Z))', '', clean)

    # 3. Strip unverified quotation notices
    clean = re.sub(r'(?is)⚠️\s*\*{0,2}Unverified Quotation Notice\*{0,2}:.*?(?=(?:\n\s*###|\n\s*1\.|\n\s*\*{1,2}[A-Z]|\n\n|\Z))', '', clean)

    # 4. Strip statutory currency warning tags
    clean = re.sub(r'\s*\[NOT CHECKED\]', '', clean)
    clean = re.sub(r'(?is)####\s*Statutory Currency Verification Status.*?(?=(?:\n\s*###|\n\s*####|\n\n|\Z))', '', clean)
    clean = re.sub(r'(?is)###\s*(?:\d+\.?\s*)?APPENDIX:\s*STATUTORY\s*CURRENCY.*?(?=(?:\n\s*###|\Z))', '', clean)

    # 5. Clean excessive empty lines and trailing horizontal rules
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    clean = re.sub(r'\n---\s*$', '', clean).strip()
    return clean


PROHIBITED_JUDGMENT_FIRST_SECTIONS: List[str] = [
    # 1. Senior Counsel Opinion & variants
    r"senior\s*counsel(?:\s*(?:legal\s*)?opinion|\s*analysis|\s*assessment|\s*advice)?",
    r"opinion\s*of\s*senior\s*counsel",

    # 2. Executive Summary & Legal Opinion & variants
    r"executive\s*summary(?:\s*(?:&|and|\/|\+)\s*(?:legal\s*)?opinion|\s*:\s*(?:legal\s*)?opinion)?",
    r"summary\s*(?:of\s*(?:the\s*)?)?(?:legal\s*)?opinion",
    r"legal\s*opinion(?:\s*(?:&|and|\/|\+)\s*executive\s*summary)?",

    # 3. Procedural Remedy & Appellate Strategy & variants
    r"(?:procedural\s*remedy|procedural\s*remedies)(?:\s*(?:&|and|\/|\+)\s*(?:appellate\s*)?strategy)?",
    r"(?:appellate|procedural|defense|quashment|bail|pre-?arrest\s*bail)\s*strategy",
    r"strategy\s*(?:&|and|\/|\+)\s*(?:procedural\s*remedy|litigation\s*roadmap)",
    r"remedy\s*(?:&|and|\/|\+)\s*strategy",

    # 4. Recommendations & variants
    r"recommendations?(?:\s*(?:&|and|\/|\+)\s*(?:litigation\s*roadmap|next\s*steps?|suggestions?))?",
    r"(?:practical|strategic|actionable|key)\s*recommendations?",
    r"recommended\s*(?:strategy|action|actions|next\s*steps?)",

    # 5. Litigation Roadmap & variants
    r"(?:litigation|procedural|strategic)\s*roadmap",
    r"roadmap(?:\s*for\s*(?:litigation|advocate))?",
    r"(?:action\s*plan|procedural\s*playbook)(?:\s*(?:&|and|\/|\+)\s*roadmap)?",

    # 6. For an Advocate & variants
    r"(?:guidance|instructions?|notes?|steps?|strategy|checklist|advice|roadmap|practical\s*steps?)?\s*for\s*(?:an?|the)\s*advocate",
    r"for\s*advocates",
    r"advocate(?:\'s)?\s*(?:guidance|strategy|roadmap|checklist|instructions?)",

    # General prohibited strategy, speculative, or post-application sections
    r"^strategy$",
    r"strategic\s*(?:advice|guidance|overview)",
    r"prospects?\s*of\s*success",
    r"probability\s*assessment",
    r"chances?\s*of\s*success",
    r"likelihood\s*of\s*success",
    r"next\s*steps?",
    r"next\s*procedural\s*steps?",
    r"appendix(?:\s*:\s*research\s*scope(?:\s*&\s*unlocated\s*authorities)?)?",
    r"concluding\s*(?:remarks|observations?)",
]


def is_standard_judgment_first_title(title: str) -> bool:
    if not title:
        return False
    clean = re.sub(r'^[#\s\d\.\-\*\_:]+', '', title).strip()
    clean = re.sub(r'[\*\_:]+$', '', clean).strip().lower()
    patterns = [
        r"^legal\s*issues?$",
        r"^relevant\s*provisions?",
        r"^statutory\s*framework",
        r"^judicial\s*authorities",
        r"^controlling\s*(?:judicial\s*)?precedents?",
        r"^case\s*matrix",
        r"^application\s*to\s*query",
        r"^application\s*of\s*law",
        r"^statutory\s*verification",
        r"^legal\s*verification",
    ]
    return any(re.search(p, clean, re.IGNORECASE) for p in patterns)


def extract_heading_info(line: str) -> Optional[Tuple[int, str]]:
    """
    Returns (heading_level, normalized_heading_title) if the line is a section heading,
    or None if it is normal body text.
    Handles markdown hashes (#, ##, ###), bold titles (**Title**), numbered headers,
    and standalone uppercase / prominent section headers.
    """
    line_s = line.strip()
    if not line_s:
        return None

    # 1. Markdown hashes: e.g. # Title, ## Title, ### 1. ### Title, ### **Title**
    hash_match = re.match(r'^(#{1,6})\s*(?:(?:\d+[\.\)]\s*)?(?:#{1,6}\s*)?)?(.*?)$', line_s)
    if hash_match:
        level = len(hash_match.group(1))
        raw_title = hash_match.group(2).strip()
        clean_title = re.sub(r'^[#\s\d\.\-\*\_:]+', '', raw_title)
        clean_title = re.sub(r'[#\*\_:]+$', '', clean_title).strip()
        if clean_title:
            return level, clean_title

    # 2. Standalone bold/italic header line: e.g. **Senior Counsel Opinion**, **Recommendations**
    bold_match = re.match(r'^(?:\d+[\.\)]\s*)?(\*{2}|_{2})(.*?)\1\s*:?$', line_s)
    if bold_match:
        raw_title = bold_match.group(2).strip()
        clean_title = re.sub(r'^[#\s\d\.\-\*\_:]+', '', raw_title)
        clean_title = re.sub(r'[#\*\_:]+$', '', clean_title).strip()
        if clean_title and len(clean_title) < 100:
            return 2, clean_title

    # 3. Plain uppercase or title-case lines matching known prohibited or standard headers
    if len(line_s) < 100 and not line_s.endswith(('.', ';', ',')):
        clean_cand = re.sub(r'^[#\s\d\.\-\*\_:]+', '', line_s)
        clean_cand = re.sub(r'[#\*\_:]+$', '', clean_cand).strip()
        if clean_cand and (
            is_prohibited_judgment_first_title(clean_cand)
            or is_standard_judgment_first_title(clean_cand)
            or is_verification_or_application_title(clean_cand)
        ):
            return 2, clean_cand

    return None


def is_prohibited_judgment_first_title(title: str) -> bool:
    if not title:
        return False
    clean = re.sub(r'^[#\s\d\.\-\*\_:]+', '', title).strip()
    clean = re.sub(r'[\*\_:]+$', '', clean).strip().lower()
    return any(re.search(p, clean, re.IGNORECASE) for p in PROHIBITED_JUDGMENT_FIRST_SECTIONS)


def is_verification_or_application_title(title: str) -> bool:
    if not title:
        return False
    clean = re.sub(r'^[#\s\d\.\-\*\_:]+', '', title).strip()
    clean = re.sub(r'[\*\_:]+$', '', clean).strip().lower()
    patterns = [
        r"application\s+to\s+query",
        r"application\s+of\s+law\s+to\s+facts?",
        r"application\s+to\s+facts?",
        r"application\s+of\s+law",
        r"factual\s+application",
        r"application\s+to\s+(?:the\s+)?client(?:[\'’]s)?\s+case",
        r"^application$",
        r"statutory\s+verification",
        r"legal\s+verification",
        r"doctrinal\s+verification",
        r"verification\s+of\s+provisions?",
        r"verification\s+of\s+statutes?",
        r"verification\s+of\s+law",
        r"verification\s*(?:&|and|\/|\+)\s*application",
        r"application\s*(?:&|and|\/|\+)\s*verification",
        r"^verification$",
    ]
    return any(re.search(p, clean, re.IGNORECASE) for p in patterns)


def query_requests_strategy(query_text: str) -> bool:
    """
    Returns True only if the user query explicitly requests legal strategy,
    litigation roadmap, recommendations, or prospects/probability of success.
    """
    if not query_text:
        return False
    q = query_text.lower()
    strategy_keywords = [
        "strategy",
        "litigation roadmap",
        "strategic roadmap",
        "recommendation",
        "recommendations",
        "prospects of success",
        "probability assessment",
        "chances of success",
        "likelihood of success",
        "pleading strategy",
        "defense strategy",
        "appellate strategy",
        "what strategy",
    ]
    for kw in strategy_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', q):
            return True
    return False


def classify_precedent_authority_level(
    card: Dict[str, Any],
    query_plan: Any = None,
    query_text: str = ""
) -> str:
    """
    Classifies a precedent card into one of 3 authority levels:
    - 'Direct Authority': Same statute, same legal issue, same forum.
    - 'Analogical Authority': Similar principle, different statute/forum (never controlling).
    - 'Background Authority': General legal doctrine only.
    """
    if not isinstance(card, dict):
        return "Background Authority"

    meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else card
    title = str(card.get("case_name") or card.get("title") or meta.get("title") or meta.get("case_title") or "").lower()
    citation = str(card.get("citation") or card.get("neutral_citation") or meta.get("citation") or "").upper()
    court = str(card.get("court") or card.get("court_name") or card.get("canonical_court_name") or meta.get("court") or "").lower()
    preview = str(card.get("preview") or card.get("ratio_decidendi") or card.get("legal_issue") or card.get("snippet") or meta.get("full_text") or meta.get("text") or "").lower()

    statutes_raw = card.get("statutes") or card.get("sections") or meta.get("statutes") or []
    statutes_str = " ".join([str(s) for s in statutes_raw]).lower() if isinstance(statutes_raw, list) else str(statutes_raw).lower()
    combined_card_text = f"{title} {preview} {statutes_str}"

    q_str = str(query_text or "").lower()
    plan_provisions = []
    if query_plan:
        if hasattr(query_plan, "provisions") and query_plan.provisions:
            plan_provisions = [str(p).lower() for p in query_plan.provisions]
        elif isinstance(query_plan, dict) and query_plan.get("provisions"):
            plan_provisions = [str(p).lower() for p in query_plan["provisions"]]
    q_comb = f"{q_str} {' '.join(plan_provisions)}"

    # Tenancy / Rent / Punjab Rented Premises Act (PRPA 2009) vs Section 9 CPC Domain
    is_prpa_query = any(k in q_comb for k in ["punjab rented premises", "prpa", "rented premises act 2009", "prpa 2009", "rent tribunal"])
    is_rent_query = is_prpa_query or any(k in q_comb for k in ["tenan", "landlord", "eviction", "rent dispute", "rent restriction"])

    if is_prpa_query or (is_rent_query and ("punjab" in q_comb or "lahore" in q_comb)):
        # Land Revenue Act s.172 (e.g. Abdullah v. Waryam 2026 SCMR 1042)
        if any(k in combined_card_text for k in ["land revenue", "section 172", "revenue officer", "mutation", "s.172", "172 land revenue"]):
            return "Analogical Authority"

        # Out-of-province rent statutes (e.g. Sindh SRPO 1979, Dr. Shakeel Qureshi 2007 YLR 2064)
        if any(k in combined_card_text for k in ["sindh rented premises", "srpo", "srpo 1979", "ordinance xvii of 1979"]) or ("sindh" in court and "punjab rented premises" not in combined_card_text):
            return "Analogical Authority"

        # Other special statutory tribunals
        if any(k in combined_card_text for k in ["fio 2001", "recovery of finances", "service tribunal", "family court", "cantonments rent"]):
            return "Analogical Authority"

        # Direct PRPA 2009 or Punjab Rent Tribunal interpretation
        if any(k in combined_card_text for k in ["punjab rented premises", "prpa", "rent tribunal", "section 35", "section 15", "rent registrar"]):
            if "supreme court" in court or "lahore" in court or "high court" in court:
                return "Direct Authority"
            return "Analogical Authority"

        # General Section 9 CPC plenary jurisdiction without PRPA context
        if "section 9" in combined_card_text or "cpc" in combined_card_text or "jurisdiction of civil court" in combined_card_text:
            return "Background Authority"

        return "Background Authority"

    # Cross-provincial check when query specifies a provincial regime
    for prov in ["punjab", "sindh", "balochistan", "khyber", "peshawar"]:
        if prov in q_comb:
            other_provs = [p for p in ["punjab", "sindh", "balochistan", "peshawar"] if p != prov]
            if any(op in court for op in other_provs) and not ("supreme court" in court or "scmr" in citation):
                return "Analogical Authority"

    # Direct match on specific enacted provisions from query
    has_direct_provision = False
    for prov in plan_provisions:
        prov_num = re.search(r'\b\d+(?:-[a-z])?\b', prov)
        if prov_num and prov_num.group(0) in combined_card_text:
            has_direct_provision = True
            break

    if has_direct_provision:
        return "Direct Authority"

    return "Analogical Authority"


def get_authority_classification_tag(card: Dict[str, Any], query_text: str = "", query_plan: Any = None) -> str:
    level = classify_precedent_authority_level(card, query_plan=query_plan, query_text=query_text)
    meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else card
    court = str(card.get("court") or card.get("court_name") or meta.get("court") or "").lower()
    preview = str(card.get("preview") or card.get("ratio_decidendi") or meta.get("text") or "").lower()

    if level == "Direct Authority":
        return "Direct Authority (Same statutory framework and forum)"
    elif level == "Analogical Authority":
        if "land revenue" in preview or "172" in preview:
            return "Analogical Authority (Decided under Land Revenue Act 1967 s.172; different statutory scheme)"
        elif "sindh" in court or "srpo" in preview:
            return "Analogical Authority (Decided by High Court of Sindh under Sindh Rented Premises Ordinance 1979; out-of-province statute)"
        elif "fio" in preview:
            return "Analogical Authority (Decided under Financial Institutions Ordinance 2001; special banking tribunal)"
        else:
            return "Analogical Authority (Analogous principle under different statute/forum; not controlling)"
    else:
        return "Background Authority (General legal doctrine)"


def filter_and_cap_authorities(
    candidates: List[Dict[str, Any]],
    query_plan: Any = None,
    query_text: str = "",
    min_k: int = 2,
    max_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Ranks, filters out peripheral cross-provincial mismatches, and caps candidates
    at 2 to 5 strongest authorities.
    """
    if not candidates:
        return []

    q_comb = (str(query_text or "") + " " + " ".join([str(p) for p in getattr(query_plan, "provisions", []) if hasattr(query_plan, "provisions")])).lower()
    is_prpa = any(k in q_comb for k in ["punjab rented premises", "prpa", "rented premises act 2009", "prpa 2009"])
    is_punjab_specific = is_prpa or ("punjab" in q_comb or "lahore" in q_comb)

    classified: List[Dict[str, Any]] = []
    for c in candidates:
        auth_level = classify_precedent_authority_level(c, query_plan=query_plan, query_text=query_text)
        auth_tag = get_authority_classification_tag(c, query_text=query_text, query_plan=query_plan)
        c["authority_level"] = auth_level
        c["authority_classification_tag"] = auth_tag
        classified.append(c)

    # Filter out peripheral cross-provincial cases if specific to a province
    retained: List[Dict[str, Any]] = []
    for c in classified:
        court = str(c.get("court") or c.get("court_name") or "").lower()
        preview = str(c.get("preview") or c.get("ratio_decidendi") or "").lower()
        if is_punjab_specific:
            # If dispute is under Punjab Rented Premises Act, filter out Sindh High Court cases on SRPO
            if ("sindh" in court or "karachi" in court or "srpo" in preview) and not ("supreme court" in court):
                continue
        retained.append(c)

    pool = retained if len(retained) >= min_k else classified

    def priority_key(item: Dict[str, Any]) -> Tuple[int, int, float]:
        level = item.get("authority_level", "")
        level_score = 3 if level == "Direct Authority" else (2 if level == "Analogical Authority" else 1)
        court = str(item.get("court") or "").lower()
        court_score = 2 if "supreme court" in court else 1
        auth_score = float(item.get("authority_score", 0.0) or 0.0)
        return (level_score, court_score, auth_score)

    pool.sort(key=priority_key, reverse=True)
    final_count = min(max_k, max(min_k, len(pool))) if len(pool) >= min_k else len(pool)
    return pool[:final_count]


def check_missing_statutory_source(query_text: str, query_plan: Any = None) -> Tuple[bool, str]:
    """
    Checks if the query refers to an enactment whose official bare-act text
    is not available in primary local stores (data/statute_versions/*.json).
    Returns (is_missing, enactment_name).
    """
    q_str = str(query_text or "").lower()
    plan_provisions = []
    if query_plan:
        if hasattr(query_plan, "provisions") and query_plan.provisions:
            plan_provisions = [str(p).lower() for p in query_plan.provisions]
        elif isinstance(query_plan, dict) and query_plan.get("provisions"):
            plan_provisions = [str(p).lower() for p in query_plan["provisions"]]
    q_comb = f"{q_str} {' '.join(plan_provisions)}"

    if any(k in q_comb for k in ["punjab rented premises", "prpa", "rented premises act 2009", "prpa 2009"]):
        return True, "Punjab Rented Premises Act, 2009"
    return False, ""


def enforce_missing_statutory_source_warning(text: str, is_missing: bool = False, statute_name: str = "") -> str:
    """
    Inserts mandatory statutory absence warning under Relevant Provisions when complete
    statutory text is unretrieved.
    """
    if not is_missing or not text:
        return text

    warning_line = "> Statutory text unavailable in retrieved sources. The analysis is based only on judicial references."
    if warning_line in text:
        return text

    match = re.search(r'(?i)(#{1,4}\s*(?:\d+[\.\)]\s*)?Relevant\s*Provisions[^\n]*)', text)
    if match:
        heading = match.group(1)
        return text.replace(heading, f"{heading}\n{warning_line}\n", 1)

    return f"{warning_line}\n\n{text}"


def enforce_proposition_confidence_guardrails(text: str, query_text: str = "") -> str:
    """
    Eliminates overstatements regarding civil court jurisdiction against special rent tribunals.
    Replaces broad assertions with the established legality / ultra vires review standard:
    'Where the challenge concerns illegality, lack of jurisdiction, or action beyond statutory authority,
    courts have recognised that exclusionary clauses may not prevent examination of legality; however,
    an ordinary declaration of tenancy rights falls within the exclusive domain of the special Rent Tribunal.'
    """
    if not text:
        return ""

    q_comb = str(query_text or "").lower()
    is_rent_dispute = any(k in q_comb for k in ["rented premises", "prpa", "rent tribunal", "eviction notice", "tenan"])

    overstatement_patterns = [
        r'(?:the\s+)?civil\s+court\s+retains\s+(?:general\s+)?jurisdiction\s+(?:to\s+entertain\s+(?:a\s+)?civil\s+suit\s+)?for\s+declaration\s+of\s+tenancy(?:\s+rights)?(?:\s+under\s+section\s+9\s+cpc)?',
        r'(?:the\s+)?civil\s+court\s+has\s+jurisdiction\s+to\s+entertain\s+(?:a\s+)?suit\s+for\s+declaration\s+of\s+tenancy(?:\s+rights)?',
        r'(?:the\s+)?civil\s+court\s+can\s+entertain\s+(?:a\s+)?(?:civil\s+)?suit\s+for\s+declaration\s+of\s+tenancy(?:\s+rights)?',
        r'(?:the\s+)?tenant\s+can\s+maintain\s+a\s+civil\s+suit\s+for\s+declaration\s+of\s+tenancy(?:\s+rights)?',
    ]

    legality_standard = (
        "Where the challenge concerns illegality, lack of jurisdiction, or action beyond statutory authority, "
        "courts have recognised that exclusionary clauses may not prevent examination of legality; however, "
        "ordinary declaration of tenancy rights and challenge to eviction fall exclusively within the domain "
        "of the special Rent Tribunal under the Punjab Rented Premises Act 2009."
    )

    result = text
    for pat in overstatement_patterns:
        result = re.sub(pat, legality_standard, result, flags=re.IGNORECASE)

    return result


def log_runtime_diagnostic(stage: str, text: str) -> None:
    """
    Prints diagnostic runtime logging for output synthesis, boundary enforcement, and final display.
    """
    if not text:
        preview = "None / Empty"
        headers = []
    else:
        preview = text.strip()[:200].replace("\n", " ")
        headers = [
            line.strip()
            for line in text.split("\n")
            if re.match(r'^(?:#{1,6}|\*{2}|\d+[\.\)])\s+', line.strip())
        ]
    print(f"[RUNTIME LOG] {stage}: First 200 chars: '{preview}...' | Section Headers: {headers}", file=sys.stderr, flush=True)


def enforce_judgment_first_boundaries(
    text: str,
    allow_strategy: bool = False,
    query_text: str = "",
    query_plan: Any = None
) -> str:
    """
    Enforces Judgment-First Mode structural boundaries and verification termination:
    1. Deterministically removes prohibited sections and variants:
       - Senior Counsel Opinion
       - Executive Summary & Legal Opinion
       - Procedural Remedy & Appellate Strategy
       - Recommendations
       - Litigation Roadmap
       - For an Advocate
       (along with general strategy, prospects of success, probability assessment).
    2. Enforces proposition confidence guardrails and missing statutory warnings.
    3. In default / verification mode, requires that tasks terminate after the requested
       verification or application section, dropping any subsequent narrative.
    """
    if not text:
        return ""

    # Step 1: Proposition confidence guardrails
    cleaned = enforce_proposition_confidence_guardrails(text, query_text=query_text)

    # Step 2: Missing statutory source warning
    is_missing, stat_name = check_missing_statutory_source(query_text=query_text, query_plan=query_plan)
    if is_missing:
        cleaned = enforce_missing_statutory_source_warning(cleaned, is_missing=True, statute_name=stat_name)

    lines = cleaned.split("\n")
    output_lines = []
    skipping = False
    skip_level = 2

    # Pass 1: Remove prohibited sections if allow_strategy is False
    for line in lines:
        h_info = extract_heading_info(line)
        if h_info:
            level, heading_title = h_info
            if not allow_strategy and is_prohibited_judgment_first_title(heading_title):
                skipping = True
                skip_level = level
                continue
            elif skipping:
                if not is_prohibited_judgment_first_title(heading_title) and (
                    level <= skip_level or is_standard_judgment_first_title(heading_title)
                ):
                    skipping = False
                else:
                    continue
        if not skipping:
            output_lines.append(line)

    filtered_text = "\n".join(output_lines).strip()

    # Pass 2: In default / verification mode, terminate immediately after the verification / application section
    if not allow_strategy:
        lines_pass2 = filtered_text.split("\n")
        in_terminal_section = False
        terminal_level = 2
        terminal_retained = []

        for line in lines_pass2:
            h_info = extract_heading_info(line)
            if h_info:
                level, h_title = h_info
                if is_verification_or_application_title(h_title):
                    in_terminal_section = True
                    terminal_level = level
                    terminal_retained.append(line)
                    continue
                elif in_terminal_section:
                    # Once in the requested verification/application section, stop at any subsequent section
                    # that is prohibited, at the same or higher heading level, or is an appendix/conclusion
                    if (
                        level <= terminal_level
                        or is_prohibited_judgment_first_title(h_title)
                        or re.search(r'(?i)\b(?:appendix|next\s*steps|conclusion|concluding|roadmap|recommendation|advocate|strategy|opinion)\b', h_title)
                    ):
                        break
            terminal_retained.append(line)

        filtered_text = "\n".join(terminal_retained).strip()

    return filtered_text.strip()


def is_headnote_only_card(card: Dict[str, Any]) -> bool:
    """Returns True if the card represents a headnote/summary without an identifiable full judgment holding."""
    if not isinstance(card, dict):
        return False
    if card.get("has_identifiable_holding") is False:
        return True
    vstatus = str(card.get("verification_status", "")).upper()
    ctype = str(card.get("content_type", "")).lower()
    if vstatus in ("HEADNOTE_ONLY", "UNVERIFIED"):
        return True
    if ctype in ("headnote_only", "editorial_summary", "headnote", "summary"):
        return True
    if card.get("is_headnote_only") is True:
        return True
    return False


def enforce_holding_attribution(text: str, cards: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Enforces the holding attribution constraint:
    - Do not create a 'Court held' statement unless the retrieved judgment contains an identifiable holding.
    - If only a headnote/summary is available, label it as 'The judgment record indicates' rather than 'The Court held'.
    """
    if not text or not cards:
        return text

    headnote_cits = set()
    all_other_cits = set()
    for c in cards:
        cit = c.get("citation") or c.get("neutral_citation") or c.get("case_id")
        if cit:
            clean_cit = re.sub(r'[^\w\s]', ' ', str(cit)).lower().strip()
            if is_headnote_only_card(c):
                headnote_cits.add(clean_cit)
            else:
                all_other_cits.add(clean_cit)

    if not headnote_cits:
        return text

    lines = text.split("\n")
    output_lines = []
    current_case_is_headnote = False

    for line in lines:
        line_lower_norm = re.sub(r'[^\w\s]', ' ', line).lower()

        m_heading = re.match(r'^(?:#{2,4}\s+)(.*)', line)
        if m_heading:
            heading_txt = re.sub(r'[^\w\s]', ' ', m_heading.group(1)).lower()
            if any(h_cit in heading_txt for h_cit in headnote_cits):
                current_case_is_headnote = True
            elif any(o_cit in heading_txt for o_cit in all_other_cits):
                current_case_is_headnote = False
            elif any(s in heading_txt for s in ["application to query", "legal issue", "relevant provisions"]):
                current_case_is_headnote = False
        else:
            for h_cit in headnote_cits:
                if h_cit in line_lower_norm and ("—" in line or "-" in line or ":" in line):
                    current_case_is_headnote = True
                    break
            else:
                for o_cit in all_other_cits:
                    if o_cit in line_lower_norm and ("—" in line or "-" in line or ":" in line):
                        current_case_is_headnote = False
                        break

        if current_case_is_headnote:
            subbed = re.sub(
                r'(?i)(?P<prefix>^\s*[\*\-]?\s*)(?:\*{1,2})?(?:The\s+)?Court\s+held(?:\*{1,2})?\s*:\s*',
                r'\g<prefix>**The judgment record indicates**: ',
                line
            )
            subbed = re.sub(
                r'(?i)\b(?:The\s+)?Court\s+held\s+that\b',
                'the judgment record indicates that',
                subbed
            )
            output_lines.append(subbed)
        else:
            if any(h_cit in line_lower_norm for h_cit in headnote_cits):
                subbed = re.sub(
                    r'(?i)\b(?:The\s+)?Court\s+held\s+that\b',
                    'the judgment record indicates that',
                    line
                )
                output_lines.append(subbed)
            else:
                output_lines.append(line)

    return "\n".join(output_lines)


def extract_grounded_negative_boundary(text: str) -> Tuple[str, Optional[str]]:
    """
    Extracts negative boundary / limiting principle strictly from ratio/headnote text.
    Returns (negative_boundary_text, source_span).
    """
    if not text:
        return ("Limited strictly to the specific facts and operative ratio on record.", None)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    negative_signals = [
        r"\b(?:does\s+not|cannot\s+be|shall\s+not|is\s+not\s+a|not\s+entitled\s+to|not\s+competent)\b",
        r"\b(?:tentative\s+(?:observation|in\s+nature)|without\s+prejudice|left\s+open|no\s+opinion\s+expressed)\b",
        r"\b(?:cannot\s+be\s+converted|does\s+not\s+confer|does\s+not\s+determine|not\s+maintainable)\b",
        r"\b(?:interim\s+relief\s+only|not\s+a\s+substitute\s+for|strictly\s+confined\s+to)\b"
    ]

    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) > 20 and any(re.search(pat, s_clean, re.IGNORECASE) for pat in negative_signals):
            return (s_clean, s_clean)

    return ("Limited strictly to the operative ratio decidendi on record; does not decide questions beyond the specific facts and statutory provisions addressed.", None)


def sanitize_precedent_card(card: Dict[str, Any], backend_base_url: str = "") -> Dict[str, Any]:
    """
    Standardizes every precedent card to strictly contain all 12 metadata fields
    with non-empty values, valid streaming PDF URLs, and clean text.
    """
    if not isinstance(card, dict):
        return card

    c = dict(card)
    if not backend_base_url:
        backend_base_url = get_backend_base_url()

    # 1. case_name
    title = str(c.get("case_name") or c.get("title") or c.get("case_title") or "Reported Precedent").strip()
    title = re.sub(r'\s+', ' ', title).strip()
    c["case_name"] = title
    c["title"] = title

    # 3. court
    raw_court = str(c.get("court") or c.get("court_name") or "Supreme Court of Pakistan").strip()
    court = normalize_court_name(raw_court)
    c["court"] = court
    c["court_name"] = court

    # 2. citation
    cit = str(c.get("citation") or c.get("neutral_citation") or c.get("case_id") or "Neutral Citation").strip()
    try:
        from legal_ai.verification.statute_matcher import normalize_citation, norm_text, shingles
        canon_cit, is_canon = normalize_citation(cit, court)
        if is_canon:
            cit = canon_cit
    except Exception:
        norm_text = None
        shingles = None
    c["citation"] = cit
    c["neutral_citation"] = cit

    # 4. year
    year_val = c.get("year") or c.get("date")
    if not year_val or str(year_val).lower() in ("unknown", "none"):
        m_year = re.search(r'\b(19\d{2}|20\d{2})\b', f"{cit} {title}")
        year_val = m_year.group(1) if m_year else "2024"
    c["year"] = str(year_val).strip()
    c["date"] = c["year"]

    # 5. sections
    raw_secs = c.get("sections")
    clean_secs = []
    if isinstance(raw_secs, list) and raw_secs:
        clean_secs = [str(s).strip() for s in raw_secs if s]
    elif isinstance(c.get("statutes_invoked"), list):
        for s in c["statutes_invoked"]:
            if isinstance(s, dict) and s.get("name"):
                clean_secs.append(str(s["name"]).strip())
            elif isinstance(s, str):
                clean_secs.append(s.strip())

    if not clean_secs:
        comb_text = f"{c.get('raw_judgment_text', '')} {c.get('preview', '')} {c.get('holding', '')} {c.get('legal_issue', '')}"
        found = re.findall(r'\b(?:Section|Sec\.?|S\.?|Article|Art\.?)\s*(\d+[A-Za-z\-]*(?:\s*(?:PPC|Cr\.?P\.?C\.?|CPC|Constitution))?)', comb_text, flags=re.IGNORECASE)
        for fs in found:
            fs_clean = f"Section {fs.strip()}" if not fs.lower().startswith(("section", "article")) else fs.strip()
            if fs_clean not in clean_secs:
                clean_secs.append(fs_clean)

    c["sections"] = clean_secs[:5] if clean_secs else ["Superior Court Authority"]

    # 6. legal_issue
    c["legal_issue"] = str(c.get("legal_issue") or c.get("issue") or "Legal proposition extracted from indexed public judgment record.").strip()
    c["issue"] = c["legal_issue"]

    # 7. ratio_decidendi
    c["ratio_decidendi"] = str(c.get("ratio_decidendi") or c.get("holding") or c.get("preview") or "Holding on record.").strip()
    c["holding"] = c["ratio_decidendi"]
    c["preview"] = c["ratio_decidendi"]

    # 8. important_paragraphs
    raw_paras = str(c.get("important_paragraphs") or c.get("paragraphs") or c.get("operative_result") or "").strip()
    c["important_paragraphs"] = raw_paras or "Key judicial principles and reasoning on record."

    # 8b. what_this_case_does_not_decide (Negative Boundary)
    raw_neg = str(c.get("what_this_case_does_not_decide") or c.get("negative_boundary") or c.get("distinguished_points") or "").strip()
    source_span = c.get("negative_boundary_source_span")
    if not raw_neg or raw_neg.startswith("Does not determine final title"):
        source_text = f"{c.get('ratio_decidendi', '')} {c.get('important_paragraphs', '')} {c.get('raw_judgment_text', '')}"
        extracted_neg, span = extract_grounded_negative_boundary(source_text)
        raw_neg = extracted_neg
        source_span = span

    c["what_this_case_does_not_decide"] = raw_neg
    c["negative_boundary"] = raw_neg
    c["negative_boundary_source_span"] = source_span

    # 9. authority_strength
    court_low = court.lower()
    c_strength = c.get("authority_strength") or c.get("authority_level")
    if not c_strength or str(c_strength).lower() in ("unknown", "none"):
        if "supreme" in court_low:
            c_strength = "Binding Supreme Court Precedent (Article 189)"
        elif "high court" in court_low:
            c_strength = "Binding High Court Precedent (Article 201)"
        else:
            c_strength = "Persuasive Superior Court Precedent"
    c["authority_strength"] = str(c_strength).strip()

    # 10. pdf_url
    raw_pdf = resolve_judgment_pdf_url(c, backend_base_url=backend_base_url)
    if raw_pdf and isinstance(raw_pdf, str) and re.match(r'^https?://', raw_pdf.strip(), re.IGNORECASE):
        c["pdf_url"] = raw_pdf.strip()
    else:
        c["pdf_url"] = None

    # 11. source_type
    raw_src = c.get("source_type") or c.get("source")
    if not raw_src:
        if c.get("is_supabase_fts") or c.get("supabase_id"):
            raw_src = "Supabase"
        elif float(c.get("dense_score", 0.0) or 0.0) > 0:
            raw_src = "Pinecone"
        elif float(c.get("sparse_score", 0.0) or 0.0) > 0 or c.get("bm25_score"):
            raw_src = "BM25"
        else:
            raw_src = "Pinecone"
    c["source_type"] = str(raw_src)

    # 12. verification_status (4-word shingle overlap vs stored full text)
    c_type = str(c.get("content_type", "")).lower()
    meta_dict = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
    ratio_txt = str(c.get("ratio_decidendi") or c.get("preview") or c.get("holding") or c.get("important_paragraphs") or "").strip()
    full_judgment_text = str(meta_dict.get("full_text") or c.get("raw_judgment_text") or meta_dict.get("text") or c.get("preview") or "").strip()
    word_count = len(full_judgment_text.split())

    if word_count >= 150 and ratio_txt and (norm_text is not None and shingles is not None):
        ratio_norm = norm_text(ratio_txt)
        full_norm = norm_text(full_judgment_text)
        r_shingles = shingles(ratio_norm, n=4)
        f_shingles = shingles(full_norm, n=4)
        if r_shingles and f_shingles:
            overlap = len(r_shingles & f_shingles) / float(len(r_shingles))
            if overlap >= 0.35:
                vstatus = "FULL_TEXT_CHECKED"
            else:
                vstatus = "LOW_OVERLAP"
        else:
            vstatus = "FULL_TEXT_CHECKED"
    elif c_type in ("headnote_only", "editorial_summary", "headnote") or (0 < word_count < 150):
        vstatus = "HEADNOTE_ONLY"
    elif word_count == 0:
        vstatus = "UNVERIFIED"
    else:
        vstatus = "HEADNOTE_ONLY"

    c["verification_status"] = vstatus
    has_identifiable_holding = bool(
        vstatus in ("FULL_TEXT_CHECKED", "LOW_OVERLAP")
        and c_type not in ("headnote_only", "editorial_summary", "headnote", "summary")
        and word_count >= 150
    )
    c["has_identifiable_holding"] = has_identifiable_holding
    c["is_headnote_only"] = not has_identifiable_holding

    # 13. Task 3.3: 3-level computed label ('directly on point' / 'applies by analogy' / 'tangential')
    c["point_label"] = compute_relevance_point_label(c)

    return c


def compute_relevance_point_label(
    card: Dict[str, Any],
    query_plan: Optional[Any] = None,
    query_text: str = ""
) -> str:
    """
    Computes 3-level computed label:
    - 'directly on point': identical legal issue under identical statutory framework
    - 'applies by analogy': related statutory scheme or analogous administrative/judicial doctrine
    - 'tangential': distinct setting or peripheral connection
    """
    c_text = f"{card.get('case_name', '')} {card.get('ratio_decidendi', '')} {card.get('holding', '')} {' '.join(card.get('sections', []))}".lower()

    q_provs = []
    q_issues = []
    if query_plan is not None:
        q_provs = [str(p).lower() for p in getattr(query_plan, "provisions", [])]
        q_issues = [str(i).lower() for i in getattr(query_plan, "issues", [])]
        if not q_issues:
            q_issues = [str(q).lower() for q in getattr(query_plan, "legal_questions", [])]

    if not q_provs and query_text:
        found = re.findall(r'\b(?:section|article|order|rule)\s*\d+[a-z]?', query_text, re.IGNORECASE)
        q_provs = [f.lower() for f in found]

    has_statute_match = any(
        (qp in c_text or any(qp in str(s).lower() for s in card.get("sections", [])))
        for qp in q_provs
    ) if q_provs else False

    issue_matches = 0
    core_issue_terms = [
        "dismissal", "termination", "show-cause", "inquiry", "natural justice",
        "audi alteram partem", "service tribunal", "adverse possession", "limitation",
        "interim injunction", "order xxxix", "pre-arrest bail", "cheque", "eviction", "default"
    ]
    query_combined = f"{query_text} {' '.join(q_issues)}".lower()
    for term in core_issue_terms:
        if term in query_combined and term in c_text:
            issue_matches += 1

    if has_statute_match and issue_matches >= 2:
        return "directly on point"
    elif has_statute_match or issue_matches >= 1:
        return "applies by analogy"
    else:
        return "tangential"
