import pdfplumber
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

pdf_path = "data/official_pdfs/cpc_1908.pdf"

with pdfplumber.open(pdf_path) as pdf:
    for page_num in range(161, 167): # 1-indexed pages 162 to 167
        if page_num <= len(pdf.pages):
            txt = pdf.pages[page_num - 1].extract_text()
            print(f"=== PAGE {page_num} (len {len(txt)}) ===")
            lines = txt.split('\n')
            for line in lines[:15]:
                print("  ", line)
            print("   ...")
            for line in lines[-5:]:
                print("  ", line)
