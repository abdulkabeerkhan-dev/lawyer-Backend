import urllib.request
import urllib.parse
import re

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# Search for Banking Companies Ordinance 1962
url = "https://pakistancode.gov.pk/english/LGu0xAD.php?alp=B&page=1"
req = urllib.request.Request(url, headers=HEADERS)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# Find links with Banking Companies
links = re.findall(r'<a\s+[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', html, flags=re.I | re.DOTALL)
for href, raw_txt in links:
    txt = re.sub(r'<[^>]+>', '', raw_txt).strip()
    if "banking companies" in txt.lower():
        print(f"Found: {txt} -> {href}")
