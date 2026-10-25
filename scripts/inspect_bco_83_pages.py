"""
scripts/inspect_bco_83_pages.py

Dumps pages 93, 94, 95, 96 of banking_companies_ordinance_1962.pdf.
"""

import os
import sys
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(REPO_DIR, "data", "official_pdfs", "banking_companies_ordinance_1962.pdf")
reader = pypdf.PdfReader(pdf_path)

for p_num in [93, 94, 95, 96]:
    txt = reader.pages[p_num - 1].extract_text()
    print(f"\n{'='*40} BCO PAGE {p_num} (len {len(txt)}) {'='*40}")
    print(txt)
