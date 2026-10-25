import pdfplumber

with pdfplumber.open("data/official_pdfs/banking_companies_ordinance_1962.pdf") as pdf:
    print(f"Num pages: {len(pdf.pages)}")
    txt = pdf.pages[0].extract_text()
    print("Page 1 text preview:")
    print(txt[:1000])
