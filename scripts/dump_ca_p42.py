import pypdf

reader = pypdf.PdfReader("data/official_pdfs/contract_act_1872.pdf")
print("=== PAGE 42 ===")
print(reader.pages[41].extract_text())
print("=== PAGE 43 ===")
print(reader.pages[42].extract_text())
