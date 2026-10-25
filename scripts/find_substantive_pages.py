import pypdf
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def find_substantive_section(pdf_path, section_regex, min_page=1):
    reader = pypdf.PdfReader(pdf_path)
    for pidx in range(min_page - 1, len(reader.pages)):
        txt = reader.pages[pidx].extract_text() or ""
        match = re.search(section_regex, txt)
        if match:
            print(f"Match for '{section_regex}' in {pdf_path} on Page {pidx + 1}:")
            start = max(0, match.start() - 50)
            end = min(len(txt), match.end() + 300)
            print(txt[start:end].strip())
            print("-" * 50)
            return pidx + 1, txt
    print(f"NOT FOUND: {section_regex} in {pdf_path}")
    return None, None

print("=== LOCATING SUBSTANTIVE SECTIONS ===")
# 1. PPC 415 & 417 (skip TOC, search page 100+)
find_substantive_section("data/official_pdfs/ppc_1860.pdf", r"415\.\s*Cheating[\.\s—\-]", min_page=120)
find_substantive_section("data/official_pdfs/ppc_1860.pdf", r"417\.\s*Punishment for cheating[\.\s—\-]", min_page=120)

# 2. CPC Section 96 (skip TOC, search page 40+)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"96\.\s*Appeal from original decree[\.\s—\-]", min_page=40)

# 3. CPC Order XXI rules (search page 95+)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"1\.\s*Modes of paying money under decree[\.\s—\-]", min_page=95)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"2\.\s*Payment out of Court to decree[\-\s]holder[\.\s—\-]", min_page=95)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"10\.\s*Application for execution[\.\s—\-]", min_page=95)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"11\.\s*Oral application[\.\s—\-]", min_page=95)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"22\.\s*Notice to show cause against execution[\.\s—\-]", min_page=95)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"24\.\s*Process for execution[\.\s—\-]", min_page=95)
find_substantive_section("data/official_pdfs/cpc_1908.pdf", r"30\.\s*Decree for payment of money[\.\s—\-]", min_page=95)

# 4. Contract Act 126-135 (search page 20+)
find_substantive_section("data/official_pdfs/contract_act_1872.pdf", r"126\.\s*['\"“]?Contract of guarantee", min_page=20)
find_substantive_section("data/official_pdfs/contract_act_1872.pdf", r"128\.\s*Surety['’]?s liability", min_page=20)
find_substantive_section("data/official_pdfs/contract_act_1872.pdf", r"133\.\s*Discharge of surety by variance", min_page=20)
find_substantive_section("data/official_pdfs/contract_act_1872.pdf", r"134\.\s*Discharge of surety by release", min_page=20)
find_substantive_section("data/official_pdfs/contract_act_1872.pdf", r"135\.\s*Discharge of surety when creditor", min_page=20)

# 5. TPA 58, 67, 69 (search page 15+)
find_substantive_section("data/official_pdfs/transfer_of_property_act_1882.pdf", r"58\.\s*['\"“]?Mortgage", min_page=15)
find_substantive_section("data/official_pdfs/transfer_of_property_act_1882.pdf", r"67\.\s*Right to foreclosure", min_page=15)
find_substantive_section("data/official_pdfs/transfer_of_property_act_1882.pdf", r"69\.\s*Power of sale", min_page=15)

# 6. BCO 1962 Sections 27, 27A, 27B, 83, 83A (search page 20+)
find_substantive_section("data/official_pdfs/banking_companies_ordinance_1962.pdf", r"27\.\s*Licensing of banking", min_page=20)
find_substantive_section("data/official_pdfs/banking_companies_ordinance_1962.pdf", r"83\.\s*Penalties[\.\s—\-]", min_page=70)
find_substantive_section("data/official_pdfs/banking_companies_ordinance_1962.pdf", r"83A\.\s*Dishonest removal", min_page=70)
