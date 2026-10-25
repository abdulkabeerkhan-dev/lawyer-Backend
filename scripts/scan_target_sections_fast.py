import pypdf
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def scan_pdf_fast(pdf_path, search_patterns):
    print(f"\nScanning {pdf_path} ({len(search_patterns)} targets)...", flush=True)
    reader = pypdf.PdfReader(pdf_path)
    print(f"Total pages: {len(reader.pages)}", flush=True)
    results = {}
    for pidx, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        for name, pat in list(search_patterns.items()):
            if name not in results and re.search(pat, txt, re.IGNORECASE):
                results[name] = (pidx + 1, txt)
                print(f"  Found {name} on Page {pidx + 1}", flush=True)
    return results

# 1. PPC 415, 417
scan_pdf_fast("data/official_pdfs/ppc_1860.pdf", {
    "PPC 415": r"415\.\s*Cheating",
    "PPC 417": r"417\.\s*Punishment for cheating"
})

# 2. CPC s.96 and Order XXI rules
scan_pdf_fast("data/official_pdfs/cpc_1908.pdf", {
    "CPC s.96": r"96\.\s*Appeal from original decree",
    "CPC O.XXI R.1": r"1\.\s*Modes of paying money under decree",
    "CPC O.XXI R.2": r"2\.\s*Payment out of Court to decree-holder",
    "CPC O.XXI R.10": r"10\.\s*Application for execution",
    "CPC O.XXI R.11": r"11\.\s*Oral application",
    "CPC O.XXI R.22": r"22\.\s*Notice to show cause",
    "CPC O.XXI R.24": r"24\.\s*Process for execution",
    "CPC O.XXI R.30": r"30\.\s*Decree for payment of money"
})

# 3. Contract Act 126-135
scan_pdf_fast("data/official_pdfs/contract_act_1872.pdf", {
    "Contract 126": r"126\.\s*['\"“]?Contract of guarantee",
    "Contract 128": r"128\.\s*Surety",
    "Contract 133": r"133\.\s*Discharge of surety by variance",
    "Contract 134": r"134\.\s*Discharge of surety by release",
    "Contract 135": r"135\.\s*Discharge of surety when creditor"
})

# 4. TPA 58, 67, 69
scan_pdf_fast("data/official_pdfs/transfer_of_property_act_1882.pdf", {
    "TPA 58": r"58\.\s*['\"“]?Mortgage",
    "TPA 67": r"67\.\s*Right to foreclosure",
    "TPA 69": r"69\.\s*Power of sale"
})
