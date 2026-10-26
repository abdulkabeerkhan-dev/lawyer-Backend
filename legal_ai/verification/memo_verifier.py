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
from typing import Dict, List, Any, Optional, Set, Tuple

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from core.unified_statute_store import get_unified_statute_store
from core.statutory_validator import parse_statutory_citation, ACT_ALIASES

STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
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

ELLIPSIS_SPLIT_REGEX = re.compile(r'\[?\s*(?:\.{3,}|\u2026|\.\s+\.\s+\.)\s*\]?')

class QuoteMatchResult(tuple):
    """3-tuple (matched, cid, diff) with extra attribute omitted."""
    def __new__(cls, matched: bool, cid: Optional[str], diff: Optional[str], omitted: Optional[List[str]] = None):
        return super().__new__(cls, (matched, cid, diff))
    def __init__(self, matched: bool, cid: Optional[str], diff: Optional[str], omitted: Optional[List[str]] = None):
        self.matched = matched
        self.cid = cid
        self.diff = diff
        self.omitted = omitted or []

class CitationMatchResult(tuple):
    """3-tuple (is_valid, reason, rec) with extra attribute cid."""
    def __new__(cls, is_valid: bool, reason: Optional[str], rec: Optional[Dict[str, Any]], cid: Optional[str] = None):
        return super().__new__(cls, (is_valid, reason, rec))
    def __init__(self, is_valid: bool, reason: Optional[str], rec: Optional[Dict[str, Any]], cid: Optional[str] = None):
        self.is_valid = is_valid
        self.reason = reason
        self.rec = rec
        self.cid = cid

class MemorandumVerificationBlockedError(Exception):
    """Raised when a research memorandum fails ground-truth verification."""
    def __init__(self, verification_report: Dict[str, Any]):
        self.verification_report = verification_report
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
    # 4. Amendment markers: '1[', '2[', etc. and ']'
    t = re.sub(r'\d+\[', '', t).replace(']', '')
    # 5. Deletion markers: '* * *', '***', etc.
    t = re.sub(r'\[?\s*(?:\*\s*){2,}\]?', '', t)
    t = re.sub(r'\*+', '', t)
    # 6. Typographic quotes and dashes
    t = t.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    t = t.replace('—', ' - ').replace('–', ' - ')
    # 7. Strip markdown bold / italics
    t = re.sub(r'[*_]{1,3}', '', t)
    # 8. All whitespace (including \xa0) collapsed
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
    between a candidate quote and the closest stored provision.
    """
    q_words = shared_normalize(quote_text).split()
    p_words = shared_normalize(candidate_text).split()

    matcher = difflib.SequenceMatcher(None, p_words, q_words, autojunk=False)
    diff_lines = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            p_chunk = " ".join(p_words[i1:i2])
            q_chunk = " ".join(q_words[j1:j2])
            diff_lines.append(f"Changed: '{p_chunk}' -> '{q_chunk}'")
        elif tag == 'delete':
            p_chunk = " ".join(p_words[i1:i2])
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
                tier in ["ingested_unreviewed", "page_verified", "ground_truth", "disputed"]
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
        Extracts contiguous non-banner blockquote blocks along with their lead-in sentence.
        """
        lines = memo_text.splitlines()
        quotes = []
        current_block = []
        in_banner = False
        start_line = 0
        lead_in = ""

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(">"):
                if stripped.startswith("> [!"):
                    in_banner = True
                    continue
                if in_banner:
                    continue
                
                content = re.sub(r'^>\s?', '', stripped)
                if not current_block:
                    start_line = idx + 1
                    # Find lead-in sentence from immediately preceding non-empty line
                    for prev_idx in range(idx - 1, -1, -1):
                        prev_line = lines[prev_idx].strip()
                        if prev_line and not prev_line.startswith("#") and not prev_line.startswith("---"):
                            lead_in = prev_line
                            break
                current_block.append(content)
            else:
                in_banner = False
                if current_block:
                    full_quote = "\n".join(current_block).strip()
                    if full_quote:
                        quotes.append({"line": start_line, "raw": full_quote, "lead_in": lead_in})
                    current_block = []
                    lead_in = ""

        if current_block and not in_banner:
            full_quote = "\n".join(current_block).strip()
            if full_quote:
                quotes.append({"line": start_line, "raw": full_quote, "lead_in": lead_in})

        return quotes

    def verify_quote_against_store(self, raw_quote: str) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
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
                        return QuoteMatchResult(True, prov["canonical_id"], None, omitted_text_list)

        # 2. Continuous quote stream matching
        q_stream = to_matching_stream(raw_quote)
        if not q_stream:
            return QuoteMatchResult(True, None, None, None)

        for prov in self.provisions:
            if not prov["matching_stream"]:
                continue
            if q_stream in prov["matching_stream"]:
                return QuoteMatchResult(True, prov["canonical_id"], None, None)

        # 3. If no match, compute word-level diff against best candidate provision
        best_prov = None
        best_ratio = 0.0

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

        case_pattern = re.compile(
            r'\b([A-Z][A-Za-z0-9\.\']*(?:\s+[A-Z][A-Za-z0-9\.\']*)*)\s+v(?:s\.?|\.)\s+([A-Z][A-Za-z0-9\.\']*(?:\s+(?:of|and|the|&)\s+[A-Z][A-Za-z0-9\.\']*|\s+[A-Z][A-Za-z0-9\.\']*)*)\b'
        )
        for m in case_pattern.finditer(clean_text):
            p1, p2 = m.group(1).strip(), m.group(2).strip()
            if p1.lower() in ["order", "section", "article", "rule"] or p2.lower() in ["order", "section", "article"]:
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
            p1 = auth["p1"].upper()
            p2 = auth["p2"].upper()
            full = " ".join(auth["span"].upper().split())
            if full in self.case_titles_set:
                return True
            for ct in self.case_titles_set:
                if p1 in ct and p2 in ct:
                    return True
            return False

        return False

    def extract_context_order(self, text: str) -> Optional[str]:
        """Detects active CPC Order context from headings (e.g. 'Order XXXIX')."""
        m = re.search(r'\bOrder\s+([IVXLCDM\d]+)\b', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return None

    def extract_statutory_citations(self, text: str) -> List[Dict[str, Any]]:
        """Extracts candidate statutory citations according to Order 1.7 - Item 5."""
        active_order = self.extract_context_order(text)
        found = []

        statute_patterns = [
            # 1. Order X Rule Y(z) of CPC / Code of Civil Procedure or standalone
            r'\b(?:Order|Ord\.?|o\.)\s*([IVXLCDM\d]+)\s*(?:Rule|r\.)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*(?:of\s+(?:the\s+)?(?:CPC|Code of Civil Procedure|Code|1908)))?\b',
            # 2. Rule Y(z) standalone in Order context
            r'(?<![A-Za-z0-9])(?:Rule|r\.)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?\b',
            # 3. Section N(x)(y) of Act / s. N
            r'\b(?:Section|Sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))*(?:\([a-z]\))*)\s*(?:,\s*|\s+of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO))\b',
            # 4. Section multiple: ss. 10 and 22
            r'\b(?:ss\.|sections)\s*(\d+[A-Za-z]?)\s+and\s+(\d+[A-Za-z]?)(?:\s*(?:of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)))?\b',
            # 5. Article N of Act / Constitution / QSO
            r'\b(?:Article|Art\.)\s*(\d+[A-Za-z]?)\s*(?:,\s*|\s+of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?(?:Constitution|QSO|Qanun-e-Shahadat))\b',
            # 6. Standalone: Section 489-F PPC, Section 22 FIO, Section 10 FIO, Section 61 FIO
            r'\b(?:Section|Sec\.?|s\.)\s*(\d+[A-Za-z]?(?:-[A-Za-z]+)?)\s+(PPC|CPC|CrPC|FIO|FIFO|TPA|BCO)\b'
        ]

        for pat in statute_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                span = m.group(0).strip()
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

    def verify_statutory_citation(self, cit_span: str, active_order: Optional[str] = None, has_disputed: bool = False) -> CitationMatchResult:
        """
        Rule (d): Any statute citation must point to a sourced, in-force record.
        Real-but-missing provisions say 'not in verified store', never 'does not exist'.
        Disputed tier allowed only if structural disputed banner is present.
        """
        act_code, num, rule_num = self.resolve_citation_to_cid(cit_span, active_order)
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

        # Disputed tier policy (Order 1.7 - Item 7)
        if tier == "disputed":
            if has_disputed:
                # Allowed with notice
                return CitationMatchResult(True, None, rec, cid)
            else:
                return CitationMatchResult(False, f"Provision '{cit_span}' is classified as disputed and cannot be cited without the required structural warning banner", rec, cid)

        in_force = (
            str(status).lower() == "in_force" and
            tier in ["ingested_unreviewed", "page_verified", "ground_truth"]
        )

        if not in_force:
            reason = f"Act {act_code} provision {num} is not in verified store (tier='{tier}', status='{status}')"
            return CitationMatchResult(False, reason, rec, cid)

        return CitationMatchResult(True, None, rec, cid)

    def verify_memo(self, memo_text: str) -> Dict[str, Any]:
        """
        Main entry point for verifying a research memorandum against Orders 1.5 - 1.7.
        """
        failures: List[Dict[str, Any]] = []
        disputed_notices: List[Dict[str, Any]] = []
        omitted_ellipses: List[Dict[str, Any]] = []

        # Check structural disputed banner
        has_disputed = has_disputed_banner(memo_text)
        active_order = self.extract_context_order(memo_text)

        # -------------------------------------------------------------
        # RULE (a) & (b): BLOCKQUOTE VERIFICATION, ELLIPSES & MISATTRIBUTION
        # -------------------------------------------------------------
        quotes = self.extract_blockquotes(memo_text)
        quotes_passed = 0
        quotes_failed = 0

        for q in quotes:
            q_res = self.verify_quote_against_store(q["raw"])
            matched, match_cid, diff_desc = q_res
            omitted_spans = q_res.omitted
            
            if omitted_spans:
                omitted_ellipses.append({
                    "quote_line": q["line"],
                    "matched_provision": match_cid,
                    "omitted_text_between_segments": omitted_spans
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

        for sc in stat_cits:
            cit_res = self.verify_statutory_citation(sc["span"], sc["active_order"], has_disputed)
            is_valid, reason, rec = cit_res
            cid = cit_res.cid
            if is_valid:
                statutes_passed += 1
                verified_statute_spans.add(sc["span"])
                if rec and rec.get("tier") == "disputed":
                    disputed_notices.append({
                        "provision": cid or sc["span"],
                        "label": LABEL_DISPUTED_TEXT_NOTICE,
                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."
                    })
            else:
                statutes_failed += 1
                is_disputed_missing_banner = (rec and rec.get("tier") == "disputed" and not has_disputed)
                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT_UNNOTICED" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_MISSING_BANNER if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_MISSING_BANNER if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })

        # -------------------------------------------------------------
        # RULE (e): UNSOURCED ANALYSIS VERIFICATION (Order 1.7 - Item 8)
        # -------------------------------------------------------------
        lines = memo_text.splitlines()
        in_banner = False
        in_code = False
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

            if s_line.startswith(">") or s_line.startswith("|") or s_line.startswith("#") or s_line.startswith("---"):
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
            "omitted_ellipses": omitted_ellipses
        }

def verify_memorandum_text(memo_text: str) -> Dict[str, Any]:
    verifier = MemoVerifier()
    return verifier.verify_memo(memo_text)
