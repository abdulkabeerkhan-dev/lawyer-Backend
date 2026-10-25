import os
import sys
import json
import difflib
import re
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPC_JSON = os.path.join(REPO_DIR, "data", "unified_statutes", "CPC_1908.json")
CPC_PDF = os.path.join(REPO_DIR, "data", "official_pdfs", "cpc_1908.pdf")

print("=" * 80)
print("ORDER 1.1 ITEM 5: CPC ORDER XXXIX PDF DIFF AUDIT")
print("=" * 80)

# 1. Read stored rules from CPC_1908.json
with open(CPC_JSON, "r", encoding="utf-8") as f:
    cpc_data = json.load(f)

stored_o39 = {}
for r in cpc_data:
    cid = r.get("canonical_id", "")
    if "ORD_XXXIX" in cid:
        # e.g. CPC_1908_ORD_XXXIX_R_1 -> "1"
        r_num = cid.split("ORD_XXXIX_R_")[-1]
        stored_o39[r_num] = r

# 2. Extract raw text from pages 162-165 of cpc_1908.pdf
reader = pypdf.PdfReader(CPC_PDF)
# Pages 162 to 165 (0-indexed: 161 to 164)
raw_pdf_text = ""
for pno in range(161, 165):
    raw_pdf_text += f"\n--- [PAGE {pno+1}] ---\n" + reader.pages[pno].extract_text()

# 3. Check Rule 2 sub-rules (1)-(4) in raw PDF text
print("\n[5.1] Rule 2 Sub-rules Verification in cpc_1908.pdf:")
has_r2_1 = "(1) In any suit for restraining" in raw_pdf_text or "(1)" in raw_pdf_text[raw_pdf_text.find("2. Injunction to restrain"):raw_pdf_text.find("3. Before granting")]
has_r2_2 = "(2) The Court may by order" in raw_pdf_text
has_r2_3 = "(3) In case of disobedience" in raw_pdf_text
has_r2_4 = "(4) No attachment under this rule" in raw_pdf_text

print(f"  - Sub-rule (1) present: {has_r2_1}")
print(f"  - Sub-rule (2) present: {has_r2_2}")
print(f"  - Sub-rule (3) present: {has_r2_3}")
print(f"  - Sub-rule (4) present: {has_r2_4}")
if has_r2_1 and has_r2_2 and has_r2_3 and has_r2_4:
    print("VERDICT: Authentic cpc_1908.pdf Rule 2 unequivocally contains all four sub-rules: (1), (2), (3), and (4).")

# 4. Extract PDF segments for each rule
# Rule start boundaries in the text
boundaries = [
    ("1", "1. Cases in which temporary injunction may be granted"),
    ("2", "2. Injunction to restrain repetition or continuance of breach"),
    ("2A", "1[(2A) An interim injunction passed under rules 1 or 2"),
    ("2B", "(2B) The order of injunction made under rules 1 or 2"),
    ("3", "3. Before granting injunction Court to direct notice to opposite party"),
    ("4", "4. Order for injunction may be discharged, varied or set aside"),
    ("4A", "4[4A. Injunction to cease to be in force after certain period"),
    ("5", "5. Injuction to corporation binding on its officers"),
    ("6", "6. Power to order interim sale"),
    ("7", "7. Detention, preservation, inspection, etc., of subject matter of suit"),
    ("8", "8. Application for such orders to be after notice"),
    ("9", "9. When party may be put in immediate possession of land the subject matter of suit"),
    ("10", "10. Deposit of money, etc., in Court"),
    ("END", "ORDER XL")
]

pdf_rules = {}
for i in range(len(boundaries) - 1):
    r_key, start_pat = boundaries[i]
    _, next_pat = boundaries[i + 1]
    
    s_idx = raw_pdf_text.find(start_pat)
    e_idx = raw_pdf_text.find(next_pat)
    
    if s_idx != -1 and e_idx != -1:
        segment = raw_pdf_text[s_idx:e_idx].strip()
    elif s_idx != -1:
        segment = raw_pdf_text[s_idx:].strip()
    else:
        # Fallback search
        segment = ""
    # Strip footnote lines and page numbers
    cleaned_lines = []
    for l in segment.split("\n"):
        l_s = l.strip()
        if re.match(r"^Page \d+ of \d+", l_s) or re.match(r"^---\s*\[PAGE", l_s):
            continue
        if re.match(r"^\d\[\*", l_s) or re.match(r"^\dSubs\. by", l_s) or re.match(r"^\dIns\. by", l_s) or re.match(r"^\dRule 4A ins\.", l_s):
            continue
        cleaned_lines.append(l_s)
    pdf_rules[r_key] = "\n".join(cleaned_lines)

# 5. Diff each stored rule against extracted PDF text layer
print("\n[5.2] Unified Diffs: Stored Rule vs Authentic cpc_1908.pdf Text Layer:")
target_rules = ["1", "2", "2A", "2B", "3", "4", "4A", "5", "6", "7", "8", "9", "10"]

for r_key in target_rules:
    stored = stored_o39.get(r_key, {})
    stored_txt = stored.get("text", "").strip()
    pdf_txt = pdf_rules.get(r_key, "").strip()
    
    stored_lines = [l.strip() for l in stored_txt.splitlines() if l.strip()]
    pdf_lines = [l.strip() for l in pdf_txt.splitlines() if l.strip()]
    
    diff = list(difflib.unified_diff(
        pdf_lines,
        stored_lines,
        fromfile=f"PDF_Text_Layer_O.XXXIX_R.{r_key}",
        tofile=f"Stored_Store_O.XXXIX_R.{r_key}",
        lineterm=""
    ))
    
    print(f"\n--- Diff for Order XXXIX Rule {r_key} ---")
    print(f"Stored Words: {len(stored_txt.split())} | PDF Extracted Words: {len(pdf_txt.split())}")
    if not diff:
        print("  NO DIFFERENCES (Exact line-by-line match with normalized whitespace).")
    else:
        print(f"  Differences found ({len(diff)} diff lines):")
        for dl in diff[:25]:
            print(f"    {dl}")
        if len(diff) > 25:
            print(f"    ... [{len(diff) - 25} more diff lines truncated]")

print("\n" + "=" * 80)
print("END OF CPC ORDER XXXIX PDF DIFF AUDIT")
print("=" * 80)
