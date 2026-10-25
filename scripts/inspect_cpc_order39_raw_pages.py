"""
scripts/inspect_cpc_order39_raw_pages.py

Dumps pages 162-166 of data/official_pdfs/cpc_1908.pdf with exact page numbers,
SHA-256 hashes, and raw text layer for Order XXXIX Rules 1, 2, 2A, 3, 3A, 4, 4A.
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

print(f"Total pages in cpc_1908.pdf: {len(reader.pages)}")

# Pages 162 to 166 (1-based)
for p_num in range(162, 167):
    page = reader.pages[p_num - 1]
    raw_bytes = page.extract_text().encode("utf-8")
    p_hash = hashlib.sha256(raw_bytes).hexdigest()
    print("\n" + "=" * 110)
    print(f"CPC 1908 PDF - 1-BASED PAGE {p_num} | Text Length: {len(raw_bytes)} bytes | SHA256: {p_hash}")
    print("=" * 110)
    print(page.extract_text())
