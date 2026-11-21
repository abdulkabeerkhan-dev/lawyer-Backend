import json
import re
from pathlib import Path

# Load all canonical IDs currently in staging + legacy
staging_dir = Path("data/statutes_v3_staging")
ALL_CANONICAL_IDS = set()

for p in staging_dir.glob("*.json"):
    with open(p, "r", encoding="utf-8") as f:
        recs = json.load(f)
    if isinstance(recs, list):
        for r in recs:
            ALL_CANONICAL_IDS.add(r["canonical_id"])

print(f"Total Canonical IDs loaded: {len(ALL_CANONICAL_IDS):,}")

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

def resolve_statute_id(raw: str) -> str:
    """
    Robust resolver accepting any raw citation variant and returning canonical ID or None.
    Handles:
    - Trailing noise (CONSTITUTIONAL, PENAL, CIVIL)
    - Lettered section formatting (382B, 382-B, 382_B, 382(B))
    - SEC/ART swaps (CONST_1973_SEC_199 -> CONST_1973_ART_199)
    - CPC Order/Rule variants (CPC_1908_O_VII_R_11, CPC_1908_O_7_R_11 -> CPC_1908_ORD_VII_R_11)
    - Cross-statute errors in judgments (CRPC_1898_SEC_302 -> PPC_1860_SEC_302)
    - Definition sub-clauses (FIO_2001_SEC_2_G -> FIO_2001_SEC_2_g)
    """
    if not raw or not isinstance(raw, str):
        return None

    cid = raw.strip().upper()
    if cid in ALL_CANONICAL_IDS:
        return cid

    # 1. Strip trailing noise words
    cid = re.sub(r'(CONSTITUTIONAL|PENAL|CIVIL|CRIMINAL|GENERAL|SPECIAL|ACT|ORD|ORDER)$', '', cid).rstrip('_')
    if cid in ALL_CANONICAL_IDS:
        return cid

    # 2. Normalize CPC Orders & Rules: CPC_1908_O_VII_R_11, CPC_1908_ORDER_7_RULE_11 -> CPC_1908_ORD_VII_R_11
    m_cpc = re.match(r'^CPC_1908_(?:O|ORD|ORDER)_([0-9IVXLCDM]+)_(?:R|RULE)_([0-9]+)$', cid)
    if m_cpc:
        ord_val = m_cpc.group(1)
        r_val = m_cpc.group(2)
        if ord_val.isdigit():
            ord_roman = INT_TO_ROMAN.get(int(ord_val), ord_val)
        else:
            ord_roman = ord_val
        cand = f"CPC_1908_ORD_{ord_roman}_R_{r_val}"
        if cand in ALL_CANONICAL_IDS:
            return cand

    # 3. Handle SEC vs ART swaps (e.g. CONST_1973_SEC_199 -> CONST_1973_ART_199)
    for art_act in ARTICLE_ACTS:
        if cid.startswith(f"{art_act}_SEC_"):
            swapped = cid.replace(f"{art_act}_SEC_", f"{art_act}_ART_")
            if swapped in ALL_CANONICAL_IDS:
                return swapped
        elif cid.startswith(f"{art_act}_ART_"):
            swapped = cid.replace(f"{art_act}_ART_", f"{art_act}_SEC_")
            if swapped in ALL_CANONICAL_IDS:
                return swapped

    # 4. Normalize lettered sections: 382-B, 382_B, 382(B) -> 382B
    # e.g. PPC_1860_SEC_382_B -> PPC_1860_SEC_382B
    m_sec = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)[\-_]?([A-Z])$', cid)
    if m_sec:
        cand = f"{m_sec.group(1)}_{m_sec.group(2)}_{m_sec.group(3)}{m_sec.group(4)}"
        if cand in ALL_CANONICAL_IDS:
            return cand
        # Also check with art swap
        if m_sec.group(1) in ARTICLE_ACTS:
            cand_art = f"{m_sec.group(1)}_ART_{m_sec.group(3)}{m_sec.group(4)}"
            if cand_art in ALL_CANONICAL_IDS:
                return cand_art

    # 5. Definition sub-clauses: e.g. FIO_2001_SEC_2_G -> FIO_2001_SEC_2_g
    m_sub = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)_([A-Z])$', cid)
    if m_sub:
        cand_lower = f"{m_sub.group(1)}_{m_sub.group(2)}_{m_sub.group(3)}_{m_sub.group(4).lower()}"
        if cand_lower in ALL_CANONICAL_IDS:
            return cand_lower
        # Or lettered section without underscore:
        cand_joined = f"{m_sub.group(1)}_{m_sub.group(2)}_{m_sub.group(3)}{m_sub.group(4)}"
        if cand_joined in ALL_CANONICAL_IDS:
            return cand_joined

    # 6. Cross-statute reconciliation for famous misplaced citations
    if cid in ("CRPC_1898_SEC_302", "ATA_1997_SEC_302", "CONST_1973_SEC_302", "ARMS_1965_SEC_302"):
        return "PPC_1860_SEC_302"
    if cid in ("CRPC_1898_SEC_302B", "PPC_1860_SEC_302B"):
        return "PPC_1860_SEC_302"
    if cid in ("CRPC_1898_SEC_382B", "PPC_1860_SEC_382B"):
        return "CRPC_1898_SEC_382B"
    if cid in ("CRPC_1898_SEC_497", "PPC_1860_SEC_497"):
        return "CRPC_1898_SEC_497"
    if cid in ("CRPC_1898_SEC_498", "PPC_1860_SEC_498"):
        return "CRPC_1898_SEC_498"
    if cid in ("CRPC_1898_SEC_342", "ATA_1997_SEC_342"):
        return "CRPC_1898_SEC_342"
    if cid in ("CRPC_1898_SEC_161", "ATA_1997_SEC_161"):
        return "CRPC_1898_SEC_161"
    if cid in ("CRPC_1898_SEC_164", "ATA_1997_SEC_164"):
        return "CRPC_1898_SEC_164"

    return None

# Test on famous problematic IDs
test_ids = [
    "CONST_1973_SEC_199",
    "CONST_1973_ART_199CONSTITUTIONAL",
    "CRPC_1898_SEC_302",
    "PPC_1860_SEC_382-B",
    "PPC_1860_SEC_382_B",
    "PPC_1860_SEC_489-F",
    "CPC_1908_O_VII_R_11",
    "CPC_1908_O_7_R_11",
    "CPC_1908_O_VI_R_17",
    "CPC_1908_O_1_R_10",
    "CONST_1973_SEC_10A",
    "QSO_1984_SEC_17",
    "FIO_2001_SEC_2_G",
    "CRPC_1898_SEC_497PENAL",
    "PPC_1860_SEC_497PENAL",
]

print("\n--- RESOLUTION TESTS ---")
for tid in test_ids:
    resolved = resolve_statute_id(tid)
    print(f"{tid:35} -> {resolved}")
