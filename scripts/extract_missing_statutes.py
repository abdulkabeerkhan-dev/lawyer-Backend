import pdfplumber
import hashlib
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

print("=" * 80)
print("EXTRACTING MISSING PROVISIONS VERBATIM FROM OFFICIAL BARE-ACT PDFS")
print("=" * 80)

# 1. BCO 1962 Section 83 heading check
print("\n--- [1] Checking Banking Companies Ordinance 1962 Section 83 Heading ---")
with pdfplumber.open("data/official_pdfs/banking_companies_ordinance_1962.pdf") as pdf:
    print(f"Total pages in BCO: {len(pdf.pages)}")
    found_s83 = False
    for pidx, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        if "83." in txt or "Section 83" in txt or "Penalties" in txt:
            lines = txt.split("\n")
            for lidx, line in enumerate(lines):
                if re.search(r"\b83\b", line):
                    print(f"  Page {pidx + 1} matching line: {line}")
                    # Print context
                    for ctx in lines[max(0, lidx-1):min(len(lines), lidx+5)]:
                        print(f"    {ctx}")
                    found_s83 = True
                    break
        if found_s83:
            break

# 2. PPC 415 and 417
print("\n--- [2] Checking Pakistan Penal Code 1860 for Sections 415 & 417 ---")
with pdfplumber.open("data/official_pdfs/ppc_1860.pdf") as pdf:
    # Pages 113 to 116
    for pidx in [113, 114, 115]: # 0-indexed: 114 to 116
        if pidx < len(pdf.pages):
            txt = pdf.pages[pidx].extract_text() or ""
            lines = txt.split("\n")
            for lidx, line in enumerate(lines):
                if re.match(r"^\s*41[57]\.", line):
                    print(f"  Page {pidx + 1} match: {line}")
                    for ctx in lines[lidx:min(len(lines), lidx+8)]:
                        print(f"    {ctx}")

# 3. CPC Section 96
print("\n--- [3] Checking Code of Civil Procedure 1908 Section 96 ---")
with pdfplumber.open("data/official_pdfs/cpc_1908.pdf") as pdf:
    # Page 44 approx
    for pidx in range(40, 48):
        txt = pdf.pages[pidx].extract_text() or ""
        lines = txt.split("\n")
        for lidx, line in enumerate(lines):
            if re.match(r"^\s*96\.", line):
                print(f"  Page {pidx + 1} match: {line}")
                for ctx in lines[lidx:min(len(lines), lidx+8)]:
                    print(f"    {ctx}")

# 4. Stamp Act Section 35
print("\n--- [4] Checking Stamp Act 1899 Section 35 ---")
with pdfplumber.open("data/official_pdfs/stamp_act_1899.pdf") as pdf:
    for pidx, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        lines = txt.split("\n")
        for lidx, line in enumerate(lines):
            if re.match(r"^\s*35\.\s*Instruments not duly stamped", line, re.IGNORECASE):
                print(f"  Page {pidx + 1} match: {line}")
                for ctx in lines[lidx:min(len(lines), lidx+8)]:
                    print(f"    {ctx}")
                break

# 5. Registration Act Sections 17 & 49
print("\n--- [5] Checking Registration Act 1908 Sections 17 & 49 ---")
with pdfplumber.open("data/official_pdfs/registration_act_1908.pdf") as pdf:
    for pidx, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        lines = txt.split("\n")
        for lidx, line in enumerate(lines):
            if re.match(r"^\s*(17|49)\.\s*Documents of which registration|^\s*49\.\s*Effect of non-registration", line, re.IGNORECASE):
                print(f"  Page {pidx + 1} match: {line}")
                for ctx in lines[lidx:min(len(lines), lidx+6)]:
                    print(f"    {ctx}")
