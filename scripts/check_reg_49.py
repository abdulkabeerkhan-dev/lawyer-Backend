import pypdf

reader = pypdf.PdfReader("data/official_pdfs/registration_act_1908.pdf")
for p in [23, 24, 25]: # pages 24, 25, 26
    txt = reader.pages[p].extract_text()
    if "49." in txt:
        print(f"=== PAGE {p+1} ===")
        print(txt)
