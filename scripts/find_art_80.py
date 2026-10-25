import pdfplumber
import re

with pdfplumber.open('data/official_pdfs/limitation_act_1908.pdf') as pdf:
    for page_idx, page in enumerate(pdf.pages):
        txt = page.extract_text()
        if not txt: continue
        lines = txt.split('\n')
        for i, l in enumerate(lines):
            if re.match(r'^\s*80[\.\s—\-]', l):
                print(f"Page {page_idx + 1}:")
                for j in range(max(0, i-1), min(len(lines), i+6)):
                    print(f"  [{j}] {lines[j]}")
