import pdfplumber
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

pdf_path = "data/official_pdfs/banking_companies_ordinance_1962.pdf"

print(f"=== CHECKING SECTION 83 HEADING IN AUTHENTIC BCO 1962 ({pdf_path}) ===")

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    for pidx, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        lines = txt.split("\n")
        for lidx, line in enumerate(lines):
            # Check for Section 83
            if re.match(r"^\s*83\.\s*", line):
                print(f"\n--- Found on Page {pidx + 1} ---")
                for ctx in lines[max(0, lidx-1):min(len(lines), lidx+10)]:
                    print(f"  {ctx}")
