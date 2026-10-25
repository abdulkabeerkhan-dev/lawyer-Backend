import urllib.request
import re
import os

HEADERS = {'User-Agent': 'Mozilla/5.0'}
url = "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ%2BV-sg-jjjjjjjjjjjjj"
req = urllib.request.Request(url, headers=HEADERS)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

pdf_matches = re.findall(r'https?://pakistancode\.gov\.pk/pdffiles/[a-zA-Z0-9]+\.pdf', html)
print(f"PDF matches for Banking Companies Ordinance 1962: {pdf_matches}")

if pdf_matches:
    pdf_url = pdf_matches[0]
    dest = "data/official_pdfs/banking_companies_ordinance_1962.pdf"
    print(f"Downloading {pdf_url} to {dest}...")
    req_dl = urllib.request.Request(pdf_url, headers=HEADERS)
    with urllib.request.urlopen(req_dl, timeout=30) as resp_dl:
        data = resp_dl.read()
    with open(dest, "wb") as f:
        f.write(data)
    print(f"Successfully downloaded authentic BCO 1962: {len(data):,} bytes!")
