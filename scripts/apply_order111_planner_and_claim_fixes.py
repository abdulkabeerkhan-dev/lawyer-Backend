"""
scripts/apply_order111_planner_and_claim_fixes.py

Applies the fixes for Item 1 of ORDER 1.11:
1. Fix planner: Years (1800-2099) are never bare section numbers.
2. Fix statute claim verifier: Automatically extract stored primary sections from stored_provisions
   and verify subsections against stored text rather than misclassifying as external cross-references.
3. Wire primary_section in query_processor.py.
"""

import os
import re

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)

# ==============================================================================
# 1. core/statutory_validator.py
# ==============================================================================
val_path = os.path.join(REPO_DIR, "core", "statutory_validator.py")
with open(val_path, "r", encoding="utf-8") as f:
    val_content = f.read()

val_target = """        # Bare section or clause e.g. "302(b)", "12(2)", "489-F", "561-A", "22-A"
        sec_match = re.search(
            r'\\b(\\d+(?:-[A-Za-z]+|[A-Za-z])?)(?:\\s*\\(\\s*(\\d+)\\s*\\))?(?:\\s*\\(\\s*([a-zA-Z])\\s*\\))?',
            clean_text, re.IGNORECASE
        )"""

val_replacement = """        # Bare section or clause e.g. "302(b)", "12(2)", "489-F", "561-A", "22-A"
        sec_match = re.search(
            r'\\b(\\d+(?:-[A-Za-z]+|[A-Za-z])?)(?:\\s*\\(\\s*(\\d+)\\s*\\))?(?:\\s*\\(\\s*([a-zA-Z])\\s*\\))?',
            clean_text, re.IGNORECASE
        )
        if sec_match:
            candidate_prim = sec_match.group(1).replace("-", "")
            if candidate_prim.isdigit() and 1800 <= int(candidate_prim) <= 2099:
                # ORDER 1.11: Standalone calendar years are not section numbers
                sec_match = None"""

if val_target in val_content:
    val_content = val_content.replace(val_target, val_replacement, 1)
    with open(val_path, "w", encoding="utf-8") as f:
        f.write(val_content)
    print("SUCCESS: Updated core/statutory_validator.py")
else:
    print("SKIPPED/ALREADY_PATCHED: core/statutory_validator.py")


# ==============================================================================
# 2. core/statute_currency.py
# ==============================================================================
curr_path = os.path.join(REPO_DIR, "core", "statute_currency.py")
with open(curr_path, "r", encoding="utf-8") as f:
    curr_content = f.read()

curr_target = """    for clause in clauses:
        clause_clean = clause.strip()
        if len(clause_clean) < 3:
            continue
        parsed = parse_statutory_citation(clause_clean, context=query)"""

curr_replacement = """    for clause in clauses:
        clause_clean = clause.strip()
        if len(clause_clean) < 3:
            continue
        bare_digits = re.sub(r'[^0-9]', '', clause_clean)
        if bare_digits.isdigit() and 1800 <= int(bare_digits) <= 2099:
            # ORDER 1.11: Standalone calendar year clauses (e.g. ', 2001?') are never section citations
            continue
        parsed = parse_statutory_citation(clause_clean, context=query)"""

if curr_target in curr_content:
    curr_content = curr_content.replace(curr_target, curr_replacement, 1)
    with open(curr_path, "w", encoding="utf-8") as f:
        f.write(curr_content)
    print("SUCCESS: Updated core/statute_currency.py")
else:
    print("SKIPPED/ALREADY_PATCHED: core/statute_currency.py")


# ==============================================================================
# 3. core/statute_claim_verifier.py
# ==============================================================================
claim_path = os.path.join(REPO_DIR, "core", "statute_claim_verifier.py")
with open(claim_path, "r", encoding="utf-8") as f:
    claim_content = f.read()

claim_target_block = """    stored_texts = []
    for v in stored_provisions.values():
        if isinstance(v, dict):
            stored_texts.append(" ".join(str(x) for x in v.values()))
        else:
            stored_texts.append(str(v))
    combined_stored_text = _normalize_text(" ".join(stored_texts))"""

claim_replacement_block = """    stored_texts = []
    stored_section_texts = {}
    for k, v in stored_provisions.items():
        v_str = " ".join(str(x) for x in v.values()) if isinstance(v, dict) else str(v)
        stored_texts.append(v_str)
        # Extract section number from key (e.g. FIO_2001_SEC_22 -> 22, PPC_1860_SEC_489F -> 489f, SEC_22 -> 22, 22 -> 22)
        m = re.search(r'(?:_SEC_|^SEC_|^)([0-9]+(?:[-][0-9a-z]+|[a-z])?)', str(k), re.IGNORECASE)
        if m:
            clean_k_sec = re.sub(r'[^0-9a-z]', '', m.group(1).lower())
            if clean_k_sec:
                stored_section_texts[clean_k_sec] = _normalize_text(v_str)

    combined_stored_text = _normalize_text(" ".join(stored_texts))

    primary_clean = re.sub(r'[^0-9a-z]', '', primary_section.lower()) if primary_section else ""
    if primary_clean and primary_clean not in stored_section_texts:
        stored_section_texts[primary_clean] = combined_stored_text"""

claim_ref_target = """        # 1. Provision & subsection cross-references
        refs = re.findall(r'(?:section|s\.)\s*([0-9]+(?:[-][0-9a-z]+|[a-z])?)(?:\(([0-9]+)\))?', line, flags=re.IGNORECASE)
        for sec_num, sub_num in refs:
            sec_num_clean = re.sub(r'[^0-9a-z]', '', sec_num.lower())
            primary_clean = re.sub(r'[^0-9a-z]', '', primary_section.lower())
            if primary_section and sec_num_clean == primary_clean:
                if sub_num:
                    if f"({sub_num})" in combined_stored_text or f"sub-section ({sub_num})" in combined_stored_text or f"subsection ({sub_num})" in combined_stored_text:
                        verified_claims.append({
                            "type": "verified_primary_subsection",
                            "reference": f"Section {sec_num}({sub_num})"
                        })
                    else:
                        violations.append({
                            "type": "unsupported_subsection",
                            "line": line,
                            "unsupported_term": f"Section {sec_num}({sub_num})",
                            "reason": f"Subsection '({sub_num})' does not exist in the stored text of Section {sec_num}."
                        })
                else:
                    verified_claims.append({
                        "type": "verified_primary_section",
                        "reference": f"Section {sec_num}"
                    })
            else:"""

claim_ref_replacement = """        # 1. Provision & subsection cross-references
        refs = re.findall(r'(?:section|s\.)\s*([0-9]+(?:[-][0-9a-z]+|[a-z])?)(?:\(([0-9]+)\))?', line, flags=re.IGNORECASE)
        for sec_num, sub_num in refs:
            sec_num_clean = re.sub(r'[^0-9a-z]', '', sec_num.lower())
            is_stored_sec = (sec_num_clean in stored_section_texts) or (primary_clean and sec_num_clean == primary_clean)
            if is_stored_sec:
                sec_text_to_check = stored_section_texts.get(sec_num_clean, combined_stored_text)
                if sub_num:
                    if f"({sub_num})" in sec_text_to_check or f"sub-section ({sub_num})" in sec_text_to_check or f"subsection ({sub_num})" in sec_text_to_check or re.search(rf'\\(\\s*{sub_num}\\s*\\)', sec_text_to_check):
                        verified_claims.append({
                            "type": "verified_primary_subsection",
                            "reference": f"Section {sec_num}({sub_num})"
                        })
                    else:
                        violations.append({
                            "type": "unsupported_subsection",
                            "line": line,
                            "unsupported_term": f"Section {sec_num}({sub_num})",
                            "reason": f"Subsection '({sub_num})' does not exist in the stored text of Section {sec_num}."
                        })
                else:
                    verified_claims.append({
                        "type": "verified_primary_section",
                        "reference": f"Section {sec_num}"
                    })
            else:"""

if claim_target_block in claim_content and claim_ref_target in claim_content:
    claim_content = claim_content.replace(claim_target_block, claim_replacement_block, 1)
    claim_content = claim_content.replace(claim_ref_target, claim_ref_replacement, 1)
    with open(claim_path, "w", encoding="utf-8") as f:
        f.write(claim_content)
    print("SUCCESS: Updated core/statute_claim_verifier.py")
else:
    print("SKIPPED/ALREADY_PATCHED: core/statute_claim_verifier.py")


# ==============================================================================
# 4. legal_ai/query_engine/query_processor.py
# ==============================================================================
qp_path = os.path.join(REPO_DIR, "legal_ai", "query_engine", "query_processor.py")
with open(qp_path, "r", encoding="utf-8") as f:
    qp_content = f.read()

qp_target = """        stored_claims_map = {}
        for p in verified_statutory_provisions:
            cid = str(p.get("canonical_id") or p.get("act_code") or "PROVISION")
            txt_val = p.get("text_cleaned") or p.get("text") or ""
            if isinstance(txt_val, dict):
                txt_val = " ".join(str(v) for v in txt_val.values())
            stored_claims_map[cid] = str(txt_val)
        claim_support_res = verify_memo_statutory_claims(clean_answer, stored_claims_map)"""

qp_replacement = """        stored_claims_map = {}
        primary_sec = ""
        for p in verified_statutory_provisions:
            cid = str(p.get("canonical_id") or p.get("act_code") or "PROVISION")
            txt_val = p.get("text_cleaned") or p.get("text") or ""
            if isinstance(txt_val, dict):
                txt_val = " ".join(str(v) for v in txt_val.values())
            stored_claims_map[cid] = str(txt_val)
            if not primary_sec:
                primary_sec = str(p.get("primary_num") or p.get("section") or "")
        claim_support_res = verify_memo_statutory_claims(clean_answer, stored_claims_map, primary_section=primary_sec)"""

if qp_target in qp_content:
    qp_content = qp_content.replace(qp_target, qp_replacement, 1)
    with open(qp_path, "w", encoding="utf-8") as f:
        f.write(qp_content)
    print("SUCCESS: Updated legal_ai/query_engine/query_processor.py")
else:
    print("SKIPPED/ALREADY_PATCHED: legal_ai/query_engine/query_processor.py")
