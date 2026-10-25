import urllib.request
import re
import os

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

targets = {
    'T': [('transfer_of_property_act_1882.pdf', 'Transfer of Property')],
    'C': [('contract_act_1872.pdf', 'Contract Act')],
    'B': [('banking_companies_ordinance_1962.pdf', 'Banking Companies')],
    'S': [('stamp_act_1899.pdf', 'Stamp Act')],
    'R': [('registration_act_1908.pdf', 'Registration Act')]
}

os.makedirs("data/official_pdfs", exist_ok=True)

for letter, laws in targets.items():
    page = 1
    while page <= 3:
        url = f"http://pakistancode.gov.pk/english/LGu0xAD.php?alp={letter}&page={page}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            
            # Find all <a href="...">text</a>
            links = re.findall(r'<a\s+[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', html, flags=re.I | re.DOTALL)
            for href, raw_txt in links:
                txt = re.sub(r'<[^>]+>', '', raw_txt).strip()
                for out_fname, law_keyword in laws:
                    dest = os.path.join("data/official_pdfs", out_fname)
                    if os.path.exists(dest):
                        continue
                    if law_keyword.lower() in txt.lower():
                        full_href = href if href.startswith('http') else "http://pakistancode.gov.pk/english/" + href
                        print(f"MATCH: {txt} -> {full_href}")
                        # fetch law page
                        try:
                            req2 = urllib.request.Request(full_href, headers=HEADERS)
                            with urllib.request.urlopen(req2, timeout=10) as resp2:
                                law_html = resp2.read().decode('utf-8', errors='ignore')
                            pdf_matches = re.findall(r'https?://pakistancode\.gov\.pk/pdffiles/[a-zA-Z0-9]+\.pdf', law_html)
                            if pdf_matches:
                                pdf_url = pdf_matches[0]
                                print(f"Downloading {pdf_url} -> {out_fname}...")
                                req3 = urllib.request.Request(pdf_url, headers=HEADERS)
                                with urllib.request.urlopen(req3, timeout=30) as resp3:
                                    pdf_data = resp3.read()
                                with open(dest, 'wb') as f:
                                    f.write(pdf_data)
                                print(f"Saved {out_fname} ({len(pdf_data):,} bytes)")
                        except Exception as dl_err:
                            print(f"Error downloading {out_fname}: {dl_err}")
            page += 1
        except Exception as e:
            print(f"Error on {letter} page {page}: {e}")
            break

print("All search/download attempts completed.")
