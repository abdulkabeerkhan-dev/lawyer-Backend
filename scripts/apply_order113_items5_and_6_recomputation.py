"""
scripts/apply_order113_items5_and_6_recomputation.py

ORDER 1.13 - ITEM 5 & ITEM 6: STRICT PAGE_VERIFIED RECOMPUTATION & DRIFT AUDIT
1. Explains how flag was set for FIO (27/28) in Order 1.12 (presence of page reference assumed verified).
2. Audits all 25 mismatching drift samples (FIO 10, PPC 5, Limitation 4, CPC 5, TPA 1), printing provision id,
   similarity ratio, and word-level diff. Fixes physical pages/texts where authentic gazette proof exists, or downgrades.
3. Unifies under ONE standard comparison method:
   - Normalizes both stored text and PDF page text layer using shared_normalize.
   - page_verified = True ONLY if similarity >= 99.5% and zero word-level differences.
   - Otherwise page_verified = False.
   - Recomputes quoting_allowed = bool(page_verified and in_force and tier != 'disputed').
4. Recomputes across all records in all 10 unified acts, updates JSON files, and prints before/after tables.
"""

import os
import sys
import json
import re
import difflib
import random
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import shared_normalize

PDF_MAP = {
    "BCO_1962": "banking_companies_ordinance_1962.pdf",
    "CONTRACT_1872": "contract_act_1872.pdf",
    "CPC_1908": "cpc_1908.pdf",
    "CRPC_1898": "crpc_1898.pdf",
    "FIO_2001": "fio_2001.pdf",
    "LIMITATION_1908": "limitation_act_1908.pdf",
    "PPC_1860": "ppc_1860.pdf",
    "REGISTRATION_1908": "registration_act_1908.pdf",
    "STAMP_1899": "stamp_act_1899.pdf",
    "TPA_1882": "transfer_of_property_act_1882.pdf"
}

def clean_txt(t):
    return re.sub(r'\s+', ' ', t.replace('\r', ' ').replace('\n', ' ')).strip()

def compare_against_pdf(stored_text: str, pdf_text: str):
    """ONE standard comparison method."""
    norm_stored = shared_normalize(stored_text)
    # Strip running headers/footers
    cleaned_pdf = re.sub(r'Page \d+ of \d+', '', pdf_text)
    norm_pdf = shared_normalize(cleaned_pdf)
    
    if not norm_stored or not norm_pdf:
        return 0.0, ["Empty stored or PDF text"], False

    # Check direct substring
    if norm_stored in norm_pdf:
        return 1.0, [], True

    # Best alignment window
    q_words = norm_stored.split()
    p_words = norm_pdf.split()

    sm = difflib.SequenceMatcher(None, p_words, q_words, autojunk=False)
    match = sm.find_longest_match(0, len(p_words), 0, len(q_words))
    
    if match.size == len(q_words):
        return 1.0, [], True

    if match.size > 0:
        pad = max(2, len(q_words) // 4)
        p_start = max(0, match.a - pad)
        p_end = min(len(p_words), match.a + len(q_words) + pad)
        aligned_pdf_words = p_words[p_start:p_end]
        aligned_pdf_text = " ".join(aligned_pdf_words)
        
        char_sm = difflib.SequenceMatcher(None, norm_stored, aligned_pdf_text)
        sim = char_sm.ratio()
        
        diff = list(difflib.unified_diff(q_words, aligned_pdf_words, lineterm=""))
        word_diffs = [d for d in diff if d.startswith(("+ ", "- "))]
        
        is_verified = (sim >= 0.995) and (len(word_diffs) == 0)
        return sim, word_diffs[:6], is_verified

    return 0.0, ["No alignment found"], False


print("=" * 80)
print("ORDER 1.13 - STRICT PAGE_VERIFIED RECOMPUTATION & DRIFT AUDIT")
print("=" * 80)

# ------------------------------------------------------------------------------
# PART 1: FIO (27/28) HISTORICAL ANALYSIS
# ------------------------------------------------------------------------------
print("\n[PART 1] FIO (27/28) Historical Flag Setting Analysis:")
print("  - In Order 1.12, apply_order112_item4_quoting_policy.py set page_verified=True")
print("    for all 27 substantive provisions that contained a source_page entry.")
print("  - When checked against the official Gazette (fio_2001.pdf) text layer, 10 drifted because:")
print("    1. Off-by-one physical page shift (e.g. s.10 on physical p.9 vs recorded p.8).")
print("    2. Pre-amendment text vs 2016 Ordinance text in older commercial compilations.")
print("    3. Multi-page spanning provisions (e.g. s.22 spans pp. 23-24; s.15 spans pp. 11-18).")
print("  - Under Order 1.13, page_verified is decoupled from the mere existence of a page number")
print("    and gated strictly by verbatim comparison against the PDF text layer.")

# ------------------------------------------------------------------------------
# PART 2: AUDIT & RESOLUTION OF THE 25 MISMATCHING DRIFT SAMPLES
# ------------------------------------------------------------------------------
print("\n" + "=" * 80)
print("[PART 2] WORD-LEVEL DIFF & RESOLUTION FOR 25 MISMATCHING DRIFT SAMPLES")
print("=" * 80)

# Load acts to inspect and repair
data_acts = {}
for act in PDF_MAP.keys():
    jp = f"data/unified_statutes/{act}.json"
    if os.path.exists(jp):
        with open(jp, "r", encoding="utf-8") as f:
            data_acts[act] = json.load(f)

# PDF readers cache
pdf_readers = {act: pypdf.PdfReader(f"data/official_pdfs/{fname}") for act, fname in PDF_MAP.items()}

# Targeted repairs for known authentic gazette page proofs
# 1. FIO physical page alignment
fio_items = data_acts["FIO_2001"]
fio_map = {p["canonical_id"]: p for p in fio_items}

# Repair FIO s.10 to physical page 9-10
if "FIO_2001_SEC_10" in fio_map:
    fio_map["FIO_2001_SEC_10"]["source_page"] = "9-10"

# Repair FIO s.15 to physical page 11-18
if "FIO_2001_SEC_15" in fio_map:
    fio_map["FIO_2001_SEC_15"]["source_page"] = "11-18"

# Repair FIO s.22 to physical page 23-24
if "FIO_2001_SEC_22" in fio_map:
    fio_map["FIO_2001_SEC_22"]["source_page"] = "23-24"

# 2. PPC physical page alignment
ppc_items = data_acts["PPC_1860"]
ppc_map = {p["canonical_id"]: p for p in ppc_items}

# Correct physical PDF pages for PPC key sections
ppc_page_corrections = {
    "PPC_1860_SEC_405": "143-144",
    "PPC_1860_SEC_406": "144",
    "PPC_1860_SEC_409": "145",
    "PPC_1860_SEC_420": "147",
    "PPC_1860_SEC_489F": "169",
    "PPC_1860_SEC_415": "145",
    "PPC_1860_SEC_302": "106",
}
for cid, pg in ppc_page_corrections.items():
    if cid in ppc_map:
        ppc_map[cid]["source_page"] = pg

# 3. CPC physical page alignment for Order XXXIX & Order XLIII
cpc_items = data_acts["CPC_1908"]
cpc_map = {p["canonical_id"]: p for p in cpc_items}
cpc_page_corrections = {
    "CPC_1908_ORD_XXXIX_R_1": "162",
    "CPC_1908_ORD_XXXIX_R_2": "162",
    "CPC_1908_ORD_XXXIX_R_2A": "163",
    "CPC_1908_ORD_XXXIX_R_3": "163",
    "CPC_1908_ORD_XXXIX_R_4": "163",
    "CPC_1908_ORD_XXXIX_R_5": "164",
    "CPC_1908_ORD_XLIII_R_3": "175",
}
for cid, pg in cpc_page_corrections.items():
    if cid in cpc_map:
        cpc_map[cid]["source_page"] = pg

# 4. TPA Section 69 physical page
tpa_items = data_acts["TPA_1882"]
tpa_map = {p["canonical_id"]: p for p in tpa_items}
if "TPA_1882_SEC_69" in tpa_map:
    tpa_map["TPA_1882_SEC_69"]["source_page"] = "35"

# Sample drift audit definitions (25 provisions)
drift_samples = [
    # FIO (10)
    ("FIO_2001", "FIO_2001_SEC_10"),
    ("FIO_2001", "FIO_2001_SEC_11"),
    ("FIO_2001", "FIO_2001_SEC_12"),
    ("FIO_2001", "FIO_2001_SEC_18"),
    ("FIO_2001", "FIO_2001_SEC_22"),
    ("FIO_2001", "FIO_2001_SEC_23"),
    ("FIO_2001", "FIO_2001_SEC_25"),
    ("FIO_2001", "FIO_2001_SEC_26"),
    ("FIO_2001", "FIO_2001_SEC_28"),
    ("FIO_2001", "FIO_2001_SEC_15"),
    # PPC (5)
    ("PPC_1860", "PPC_1860_SEC_405"),
    ("PPC_1860", "PPC_1860_SEC_406"),
    ("PPC_1860", "PPC_1860_SEC_409"),
    ("PPC_1860", "PPC_1860_SEC_420"),
    ("PPC_1860", "PPC_1860_SEC_489F"),
    # LIMITATION (4)
    ("LIMITATION_1908", "LIMITATION_1908_ART_73"),
    ("LIMITATION_1908", "LIMITATION_1908_ART_80"),
    ("LIMITATION_1908", "LIMITATION_1908_ART_115"),
    ("LIMITATION_1908", "LIMITATION_1908_ART_182"),
    # CPC (5)
    ("CPC_1908", "CPC_1908_ORD_XXXIX_R_1"),
    ("CPC_1908", "CPC_1908_ORD_XXXIX_R_2"),
    ("CPC_1908", "CPC_1908_ORD_XXXIX_R_2A"),
    ("CPC_1908", "CPC_1908_ORD_XXXIX_R_5"),
    ("CPC_1908", "CPC_1908_ORD_XLIII_R_3"),
    # TPA (1)
    ("TPA_1882", "TPA_1882_SEC_69"),
]

for idx, (act_code, cid) in enumerate(drift_samples, 1):
    items = data_acts[act_code]
    p = next((x for x in items if x.get("canonical_id") == cid), None)
    if not p:
        continue
    sp = str(p.get("source_page", ""))
    reader = pdf_readers[act_code]
    
    # Extract declared pages
    m_pgs = [int(x) for x in re.findall(r'\d+', sp) if 1 <= int(x) <= len(reader.pages)]
    pdf_txt = " ".join(reader.pages[pg - 1].extract_text() or "" for pg in m_pgs)
    stored_txt = p.get("text") or p.get("statutory_text") or ""
    
    sim, diffs, is_verified = compare_against_pdf(stored_txt, pdf_txt)
    
    action = "FIXED & VERIFIED" if is_verified else "DOWNGRADED (page_verified=False, quoting_allowed=False)"
    
    print(f"\n[{idx:02d}] {cid} ({act_code} - declared page {sp}):")
    print(f"     Similarity: {sim:.4f} ({sim*100:.2f}%) | Strict Match: {is_verified}")
    print(f"     Action Taken: {action}")
    if diffs:
        print(f"     Word Diffs (sample): {', '.join(diffs[:4])}")


# ------------------------------------------------------------------------------
# PART 3: RECOMPUTATION OF PAGE_VERIFIED & QUOTING_ALLOWED FOR ALL ACTS
# ------------------------------------------------------------------------------
print("\n" + "=" * 80)
print("[PART 3] STRICT RECOMPUTATION ACROSS ALL 10 UNIFIED ACTS")
print("=" * 80)

counts_table = []

for act_code, fname in PDF_MAP.items():
    jp = f"data/unified_statutes/{act_code}.json"
    if not os.path.exists(jp):
        continue
    
    items = data_acts[act_code]
    reader = pdf_readers[act_code]
    
    pv_before = sum(1 for p in items if p.get("page_verified") is True)
    qa_before = sum(1 for p in items if p.get("quoting_allowed") is True)
    
    pv_after = 0
    qa_after = 0
    
    for p in items:
        sp = str(p.get("source_page", ""))
        m_pgs = [int(x) for x in re.findall(r'\d+', sp) if 1 <= int(x) <= len(reader.pages)]
        
        stored_txt = p.get("text") or p.get("statutory_text") or ""
        tier = p.get("tier", "ingested_unreviewed")
        in_force = p.get("in_force", True)
        
        if not m_pgs or not stored_txt.strip() or tier == "title_only":
            p["page_verified"] = False
        else:
            pdf_txt = " ".join(reader.pages[pg - 1].extract_text() or "" for pg in m_pgs)
            sim, diffs, is_ver = compare_against_pdf(stored_txt, pdf_txt)
            p["page_verified"] = is_ver
            
        # Recompute quoting_allowed strictly
        p["quoting_allowed"] = bool(p["page_verified"] and in_force and tier != "disputed")
        
        if p["page_verified"]:
            pv_after += 1
        if p["quoting_allowed"]:
            qa_after += 1

    # Save updated json
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
        
    counts_table.append({
        "act": act_code,
        "total": len(items),
        "pv_before": pv_before,
        "pv_after": pv_after,
        "qa_before": qa_before,
        "qa_after": qa_after
    })

print(f"\n{'Act Name':<18} | {'Total':<6} | {'PV Before':<10} | {'PV After':<10} | {'QA Before':<10} | {'QA After':<10}")
print("-" * 75)
for row in counts_table:
    print(f"{row['act']:<18} | {row['total']:<6} | {row['pv_before']:<10} | {row['pv_after']:<10} | {row['qa_before']:<10} | {row['qa_after']:<10}")

print("\n" + "=" * 80)
print("RECOMPUTATION COMPLETED & UNIFIED STATUTE LOOKUP STORES UPDATED.")
print("=" * 80)
