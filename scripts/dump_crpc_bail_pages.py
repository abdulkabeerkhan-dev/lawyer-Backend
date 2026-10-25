"""
scripts/dump_crpc_bail_pages.py

Dumps pages 166, 167, 168 of crpc_1898.pdf (Chapter XXXIX: OF BAIL).
"""

import os
import sys
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(REPO_DIR, "data", "official_pdfs", "crpc_1898.pdf")
reader = pypdf.PdfReader(pdf_path)

for p_num in [166, 167, 168]:
    txt = reader.pages[p_num - 1].extract_text()
    print(f"\n{'='*40} CRPC PAGE {p_num} (len {len(txt)}) {'='*40}")
    print(txt)
