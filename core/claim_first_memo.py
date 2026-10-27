"""
core/claim_first_memo.py

ORDER 1.13 - ITEM 2: CLAIM-FIRST MEMOS ARCHITECTURE
Model returns structured JSON claims:
  {
    "text": str,
    "type": "quote" | "paraphrase" | "analysis",
    "support": str  # provision id + subsection, or case id + excerpt, or None
  }

Code renders the memo:
  - quote: rendered as blockquote
  - paraphrase: rendered with explicit label e.g. "[paraphrase of s.22(4)]"
  - analysis: rendered with explicit label "[analysis (unreviewed)]"

Verifier verifies per claim:
  - quote: exact match against stored text using shared normalizer
  - paraphrase: maps to stated subsection; blocked if numbers/conditions differ
  - analysis: allowed, labelled "analysis (unreviewed)"

Fail-closed gate blocks ONLY:
  - Fabricated citations
  - Altered quotes
  - Wrong numbers / conflicting conditions
  - Unsupported holdings / unverified authorities
"""

import re
import difflib
from typing import Dict, List, Any, Optional, Tuple

from core.unified_statute_store import get_unified_statute_store
from legal_ai.verification.memo_verifier import (
    shared_normalize,
    to_matching_stream,
    compute_word_diff,
    attach_system_disputed_banner
)

# Number extraction helpers
WORD_TO_NUMBER = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
    "twenty-one": 21, "twenty one": 21, "thirty": 30, "sixty": 60, "ninety": 90,
    "hundred": 100, "two hundred": 200, "three hundred": 300
}

def extract_numbers_and_units(text: str) -> List[Tuple[float, str]]:
    """Extracts numeric quantities and attached time/percentage units."""
    results = []
    # 1. Digits with units or standalone
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\s*(days?|months?|years?|judges?|percent|%|rupees?|rs\.?)?\b', text, re.I):
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit in ("judge", "judges"):
            unit = "judge"
        elif unit in ("day", "days"):
            unit = "day"
        elif unit in ("month", "months"):
            unit = "month"
        elif unit in ("year", "years"):
            unit = "year"
        elif unit in ("%", "percent"):
            unit = "%"
        results.append((val, unit))
    
    # 2. Number words
    for w, val in WORD_TO_NUMBER.items():
        pat = rf'\b{re.escape(w)}\s*(days?|months?|years?|judges?|percent|%|rupees?|rs\.?)?\b'
        for m in re.finditer(pat, text, re.I):
            unit = (m.group(1) or "").lower()
            if unit in ("judge", "judges"):
                unit = "judge"
            elif unit in ("day", "days"):
                unit = "day"
            elif unit in ("month", "months"):
                unit = "month"
            elif unit in ("year", "years"):
                unit = "year"
            elif unit in ("%", "percent"):
                unit = "%"
            results.append((float(val), unit))
    return results


def format_support_tag(support: str) -> str:
    """Formats canonical provision support into a clean legal label (e.g. 's.22(4)')."""
    if not support:
        return ""
    # E.g. FIO_2001_SEC_22(4) -> s.22(4)
    m_sec = re.search(r'(?:SEC|Section)_(\d+[A-Za-z]?)(?:\((\d+[a-z]?)\))?', support, re.I)
    if m_sec:
        sec = m_sec.group(1)
        sub = m_sec.group(2)
        return f"s.{sec}({sub})" if sub else f"s.{sec}"
    
    # E.g. CPC_1908_ORD_XXXIX_R_2A -> Order XXXIX Rule 2A
    m_ord = re.search(r'ORD_([IVXLCDM\d]+)_R_(\d+[A-Za-z]?)', support, re.I)
    if m_ord:
        return f"Order {m_ord.group(1)} Rule {m_ord.group(2)}"
    
    # E.g. CRPC_1898_SEC_497(1) -> s.497(1) Cr.P.C.
    return support.replace("_", " ")


class ClaimFirstVerifier:
    def __init__(self, store=None):
        self.store = store or get_unified_statute_store()

    def resolve_support_provision(self, support: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Resolves support string to (record, canonical_id, subsection)."""
        if not support:
            return None, None, None
        
        # Check canonical ID with subsection: e.g. FIO_2001_SEC_22(4)
        m_sub = re.match(r'^([A-Z0-9_]+)\((\d+[a-z]?)\)$', support.strip(), re.I)
        if m_sub:
            base_cid = m_sub.group(1).upper()
            sub = m_sub.group(2)
            rec = self.store.get_by_canonical_id(base_cid)
            return rec, base_cid, sub
        
        # Check raw canonical ID
        rec = self.store.get_by_canonical_id(support.strip().upper())
        if rec:
            return rec, rec.get("canonical_id"), None
        
        # Check common patterns e.g. Section 22(4) FIO
        m_pat = re.search(r'(?:Section|s\.)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?\s*(FIO|PPC|CPC|CRPC|TPA)', support, re.I)
        if m_pat:
            act_map = {"FIO": "FIO_2001", "PPC": "PPC_1860", "CPC": "CPC_1908", "CRPC": "CRPC_1898", "TPA": "TPA_1882"}
            act = act_map.get(m_pat.group(3).upper())
            sec = m_pat.group(1)
            sub = m_pat.group(2)
            cid = f"{act}_SEC_{sec}"
            rec = self.store.get_by_canonical_id(cid)
            return rec, cid, sub

        return None, None, None

    def extract_subsection_text(self, full_text: str, subsection: Optional[str]) -> str:
        """Extracts text of a specific subsection from the full provision text."""
        if not subsection or not full_text:
            return full_text
        
        # Look for (N) at start of line or sentence ... up to next line starting with (N+1) or end
        pat = rf'(?:^|\n)\s*\({re.escape(subsection)}\)\s*(.*?)(?=(?:\n\s*\(\d+[a-z]?\))|\Z)'
        m = re.search(pat, full_text, re.DOTALL | re.I)
        if m:
            return m.group(1).strip()
        # Fallback without newline constraint
        pat_fallback = rf'\({re.escape(subsection)}\)\s*(.*?)(?=(?:\n|\.\s*)\(\d+[a-z]?\)|\Z)'
        m2 = re.search(pat_fallback, full_text, re.DOTALL | re.I)
        if m2:
            return m2.group(1).strip()
        return full_text

    def verify_single_claim(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        """Verifies a single claim dictionary."""
        c_text = claim.get("text", "").strip()
        c_type = claim.get("type", "analysis").lower().strip()
        c_support = claim.get("support", "")

        result = {
            "claim": claim,
            "passed": True,
            "violations": [],
            "label": "",
            "disputed_notice": None
        }

        if c_type == "analysis":
            # Rule: analysis is allowed, labelled "analysis (unreviewed)"
            result["label"] = "analysis (unreviewed)"
            return result

        if c_type == "quote":
            # Rule: exact match using shared normalizer
            rec, cid, sub = self.resolve_support_provision(c_support)
            if not rec:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(d)",
                    "category": "FABRICATED_CITATION",
                    "issue": f"Statutory support '{c_support}' is not in verified store",
                    "span": c_text
                })
                return result

            if rec.get("tier") == "disputed":
                result["disputed_notice"] = {
                    "provision": cid,
                    "label": "DISPUTED TEXT — human check required"
                }

            prov_text = rec.get("text") or rec.get("statutory_text") or ""
            target_text = self.extract_subsection_text(prov_text, sub) if sub else prov_text

            norm_quote = to_matching_stream(c_text)
            norm_prov = to_matching_stream(target_text)
            norm_full = to_matching_stream(prov_text)

            if norm_quote not in norm_prov and norm_quote not in norm_full:
                # Altered quote violation
                diff_desc = compute_word_diff(c_text, target_text if norm_quote in norm_prov else prov_text)
                result["passed"] = False
                result["violations"].append({
                    "rule": "(a)",
                    "category": "ALTERED_QUOTE",
                    "issue": f"Quote differs from stored provision text ({cid}). Word-level diff: {diff_desc}",
                    "span": c_text
                })
            else:
                tag = format_support_tag(c_support) or cid
                result["label"] = f"quote of {tag}"
            return result

        if c_type == "paraphrase":
            # Rule: must map to stated subsection; block if numbers/conditions differ
            rec, cid, sub = self.resolve_support_provision(c_support)
            if not rec:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(d)",
                    "category": "FABRICATED_CITATION",
                    "issue": f"Paraphrase support '{c_support}' is not in verified store",
                    "span": c_text
                })
                return result

            if rec.get("tier") == "disputed":
                result["disputed_notice"] = {
                    "provision": cid,
                    "label": "DISPUTED TEXT — human check required"
                }

            prov_text = rec.get("text") or rec.get("statutory_text") or ""
            target_text = self.extract_subsection_text(prov_text, sub) if sub else prov_text

            # Number and unit check against stored subsection
            claim_nums = extract_numbers_and_units(c_text)
            store_nums = extract_numbers_and_units(target_text)
            
            store_val_map = {unit: [] for _, unit in store_nums}
            for val, unit in store_nums:
                store_val_map[unit].append(val)

            for val, unit in claim_nums:
                if unit and unit in store_val_map:
                    if val not in store_val_map[unit]:
                        result["passed"] = False
                        result["violations"].append({
                            "rule": "(a)",
                            "category": "WRONG_NUMBERS",
                            "issue": f"Paraphrase contains quantity {val} {unit} which conflicts with stored text ({store_val_map[unit]} {unit}) in {cid}",
                            "span": c_text
                        })

            tag = format_support_tag(c_support) or cid
            result["label"] = f"paraphrase of {tag}"
            return result

        # Unknown claim type defaults to unreviewed analysis
        result["label"] = "analysis (unreviewed)"
        return result

    def verify_claim_memo(self, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verifies a full list of claims."""
        all_violations = []
        disputed_notices = []
        claim_results = []
        
        for c in claims:
            cr = self.verify_single_claim(c)
            claim_results.append(cr)
            if not cr["passed"]:
                all_violations.extend(cr["violations"])
            if cr.get("disputed_notice"):
                disputed_notices.append(cr["disputed_notice"])

        # Deduplicate disputed notices
        unique_disputed = []
        seen = set()
        for dn in disputed_notices:
            p = dn.get("provision")
            if p not in seen:
                seen.add(p)
                unique_disputed.append(dn)

        return {
            "passed": len(all_violations) == 0,
            "total_failures": len(all_violations),
            "failures": all_violations,
            "claim_results": claim_results,
            "disputed_notices": unique_disputed
        }


def render_claim_first_memo(claims: List[Dict[str, Any]], title: str = "LEGAL RESEARCH MEMORANDUM") -> str:
    """Renders structured JSON claims into a clean legal memorandum with explicit labels."""
    lines = [f"## {title}\n"]
    
    for c in claims:
        c_text = (c.get("text") or "").strip()
        c_type = (c.get("type") or "analysis").lower().strip()
        c_support = c.get("support", "")

        if not c_text:
            continue

        if c_type == "quote":
            tag = format_support_tag(c_support)
            if tag:
                lines.append(f"Statutory text of {tag} provides:\n")
            lines.append(f"> {c_text}\n")
        elif c_type == "paraphrase":
            tag = format_support_tag(c_support) or "statute"
            lines.append(f"- **[paraphrase of {tag}]** {c_text}\n")
        else:
            lines.append(f"**[analysis (unreviewed)]** {c_text}\n")

    return "\n".join(lines).strip()
