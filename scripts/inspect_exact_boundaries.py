"""
scripts/inspect_exact_boundaries.py

Dumps the exact raw text of PDF pages to determine the authentic boundaries for:
1. Cr.P.C. 1898: Sections 496, 497, 498, 498-A (pages 217-219)
2. TPA 1882: Section 69 vs 69A (pages 35-38)
3. BCO 1962: Section 83 vs 83A (pages 93-97)
"""

import os
import sys
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")

def print_page_slice(pdf_name, pages):
    pdf_path = os.path.join(PDF_DIR, pdf_name)
    reader = pypdf.PdfReader(pdf_path)
    for p_num in pages:
        txt = reader.pages[p_num - 1].extract_text()
        print(f"\n{'='*40} {pdf_name} - PAGE {p_num} (len {len(txt)}) {'='*40}")
        print(txt)

def main():
    print("--- CRPC PAGES 217-219 ---")
    print_page_slice("crpc_1898.pdf", [217, 218, 219])
    
    print("\n--- TPA PAGES 35-38 ---")
    print_page_slice("transfer_of_property_act_1882.pdf", [35, 36, 37, 38])
    
    print("\n--- BCO PAGES 93-97 ---")
    print_page_slice("banking_companies_ordinance_1962.pdf", [93, 94, 95, 96, 97])

if __name__ == "__main__":
    main()
