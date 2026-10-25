import pypdf
import re

reader = pypdf.PdfReader("data/official_pdfs/cpc_1908.pdf")
for pidx in range(100, 115):
    txt = reader.pages[pidx].extract_text()
    if re.search(r"24\.\s*Process", txt):
        print(f"Match on page {pidx+1}:")
        idx = txt.find("24.")
        print(txt[idx:idx+400])
