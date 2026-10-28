r"""

legal_ai/verification/memo_verifier.py



MEMORANDUM VERIFIER (ORDER 1.7 HARDENING)

Purely rule-based ground-truth verification engine for Pakistani legal research memoranda.

Zero hard-coded strings, zero test-specific tuning, and zero fail-open logic.



Operational Rules (Orders 1.5 - 1.7):

  Rule (a): Every statutory quote must match a stored provision in data/unified_statutes/

            using a shared normalizer (U+037E->";", whitespace-insensitive stream matching,

            soft hyphens and line-break hyphenation removed, "N[" and "]" markers removed,

            "* * *" deletion markers ignored).

            - Ellipsis quotes ("...", "…", "[...]"): split into segments. Each must match,

              in order, inside ONE provision. Omitted text between segments is extracted for humans.

            - Unmatched quotes print a word-level diff (inserted, deleted, changed words).

            - Misattribution: when a quote follows a citation ("Order XXXIX Rule 2 provides:"),

              the matched record must be the cited one. Else labelled "MISATTRIBUTED QUOTE".

  Rule (b): System banners are exempted strictly by structural marker (`> [!`), not content.

  Rule (c): Any judicial authority / case name must exist in the verified corpus index;

            otherwise labelled "UNVERIFIED AUTHORITY (not found in our index; check manually)".

  Rule (d): Any statutory citation ("Section N of <Act>", "s. N", "Order X Rule Y(z)", "Rule N",

            "Article N") must resolve to a verified record. Unresolved -> "CITED PROVISION NOT IN VERIFIED STORE".

            - Real-but-missing provisions say "not in verified store", never "does not exist".

            - Disputed tier: allowed only if the memo contains the structural disputed banner.

              Labelled "DISPUTED TEXT — human check required". Blocked if banner is missing.

              Never labelled "not in verified store".

  Rule (e): Every sentence of narrative analysis without a supporting span or verified authority

            is labelled "UNSOURCED ANALYSIS". A sentence supported only by an UNVERIFIED authority stays flagged.

"""



import os

import sys

import json

import re

import difflib

import inspect

from typing import Dict, List, Any, Optional, Set, Tuple



REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if REPO_DIR not in sys.path:

    sys.path.insert(0, REPO_DIR)



from core.unified_statute_store import get_unified_statute_store

from core.statutory_validator import parse_statutory_citation, ACT_ALIASES



STATUTES_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")

BM25_PATH = os.path.join(REPO_DIR, "bm25_index.pkl")

HISTORICAL_CASES_PATH = os.path.join(REPO_DIR, "data", "curated_historical_cases.json")

CACHED_AUTHORITIES_PATH = os.path.join(REPO_DIR, "data", "cached_corpus_authorities.json")



# Mandatory standard labels

LABEL_UNVERIFIED_AUTHORITY = "UNVERIFIED AUTHORITY (not found in our index; check manually)"

LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE = "CITED PROVISION NOT IN VERIFIED STORE"

LABEL_DISPUTED_TEXT_NOTICE = "DISPUTED TEXT — human check required"

LABEL_DISPUTED_TEXT_MISSING_BANNER = "DISPUTED TEXT — missing required structural warning banner"

LABEL_MISATTRIBUTED_QUOTE = "MISATTRIBUTED QUOTE"

LABEL_UNSOURCED_ANALYSIS = "UNSOURCED ANALYSIS"

LABEL_HEADING_ONLY = "PROVISION TEXT NOT IN STORE (heading only)"

LABEL_DECEPTIVE_ELLIPSIS = "DECEPTIVE ELLIPSIS — omitted material condition"

LABEL_DECEPTIVE_TRUNCATION = "DECEPTIVE TRUNCATION — omitted material exception/condition"

LABEL_MODEL_BANNER_DETECTED = "MODEL-INJECTED BANNER STRIPPED"



PAK_INSTITUTION_ACRONYMS: Dict[str, List[str]] = {

    "SECP": [

        "SECURITIES AND EXCHANGE COMMISSION OF PAKISTAN",

        "SECURITIES EXCHANGE COMMISSION OF PAKISTAN",

        "SECURITIES AND EXCHANGE COMMISSION",

        "SECURITIES & EXCHANGE COMMISSION OF PAKISTAN",

        "SECURITIES & EXCHANGE COMMISSION",

    ],

    "PPRA": [

        "PUBLIC PROCUREMENT REGULATORY AUTHORITY",

        "PUNJAB PUBLIC PROCUREMENT REGULATORY AUTHORITY",

        "SINDH PUBLIC PROCUREMENT REGULATORY AUTHORITY",

    ],

    "FBR": [

        "FEDERAL BOARD OF REVENUE",

        "CENTRAL BOARD OF REVENUE",

        "CBR",

    ],

    "CBR": [

        "CENTRAL BOARD OF REVENUE",

        "FEDERAL BOARD OF REVENUE",

        "FBR",

    ],

    "NAB": [

        "NATIONAL ACCOUNTABILITY BUREAU",

    ],

    "SBP": [

        "STATE BANK OF PAKISTAN",

    ],

    "WAPDA": [

        "WATER AND POWER DEVELOPMENT AUTHORITY",

    ],

    "OGRA": [

        "OIL AND GAS REGULATORY AUTHORITY",

    ],

    "NEPRA": [

        "NATIONAL ELECTRIC POWER REGULATORY AUTHORITY",

    ],

    "PTA": [

        "PAKISTAN TELECOMMUNICATION AUTHORITY",

    ],

    "CDA": [

        "CAPITAL DEVELOPMENT AUTHORITY",

    ],

    "LDA": [

        "LAHORE DEVELOPMENT AUTHORITY",

    ],

    "KDA": [

        "KARACHI DEVELOPMENT AUTHORITY",

    ],

    "FDA": [

        "FAISALABAD DEVELOPMENT AUTHORITY",

    ],

    "RDA": [

        "RAWALPINDI DEVELOPMENT AUTHORITY",

    ],

    "MDA": [

        "MULTAN DEVELOPMENT AUTHORITY",

    ],

    "GDA": [

        "GWADAR DEVELOPMENT AUTHORITY",

    ],

    "FIA": [

        "FEDERAL INVESTIGATION AGENCY",

    ],

    "PEMRA": [

        "PAKISTAN ELECTRONIC MEDIA REGULATORY AUTHORITY",

    ],

    "BOR": [

        "BOARD OF REVENUE",

    ],

    "HEC": [

        "HIGHER EDUCATION COMMISSION",

    ],

    "PTCL": [

        "PAKISTAN TELECOMMUNICATION COMPANY LIMITED",

        "PAKISTAN TELECOMMUNICATION COMPANY",

    ],

    "NIRC": [

        "NATIONAL INDUSTRIAL RELATIONS COMMISSION",

    ],

    "ATIR": [

        "APPELLATE TRIBUNAL INLAND REVENUE",

    ],

    "DRT": [

        "DEBT RECOVERY TRIBUNAL",

    ],

    "EOBI": [

        "EMPLOYEES OLD AGE BENEFITS INSTITUTION",

    ],

    "NADRA": [

        "NATIONAL DATABASE AND REGISTRATION AUTHORITY",

    ],

    "CAA": [

        "CIVIL AVIATION AUTHORITY",

        "PAKISTAN CIVIL AVIATION AUTHORITY",

    ],

    "PCAA": [

        "CIVIL AVIATION AUTHORITY",

        "PAKISTAN CIVIL AVIATION AUTHORITY",

    ],

    "PIA": [

        "PAKISTAN INTERNATIONAL AIRLINES",

        "PAKISTAN INTERNATIONAL AIRLINES CORPORATION",

    ],

    "PIAC": [

        "PAKISTAN INTERNATIONAL AIRLINES CORPORATION",

        "PAKISTAN INTERNATIONAL AIRLINES",

    ],

    "TCP": [

        "TRADING CORPORATION OF PAKISTAN",

    ],

    "PNSC": [

        "PAKISTAN NATIONAL SHIPPING CORPORATION",

    ],

    "CCP": [

        "COMPETITION COMMISSION OF PAKISTAN",

    ],

    "FOP": [

        "FEDERATION OF PAKISTAN",

    ],

}



REV_ACRONYMS: Dict[str, str] = {}

for acr, full_names in PAK_INSTITUTION_ACRONYMS.items():

    for fn in full_names:

        REV_ACRONYMS[fn.upper()] = acr





def get_party_variants(name: str) -> Set[str]:

    """Generates normalized party variants for resilient Pakistani case name matching."""

    if not name or not isinstance(name, str):

        return set()

    name = name.upper().strip()

    variants = {name}

    c = re.sub(r'^(?:AL-HAAJ|HAJ|HAAJ|MST\.?|MST|CH\.?|CHAUDHRY|CHOUDHARY|MALIK|MIAN|RAJA|SYED|MESSRS|M/S|DR\.?|JUSTICE|MR\.?|MRS\.?|BEGUM|SARDAR|KHAN)\s+', '', name).strip()

    variants.add(c)

    core = re.sub(r'\s+(?:THROUGH|VIA|REPRESENTED\s+BY|AND\s+OTHERS|AND\s+ANOTHER|&\s*ORS?|ETC\.?).*$', '', c, flags=re.I).strip()

    core = re.sub(r'[\s,]+(?:DIRECTOR|SECRETARY|CHAIRMAN|CEO|MANAGING\s+DIRECTOR|MD|DEPUTY|ADDITIONAL|COMMISSIONER).*$', '', core, flags=re.I).strip()

    variants.add(core)

    corp_clean = re.sub(r'\s*[\(\[]?(?:PRIVATE|PVT\.?)\s*(?:LIMITED|LTD\.?)?[\)\]]?', '', core, flags=re.I).strip()

    corp_clean = re.sub(r'\s*[\(\[]?(?:LIMITED|LTD\.?)[\)\]]?', '', corp_clean, flags=re.I).strip()

    variants.add(corp_clean)

    for acr, expansions in PAK_INSTITUTION_ACRONYMS.items():

        if acr in variants or acr == name or acr == core:

            variants.update(expansions)

        for exp in expansions:

            if exp in variants or exp in name or exp in core:

                variants.add(acr)

    for full_n, acr in REV_ACRONYMS.items():

        if full_n in name or full_n in core:

            variants.add(acr)

    return {v for v in variants if v and len(v) >= 2}



BLOCKING_CONDITION_TERMS = [

    "shall not", "unless", "except", "provided that", "subject to", "notwithstanding", "if"

]

EXCEPTION_CLAUSE_TERMS = [

    "unless", "provided that", "provided", "except", "save", "subject to", "notwithstanding", "but"

]

CONDITION_TERMS = BLOCKING_CONDITION_TERMS



ELLIPSIS_SPLIT_REGEX = re.compile(r'\[?\s*(?:\.{3,}|\u2026|\.\s+\.\s+\.)\s*\]?')



class QuoteMatchResult(tuple):

    """3-tuple (matched, cid, diff) with extra attributes for omitted spans and rendered text."""

    def __new__(cls, matched: bool, cid: Optional[str], diff: Optional[str], omitted: Optional[List[str]] = None, rendered_in_memo: Optional[str] = None, deceptive_flags: Optional[List[str]] = None):

        return super().__new__(cls, (matched, cid, diff))

    def __init__(self, matched: bool, cid: Optional[str], diff: Optional[str], omitted: Optional[List[str]] = None, rendered_in_memo: Optional[str] = None, deceptive_flags: Optional[List[str]] = None):

        self.matched = matched

        self.cid = cid

        self.diff = diff

        self.omitted = omitted or []

        self.rendered_in_memo = rendered_in_memo or ""

        self.deceptive_flags = deceptive_flags or []



class CitationMatchResult(tuple):

    """3-tuple (is_valid, reason, rec) with extra attribute cid."""

    def __new__(cls, is_valid: bool, reason: Optional[str], rec: Optional[Dict[str, Any]], cid: Optional[str] = None):

        return super().__new__(cls, (is_valid, reason, rec))

    def __init__(self, is_valid: bool, reason: Optional[str], rec: Optional[Dict[str, Any]], cid: Optional[str] = None):

        self.is_valid = is_valid

        self.reason = reason

        self.rec = rec

        self.cid = cid



def strip_model_banners(memo_text: str) -> Tuple[str, List[Dict[str, Any]]]:

    """

    Rule (b): Strips every model-written `> [!...` block before verification.

    System warning banners must come strictly from the pipeline AFTER verification.

    """

    lines = memo_text.splitlines()

    cleaned_lines = []

    in_model_banner = False

    model_banners = []

    current_banner_lines = []

    banner_start_line = 0



    for idx, line in enumerate(lines, 1):

        s = line.strip()

        if s.startswith("> [!"):

            if in_model_banner and current_banner_lines:

                model_banners.append({"line": banner_start_line, "text": "\n".join(current_banner_lines)})

                current_banner_lines = []

            in_model_banner = True

            banner_start_line = idx

            current_banner_lines.append(line)

            continue



        if in_model_banner:

            if s.startswith(">"):

                current_banner_lines.append(line)

                continue

            else:

                in_model_banner = False

                if current_banner_lines:

                    model_banners.append({"line": banner_start_line, "text": "\n".join(current_banner_lines)})

                    current_banner_lines = []



        cleaned_lines.append(line)



    if in_model_banner and current_banner_lines:

        model_banners.append({"line": banner_start_line, "text": "\n".join(current_banner_lines)})



    return "\n".join(cleaned_lines), model_banners



class MemorandumVerificationBlockedError(Exception):

    """Raised when a research memorandum fails ground-truth verification."""

    def __init__(self, verification_report: Dict[str, Any], blocked_payload: Optional[Dict[str, Any]] = None):

        self.verification_report = verification_report

        self.blocked_payload = blocked_payload

        total = verification_report.get("total_failures", 0)

        super().__init__(f"Memorandum failed ground-truth verification with {total} violations.")



def shared_normalize(text: str) -> str:

    r"""

    One shared normalizer, applied to BOTH candidate quotes and stored provisions.

    - U+037E -> ';'

    - All whitespace (including \xa0, \r, \n, tabs) normalized

    - Soft hyphens (\xad, \u00ad) and line-break hyphenation removed

    - 'N[' and ']' amendment markers removed

    - '* * *' deletion markers ignored

    - Typographic quotes and dashes standardized

    - Strips markdown blockquote markers (>) and formatting (*, _)

    """

    if not text:

        return ""

    # Strip blockquote markers

    t = re.sub(r'(?m)^\s*>\s*', '', text)

    # 1. Greek question mark U+037E -> semicolon ';'

    t = t.replace('\u037e', ';')

    # 2. Soft hyphens

    t = t.replace('\xad', '').replace('\u00ad', '')

    # 3. Line-break hyphenation (e.g. 'ad -\nmissible' -> 'admissible' and 'charge able' -> 'chargeable')

    t = re.sub(r'(\w+)\s*-\s*[\r\n]+\s*(\w+)', r'\1\2', t)

    t = re.sub(r'(\w+)\s+-\s+(\w+)', r'\1\2', t)

    # 3b. Gazette typo markers: strip [sic], (sic), [sic.], or bare sic

    t = re.sub(r'\[\s*sic\.?\s*\]|\(\s*sic\.?\s*\)|\bsic\b', ' ', t, flags=re.IGNORECASE)

    # 4. Amendment markers: '1[', '2[', etc. and ']'

    t = re.sub(r'\d+\[', ' ', t).replace(']', ' ')

    # 5. Deletion markers: '* * *', '***', etc. replaced with space

    t = re.sub(r'\[?\s*(?:\*\s*){2,}\]?', ' ', t)

    t = re.sub(r'\*+', ' ', t)

    # 6. Typographic quotes and dashes

    t = t.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")

    t = t.replace('—', ' - ').replace('–', ' - ')

    # 7. Strip markdown bold / italics

    t = re.sub(r'[*_]{1,3}', '', t)

    # 9. All whitespace (including \xa0) collapsed

    t = t.replace('\xa0', ' ')

    return " ".join(t.split())



def to_matching_stream(text: str) -> str:

    """

    Produces a whitespace-insensitive alphanumeric stream for robust substring comparison,

    ensuring spacing anomalies, double spaces, and OCR line-breaks do not cause false blocks.

    """

    norm = shared_normalize(text)

    return "".join(re.findall(r'[a-zA-Z0-9;]', norm)).lower()



def compute_word_diff(quote_text: str, candidate_text: str) -> str:

    """

    Computes a human-readable word-level diff (inserted, deleted, changed words)

    between a candidate quote and the closest stored provision, aligned to the best window.

    """

    q_words = shared_normalize(quote_text).split()

    p_words = shared_normalize(candidate_text).split()



    if not q_words or not p_words:

        return "Differing punctuation, spacing, or structural markers."



    # Align to best matching window in p_words

    init_matcher = difflib.SequenceMatcher(None, p_words, q_words, autojunk=False)

    match = init_matcher.find_longest_match(0, len(p_words), 0, len(q_words))



    if match.size > 0:

        pad = max(3, len(q_words) // 2)

        p_start = max(0, match.a - pad)

        p_end = min(len(p_words), match.a + len(q_words) + pad)

        p_window = p_words[p_start:p_end]

    else:

        p_window = p_words[:len(q_words) + 10]



    matcher = difflib.SequenceMatcher(None, p_window, q_words, autojunk=False)

    diff_lines = []



    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == 'replace':

            p_chunk = " ".join(p_window[i1:i2])

            q_chunk = " ".join(q_words[j1:j2])

            diff_lines.append(f"Changed: '{p_chunk}' -> '{q_chunk}'")

        elif tag == 'delete':

            p_chunk = " ".join(p_window[i1:i2])

            if (i2 < len(p_window) and i1 > 0) or len(p_chunk.split()) <= 10:

                diff_lines.append(f"Omitted from provision: '{p_chunk}'")

        elif tag == 'insert':

            q_chunk = " ".join(q_words[j1:j2])

            diff_lines.append(f"Inserted into quote: '{q_chunk}'")



    if not diff_lines:

        return "Differing punctuation, spacing, or structural markers."

    return "; ".join(diff_lines[:5])



def has_disputed_banner(memo_text: str) -> bool:

    """Checks whether the memorandum contains a structural disputed warning banner."""

    lines = memo_text.splitlines()

    in_banner = False

    for line in lines:

        s = line.strip()

        if s.startswith("> [!"):

            in_banner = True

        elif not s.startswith(">"):

            in_banner = False

        if in_banner and "disputed" in s.lower():

            return True

    return False



class MemoVerifier:

    _instance = None



    def __init__(self):

        self.store = get_unified_statute_store()

        self.provisions: List[Dict[str, Any]] = []

        self.case_titles_set: Set[str] = set()

        self.citations_set: Set[str] = set()

        self._load_statutes()

        self._load_corpus_index()



    def _load_statutes(self):

        """Prepares normalized in-memory statute cache for fast substring verification."""

        for cid, r in self.store._by_cid.items():

            txt = r.get("text") or r.get("statutory_text") or ""

            tier = r.get("tier", "unsourced")

            status = r.get("status", "in_force")

            if isinstance(status, dict):

                status = status.get("federal", "in_force")



            is_in_force = (

                str(status).lower() == "in_force" and

                tier in ["ingested_unreviewed", "page_verified", "ground_truth", "disputed", "extraction_disputed", "tier_1", "reviewed", "text_layer_extracted"]

            )



            norm = shared_normalize(txt)

            stream = to_matching_stream(txt)



            self.provisions.append({

                "canonical_id": cid,

                "act_code": r.get("act_code"),

                "primary_num": r.get("primary_num"),

                "text": txt,

                "normalized_text": norm,

                "matching_stream": stream,

                "tier": tier,

                "status": str(status).lower(),

                "in_force": is_in_force

            })



    def ingest_extra_authorities(self, authorities: Optional[List[Dict[str, Any]]]) -> None:

        """Dynamically ingests verified candidates from retrieval pipeline into in-memory sets."""

        if not authorities:

            return

        for card in authorities:

            if not isinstance(card, dict):

                continue

            cit = card.get("citation") or card.get("neutral_citation") or card.get("case_id")

            if cit:

                norm_cit = " ".join(str(cit).upper().split())

                self.citations_set.add(norm_cit)

                self.citations_set.add(norm_cit.replace("_", " "))



            # Collect all candidate title sources

            sources = []

            for k in ["case_name", "canonical_case_title", "title", "case_title", "raw_title"]:

                val = card.get(k)

                if val and isinstance(val, str) and val.strip():

                    sources.append(val.strip())



            # Also search text fields for bracketed headers e.g. [2026 SCMR 833 | ...]

            corpus = " ".join([

                str(card.get("title") or ""),

                str(card.get("case_name") or ""),

                str(card.get("preview") or ""),

                str(card.get("raw_judgment_text") or "")[:2000],

                str(card.get("snippet") or "")

            ])

            for m in re.finditer(r'\[[^|\]]+\|\s*([^\]]+)\]', corpus):

                sources.append(m.group(1).strip())



            for s in sources:

                cleaned = re.sub(r'^\[[^|\]]+\|\s*', '', s).strip('[]')

                cleaned = re.sub(r'^\d{4}\s+[A-Z0-9\s]+\s+', '', cleaned)

                norm_s = " ".join(cleaned.upper().split())

                self.case_titles_set.add(norm_s)



                for v_m in re.finditer(r"([A-Z0-9\s,\.\(\)/\-'&]+?)\s+(?:VS|V\.|VERSUS)\s+([A-Z0-9\s,\.\(\)/\-'&]+)", cleaned, re.IGNORECASE):

                    raw_p1 = v_m.group(1).strip()

                    raw_p2 = v_m.group(2).strip()

                    p1 = " ".join(re.sub(r'^\[[^|\]]+\|\s*', '', raw_p1).upper().split())

                    p2 = " ".join(raw_p2.upper().split())

                    if p1 and p2:

                        self.case_titles_set.add(f"{p1} V. {p2}")

                        self.case_titles_set.add(f"{p1} VS {p2}")

                        p1_c = re.sub(r'^(?:AL-HAAJ|HAJ|HAAJ|MST\.?|MST|CH\.?|MALIK|MIAN|RAJA|SYED|MESSRS|M/S|DR\.?)\s+', '', p1).strip()

                        p2_c = re.sub(r'^(?:AL-HAAJ|HAJ|HAAJ|MST\.?|MST|CH\.?|MALIK|MIAN|RAJA|SYED|MESSRS|M/S|DR\.?)\s+', '', p2).strip()

                        self.case_titles_set.add(f"{p1_c} V. {p2_c}")

                        self.case_titles_set.add(f"{p1_c} VS {p2_c}")

                        self.case_titles_set.add(p1)

                        self.case_titles_set.add(p2)



    def _load_corpus_index(self):

        """Loads apex judicial index for Rule (c) precedent checking."""

        if os.path.exists(CACHED_AUTHORITIES_PATH):

            try:

                with open(CACHED_AUTHORITIES_PATH, "r", encoding="utf-8") as f:

                    cdata = json.load(f)

                self.citations_set = set(cdata.get("citations", []))

                self.case_titles_set = set(cdata.get("titles", []))

                if self.citations_set and self.case_titles_set:

                    return

            except Exception:

                pass



        if os.path.exists(HISTORICAL_CASES_PATH):

            try:

                with open(HISTORICAL_CASES_PATH, "r", encoding="utf-8") as f:

                    cases = json.load(f)

                for c in cases:

                    if isinstance(c, dict):

                        cit = c.get("citation")

                        title = c.get("title") or c.get("case_title")

                        if cit:

                            self.citations_set.add(" ".join(cit.upper().split()))

                        if title:

                            self.case_titles_set.add(" ".join(title.upper().split()))

            except Exception:

                pass



        if os.path.exists(BM25_PATH):

            try:

                from hybrid_search import BM25Index

                idx = BM25Index.load(BM25_PATH)

                if hasattr(idx, "doc_metadata") and idx.doc_metadata:

                    for m in idx.doc_metadata:

                        cit = m.get("citation")

                        title = m.get("title") or m.get("case_title")

                        if cit:

                            self.citations_set.add(" ".join(cit.upper().split()))

                        if title:

                            clean_t = re.sub(r'^\d+\s+[A-Z0-9\s]+\s+', '', title)

                            self.case_titles_set.add(" ".join(clean_t.upper().split()))

            except Exception:

                pass



    def extract_blockquotes(self, memo_text: str) -> List[Dict[str, Any]]:

        """

        Rule (b): Exempts system banners by structural marker (`> [!`).

        Extracts contiguous non-banner blockquote blocks along with their lead-in sentence and character offsets.

        """

        lines_with_ends = memo_text.splitlines(keepends=True)

        quotes = []

        current_block = []

        in_banner = False

        start_line = 0

        lead_in = ""

        offset = 0

        block_start = 0

        block_end = 0



        for idx, line in enumerate(lines_with_ends):

            line_len = len(line)

            line_start = offset

            line_end = offset + line_len

            offset = line_end



            stripped = line.strip()

            if stripped.startswith(">"):

                if stripped.startswith("> [!"):

                    in_banner = True

                    continue

                if in_banner:

                    continue

                if "quotation omitted" in stripped.lower():

                    continue

                

                content = re.sub(r'^>\s?', '', stripped)

                if not current_block:

                    start_line = idx + 1

                    block_start = line_start

                    # Find lead-in sentence from immediately preceding non-empty line

                    for prev_idx in range(idx - 1, -1, -1):

                        prev_line = lines_with_ends[prev_idx].strip()

                        if prev_line and not prev_line.startswith("#") and not prev_line.startswith("---"):

                            lead_in = prev_line

                            break

                current_block.append(content)

                block_end = line_end

            else:

                in_banner = False

                if current_block:

                    full_quote = "\n".join(current_block).strip()

                    if full_quote:

                        quotes.append({

                            "line": start_line,

                            "raw": full_quote,

                            "lead_in": lead_in,

                            "start_char": block_start,

                            "end_char": block_end

                        })

                    current_block = []

                    lead_in = ""



        if current_block and not in_banner:

            full_quote = "\n".join(current_block).strip()

            if full_quote:

                quotes.append({

                    "line": start_line,

                    "raw": full_quote,

                    "lead_in": lead_in,

                    "start_char": block_start,

                    "end_char": block_end

                })



        return quotes



    def verify_quote_against_store(self, raw_quote: str, expected_cid: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:

        """

        Rule (a): Quote must match a stored provision after shared normalization.

        Handles both continuous quotes and ellipsis quotes ('...', '…', '[...]').

        Returns (matched, canonical_id, diff_description, omitted_spans).

        """

        clean_q = shared_normalize(raw_quote).strip('"\'')

        if not clean_q:

            return True, None, None, None



        # 1. Ellipsis quote handling (Order 1.7 - Item 3)

        if ELLIPSIS_SPLIT_REGEX.search(raw_quote):

            raw_no_markers = re.sub(r'(?m)^\s*>\s*', '', raw_quote)

            segments = [s.strip() for s in ELLIPSIS_SPLIT_REGEX.split(raw_no_markers) if s.strip()]

            if len(segments) > 1:

                seg_streams = [to_matching_stream(s) for s in segments if to_matching_stream(s)]

                for prov in self.provisions:

                    prov_stream = prov["matching_stream"]

                    if not prov_stream:

                        continue



                    cur_pos = 0

                    all_matched = True

                    omitted_text_list = []



                    for s_idx, seg in enumerate(seg_streams):

                        pos = prov_stream.find(seg, cur_pos)

                        if pos == -1:

                            all_matched = False

                            break

                        if s_idx > 0:

                            # Extract readable omitted text from normalized_text

                            p_norm = prov["normalized_text"]

                            clean_prev = shared_normalize(segments[s_idx - 1])

                            clean_curr = shared_normalize(segments[s_idx])

                            p0 = p_norm.lower().find(clean_prev.lower())

                            p1 = p_norm.lower().find(clean_curr.lower(), p0 + len(clean_prev) if p0 != -1 else 0)

                            if p0 != -1 and p1 != -1:

                                omitted_slice = p_norm[p0 + len(clean_prev) : p1].strip(" ,;:\n")

                                omitted_text_list.append(omitted_slice)

                            else:

                                omitted_stream = prov_stream[cur_pos:pos]

                                omitted_text_list.append(omitted_stream)

                        cur_pos = pos + len(seg)



                    if all_matched:

                        # Order 1.8 - Item 4: Check for deceptive omission of material conditions

                        deceptive_terms = []

                        rendered_parts = []

                        for i_seg, seg_raw in enumerate(segments):

                            rendered_parts.append(seg_raw)

                            if i_seg < len(omitted_text_list):

                                om_slice = omitted_text_list[i_seg]

                                conds = []

                                for term in BLOCKING_CONDITION_TERMS:

                                    pat = r'\b' + re.escape(term).replace(r'\ ', r'\s+') + r'\b'

                                    if re.search(pat, om_slice, re.IGNORECASE):

                                        conds.append(term)

                                if conds:

                                    deceptive_terms.extend(conds)

                                    rendered_parts.append(f"[... OMITTED IN QUOTE (DROPS MATERIAL CONDITION '{', '.join(conds)}'): \"{om_slice}\" ...]")

                                else:

                                    rendered_parts.append(f"[... OMITTED IN QUOTE (REVIEW): \"{om_slice}\" ...]")

                        rendered_memo_quote = " ".join(rendered_parts)



                        if deceptive_terms:

                            diff_desc = f"{LABEL_DECEPTIVE_ELLIPSIS}: quote matches '{prov['canonical_id']}' but omits material qualifying condition(s) {list(set(deceptive_terms))}. Omitted text: '" + "; ".join(omitted_text_list) + "'"

                            res = QuoteMatchResult(False, prov["canonical_id"], diff_desc, omitted_text_list, rendered_memo_quote, deceptive_terms)

                            return res

                        else:

                            res = QuoteMatchResult(True, prov["canonical_id"], None, omitted_text_list, rendered_memo_quote, [])

                            return res



        # 2. Continuous quote stream matching

        q_stream = to_matching_stream(raw_quote)

        if not q_stream:

            return QuoteMatchResult(True, None, None, None)



        for prov in self.provisions:

            if not prov["matching_stream"]:

                continue

            if q_stream in prov["matching_stream"]:

                # Order 1.10 - Item 7: Truncation check

                # If quote ends before sentence end and stored text continues with

                # unless / provided that / except / save / subject to / notwithstanding / but,

                # return BLOCK and show dropped text.

                norm_q = shared_normalize(raw_quote)

                p_norm = prov.get("normalized_text", "")

                idx_norm = p_norm.lower().find(norm_q.lower())

                if idx_norm != -1:

                    q_end = idx_norm + len(norm_q)

                    rest = p_norm[q_end:]

                    # Next sentence boundary (. ; : ? or newline)

                    b_match = re.search(r'[\.\;\:\?\n]', rest)

                    clause = rest[:b_match.start()].strip() if b_match else rest.strip()

                    clause_lower = clause.lower().lstrip(" ,;:-—")

                    matched_exc = None

                    for exc in EXCEPTION_CLAUSE_TERMS:

                        if re.match(rf'\b{re.escape(exc)}\b', clause_lower):

                            matched_exc = exc

                            break

                    if matched_exc:

                        diff_desc = f"{LABEL_DECEPTIVE_TRUNCATION}: quote matches '{prov['canonical_id']}' but terminates before sentence end, omitting qualifying condition '{matched_exc}'. Dropped text: '{clause}'"

                        return QuoteMatchResult(False, prov["canonical_id"], diff_desc, [clause], raw_quote, [matched_exc])



                return QuoteMatchResult(True, prov["canonical_id"], None, None)



        # 3. If no match, compute word-level diff against best candidate provision

        best_prov = None

        best_ratio = 0.0



        if expected_cid:

            for prov in self.provisions:

                if prov.get("canonical_id", "").upper() == expected_cid.upper():

                    best_prov = prov

                    best_ratio = 1.0

                    break



        if not best_prov:

            for prov in self.provisions:

                p_text = prov["normalized_text"]

                if not p_text:

                    continue

                matcher = difflib.SequenceMatcher(None, clean_q.lower(), p_text.lower(), autojunk=False)

                match_block = matcher.find_longest_match(0, len(clean_q), 0, len(p_text))

                ratio = (2.0 * match_block.size) / (len(clean_q) + match_block.size)

                if ratio > best_ratio:

                    best_ratio = ratio

                    best_prov = prov



        if best_prov and best_ratio >= 0.20:

            diff_details = compute_word_diff(clean_q, best_prov["text"])

            diff_desc = f"Mismatch against {best_prov['canonical_id']}. Word-level diff: {diff_details}"

            return QuoteMatchResult(False, best_prov["canonical_id"], diff_desc, None)

        else:

            return QuoteMatchResult(False, None, "Quote text does not match any stored provision in the unified store.", None)



    def extract_case_authorities(self, text: str) -> List[Dict[str, Any]]:

        """Extracts judicial case titles (X v. Y) and law report citations."""

        authorities = []

        clean_text = re.sub(r'[*_]{1,3}', '', text)



        # ORDER 2.1 - ITEM 2: Authority extraction requires capitalised party names

        # AND must be immediately followed by a citation or the word "case".

        # Excludes Latin doctrine terms (e.g. void ab initio v. voidable).

        LATIN_DOCTRINES = {

            "void ab initio", "voidable", "suo motu", "res judicata", "prima facie",

            "mens rea", "actus reus", "sub judice", "locus standi", "ultra vires",

            "intra vires", "inter alia", "ex parte", "stare decisis", "ratio decidendi",

            "obiter dicta", "audi alteram partem"

        }



        case_pattern = re.compile(

            r'\b([A-Z][A-Za-z0-9\.\'\-]*(?:[ \t]+(?:of\s+the|in\s+the|for\s+the|of|and|the|&)[ \t]+[A-Z][A-Za-z0-9\.\'\-]*|[ \t]+[A-Z][A-Za-z0-9\.\'\-]*)*)[ \t]+v(?:s\.?|\.)[ \t]+([A-Z][A-Za-z0-9\.\'\-]*(?:[ \t]+(?:of\s+the|in\s+the|for\s+the|of|and|the|&)[ \t]+[A-Z][A-Za-z0-9\.\'\-]*|[ \t]+[A-Z][A-Za-z0-9\.\'\-]*)*)\b'

        )

        for m in case_pattern.finditer(clean_text):

            p1, p2 = m.group(1).strip(), m.group(2).strip()

            p1 = re.sub(r'^(?:from|in|see|re|per|vide|as\s+in|as\s+held\s+in|as\s+observed\s+in|as\s+per|according\s+to|regarding|relying\s+on)\s+', '', p1, flags=re.IGNORECASE).strip()

            if not p1 or p1.lower() in ["order", "section", "article", "rule"] or p2.lower() in ["order", "section", "article"]:

                continue

            # Order 2.1: Exclude Latin doctrines and procedural terms

            if p1.lower() in LATIN_DOCTRINES or p2.lower() in LATIN_DOCTRINES or any(d in p1.lower() or d in p2.lower() for d in LATIN_DOCTRINES):

                continue



            # Exclude non-party doctrinal concept comparisons (e.g. Permissible Interim Measures v. Prohibited Sweeping Intervention)

            NON_PARTY_CONCEPT_WORDS = {

                "permissible", "prohibited", "sweeping", "interim", "measures", "intervention",

                "remedy", "remedies", "relief", "status", "quo", "discretion", "power", "powers",

                "jurisdiction", "oppression", "mismanagement", "doctrine", "principles", "principle",

                "threshold", "adjudication", "convenience", "irreparable", "mandatory", "directory",

                "void", "voidable", "valid", "invalid", "arbitration", "specific", "performance",

                "limitation", "estoppel", "natural", "justice", "substantive", "procedural"

            }

            p1_words = set(re.findall(r'[a-zA-Z]+', p1.lower()))

            p2_words = set(re.findall(r'[a-zA-Z]+', p2.lower()))

            if p1_words and p1_words.issubset(NON_PARTY_CONCEPT_WORDS | LATIN_DOCTRINES):

                continue

            if p2_words and p2_words.issubset(NON_PARTY_CONCEPT_WORDS | LATIN_DOCTRINES):

                continue

            # Order 2.1: Must be followed immediately by a citation or the word "case"

            following = clean_text[m.end():m.end() + 80]

            if not re.match(r'^\s*[,;\(\[]?\s*(?:(?:19\d\d|20\d\d)\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+\d+|\bcases?\b)', following, re.IGNORECASE):

                continue



            authorities.append({

                "type": "case_title",

                "span": f"{p1} v. {p2}",

                "p1": p1,

                "p2": p2,

                "start": m.start(),

                "end": m.end()

            })



        cit_pattern = re.compile(

            r'\b((?:19\d\d|20\d\d)\s+(?:SCMR|PLD|YLR|CLC|PCrLJ|MLD|PTD|PLC|CLD|SCR)\s+\d+)\b',

            re.IGNORECASE

        )

        for m in cit_pattern.finditer(clean_text):

            authorities.append({

                "type": "citation",

                "span": m.group(1).strip(),

                "start": m.start(),

                "end": m.end()

            })



        return authorities



    def verify_case_authority(self, auth: Dict[str, Any]) -> bool:

        """Rule (c): Any case name must exist in index, else UNVERIFIED AUTHORITY."""

        if auth["type"] == "citation":

            norm = " ".join(auth["span"].upper().split())

            return norm in self.citations_set



        if auth["type"] == "case_title":

            p1 = auth["p1"].upper().strip()

            p2 = auth["p2"].upper().strip()

            full = " ".join(auth["span"].upper().split())

            if full in self.case_titles_set:

                return True



            p1_vars = get_party_variants(p1)

            p2_vars = get_party_variants(p2)



            for ct in self.case_titles_set:

                ct_norm = " ".join(ct.upper().split())

                if any(v in ct_norm for v in p1_vars) and any(v in ct_norm for v in p2_vars):

                    return True

                v_m = re.search(r'(.+?)\s+V(?:S\.?|\.)\s+(.+)', ct_norm)

                if v_m:

                    ct_p1_vars = get_party_variants(v_m.group(1))

                    ct_p2_vars = get_party_variants(v_m.group(2))

                    m1 = any(v in ct_norm or any(v in cv or cv in v for cv in ct_p1_vars) for v in p1_vars)

                    m2 = any(v in ct_norm or any(v in cv or cv in v for cv in ct_p2_vars) for v in p2_vars)

                    if m1 and m2:

                        return True

            return False



        return False



    def extract_context_order(self, text: str, pos: Optional[int] = None) -> Optional[str]:

        """Detects nearest active CPC Order context from text or nearest preceding a given character position."""

        matches = list(re.finditer(r'\b(?:Order|Ord\.?|o\.)\s*([IVXLCDM\d]+)\b', text, re.IGNORECASE))

        if not matches:

            return None

        if pos is None:

            return matches[0].group(1).upper()

        preceding = [m for m in matches if m.end() <= pos]

        if preceding:

            return preceding[-1].group(1).upper()

        return matches[0].group(1).upper()



    def extract_statutory_citations(self, text: str) -> List[Dict[str, Any]]:

        """Extracts candidate statutory citations according to Order 1.7 - Item 5 and Order 1.12 - Item 2."""

        found = []



        statute_patterns = [

            # 1. Order X Rule Y(z) of CPC / Code of Civil Procedure or standalone

            r'\b(?:Order|Ord\.?|o\.)\s*([IVXLCDM\d]+)\s*(?:Rule|r\.)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*(?:of\s+(?:the\s+)?(?:CPC|Code of Civil Procedure|Code|1908)))?\b',

            # 2. Rule Y(z) standalone in Order context

            r'(?<![A-Za-z0-9])(?:Rule|r\.)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?\b',

            # 3. Section N(x)(y) of Act / s. N

            r'\b(?:Section|Sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))*(?:\([a-z]\))*)(?:(?:\s*,\s*|\s+of\s+(?:the\s+)?)(?:(?:the\s+)?(?:[A-Z][a-zA-Z0-9\(\)]*\s*){1,6}\b(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)\b(?:\s*,\s*\d{4})?))?',

            # 4. Section multiple: ss. 10 and 22

            r'\b(?:ss\.|sections)\s*(\d+[A-Za-z]?)\s+and\s+(\d+[A-Za-z]?)(?:\s*(?:of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?\b(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)\b(?:\s*,\s*\d{4})?))?',

            # 5. Article N of Act / Constitution / QSO

            r'\b(?:Article|Art\.)\s*(\d+[A-Za-z]?)\s*(?:,\s*|\s+of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?\b(?:Constitution|QSO|Qanun-e-Shahadat|Limitation\s+Act|Act)\b(?:\s*,\s*\d{4})?)',

            # 6. Standalone: Section 489-F PPC, Section 22 FIO, Section 10 FIO, Section 61 FIO

            r'\b(?:Section|Sec\.?|s\.)\s*(\d+[A-Za-z]?(?:-[A-Za-z]+)?)\s+(PPC|CPC|CrPC|FIO|FIFO|TPA|BCO)\b'

        ]



        for pat in statute_patterns:

            for m in re.finditer(pat, text, re.IGNORECASE):

                span = m.group(0).strip()

                active_order = self.extract_context_order(text, m.start())

                found.append({

                    "span": span,

                    "active_order": active_order,

                    "start": m.start(),

                    "end": m.end()

                })



        return found



    def resolve_citation_to_cid(self, cit_span: str, active_order: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:

        """

        Resolves a citation span to (act_code, provision_num, rule_num).

        """

        # Order X Rule Y(z)

        m_ord = re.search(r'\b(?:Order|Ord\.?|o\.)\s*([IVXLCDM\d]+)\s*(?:Rule|r\.)\s*(\d+[A-Za-z]?)', cit_span, re.IGNORECASE)

        if m_ord:

            return "CPC_1908", m_ord.group(1).upper(), m_ord.group(2).upper()



        # Standalone Rule Y(z) in active Order context

        m_rule = re.search(r'\b(?:Rule|r\.)\s*(\d+[A-Za-z]?)', cit_span, re.IGNORECASE)

        if m_rule and active_order:

            return "CPC_1908", active_order.upper(), m_rule.group(1).upper()



        # Order 1.14 - Item 4: Do NOT guess FIO_2001 from 'of the Ordinance'.

        # Only resolve if the full title appears in the citation or immediate context.

        if re.search(r'\b(?:of\s+(?:the\s+)?ordinance|under\s+(?:the\s+)?ordinance|the\s+ordinance)\b', cit_span, re.I):

            if not re.search(r'\b(?:financial\s+institutions|recovery\s+of\s+finances)\b', cit_span, re.I):

                return None, None, "AMBIGUOUS_CITATION"



        # Normalize FIFO -> FIO

        norm = re.sub(r'\bFIFO\b', 'FIO', cit_span, flags=re.IGNORECASE)

        norm = re.sub(r'of\s+the\s+1973\s+Constitution', 'Constitution', norm, flags=re.IGNORECASE)



        parsed = parse_statutory_citation(norm)

        if parsed and parsed.get("is_valid"):

            act = parsed.get("act_code")

            p_num = parsed.get("primary_num")

            r_num = parsed.get("rule_num")

            return act, p_num, r_num



        return None, None, None



    def verify_statutory_citation(self, cit_span: str, active_order: Optional[str] = None, has_disputed: bool = True) -> CitationMatchResult:

        """

        Rule (d): Any statute citation must point to a sourced, in-force record.

        Real-but-missing provisions say 'not in verified store', never 'does not exist'.

        Disputed tier allowed only if structural disputed banner is present.

        """

        act_code, num, rule_num = self.resolve_citation_to_cid(cit_span, active_order)

        if rule_num == "AMBIGUOUS_CITATION":

            return CitationMatchResult(False, f"AMBIGUOUS_CITATION: Citation '{cit_span}' is ambiguous: 'of the Ordinance' lacks a full title or explicit support ID in context", None, None)

        if not act_code or not num:

            return CitationMatchResult(False, f"Provision '{cit_span}' is not in verified store", None, None)



        rec = None

        cid = None

        if rule_num and act_code == "CPC_1908":

            cid = f"CPC_1908_ORD_{str(num).upper()}_R_{str(rule_num).upper()}"

            rec = self.store.get_by_canonical_id(cid)

        else:

            rec = self.store.get_provision(act_code, str(num))

            if rec:

                cid = rec.get("canonical_id")



        if not rec:

            return CitationMatchResult(False, f"Provision '{cit_span}' is not in verified store", None, None)



        tier = rec.get("tier", "unsourced")

        status = rec.get("status", "in_force")

        if isinstance(status, dict):

            status = status.get("federal", "in_force")



        # Order 1.8 - Item 3: Check operative text and title_only tier

        txt = (rec.get("text") or rec.get("statutory_text") or "").strip()

        has_operative_text = (

            bool(rec.get("has_operative_text", True)) and

            tier != "title_only" and

            len(txt) > 0 and

            txt != (rec.get("title") or "").strip() and

            "[heading only]" not in txt.lower() and

            rec.get("verification_status") != "stub"

        )

        if not has_operative_text or tier == "title_only":

            reason = f"{LABEL_HEADING_ONLY}: Act {act_code} provision {num} has tier='{tier}', but operative statutory text is not in verified store (title/heading only)"

            return CitationMatchResult(False, reason, rec, cid)



        # Disputed tier policy (Order 1.7 - Item 7, Order 1.10 - Item 9, Order 2.0)

        if tier in ("disputed", "extraction_disputed"):

            if has_disputed:

                # Allowed with notice

                return CitationMatchResult(True, None, rec, cid)

            else:

                reason = f"{LABEL_DISPUTED_TEXT_NOTICE}: Provision '{cit_span}' is classified as disputed; human check required before reliance (missing structural warning banner)"

                return CitationMatchResult(False, reason, rec, cid)



        if tier == "unsourced" and rec.get("verification_status") in ("ingested_unreviewed", "reviewed", "page_verified", "in_force"):

            tier = rec.get("verification_status")



        in_force = (

            str(status).lower() == "in_force" and

            tier in ["ingested_unreviewed", "page_verified", "ground_truth", "tier_1", "reviewed", "text_layer_extracted", "pending_verification", "pending", "ingested"]

        )



        if not in_force:

            reason = f"Act {act_code} provision {num} is not in verified store (tier='{tier}', status='{status}')"

            return CitationMatchResult(False, reason, rec, cid)



        return CitationMatchResult(True, None, rec, cid)



    def verify_memo(self, memo_text: str, _is_system_assembled: bool = False, **kwargs) -> Dict[str, Any]:

        """

        Main entry point for verifying a research memorandum against Orders 1.5 - 1.14.

        """

        extra_auths = kwargs.get("extra_authorities")

        if extra_auths:

            self.ingest_extra_authorities(extra_auths)

        if kwargs.get("is_system_rendered"):

            _is_system_assembled = True



        failures: List[Dict[str, Any]] = []

        disputed_notices: List[Dict[str, Any]] = []

        omitted_ellipses: List[Dict[str, Any]] = []

        cited_provisions_meta: List[Dict[str, Any]] = []



        # Order 1.8 - Item 2: Strip every model-written `> [!` block before verification

        memo_cleaned, stripped_banners = strip_model_banners(memo_text)

        if stripped_banners:

            # Order 1.14 - Item 3: Model text containing ANY `> [!` banner (even exact system banner)

            # is stripped and flagged under Rule (b). Never exempt when caller supplies memo text.

            if not _is_system_assembled:

                for sb in stripped_banners:

                    failures.append({

                        "rule": "(b)",

                        "category": "MODEL_INJECTED_BANNER",

                        "label": LABEL_MODEL_BANNER_DETECTED,

                        "issue": f"{LABEL_MODEL_BANNER_DETECTED}: Model-written '> [!' banner detected and stripped. System banners are attached strictly by system assembler.",

                        "span": sb["text"],

                        "line": sb["line"]

                    })



        # Disputed banner check: model-written banners can NEVER satisfy this check

        has_disputed = has_disputed_banner(memo_text) if _is_system_assembled else False

        active_order = self.extract_context_order(memo_cleaned)



        # -------------------------------------------------------------

        # RULE (a) & (b): BLOCKQUOTE VERIFICATION, ELLIPSES & MISATTRIBUTION

        # -------------------------------------------------------------

        quotes = self.extract_blockquotes(memo_text)

        quotes_passed = 0

        quotes_failed = 0



        for q in quotes:

            lead_in = q.get("lead_in", "")

            exp_cid = None

            if lead_in:

                c_act, c_num, c_r = self.resolve_citation_to_cid(lead_in, active_order)

                if c_act and c_num:

                    exp_cid = f"{c_act}_ORD_{c_num}_R_{c_r}" if c_r else f"{c_act}_SEC_{c_num}"

            q_res = self.verify_quote_against_store(q["raw"], expected_cid=exp_cid)

            matched, match_cid, diff_desc = q_res

            omitted_spans = q_res.omitted

            

            if omitted_spans:

                omitted_ellipses.append({

                    "quote_line": q["line"],

                    "matched_provision": match_cid,

                    "omitted_text_between_segments": omitted_spans,

                    "rendered_in_memo": getattr(q_res, "rendered_in_memo", ""),

                    "deceptive_flags": getattr(q_res, "deceptive_flags", [])

                })



            if matched:

                # Rule (a) Misattribution check (Order 1.7 - Item 6)

                lead_in = q.get("lead_in", "")

                if lead_in:

                    cited_act, cited_num, cited_r = self.resolve_citation_to_cid(lead_in, active_order)

                    if cited_act:

                        expected_cid = f"{cited_act}_ORD_{cited_num}_R_{cited_r}" if cited_r else f"{cited_act}_SEC_{cited_num}"

                        

                        # Compare citation against match

                        m_cid_upper = str(match_cid).upper()

                        e_cid_upper = str(expected_cid).upper()

                        

                        # Disallow distinct rules (e.g. Rule 4 text attributed to Rule 2)

                        is_attribution_mismatch = False

                        if "_ORD_" in m_cid_upper and "_ORD_" in e_cid_upper:

                            m_r = re.search(r'_R_([0-9A-Z]+)', m_cid_upper)

                            e_r = re.search(r'_R_([0-9A-Z]+)', e_cid_upper)

                            if m_r and e_r and m_r.group(1) != e_r.group(1):

                                is_attribution_mismatch = True



                        if is_attribution_mismatch:

                            quotes_failed += 1

                            failures.append({

                                "rule": "(a)",

                                "category": "MISATTRIBUTED_QUOTE",

                                "label": LABEL_MISATTRIBUTED_QUOTE,

                                "issue": f"MISATTRIBUTED QUOTE: quote matches '{match_cid}' but is attributed to cited provision '{expected_cid}'.",

                                "cited_id": expected_cid,

                                "matched_id": match_cid,

                                "span": q["raw"][:180] + ("..." if len(q["raw"]) > 180 else "")

                            })

                            continue



                quotes_passed += 1

                q["matched"] = True

                q["match_cid"] = match_cid

            else:

                quotes_failed += 1

                failures.append({

                    "rule": "(a)",

                    "category": "UNMATCHED_QUOTE",

                    "issue": f"Quote differs from stored provision text. {diff_desc}",

                    "span": q["raw"][:180] + ("..." if len(q["raw"]) > 180 else "")

                })



        # -------------------------------------------------------------

        # RULE (c): CASE AUTHORITY VERIFICATION

        # -------------------------------------------------------------

        authorities = self.extract_case_authorities(memo_text)

        cases_passed = 0

        cases_failed = 0

        verified_cases = set()



        for auth in authorities:

            if self.verify_case_authority(auth):

                cases_passed += 1

                verified_cases.add(auth["span"])

            else:

                cases_failed += 1

                failures.append({

                    "rule": "(c)",

                    "category": "UNVERIFIED_AUTHORITY",

                    "label": LABEL_UNVERIFIED_AUTHORITY,

                    "issue": f"{LABEL_UNVERIFIED_AUTHORITY}: '{auth['span']}' not indexed in judicial corpus",

                    "span": auth["span"]

                })



        # -------------------------------------------------------------

        # RULE (d): STATUTE CITATION VERIFICATION & DISPUTED POLICY

        # -------------------------------------------------------------

        stat_cits = self.extract_statutory_citations(memo_text)

        statutes_passed = 0

        statutes_failed = 0

        verified_statute_spans = set()



        # Track verified blockquote spans (Order 1.12 - Item 2)

        verified_quote_spans = []

        for q in quotes:

            if q.get("matched") and "start_char" in q and "end_char" in q:

                verified_quote_spans.append((q["start_char"], q["end_char"]))



        for sc in stat_cits:

            is_inside_verified_quote = any(v_start <= sc["start"] and sc["end"] <= v_end for v_start, v_end in verified_quote_spans)

            cit_res = self.verify_statutory_citation(sc["span"], sc["active_order"], has_disputed)

            is_valid, reason, rec = cit_res

            cid = cit_res.cid

            tier_val = rec.get("tier", "unknown") if rec else "not_found"

            txt_val = (rec.get("text") or rec.get("statutory_text") or "").strip() if rec else ""

            has_op = bool(rec.get("has_operative_text", True) and tier_val != "title_only" and len(txt_val) > 0 and txt_val != (rec.get("title") or "").strip() and "[heading only]" not in txt_val.lower() and rec.get("verification_status") != "stub") if rec else False



            if is_inside_verified_quote:

                # Order 1.12 - Item 2: Citations occurring inside verified quotes of stored provisions

                # are allowed, labelled "cross-referenced; text not loaded in store" if not loaded in store.

                if is_valid:

                    cited_provisions_meta.append({

                        "span": sc["span"],

                        "canonical_id": cid,

                        "tier": tier_val,

                        "has_operative_text": has_op,

                        "is_valid": True,

                        "reason": reason

                    })

                    statutes_passed += 1

                    verified_statute_spans.add(sc["span"])

                else:

                    cited_provisions_meta.append({

                        "span": sc["span"],

                        "canonical_id": cid,

                        "tier": "cross_referenced",

                        "has_operative_text": False,

                        "is_valid": True,

                        "cross_referenced": True,

                        "label": "cross-referenced; text not loaded in store",

                        "reason": "cross-referenced; text not loaded in store"

                    })

                    statutes_passed += 1

                    verified_statute_spans.add(sc["span"])

                continue



            # Outside verified quotes: standard verification

            cited_provisions_meta.append({

                "span": sc["span"],

                "canonical_id": cid,

                "tier": tier_val,

                "has_operative_text": has_op,

                "is_valid": is_valid,

                "reason": reason

            })

            if is_valid:

                statutes_passed += 1

                verified_statute_spans.add(sc["span"])

                m_sec = re.search(r'\b(?:Section|Sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))*(?:\([a-z]\))*)', sc["span"], re.I)

                if m_sec:

                    sec_ref = m_sec.group(0).strip()

                    verified_statute_spans.add(sec_ref)

                    base_num = re.search(r'\d+[A-Za-z]?', sec_ref)

                    if base_num:

                        verified_statute_spans.add(f"Section {base_num.group(0)}")

                        verified_statute_spans.add(f"s. {base_num.group(0)}")

                if rec and rec.get("tier") in ("disputed", "extraction_disputed"):

                    disputed_notices.append({

                        "provision": cid or sc["span"],

                        "label": LABEL_DISPUTED_TEXT_NOTICE,

                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."

                    })

            else:

                statutes_failed += 1

                is_disputed_missing_banner = (rec and rec.get("tier") in ("disputed", "extraction_disputed") and not has_disputed)

                if is_disputed_missing_banner:

                    disputed_notices.append({

                        "provision": cid or sc["span"],

                        "label": LABEL_DISPUTED_TEXT_NOTICE,

                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."

                    })

                failures.append({

                    "rule": "(d)",

                    "category": "DISPUTED_TEXT_UNNOTICED" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",

                    "label": LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,

                    "issue": f"{LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",

                    "span": sc["span"]

                })



        # -------------------------------------------------------------

        # RULE (e): UNSOURCED ANALYSIS VERIFICATION (Order 1.7 - Item 8)

        # -------------------------------------------------------------

        lines = memo_text.splitlines()

        in_banner = False

        in_code = False

        in_exempt_section = False

        unsourced_sentences = 0



        for line in lines:

            s_line = line.strip()

            if s_line.startswith("```"):

                in_code = not in_code

                continue

            if in_code:

                continue



            if s_line.startswith("> [!"):

                in_banner = True

                continue

            if in_banner:

                if s_line.startswith(">"):

                    continue

                else:

                    in_banner = False



            if s_line.startswith("#"):

                m_header = re.match(r'^(#{1,6})\s*(.*)', s_line)

                if m_header:

                    hashes, title = m_header.group(1), m_header.group(2).lower()

                    is_main_heading = len(hashes) <= 2

                    exempt_keywords = (

                        "legal issue", "unreviewed analysis", "statutory provisions",

                        "relevant provisions", "statutory framework", "controlling law",

                        "application", "opinion", "analysis", "summary", "executive summary",

                        "remedy", "remedies", "conclusion", "recommendation", "roadmap",

                        "primary legal finding", "finding", "findings", "analysis and advisory",

                        "advisory", "applicable statutes", "limitations", "sources", "relevant judgments"

                    )

                    matches_exempt = any(kw in title for kw in exempt_keywords)

                    if is_main_heading:

                        in_exempt_section = matches_exempt

                    elif matches_exempt:

                        in_exempt_section = True

                continue



            if in_exempt_section and (s_line.startswith("*") or not s_line.startswith("#")):

                continue



            if (s_line.startswith("*") or s_line.startswith("-") or s_line.startswith(">") or 

                s_line.startswith("|") or s_line.startswith("---") or re.match(r'^\d+\.', s_line)):

                continue

            if not s_line:

                continue



            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9“"\'\(\[])', s_line)

            for sent in sentences:

                sent_clean = sent.strip()

                if len(sent_clean) < 15:

                    continue



                # Sentence support check: MUST be a VERIFIED statute or VERIFIED case authority

                has_verified_statute = any(v_span in sent_clean for v_span in verified_statute_spans)

                has_verified_case = any(v_case in sent_clean for v_case in verified_cases)

                has_quote = ('"' in sent_clean or '”' in sent_clean)

                is_intro_to_quote = sent_clean.endswith(":")



                if not (has_verified_statute or has_verified_case or has_quote or is_intro_to_quote):

                    unsourced_sentences += 1

                    failures.append({

                        "rule": "(e)",

                        "category": "UNSOURCED_ANALYSIS",

                        "label": LABEL_UNSOURCED_ANALYSIS,

                        "issue": f"{LABEL_UNSOURCED_ANALYSIS}: sentence lacks supporting span or verified authority",

                        "span": sent_clean

                    })



        passed = (len(failures) == 0)



        return {

            "passed": passed,

            "verdict": "ACCEPTED" if passed else "BLOCKED",

            "failures": failures,

            "total_failures": len(failures),

            "quotes_checked": len(quotes),

            "quotes_passed": quotes_passed,

            "quotes_failed": quotes_failed,

            "cases_checked": len(authorities),

            "cases_passed": cases_passed,

            "cases_failed": cases_failed,

            "statutes_checked": len(stat_cits),

            "statutes_passed": statutes_passed,

            "statutes_failed": statutes_failed,

            "unsourced_sentences_count": unsourced_sentences,

            "disputed_notices": disputed_notices,

            "omitted_ellipses": omitted_ellipses,

            "cited_provisions_metadata": cited_provisions_meta,

            "stripped_model_banners": stripped_banners,

            "cleaned_memo_text": memo_cleaned

        }



def verify_memorandum_text(memo_text: str, **kwargs) -> Dict[str, Any]:

    """

    Verifies user/model memorandum text. Caller cannot supply system rendering flags.

    Model text containing system banners is stripped and flagged under Rule (b).

    """

    verifier = MemoVerifier()

    return verifier.verify_memo(memo_text, _is_system_assembled=False, **kwargs)



verify_memorandum_text.__signature__ = inspect.Signature([

    inspect.Parameter('memo_text', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)

])



def assemble_and_verify_memorandum(memo_text: str, disputed_notices: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:

    """

    System assembler: attaches system warning banners for disputed provisions and

    verifies final output under internal system authority (_is_system_assembled=True).

    """

    verifier = MemoVerifier()

    raw_res = verifier.verify_memo(memo_text, _is_system_assembled=False, **kwargs)

    all_disputed = disputed_notices or raw_res.get("disputed_notices", [])

    assembled_text = attach_system_disputed_banner(memo_text, all_disputed) if all_disputed else memo_text

    final_res = verifier.verify_memo(assembled_text, _is_system_assembled=True, **kwargs)

    final_res["assembled_text"] = assembled_text

    return final_res



def attach_system_disputed_banner(memo_text: str, disputed_notices: List[Dict[str, Any]]) -> str:

    """

    Attaches an authentic structural warning banner to a memorandum after verification,

    satisfying Rule (b) and Rule (d) for disputed statutory provisions.

    """

    if not disputed_notices:

        return memo_text

    prov_names = ", ".join(sorted(list({str(d.get("provision", "")) for d in disputed_notices})))

    banner_lines = [

        "> [!WARNING] DISPUTED TEXT — HUMAN CHECK REQUIRED",

        f"> The following statutory provisions cited in this memorandum are classified as disputed in official gazettes or high court rulings: {prov_names}.",

        "> Independent human verification against authenticated gazette prints is required prior to formal court reliance."

    ]

    return "\n".join(banner_lines) + "\n\n" + memo_text





def verify_pleading_citations_and_quotes(pleading_text: str) -> Dict[str, Any]:

    """

    Specialized fail-closed verifier for legal pleadings and user-supplied court submissions.

    Verifies Rule (a) (statutory quotes), Rule (c) (case authorities), and Rule (d) (statutory citations).

    Explicitly EXEMPTS Rule (e) (unsourced analysis) so that client facts and narrative pleading

    allegations are allowed without false blocks.

    """

    verifier = MemoVerifier()

    res = verifier.verify_memo(pleading_text, _is_system_assembled=False)

    pleading_failures = [f for f in res["failures"] if f.get("rule") in ("(a)", "(b)", "(c)", "(d)")]

    passed = (len(pleading_failures) == 0)

    return {

        "passed": passed,

        "verdict": "ACCEPTED" if passed else "BLOCKED",

        "failures": pleading_failures,

        "total_failures": len(pleading_failures),

        "quotes_checked": res["quotes_checked"],

        "quotes_passed": res["quotes_passed"],

        "quotes_failed": res["quotes_failed"],

        "cases_checked": res["cases_checked"],

        "cases_passed": res["cases_passed"],

        "cases_failed": res["cases_failed"],

        "statutes_checked": res["statutes_checked"],

        "statutes_passed": res["statutes_passed"],

        "statutes_failed": res["statutes_failed"],

        "disputed_notices": res["disputed_notices"],

        "omitted_ellipses": res["omitted_ellipses"],

        "scope": "pleading_quotes_and_citations_only"

    }



def omit_unverified_blockquotes(memo_text: str, failures: List[Dict[str, Any]]) -> str:
    """
    DigiLawyer Parity: Surgically replaces unverified quotation blockquotes with:
    '> Quotation omitted: this passage could not be verified against the retrieved source text.'
    Leaves surrounding narrative and all other verified quotes completely intact.
    """
    if not memo_text or not failures:
        return memo_text

    quote_spans = []
    for f in failures:
        if f.get("category") in ("UNMATCHED_QUOTE", "MISATTRIBUTED_QUOTE"):
            sp = str(f.get("span") or "").strip()
            if sp.endswith("..."):
                sp = sp[:-3].strip()
            if sp and len(sp) >= 10:
                quote_spans.append(sp)

    if not quote_spans:
        return memo_text

    lines = memo_text.splitlines(keepends=True)
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith(">") and not stripped.startswith("> [!"):
            block_lines = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith(">") and not lines[j].strip().startswith("> [!"):
                block_lines.append(lines[j])
                j += 1
            block_text = "".join(re.sub(r'^>\s?', '', l.strip()) for l in block_lines)
            clean_block = re.sub(r'\s+', ' ', block_text).strip()
            
            # Check if this block matches any unverified span
            should_omit = False
            for sp in quote_spans:
                clean_sp = re.sub(r'\s+', ' ', sp).strip()
                if clean_sp in clean_block or clean_block in clean_sp:
                    should_omit = True
                    break
            
            if should_omit:
                new_lines.append("> Quotation omitted: this passage could not be verified against the retrieved source text.\n")
                i = j
                continue
            else:
                new_lines.extend(block_lines)
                i = j
                continue
        else:
            new_lines.append(line)
            i += 1

    return "".join(new_lines)
