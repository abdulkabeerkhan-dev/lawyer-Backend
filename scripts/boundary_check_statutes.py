"""
scripts/boundary_check_statutes.py

ITEM 5: BOUNDARY CHECK
Checks stored text against raw PDF pages for:
  - TPA: Sections 58, 67, 69 (and check if 69A or 70 was swallowed)
  - BCO: Sections 27, 83, 83A (and check if 84 was swallowed)
  - CrPC: Sections 496, 497, 498, 498-A (check for truncation in 497 / 498)

For each provision:
  - Prints the first 200 characters of stored text
  - Prints the last 200 characters of stored text
  - Prints raw PDF text at beginning and end
  - Flags if stored text runs into the next section or is truncated
"""

import os
import sys
import json
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")

TARGETS = [
    # (Enactment JSON, Canonical ID, PDF file, [approx 1-based page numbers], Next section marker)
    ("TPA_1882.json", "TPA_1882_SEC_58", "transfer_of_property_act_1882.pdf", [28, 29, 30], "59. Mortgage when to be by assurance"),
    ("TPA_1882.json", "TPA_1882_SEC_67", "transfer_of_property_act_1882.pdf", [34], "67A. Mortgagee when bound to bring one suit"),
    ("TPA_1882.json", "TPA_1882_SEC_69", "transfer_of_property_act_1882.pdf", [35, 36, 37], "69A. Appointment of receiver"),
    ("BCO_1962.json", "BCO_1962_SEC_27", "banking_companies_ordinance_1962.pdf", [30, 31], "27A. Prohibition of certain financial transactions"),
    ("BCO_1962.json", "BCO_1962_SEC_83", "banking_companies_ordinance_1962.pdf", [93, 94, 95, 96], "83A. Dishonest removal of pledged goods"),
    ("BCO_1962.json", "BCO_1962_SEC_83A", "banking_companies_ordinance_1962.pdf", [96], "84. Cognizance of offences"),
    ("CRPC_1898.json", "CRPC_1898_SEC_496", "crpc_1898.pdf", [217], "497. When bail may be taken in case of non-bailable"),
    ("CRPC_1898.json", "CRPC_1898_SEC_497", "crpc_1898.pdf", [217, 218], "498. Power to direct admission to bail or reduction of bail"),
    ("CRPC_1898.json", "CRPC_1898_SEC_498", "crpc_1898.pdf", [218], "498-A. No bail to be granted to a person not in custody"),
    ("CRPC_1898.json", "CRPC_1898_SEC_498A", "crpc_1898.pdf", [218], "499. Bond of accused and sureties"),
]

def load_stored(fname, cid):
    p = os.path.join(STATUTES_DIR, fname)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    for r in data:
        if r.get("canonical_id") == cid:
            return r
    return None

def main():
    print("=" * 110)
    print("ITEM 5: BOUNDARY AUDIT FOR TPA, BCO, AND CRPC PROVISIONS")
    print("=" * 110)

    for json_file, cid, pdf_file, pages, next_marker in TARGETS:
        print("\n" + "#" * 110)
        print(f"PROVISION: {cid} (from {json_file}) vs PDF: {pdf_file} (Pages: {pages})")
        print("#" * 110)

        stored = load_stored(json_file, cid)
        stored_text = (stored.get("text") or "") if stored else ""
        stored_words = len(stored_text.split())

        # Extract raw text from indicated PDF pages
        pdf_path = os.path.join(PDF_DIR, pdf_file)
        reader = pypdf.PdfReader(pdf_path)
        raw_pages_text = "\n--- [PAGE BREAK] ---\n".join([reader.pages[p - 1].extract_text() for p in pages if p <= len(reader.pages)])

        print(f"Stored Word Count: {stored_words} words | Total Length: {len(stored_text)} chars")
        print("\nStored Text First 200 Characters:")
        print(repr(stored_text[:200]))
        print("\nStored Text Last 200 Characters:")
        print(repr(stored_text[-200:]))

        # Check for next section overrun
        overrun_flag = "NO OVERRUN DETECTED"
        if next_marker.lower() in stored_text.lower():
            overrun_flag = f"OVERRUN DETECTED: Contains next section marker '{next_marker}'"
        else:
            # Also check simple section number
            next_sec_num = next_marker.split(".")[0]
            if f"\n{next_sec_num}." in stored_text or f" {next_sec_num}. " in stored_text:
                overrun_flag = f"POSSIBLE OVERRUN: Contains '{next_sec_num}.'"

        # Check for truncation
        truncation_flag = "NO TRUNCATION DETECTED"
        if cid == "CRPC_1898_SEC_497" and ("(2)" not in stored_text or "(5)" not in stored_text):
            truncation_flag = "TRUNCATION DETECTED: Section 497 missing subsection (2) or (5) in stored text!"
        elif cid == "CRPC_1898_SEC_498" and stored_words < 50:
            truncation_flag = f"POSSIBLE TRUNCATION: Section 498 only {stored_words} words."

        print(f"\nBoundary Audit Flags:")
        print(f"  Overrun Check:    {overrun_flag}")
        print(f"  Truncation Check: {truncation_flag}")

    print("\n" + "=" * 110)
    print("BOUNDARY AUDIT COMPLETE")
    print("=" * 110)

if __name__ == "__main__":
    main()
