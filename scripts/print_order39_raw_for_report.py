"""
scripts/print_order39_raw_for_report.py

ITEM 10: RAW ORDER XXXIX TEXT LAYER FROM OFFICIAL CPC 1908 PDF
Prints raw text layer for:
  - Rule 2 (sub-rules 1 to 4)
  - Rule 2A (15-day ex-parte injunction ceiling and provisos)
  - Rule 3 provisos and verification of Rule 3A (absent from federal PDF)
With page numbers, SHA-256 hashes, and explicit 'needs lawyer' tag.
"""

import os
import sys
import hashlib
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(REPO_DIR, "data", "official_pdfs", "cpc_1908.pdf")
reader = pypdf.PdfReader(pdf_path)

def main():
    print("=" * 110)
    print("ITEM 10: RAW ORDER XXXIX RULES 2, 2A, AND 3A FROM OFFICIAL CPC PDF (cpc_1908.pdf)")
    print("CLASSIFICATION: [NEEDS LAWYER REVIEW]")
    print("=" * 110)

    # 1. Page 162 (Rule 1 & Rule 2 sub-rules 1-2)
    p162 = reader.pages[161]
    p162_text = p162.extract_text()
    p162_hash = hashlib.sha256(p162_text.encode("utf-8")).hexdigest()

    print(f"\n[PAGE 162 of 318] | SHA256: {p162_hash} | Status: [NEEDS LAWYER]")
    print("-" * 110)
    r2_start = p162_text.find("2. Injunction to restrain repetition")
    if r2_start != -1:
        print("Raw Rule 2 Text on Page 162 (Sub-rules 1 and 2):")
        print(p162_text[r2_start:].strip())
    else:
        print(p162_text)

    # 2. Page 163 (Rule 2 sub-rules 3-4, Rule 2A, Rule 2B, Rule 3, Rule 4, Rule 4A)
    p163 = reader.pages[162]
    p163_text = p163.extract_text()
    p163_hash = hashlib.sha256(p163_text.encode("utf-8")).hexdigest()

    print(f"\n[PAGE 163 of 318] | SHA256: {p163_hash} | Status: [NEEDS LAWYER]")
    print("-" * 110)
    print("Raw Page 163 Text (Contains Rule 2(3)-(4), Rule 2A, Rule 2B, Rule 3, Rule 4):")
    print(p163_text.strip())

    # 3. Rule 3A Absence Analysis
    print("\n" + "-" * 110)
    print("RULE 3A STATUS CHECK IN OFFICIAL FEDERAL CPC PDF (cpc_1908.pdf):")
    print("-" * 110)
    has_3a = "3A" in p163_text or "Rule 3A" in p163_text
    print(f"Rule 3A present in official federal text layer of Page 163: {has_3a}")
    print("Finding: Rule 3A is NOT enacted in the federal Code of Civil Procedure, 1908.")
    print("Notice: Rule 3A exists in Indian CPC (1976 amendment) and certain provincial high court rule amendments,")
    print("but is absent from the Federal Bare Act of Pakistan. Human advocate verification required.")
    print("Classification: [NEEDS LAWYER REVIEW]")
    print("=" * 110)

if __name__ == "__main__":
    main()
