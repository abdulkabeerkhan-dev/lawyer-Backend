"""
scripts/find_crpc_bail_pages.py

Searches crpc_1898.pdf for the main text of Chapter XXXIX (Bail: Sections 496-502).
"""

import os
import re
import pypdf

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(REPO_DIR, "data", "official_pdfs", "crpc_1898.pdf")
reader = pypdf.PdfReader(pdf_path)

print(f"Total pages in crpc_1898.pdf: {len(reader.pages)}")

for idx, page in enumerate(reader.pages):
    txt = page.extract_text()
    if re.search(r'CHAPTER\s+XXXIX', txt, re.I) or re.search(r'496\.\s*In\s+what\s+cases\s+bail', txt, re.I):
        print(f"Found Chapter XXXIX / Section 496 on 1-based Page {idx + 1}")
    if re.search(r'497\.\s*When\s+bail\s+may\s+be\s+taken', txt, re.I):
        print(f"Found Section 497 on 1-based Page {idx + 1}")
    if re.search(r'498\.\s*Power\s+to\s+direct\s+admission\s+to\s+bail', txt, re.I):
        print(f"Found Section 498 on 1-based Page {idx + 1}")
    if re.search(r'498[\-\s]*A\.', txt, re.I) and "bail" in txt.lower():
        print(f"Found Section 498-A on 1-based Page {idx + 1}")
