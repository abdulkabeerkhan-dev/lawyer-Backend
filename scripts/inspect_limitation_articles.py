import pdfplumber
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

pdf_path = "data/official_pdfs/limitation_act_1908.pdf"

print(f"=== EXTRACTING LIMITATION ARTICLES FROM {pdf_path} ===")

articles_to_find = ["73", "80", "115", "116", "132", "181", "182"]

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    
    # Let's search each page for the target articles
    for page_idx, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
        for art in articles_to_find:
            # Match Article number at line start or within table
            if re.search(rf"\b{art}\.?\b", text):
                # Print occurrences
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if re.match(rf"^\s*{art}[\.\s]", line) or re.search(rf"\bArt(icle)?\.?\s*{art}\b", line):
                        print(f"\n--- Page {page_idx + 1} | Article {art} ---")
                        # print surrounding lines
                        start = max(0, i - 1)
                        end = min(len(lines), i + 8)
                        for j in range(start, end):
                            print(f"  [{j}] {lines[j]}")
