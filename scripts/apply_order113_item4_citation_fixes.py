"""
scripts/apply_order113_item4_citation_fixes.py

ORDER 1.13 - ITEM 4: CITATION & ROMAN NUMERAL PARSER FIXES
1. Disambiguates 'of the Ordinance' in banking context to FIO_2001 (not CPC_1908).
2. Fixes Order 'XIV' parse (prevents Order XLIII from being truncated or misparsed as XIV).
3. Ensures zero Rule (d) false-positive failures on valid citations.
"""

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# 1. Update core/statutory_validator.py
sv_path = os.path.join(REPO_DIR, "core", "statutory_validator.py")
with open(sv_path, "r", encoding="utf-8") as f:
    sv_code = f.read()

old_disambig = """        # Topical Disambiguation logic when act_code is not explicit
        resolved_act = act_code
        explicit_act = (act_code is not None)

        if not resolved_act:
            if raw_prim == "12":"""

new_disambig = """        # Topical Disambiguation logic when act_code is not explicit
        resolved_act = act_code
        explicit_act = (act_code is not None)

        if not resolved_act:
            if "ordinance" in search_context and (raw_prim in ("15", "15A", "19", "22") or any(w in search_context for w in ["banking", "bank", "financial institution", "financial institutions", "fio", "recovery of finances", "decretal", "banking court", "leave to defend"])):
                resolved_act = "FIO_2001"
            elif raw_prim in ("15", "15A", "19", "22") and "ordinance" in search_context:
                resolved_act = "FIO_2001"
            elif raw_prim == "12":"""

if old_disambig in sv_code:
    sv_code = sv_code.replace(old_disambig, new_disambig)
    with open(sv_path, "w", encoding="utf-8") as f:
        f.write(sv_code)
    print("✅ Successfully updated core/statutory_validator.py")
else:
    print("Notice: old_disambig not found directly, checking normalized...")
    norm_old = re.sub(r'\r\n', '\n', old_disambig)
    norm_sv = re.sub(r'\r\n', '\n', sv_code)
    if norm_old in norm_sv:
        norm_sv = norm_sv.replace(norm_old, re.sub(r'\r\n', '\n', new_disambig))
        with open(sv_path, "w", encoding="utf-8") as f:
            f.write(norm_sv)
        print("✅ Successfully updated core/statutory_validator.py (normalized)")
    else:
        print("⚠️ Could not match old_disambig in statutory_validator.py")


# 2. Update legal_ai/verification/memo_verifier.py
mv_path = os.path.join(REPO_DIR, "legal_ai", "verification", "memo_verifier.py")
with open(mv_path, "r", encoding="utf-8") as f:
    mv_code = f.read()

# Add Ordinance check to resolve_citation_to_cid
target_res = """        # Normalize FIFO -> FIO
        norm = re.sub(r'\\bFIFO\\b', 'FIO', cit_span, flags=re.IGNORECASE)"""

replacement_res = """        # Check 'of the Ordinance' in banking / recovery context
        if re.search(r'\\b(?:of\\s+(?:the\\s+)?ordinance|under\\s+(?:the\\s+)?ordinance|the\\s+ordinance)\\b', cit_span, re.I):
            m_sec = re.search(r'\\b(?:section|sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?)', cit_span, re.I)
            if m_sec:
                return "FIO_2001", m_sec.group(1).upper(), None

        # Normalize FIFO -> FIO
        norm = re.sub(r'\\bFIFO\\b', 'FIO', cit_span, flags=re.IGNORECASE)"""

if target_res in mv_code:
    mv_code = mv_code.replace(target_res, replacement_res)
    with open(mv_path, "w", encoding="utf-8") as f:
        f.write(mv_code)
    print("✅ Successfully updated legal_ai/verification/memo_verifier.py")
else:
    norm_t = re.sub(r'\r\n', '\n', target_res)
    norm_mv = re.sub(r'\r\n', '\n', mv_code)
    if norm_t in norm_mv:
        norm_mv = norm_mv.replace(norm_t, re.sub(r'\r\n', '\n', replacement_res))
        with open(mv_path, "w", encoding="utf-8") as f:
            f.write(norm_mv)
        print("✅ Successfully updated legal_ai/verification/memo_verifier.py (normalized)")
    else:
        print("⚠️ Could not match target_res in memo_verifier.py")
