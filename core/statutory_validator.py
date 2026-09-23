"""
Statutory Citation Validator & Ground-Truth Registry Layer
Phase 2 Component: Prevents fabricated/hybrid statutory citations and verifies
every cited provision against official bare-act lookup tables.
"""

import os
import re
import json
from typing import Dict, List, Optional, Tuple, Any

# Path to statutory lookup tables
TABLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "statute_tables"))

# Act alias mapping to canonical act_codes
ACT_ALIASES = {
    # CPC
    "cpc": "CPC_1908",
    "c.p.c": "CPC_1908",
    "c.p.c.": "CPC_1908",
    "code of civil procedure": "CPC_1908",
    "civil procedure code": "CPC_1908",
    "cpc 1908": "CPC_1908",
    "cpc, 1908": "CPC_1908",

    # PPC
    "ppc": "PPC_1860",
    "p.p.c": "PPC_1860",
    "p.p.c.": "PPC_1860",
    "pakistan penal code": "PPC_1860",
    "penal code": "PPC_1860",
    "ppc 1860": "PPC_1860",
    "ppc, 1860": "PPC_1860",

    # CrPC
    "crpc": "CRPC_1898",
    "cr.pc": "CRPC_1898",
    "cr.p.c": "CRPC_1898",
    "cr.p.c.": "CRPC_1898",
    "code of criminal procedure": "CRPC_1898",
    "criminal procedure code": "CRPC_1898",
    "crpc 1898": "CRPC_1898",
    "crpc, 1898": "CRPC_1898",

    # Constitution
    "constitution": "CONST_1973",
    "constitution of pakistan": "CONST_1973",
    "pakistan constitution": "CONST_1973",
    "constitution 1973": "CONST_1973",
    "constitution, 1973": "CONST_1973",
    "const": "CONST_1973",
    "const.": "CONST_1973",

    # QSO
    "qso": "QSO_1984",
    "q.s.o": "QSO_1984",
    "q.s.o.": "QSO_1984",
    "qanun-e-shahadat": "QSO_1984",
    "qanun-e-shahadat order": "QSO_1984",
    "qanun e shahadat": "QSO_1984",
    "qso 1984": "QSO_1984",
    "qso, 1984": "QSO_1984",
    "evidence act": "QSO_1984",
    "evidence act 1872": "QSO_1984",

    # Limitation Act
    "limitation act": "LIMITATION_1908",
    "limitation act 1908": "LIMITATION_1908",
    "limitation act, 1908": "LIMITATION_1908",
    "the limitation act": "LIMITATION_1908",

    # Doctrinal statutes
    "mflo": "MFLO_1961",
    "muslim family laws ordinance": "MFLO_1961",
    "muslim family laws ordinance 1961": "MFLO_1961",
    "mflo 1961": "MFLO_1961",

    "family courts act": "FAMILY_COURTS_1964",
    "family court act": "FAMILY_COURTS_1964",
    "family courts act 1964": "FAMILY_COURTS_1964",
    "the family courts act, 1964": "FAMILY_COURTS_1964",

    "dmma": "DMMA_1939",
    "dissolution of muslim marriages act": "DMMA_1939",
    "dissolution of muslim marriages act 1939": "DMMA_1939",
    "dmma 1939": "DMMA_1939",

    "cnsa": "CNSA_1997",
    "control of narcotic substances act": "CNSA_1997",
    "control of narcotic substances act 1997": "CNSA_1997",
    "cnsa 1997": "CNSA_1997",

    "prpa": "PRPA_2009",
    "punjab rented premises act": "PRPA_2009",
    "punjab rented premises act 2009": "PRPA_2009",
    "prpa 2009": "PRPA_2009",

    "punjab pre-emption act": "PREEMPTION_1991",
    "punjab pre-emption act 1991": "PREEMPTION_1991",
    "punjab preemption act": "PREEMPTION_1991",
    "pre-emption act": "PREEMPTION_1991",
    "preemption act": "PREEMPTION_1991"
}

# Roman to Integer mapping
ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
    "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25, "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
    "XXXI": 31, "XXXII": 32, "XXXIII": 33, "XXXIV": 34, "XXXV": 35, "XXXVI": 36, "XXXVII": 37, "XXXVIII": 38, "XXXIX": 39, "XL": 40,
    "XLI": 41, "XLII": 42, "XLIII": 43, "XLIV": 44, "XLV": 45, "XLVI": 46, "XLVII": 47, "XLVIII": 48, "XLIX": 49, "L": 50,
    "LI": 51
}

INT_TO_ROMAN = {v: k for k, v in ROMAN_TO_INT.items()}


def normalize_roman(val: str) -> str:
    """Convert Arabic integer string or Roman numeral to normalized Roman numeral."""
    val_clean = str(val).strip().upper()
    if val_clean in ROMAN_TO_INT:
        return val_clean
    if val_clean.isdigit():
        num = int(val_clean)
        return INT_TO_ROMAN.get(num, val_clean)
    return val_clean


class GroundTruthStatuteRegistry:
    """In-memory cache and query interface for official bare-act lookup tables."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GroundTruthStatuteRegistry, cls).__new__(cls)
            cls._instance._loaded = False
            cls._instance._by_canonical_id = {}
            cls._instance._by_act = {}
        return cls._instance

    def ensure_loaded(self):
        if self._loaded:
            return

        if not os.path.exists(TABLES_DIR):
            return

        for fname in os.listdir(TABLES_DIR):
            if fname.endswith(".json"):
                act_code = fname[:-5]
                filepath = os.path.join(TABLES_DIR, fname)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                    self._by_act[act_code] = entries
                    for e in entries:
                        cid = e.get("canonical_id")
                        if cid:
                            self._by_canonical_id[cid] = e
                except Exception as exc:
                    print(f"[StatuteRegistry] Warning loading {fname}: {exc}")

        self._loaded = True

    def get_by_canonical_id(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_loaded()
        return self._by_canonical_id.get(canonical_id)

    def get_act_entries(self, act_code: str) -> List[Dict[str, Any]]:
        self.ensure_loaded()
        return self._by_act.get(act_code, [])

    def has_act(self, act_code: str) -> bool:
        self.ensure_loaded()
        return act_code in self._by_act


def generate_canonical_id(act_code: str, primary_num: str, 
                            subsection: str = None, clause: str = None,
                            rule_num: str = None, sub_rule: str = None,
                            provision_type: str = "section") -> str:
    """
    Deterministic canonical_id generator per Phase 2 spec.
    Structural distinction:
      subsection = numbered, nested directly under section (e.g. 12(2))
      clause     = lettered, nested under a subsection or section (e.g. 302(b), 22-A(6)(a))
      rule       = only applies to Order/Rule provisions (CPC First Schedule)
      sub_rule   = numbered, nested under a rule (e.g. Order XXXIX Rule 1(2))
    """
    parts = [act_code]

    if rule_num is not None:
        # Order/Rule track (CPC procedural)
        parts += ["ORD", normalize_roman(primary_num), "R", str(rule_num)]
        if sub_rule:
            parts += ["SR", str(sub_rule)]
    else:
        # Section/Article track (substantive)
        prefix = "ART" if (act_code in ("CONST_1973", "QSO_1984") or provision_type == "article") else "SEC"
        norm_primary = str(primary_num).upper().replace("-", "").replace(" ", "")
        parts += [prefix, norm_primary]
        if subsection:
            parts += [str(subsection)]
        if clause:
            parts += [str(clause).upper()]

    return "_".join(parts)


def check_hybrid_hallucination(text: str) -> Optional[Dict[str, Any]]:
    """
    Upstream check: Detects if a citation conflates substantive sections with procedural Orders/Rules
    (e.g., 'Section 12(2) Order XXI CPC', 'Order XXI Section 12(2)', 'Section 12(2) of Order XXI').
    """
    lower = text.lower()
    
    # 1. Direct co-occurrence of "Section ... Order ..." or "Order ... Section ..."
    has_sec = bool(re.search(r'\b(?:sec|section|s\.)\s*\d+', lower))
    has_ord = bool(re.search(r'\b(?:order|ord|o\.)\s*(?:[ivxlcdm]+|\d+)', lower))
    has_rule = bool(re.search(r'\b(?:rule|r\.)\s*\d+', lower))

    # CPC hybrid signature: combining Section with Order or Rule in the same citation clause
    if has_sec and (has_ord or has_rule):
        # Check if they are part of the same phrase
        hybrid_patterns = [
            r'section\s*[\d\(\)a-zA-Z\-]+\s*(?:of\s+)?order\s*[ivxlcdm\d]+',
            r'order\s*[ivxlcdm\d]+\s*(?:rule\s*\d+\s*)?(?:of\s+)?section\s*[\d\(\)a-zA-Z\-]+',
            r'section\s*12\s*\(\s*2\s*\)\s*order\s*[ivxlcdm\d]+',
            r'section\s*[\d\(\)a-zA-Z\-]+\s*rule\s*\d+'
        ]
        for pat in hybrid_patterns:
            if re.search(pat, lower):
                return {
                    "is_valid": False,
                    "status": "hybrid_hallucination",
                    "raw_citation": text,
                    "message": f"Statutory citation '{text}' is a hybrid hallucination. It conflates a substantive Section with a procedural Order/Rule, which do not exist as a single provision in the Code of Civil Procedure, 1908."
                }

    return None


def parse_statutory_citation(text: str) -> Dict[str, Any]:
    """
    Parses a raw citation string into structured components:
    {
       'act_code': str,
       'provision_type': 'section' | 'order_rule' | 'article',
       'primary_num': str,
       'subsection': Optional[str],
       'clause': Optional[str],
       'rule_num': Optional[str],
       'sub_rule': Optional[str],
       'is_hybrid': bool
    }
    """
    # Check upstream hybrid hallucination first
    hybrid_check = check_hybrid_hallucination(text)
    if hybrid_check:
        return hybrid_check

    clean_text = text.strip()

    # Identify act code
    act_code = None
    lower_text = clean_text.lower()
    for alias, code in sorted(ACT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf'\b{re.escape(alias)}\b', lower_text):
            act_code = code
            break

    # If no act identified, check for default cues
    if not act_code:
        if "order" in lower_text and ("rule" in lower_text or "cpc" in lower_text):
            act_code = "CPC_1908"
        elif "article" in lower_text:
            if "constitution" in lower_text or "1973" in lower_text:
                act_code = "CONST_1973"
            elif "qso" in lower_text or "shahadat" in lower_text:
                act_code = "QSO_1984"
            else:
                act_code = "CONST_1973"

    # Default fallback to CPC_1908 if Order/Rule is present
    if not act_code and re.search(r'\border\s+[ivxlcdm\d]+', lower_text):
        act_code = "CPC_1908"

    # 1. Parse Order/Rule track
    ord_match = re.search(
        r'\b(?:order|ord\.?|o\.?)\s*([ivxlcdm]+|\d+)\s*(?:rule|r\.?)\s*(\d+)(?:\s*\(\s*(\d+)\s*\))?',
        clean_text, re.IGNORECASE
    )
    if ord_match:
        ord_num = ord_match.group(1).upper()
        rule_num = ord_match.group(2)
        sub_rule = ord_match.group(3) if ord_match.group(3) else None
        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": act_code or "CPC_1908",
            "provision_type": "order_rule",
            "primary_num": normalize_roman(ord_num),
            "subsection": None,
            "clause": None,
            "rule_num": rule_num,
            "sub_rule": sub_rule,
            "raw_citation": text
        }

    # 2. Parse Article track (Constitution, QSO, Limitation Schedule)
    art_match = re.search(
        r'\b(?:article|art\.?)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?',
        clean_text, re.IGNORECASE
    )
    if art_match:
        primary_num = art_match.group(1).upper()
        sub = art_match.group(2)
        cl = art_match.group(3)
        resolved_act = act_code or ("LIMITATION_1908" if "limitation" in lower_text else "CONST_1973")
        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": resolved_act,
            "provision_type": "article",
            "primary_num": primary_num,
            "subsection": sub,
            "clause": cl,
            "rule_num": None,
            "sub_rule": None,
            "raw_citation": text
        }

    # 3. Parse Section track (CPC substantive, PPC, CrPC, etc.)
    # Handles 12(2), 302(b), 22-A(6)(a), 489-F, 9(c), etc.
    sec_match = re.search(
        r'\b(?:section|sec\.?|s\.?)\s*(\d+(?:-[A-Za-z]+|[A-Za-z])?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?',
        clean_text, re.IGNORECASE
    )
    if not sec_match:
        # Bare section or clause, e.g. "302(b)", "489-F"
        sec_match = re.search(
            r'\b(\d+(?:-[A-Za-z]+|[A-Za-z])?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))',
            clean_text, re.IGNORECASE
        )

    if sec_match:
        raw_prim = sec_match.group(1).upper().replace("-", "")
        # Distinguish: if only group 2 is letter e.g. 302(b), that is clause, not subsection
        g2 = sec_match.group(2)
        g3 = sec_match.group(3)

        sub = None
        cl = None

        if g2 and g2.isdigit():
            sub = g2
            if g3:
                cl = g3
        elif g2 and g2.isalpha():
            cl = g2
        elif g3:
            cl = g3

        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": act_code or "CPC_1908",
            "provision_type": "section",
            "primary_num": raw_prim,
            "subsection": sub,
            "clause": cl,
            "rule_num": None,
            "sub_rule": None,
            "raw_citation": text
        }

    return {
        "is_valid": False,
        "status": "unparseable",
        "raw_citation": text,
        "message": f"Could not parse statutory citation structure from '{text}'."
    }


def validate_statutory_citation(citation: str, default_act: str = None) -> Dict[str, Any]:
    """
    Validates a statutory citation string against the ground-truth lookup registry.
    Performs upstream hybrid rejection, canonical ID generation, and exact registry check.
    """
    registry = GroundTruthStatuteRegistry()
    registry.ensure_loaded()

    # Upstream hybrid check
    hybrid = check_hybrid_hallucination(citation)
    if hybrid:
        return hybrid

    parsed = parse_statutory_citation(citation)
    if not parsed.get("is_valid"):
        return parsed

    act_code = parsed.get("act_code") or default_act
    if not act_code:
        return {
            "is_valid": False,
            "status": "missing_act",
            "raw_citation": citation,
            "message": f"Could not determine statute for citation '{citation}'."
        }

    canonical_id = generate_canonical_id(
        act_code=act_code,
        primary_num=parsed["primary_num"],
        subsection=parsed.get("subsection"),
        clause=parsed.get("clause"),
        rule_num=parsed.get("rule_num"),
        sub_rule=parsed.get("sub_rule"),
        provision_type=parsed.get("provision_type", "section")
    )

    record = registry.get_by_canonical_id(canonical_id)
    if record:
        return {
            "is_valid": True,
            "status": "verified",
            "canonical_id": canonical_id,
            "display_name": record.get("display_name"),
            "title": record.get("title"),
            "status_jurisdiction": record.get("status"),
            "superseded_reference": record.get("superseded_reference"),
            "source_citation": record.get("source_citation"),
            "raw_citation": citation
        }

    # If canonical ID not found, check if base primary exists (e.g. Section 12 exists, but subsection 99 does not)
    base_id = generate_canonical_id(
        act_code=act_code,
        primary_num=parsed["primary_num"],
        rule_num=parsed.get("rule_num"),
        provision_type=parsed.get("provision_type", "section")
    )
    base_record = registry.get_by_canonical_id(base_id)

    if base_record:
        return {
            "is_valid": False,
            "status": "unverified_sub_provision",
            "canonical_id": canonical_id,
            "base_provision": base_record.get("display_name"),
            "raw_citation": citation,
            "message": f"The base provision '{base_record.get('display_name')}' exists, but specific sub-provision ({parsed.get('subsection') or parsed.get('clause') or parsed.get('sub_rule')}) could not be verified in official text."
        }

    return {
        "is_valid": False,
        "status": "unverified_provision",
        "canonical_id": canonical_id,
        "raw_citation": citation,
        "message": f"Provision with Canonical ID '{canonical_id}' does not exist in verified statutory lookup tables."
    }


def validate_citations_in_text(text: str) -> Dict[str, Any]:
    """
    Scans free-text content (e.g. LLM synthesis or draft pleading), validates all statutory
    citations, and flags hallucinations or unverified provisions with a deterministic banner.
    """
    # Regex to find candidate statutory references in text
    citation_patterns = [
        # Hybrid patterns
        r'\b(?:section|sec\.?)\s*\d+[\(\)\w\-]*\s*(?:of\s+)?(?:order|ord\.?)\s*[ivxlcdm\d]+(?:\s*(?:rule|r\.?)\s*\d+)?(?:\s*cpc)?\b',
        # Order / Rule
        r'\b(?:order|ord\.?|o\.?)\s*[ivxlcdm\d]+\s*(?:rule|r\.?)\s*\d+(?:\s*\(\s*\d+\s*\))?(?:\s*(?:of\s+the\s+)?cpc)?\b',
        # Article
        r'\b(?:article|art\.?)\s*\d+[a-zA-Z]?(?:\s*\(\s*\d+\s*\))?(?:\s*\(\s*[a-zA-Z]\s*\))?(?:\s*(?:of\s+the\s+)?(?:constitution|qso))?\b',
        # Section with Act
        r'\b(?:section|sec\.?|s\.?)\s*\d+(?:-[A-Za-z]+|[A-Za-z])?(?:\s*\(\s*\d+\s*\))?(?:\s*\(\s*[a-zA-Z]\s*\))?(?:\s*(?:of\s+the\s+)?(?:cpc|ppc|crpc|cnsa|prpa|mflo|limitation\s+act))?\b'
    ]

    all_matches = set()
    for cp in citation_patterns:
        for m in re.finditer(cp, text, re.IGNORECASE):
            match_str = m.group(0).strip()
            # Filter trivial noise
            if len(match_str) > 4:
                all_matches.add(match_str)

    results = []
    hybrids = []
    unverified = []
    verified = []

    for cit in sorted(all_matches):
        res = validate_statutory_citation(cit)
        results.append(res)
        if res.get("status") == "hybrid_hallucination":
            hybrids.append(res)
        elif res.get("status") == "verified":
            verified.append(res)
        elif not res.get("is_valid"):
            unverified.append(res)

    warning_banner = None
    if hybrids or unverified:
        lines = ["⚠️ **Statutory Citation Notice**: The following cited provision(s) could not be verified against official bare acts:"]
        for h in hybrids:
            lines.append(f"- **{h['raw_citation']}**: Conflates substantive section with procedural order (invalid hybrid citation).")
        for u in unverified:
            lines.append(f"- **{u['raw_citation']}**: {u.get('message', 'Provision unverified.')}")
        warning_banner = "\n".join(lines)

    return {
        "verified_count": len(verified),
        "hybrid_count": len(hybrids),
        "unverified_count": len(unverified),
        "verified": verified,
        "hybrids": hybrids,
        "unverified": unverified,
        "warning_banner": warning_banner
    }
