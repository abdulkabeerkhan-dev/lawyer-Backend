import urllib.request
import urllib.parse
import json
import re
import os

os.makedirs('data/official_pdfs', exist_ok=True)

# List of laws we want to search and download
laws_to_find = [
    ("tpa_1882.pdf", "Transfer of Property Act", "1882"),
    ("contract_1872.pdf", "Contract Act", "1872"),
    ("bco_1962.pdf", "Banking Companies Ordinance", "1962"),
    ("stamp_act_1899.pdf", "Stamp Act", "1899"),
    ("registration_act_1908.pdf", "Registration Act", "1908"),
]

search_url_template = "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apg%3D%3D?search={query}"

for out_name, law_name, year in laws_to_find:
    dest = os.path.join("data/official_pdfs", out_name)
    if os.path.exists(dest):
        print(f"{out_name} already exists.")
        continue

    query = urllib.parse.quote(law_name)
    url = search_url_template.format(query=query)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        
        # Look for PDF links in the page
        pdf_links = re.findall(r'https?://pakistancode\.gov\.pk/pdffiles/[a-zA-Z0-9]+\.pdf', html)
        if not pdf_links:
            # Look for law view links
            law_links = re.findall(r'/english/UY2FqaJw1-apaUY2Fqa-[a-zA-Z0-9%_\-]+', html)
            print(f"Found {len(law_links)} law page links for '{law_name}'")
            for ll in law_links[:3]:
                sub_url = f"https://pakistancode.gov.pk{ll}"
                req2 = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    sub_html = resp2.read().decode("utf-8", errors="ignore")
                    sub_pdfs = re.findall(r'https?://pakistancode\.gov\.pk/pdffiles/[a-zA-Z0-9]+\.pdf', sub_html)
                    if sub_pdfs:
                        pdf_links.extend(sub_pdfs)
                        break

        if pdf_links:
            chosen_pdf = pdf_links[0]
            print(f"Downloading {chosen_pdf} -> {out_name}...")
            req_dl = urllib.request.Request(chosen_pdf, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_dl, timeout=30) as resp_dl:
                pdf_bytes = resp_dl.read()
            with open(dest, "wb") as f:
                f.write(pdf_bytes)
            print(f"Saved {out_name}: {len(pdf_bytes):,} bytes.")
        else:
            print(f"Could not find PDF link for '{law_name}'")
    except Exception as e:
        print(f"Error searching for '{law_name}': {e}")
