import pypdf
import re

reader = pypdf.PdfReader("data/official_pdfs/registration_act_1908.pdf")
for pidx, page in enumerate(reader.pages):
    txt = page.extract_text()
    if re.search(r"49\.\s*Effect", txt):
        print(f"Match on page {pidx+1}:")
        idx = txt.find("49.")
        print(txt[idx:idx+400])
