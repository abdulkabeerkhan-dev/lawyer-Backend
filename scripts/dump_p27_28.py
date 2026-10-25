import pdfplumber

with pdfplumber.open('data/official_pdfs/limitation_act_1908.pdf') as pdf:
    for p in [26, 27]: # 0-indexed: pages 27 and 28
        print(f"=== PAGE {p+1} ===")
        print(pdf.pages[p].extract_text())
