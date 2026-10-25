"""
scripts/dump_order39_raw.py

Dumps pages 162, 163, 164 of cpc_1908.pdf with SHA-256 hashes and line-by-line text.
"""

import os
import sys
import hashlib
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(REPO_DIR, "data", "official_pdfs", "cpc_1908.pdf")
reader = pypdf.PdfReader(pdf_path)

for p_num in [162, 163, 164]:
    page = reader.pages[p_num - 1]
    raw_text = page.extract_text()
    p_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    print("=" * 110)
    print(f"OFFICIAL CPC PDF (cpc_1908.pdf) -- PAGE {p_num} | SHA-256: {p_hash}")
    print("=" * 110)
    print(raw_text)
    print()
