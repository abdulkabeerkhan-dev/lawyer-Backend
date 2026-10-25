"""
scripts/inspect_tpa_69_end.py

Dumps pages 37 and 38 of transfer_of_property_act_1882.pdf to see the exact end of Section 69.
"""

import os
import sys
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(REPO_DIR, "data", "official_pdfs", "transfer_of_property_act_1882.pdf")
reader = pypdf.PdfReader(pdf_path)

for p_num in [36, 37, 38]:
    txt = reader.pages[p_num - 1].extract_text()
    print(f"\n{'='*40} TPA PAGE {p_num} (len {len(txt)}) {'='*40}")
    print(txt)
