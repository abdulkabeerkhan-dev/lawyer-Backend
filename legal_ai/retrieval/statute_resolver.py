"""
legal_ai/retrieval/statute_resolver.py

Universal Canonical Statute ID Resolver.
Resolves any raw citation variant to its canonical provision ID.
STRICT RULE: Performs syntax normalization ONLY. Zero cross-statute rewrites.

Handles:
- Trailing noise words: CONSTITUTIONAL, PENAL, CIVIL, CRIMINAL, REVISIONAL, SUIT
- CPC Orders & Rules: CPC_1908_O_VII_R_11, CPC_1908_O_7_R_11 -> CPC_1908_ORD_VII_R_11
- SEC vs ART swaps: CONST_1973_SEC_199 -> CONST_1973_ART_199 (same act only)
- Letter suffix rule: NNNX is a lettered section only if ACT_SEC_NNNX (or hyphen/underscore variant)
  exists in staging. Otherwise maps to parent section NNN with clause x (e.g. 302B -> PPC s.302 clause b).
- Concatenated digits rule: 4972 resolves to 497(2) only if ACT_SEC_4972 does not exist
  AND ACT_SEC_497 exists (flagged as low confidence).
- Sub-clauses: FIO_2001_SEC_2_G -> FIO_2001_SEC_2_g
"""

import os
import re
import json
from pathlib import Path
from typing import Optional, Set, Dict, Any, Union

# Roman numeral conversions for CPC Orders
INT_TO_ROMAN = {
    1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X',
    11: 'XI', 12: 'XII', 13: 'XIII', 14: 'XIV', 15: 'XV', 16: 'XVI', 17: 'XVII', 18: 'XVIII', 19: 'XIX', 20: 'XX',
    21: 'XXI', 22: 'XXII', 23: 'XXIII', 24: 'XXIV', 25: 'XXV', 26: 'XXVI', 27: 'XXVII', 28: 'XXVIII', 29: 'XXIX', 30: 'XXX',
    31: 'XXXI', 32: 'XXXII', 33: 'XXXIII', 34: 'XXXIV', 35: 'XXXV', 36: 'XXXVI', 37: 'XXXVII', 38: 'XXXVIII', 39: 'XXXIX', 40: 'XL',
    41: 'XLI', 42: 'XLII', 43: 'XLIII', 44: 'XLIV', 45: 'XLV', 46: 'XLVI', 47: 'XLVII', 48: 'XLVIII', 49: 'XLIX', 50: 'L'
}
ROMAN_TO_INT = {v: k for k, v in INT_TO_ROMAN.items()}

ARTICLE_ACTS = {'CONST_1973', 'QSO_1984', 'LIMITATION_1908'}

_CANONICAL_SET: Optional[Set[str]] = None

def _get_canonical_set() -> Set[str]:
    global _CANONICAL_SET
    if _CANONICAL_SET is not None:
        return _CANONICAL_SET

    c_set = set()
    base_dir = Path(__file__).resolve().parent.parent.parent
    staging_dir = base_dir / "data" / "statutes_v3_staging"
    if staging_dir.exists():
        for f in staging_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    recs = json.load(fp)
                    if isinstance(recs, list):
                        for r in recs:
                            cid = r.get("canonical_id")
                            if cid:
                                c_set.add(cid.upper())
            except Exception:
                pass
    _CANONICAL_SET = c_set
    return _CANONICAL_SET


def resolve_statute_id(raw: str, return_meta: bool = False) -> Union[Optional[str], Optional[Dict[str, Any]]]:
    """
    Resolves raw citation input to canonical ID or returns None if unresolvable.
    Strictly syntax normalization within the cited act. Zero cross-statute changes.
    
    If return_meta=True, returns dict with:
      canonical_id: str
      clause: Optional[str]
      sub_section: Optional[str]
      confidence: "high" | "low"
    """
    if not raw or not isinstance(raw, str):
        return None

    cid = re.sub(r'[\s\.\-]+', '_', raw.strip().upper()).strip('_')
    # If CPC without 1908
    if cid.startswith("CPC_O") or cid.startswith("CPC_ORD"):
        cid = "CPC_1908" + cid[3:]

    c_set = _get_canonical_set()

    if cid in c_set:
        if return_meta:
            return {"canonical_id": cid, "confidence": "high", "clause": None, "sub_section": None}
        return cid

    # 1. Strip trailing noise words (e.g. CONSTITUTIONAL, PENAL, CIVIL, REVISIONAL, SUIT)
    clean_noise = re.sub(
        r'_(CONSTITUTIONAL|PENAL|CIVIL|CRIMINAL|GENERAL|SPECIAL|ACT|ORD|ORDER|REVISIONAL|SUIT)$',
        '',
        cid
    )
    clean_noise = re.sub(
        r'(CONSTITUTIONAL|PENAL|CIVIL|CRIMINAL|GENERAL|SPECIAL|ACT|ORD|ORDER|REVISIONAL|SUIT)$',
        '',
        clean_noise
    ).rstrip('_')

    if clean_noise in c_set:
        if return_meta:
            return {"canonical_id": clean_noise, "confidence": "high", "clause": None, "sub_section": None}
        return clean_noise

    # 2. CPC Orders & Rules: CPC_1908_O_VII_R_11, CPC_1908_ORDER_7_RULE_11 -> CPC_1908_ORD_VII_R_11
    m_cpc = re.match(r'^CPC_1908_O(?:RD|RDER)?_([0-9IVXLCDM]+)_R(?:ULE)?_([0-9A-Z]+)$', clean_noise)
    if m_cpc:
        ord_val = m_cpc.group(1)
        r_val = m_cpc.group(2)
        ord_roman = INT_TO_ROMAN.get(int(ord_val), ord_val) if ord_val.isdigit() else ord_val
        cand = f"CPC_1908_ORD_{ord_roman}_R_{r_val}"
        if cand in c_set:
            if return_meta:
                return {"canonical_id": cand, "confidence": "high", "clause": None, "sub_section": None}
            return cand

    # 3. SEC vs ART swaps (e.g. CONST_1973_SEC_199 -> CONST_1973_ART_199) - within the SAME act
    for art_act in ARTICLE_ACTS:
        if clean_noise.startswith(f"{art_act}_SEC_"):
            swapped = clean_noise.replace(f"{art_act}_SEC_", f"{art_act}_ART_")
            if swapped in c_set:
                if return_meta:
                    return {"canonical_id": swapped, "confidence": "high", "clause": None, "sub_section": None}
                return swapped
        elif clean_noise.startswith(f"{art_act}_ART_"):
            swapped = clean_noise.replace(f"{art_act}_ART_", f"{art_act}_SEC_")
            if swapped in c_set:
                if return_meta:
                    return {"canonical_id": swapped, "confidence": "high", "clause": None, "sub_section": None}
                return swapped

    # 4. Normalize hyphenated/bracketed lettered sections: 382-B, 382_B, 382(B) -> 382B / 382-B / 382_B
    m_hyphen = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)[\-_]?\(?([A-Z])\)?$', clean_noise)
    if m_hyphen:
        act = m_hyphen.group(1)
        prefix = m_hyphen.group(2)
        num = m_hyphen.group(3)
        letter = m_hyphen.group(4)
        
        cand_direct = f"{act}_{prefix}_{num}{letter}"
        cand_hyphen = f"{act}_{prefix}_{num}-{letter}"
        cand_underscore = f"{act}_{prefix}_{num}_{letter}"
        for cand in [cand_direct, cand_hyphen, cand_underscore]:
            if cand in c_set:
                if return_meta:
                    return {"canonical_id": cand, "confidence": "high", "clause": None, "sub_section": None}
                return cand

        # Try prefix swap for article acts
        if act in ARTICLE_ACTS:
            swap_prefix = "ART" if prefix == "SEC" else "SEC"
            for cand in [f"{act}_{swap_prefix}_{num}{letter}", f"{act}_{swap_prefix}_{num}-{letter}", f"{act}_{swap_prefix}_{num}_{letter}"]:
                if cand in c_set:
                    if return_meta:
                        return {"canonical_id": cand, "confidence": "high", "clause": None, "sub_section": None}
                    return cand

    # 5. Letter suffix rule: NNNX is a lettered section only if ACT_SEC_NNNX (or -X / _X) exists in staging.
    # Otherwise map to parent section NNN with clause x (e.g. 302B -> PPC s.302 clause b; CNSA 9C -> s.9 clause c)
    m_letter = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)([A-Z])$', clean_noise)
    if m_letter:
        act = m_letter.group(1)
        prefix = m_letter.group(2)
        num = m_letter.group(3)
        letter = m_letter.group(4)

        cand_direct = f"{act}_{prefix}_{num}{letter}"
        cand_hyphen = f"{act}_{prefix}_{num}-{letter}"
        cand_underscore = f"{act}_{prefix}_{num}_{letter}"
        for cand in [cand_direct, cand_hyphen, cand_underscore]:
            if cand in c_set:
                if return_meta:
                    return {"canonical_id": cand, "confidence": "high", "clause": None, "sub_section": None}
                return cand
        
        # Parent section check:
        cand_parent = f"{act}_{prefix}_{num}"
        if cand_parent in c_set:
            if return_meta:
                return {"canonical_id": cand_parent, "clause": letter.lower(), "sub_section": None, "confidence": "high"}
            return cand_parent

        # Try prefix swap for parent (e.g. CONST_1973_SEC_199A -> ART_199)
        if act in ARTICLE_ACTS and prefix == "SEC":
            cand_parent_art = f"{act}_ART_{num}"
            if cand_parent_art in c_set:
                if return_meta:
                    return {"canonical_id": cand_parent_art, "clause": letter.lower(), "sub_section": None, "confidence": "high"}
                return cand_parent_art

    # 6. Definition sub-clauses: FIO_2001_SEC_2_G -> FIO_2001_SEC_2_g
    m_sub = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)_([A-Z])$', clean_noise)
    if m_sub:
        act = m_sub.group(1)
        prefix = m_sub.group(2)
        num = m_sub.group(3)
        letter = m_sub.group(4)
        
        cand_lower = f"{act}_{prefix}_{num}_{letter.lower()}"
        if cand_lower in c_set:
            if return_meta:
                return {"canonical_id": cand_lower, "confidence": "high", "clause": None, "sub_section": None}
            return cand_lower
        
        for cand in [f"{act}_{prefix}_{num}{letter}", f"{act}_{prefix}_{num}-{letter}", f"{act}_{prefix}_{num}_{letter}"]:
            if cand in c_set:
                if return_meta:
                    return {"canonical_id": cand, "confidence": "high", "clause": None, "sub_section": None}
                return cand

        cand_parent = f"{act}_{prefix}_{num}"
        if cand_parent in c_set:
            if return_meta:
                return {"canonical_id": cand_parent, "clause": letter.lower(), "sub_section": None, "confidence": "high"}
            return cand_parent

    # 7. Concatenated digits rule (e.g. 4972 -> 497(2), 3402 -> 340(2)):
    # 4-digit number: 3-digit parent + 1 sub-section digit.
    # Resolve to parent section only if full number does NOT exist AND parent section DOES exist.
    # Flagged as low confidence.
    m_digits = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d{3})(\d)$', clean_noise)
    if m_digits:
        act = m_digits.group(1)
        prefix = m_digits.group(2)
        parent_num = m_digits.group(3)
        sub_digit = m_digits.group(4)
        
        full_cand = f"{act}_{prefix}_{parent_num}{sub_digit}"
        if full_cand not in c_set:
            cand_parent = f"{act}_{prefix}_{parent_num}"
            if cand_parent in c_set:
                if return_meta:
                    return {"canonical_id": cand_parent, "clause": None, "sub_section": sub_digit, "confidence": "low"}
                return cand_parent
            if act in ARTICLE_ACTS and prefix == "SEC":
                cand_parent_art = f"{act}_ART_{parent_num}"
                if cand_parent_art in c_set:
                    if return_meta:
                        return {"canonical_id": cand_parent_art, "clause": None, "sub_section": sub_digit, "confidence": "low"}
                    return cand_parent_art

    return None
