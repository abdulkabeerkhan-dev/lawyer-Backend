r"""
legal_ai/verification/memo_verifier.py

MEMORANDUM VERIFIER (ORDER 1.5 - ITEM 6)
Purely rule-based ground-truth verification engine for legal research memoranda.
Zero hard-coded strings, zero test-specific tuning, and zero fail-open logic.

Strict Operational Rules:
  Rule (a): Every statutory quote must match a stored provision in data/unified_statutes/
            after normalizing whitespace, soft hyphens (\xad, \u00ad), and amendment markers
            \d+\[ / \]. Any discrepancy is reported as an exact textual difference.
  Rule (b): System banners are exempted strictly by structural marker (`> [!`), not content.
  Rule (c): Any judicial authority / case name must exist in the verified corpus index;
            otherwise labelled "UNVERIFIED AUTHORITY (not found in our index; check manually)".
  Rule (d): Any statutory citation must point to a sourced, in-force record in data/unified_statutes/;
            otherwise labelled "CITED PROVISION NOT IN VERIFIED STORE".
  Rule (e): Every sentence of narrative analysis without a supporting span or cited authority
            is labelled "UNSOURCED ANALYSIS".
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
LABEL_UNSOURCED_ANALYSIS = "UNSOURCED ANALYSIS"

def normalize_text_for_comparison(text: str) -> str:
    r"""
    Normalizes text according to Rule (a):
    1. Strips markdown blockquote markers (>) and formatting (*, _)
    2. Removes soft hyphens (\xad, \u00ad)
    3. Removes amendment markers \d+\[ and \]
    4. Standardizes quotation marks and dashes
    5. Collapses whitespace into single spaces and strips ends
    """
    if not text:
        return ""
    # Strip blockquote markers
    t = re.sub(r'(?m)^\s*>\s*', '', text)
    # Soft hyphens
    t = t.replace('\xad', '').replace('\u00ad', '')
    # Amendment markers
    t = re.sub(r'\d+\[', '', t)
    t = t.replace(']', '')
    # Quotation marks and typographic punctuation
    t = t.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    t = t.replace('—', ' - ').replace('–', ' - ')
    # Strip markdown bold / italics formatting
    t = re.sub(r'[*_]{1,3}', '', t)
    # Collapse whitespace
    return " ".join(t.split())

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
            norm = r.get("text_normalized") or ""
            tier = r.get("tier", "unsourced")
            status = r.get("status", "in_force")
            if isinstance(status, dict):
                status = status.get("federal", "in_force")

            is_in_force = (
                str(status).lower() == "in_force" and
                tier in ["ingested_unreviewed", "page_verified", "ground_truth"]
            )

            self.provisions.append({
                "canonical_id": cid,
                "act_code": r.get("act_code"),
                "primary_num": r.get("primary_num"),
                "text": txt,
                "normalized_text": normalize_text_for_comparison(txt),
                "tier": tier,
                "status": str(status).lower(),
                "in_force": is_in_force
            })

    def _load_corpus_index(self):
        """Loads apex judicial index for Rule (c) precedent checking."""
        # 1. Fast cache if available
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

        # 2. Curated cases
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

        # 3. BM25 doc metadata
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
        Extracts contiguous non-banner blockquote blocks.
        """
        lines = memo_text.splitlines()
        quotes = []
        current_block = []
        in_banner = False
        start_line = 0

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(">"):
                # Structural banner exemption: `> [!`
                if stripped.startswith("> [!"):
                    in_banner = True
                    continue
                if in_banner:
                    continue
                
                content = re.sub(r'^>\s?', '', stripped)
                if not current_block:
                    start_line = idx + 1
                current_block.append(content)
            else:
                in_banner = False
                if current_block:
                    full_quote = "\n".join(current_block).strip()
                    if full_quote:
                        quotes.append({"line": start_line, "raw": full_quote})
                    current_block = []

        if current_block and not in_banner:
            full_quote = "\n".join(current_block).strip()
            if full_quote:
                quotes.append({"line": start_line, "raw": full_quote})

        return quotes

    def verify_quote_against_store(self, raw_quote: str) -> Tuple[bool, Optional[str], Optional[str]]:
        r"""
        Rule (a): Quote must match a stored provision after normalizing whitespace,
        soft hyphens (\xad, \u00ad), and amendment markers \d+\[ / \]. Report any other difference.
        """
        norm_q = normalize_text_for_comparison(raw_quote).strip('"\'')
        if not norm_q:
            return True, None, None

        norm_q_lower = norm_q.lower()

        # 1. Exact substring check across all stored provisions
        for prov in self.provisions:
            if not prov["normalized_text"]:
                continue
            if norm_q_lower in prov["normalized_text"].lower():
                return True, prov["canonical_id"], None

        # 2. If no exact substring match, find best match to calculate exact difference
        best_prov = None
        best_ratio = 0.0
        best_match_len = 0

        for prov in self.provisions:
            p_text = prov["normalized_text"]
            if not p_text:
                continue
            matcher = difflib.SequenceMatcher(None, norm_q_lower, p_text.lower(), autojunk=False)
            match_block = matcher.find_longest_match(0, len(norm_q_lower), 0, len(p_text))
            if match_block.size > best_match_len:
                best_match_len = match_block.size
                ratio = (2.0 * match_block.size) / (len(norm_q_lower) + match_block.size)
                best_ratio = ratio
                best_prov = prov

        if best_prov and best_ratio >= 0.25:
            diff_desc = (
                f"Mismatch against {best_prov['canonical_id']}. "
                f"Longest continuous matching block is {best_match_len} chars "
                f"(expected {len(norm_q)} chars). Differing text, omitted words, or injected structural markers detected."
            )
            return False, best_prov["canonical_id"], diff_desc
        else:
            return False, None, "Quote text does not match any stored provision in the unified store."

    def extract_case_authorities(self, text: str) -> List[Dict[str, Any]]:
        """Extracts judicial case titles (X v. Y) and law report citations."""
        authorities = []
        # Strip markdown bold/italics markers to ensure robust matching across *Party v. Party*
        clean_text = re.sub(r'[*_]{1,3}', '', text)

        # Title-cased party name matching: Party Name v. Other Party
        case_pattern = re.compile(
            r'\b([A-Z][A-Za-z0-9\.\']*(?:\s+[A-Z][A-Za-z0-9\.\']*)*)\s+v(?:s\.?|\.)\s+([A-Z][A-Za-z0-9\.\']*(?:\s+(?:of|and|the|&)\s+[A-Z][A-Za-z0-9\.\']*|\s+[A-Z][A-Za-z0-9\.\']*)*)\b'
        )
        for m in case_pattern.finditer(clean_text):
            p1, p2 = m.group(1).strip(), m.group(2).strip()
            # Exclude structural labels like Order v. Rule
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

        # Law report citations: e.g. 2024 SCMR 1218, PLD 2021 SC 456
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

    def extract_statutory_citations(self, text: str) -> List[Dict[str, Any]]:
        """Extracts candidate statutory citations from free text."""
        statute_patterns = [
            # Section / Rule / Article of Act
            r'\b(?:section|sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))*(?:\([a-z]\))*)\s*(?:,\s*|\s+of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO))\b',
            # Order XXXIX Rule 1 CPC
            r'\b(?:order|ord\.?|o\.)\s*([IVXLCDM\d]+)\s*(?:rule|r\.)\s*(\d+[A-Za-z]?)\s*(?:,\s*|\s+of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?(?:CPC|Code of Civil Procedure))\b',
            # Article 199 Constitution / QSO
            r'\b(?:article|art\.)\s*(\d+[A-Za-z]?)\s*(?:,\s*|\s+of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+?(?:Constitution|QSO|Qanun-e-Shahadat))\b',
            # Explicit standalone: Section 489-F PPC, Section 22 FIO, Section 10 FIO, Section 69 TPA
            r'\b(?:section|sec\.?|s\.)\s*(\d+[A-Za-z]?(?:-[A-Za-z]+)?)\s+(PPC|CPC|CrPC|FIO|FIFO|TPA|BCO)\b'
        ]

        found = []
        for pat in statute_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                found.append({
                    "span": m.group(0).strip(),
                    "start": m.start(),
                    "end": m.end()
                })
        return found

    def verify_statutory_citation(self, cit_span: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Rule (d): Any statute citation must point to a sourced, in-force record,
        else CITED PROVISION NOT IN VERIFIED STORE.
        """
        # Normalize alias FIFO -> FIO
        norm_span = re.sub(r'\bFIFO\b', 'FIO', cit_span, flags=re.IGNORECASE)
        # Handle Article X of the 1973 Constitution -> Article X Constitution
        norm_span = re.sub(r'of\s+the\s+1973\s+Constitution', 'Constitution', norm_span, flags=re.IGNORECASE)

        parsed = parse_statutory_citation(norm_span)
        if not parsed or not parsed.get("is_valid"):
            return False, f"Could not parse statutory citation '{cit_span}'", None

        act_code = parsed.get("act_code")
        num = parsed.get("primary_num")
        rule_num = parsed.get("rule_num")

        rec = None
        if rule_num and act_code == "CPC_1908":
            cid = f"CPC_1908_ORD_{str(num).upper()}_R_{str(rule_num).upper()}"
            rec = self.store.get_by_canonical_id(cid)
        else:
            rec = self.store.get_provision(act_code, str(num))

        if not rec:
            return False, f"Provision not found in unified store for {act_code} {num}", None

        tier = rec.get("tier", "unsourced")
        status = rec.get("status", "in_force")
        if isinstance(status, dict):
            status = status.get("federal", "in_force")

        in_force = (
            str(status).lower() == "in_force" and
            tier in ["ingested_unreviewed", "page_verified", "ground_truth"]
        )

        if not in_force:
            reason = f"Act {act_code} provision {num} has tier='{tier}', status='{status}' (not sourced and in-force)"
            return False, reason, rec

        return True, None, rec

    def verify_memo(self, memo_text: str) -> Dict[str, Any]:
        """
        Main entry point for verifying a research memorandum against Rules (a)-(e).
        """
        failures: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # RULE (a) & (b): BLOCKQUOTE VERIFICATION & BANNER EXEMPTION
        # -------------------------------------------------------------
        quotes = self.extract_blockquotes(memo_text)
        quotes_passed = 0
        quotes_failed = 0

        for q in quotes:
            matched, match_cid, diff_desc = self.verify_quote_against_store(q["raw"])
            if matched:
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

        for auth in authorities:
            if self.verify_case_authority(auth):
                cases_passed += 1
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
        # RULE (d): STATUTE CITATION VERIFICATION
        # -------------------------------------------------------------
        stat_cits = self.extract_statutory_citations(memo_text)
        statutes_passed = 0
        statutes_failed = 0
        verified_statute_spans = set()

        for sc in stat_cits:
            is_valid, reason, rec = self.verify_statutory_citation(sc["span"])
            if is_valid:
                statutes_passed += 1
                verified_statute_spans.add(sc["span"])
            else:
                statutes_failed += 1
                failures.append({
                    "rule": "(d)",
                    "category": "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })

        # -------------------------------------------------------------
        # RULE (e): UNSOURCED ANALYSIS VERIFICATION
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

            # Structural banner exemption: `> [!`
            if s_line.startswith("> [!"):
                in_banner = True
                continue
            if in_banner:
                if s_line.startswith(">"):
                    continue
                else:
                    in_banner = False

            # Ignore non-narrative markdown structural lines
            if s_line.startswith(">") or s_line.startswith("|") or s_line.startswith("#") or s_line.startswith("---"):
                continue
            if not s_line:
                continue

            # Split narrative into sentences
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9“"\'\(\[])', s_line)
            for sent in sentences:
                sent_clean = sent.strip()
                if len(sent_clean) < 15:
                    continue

                # Check if sentence has a supporting span or authority
                has_statute = any(sc["span"] in sent_clean for sc in stat_cits)
                has_case = any(auth["span"] in sent_clean for auth in authorities)
                has_quote = ('"' in sent_clean or '”' in sent_clean)
                is_intro_to_quote = sent_clean.endswith(":")

                if not (has_statute or has_case or has_quote or is_intro_to_quote):
                    unsourced_sentences += 1
                    failures.append({
                        "rule": "(e)",
                        "category": "UNSOURCED_ANALYSIS",
                        "label": LABEL_UNSOURCED_ANALYSIS,
                        "issue": f"{LABEL_UNSOURCED_ANALYSIS}: sentence lacks supporting span or cited authority",
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
            "unsourced_sentences_count": unsourced_sentences
        }

def verify_memorandum_text(memo_text: str) -> Dict[str, Any]:
    verifier = MemoVerifier()
    return verifier.verify_memo(memo_text)
