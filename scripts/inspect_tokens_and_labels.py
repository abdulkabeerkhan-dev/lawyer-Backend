import inspect
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main
from core.pdf_resolver import create_hmac_pdf_token, verify_hmac_pdf_token

print("verify_hmac_pdf_token signature:", inspect.signature(verify_hmac_pdf_token))
print("create_hmac_pdf_token signature:", inspect.signature(create_hmac_pdf_token))

# Let's see how candidate labeling handles boosted records in main.py
with open("main.py", "r", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r"def .*format.*card.*\(|def .*label.*\(", text)
print("Formatting/labeling functions in main.py:", matches)
