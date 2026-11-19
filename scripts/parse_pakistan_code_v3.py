import os
import sys
import json
import re
from pathlib import Path

# Paths
ROOT_DIR = Path(r"d:\lawyer-Backend")
PC_TEXT_DIR = Path(r"D:\pakistan_code_text")
PC_PDF_DIR = Path(r"D:\pakistan_code_pdfs")
V2_DIR = ROOT_DIR / "data" / "statutes_v2"
V3_STAGING_DIR = ROOT_DIR / "data" / "statutes_v3_staging"

V3_STAGING_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------
# 1. Primary canonical map of statutes_v2 act codes to PC text files
# ---------------------------------------------------------
V2_PRIMARY_MAP = {
    'Financial Institutions (Recovery of Finances) Ordinance, 2001.txt': 'FIO_2001',
    'National Accountability Ordinance, 1999.txt': 'NAO_1999',
    'Pakistan Penal Code (PPC),1860 (Under Review).txt': 'PPC_1860',
    'Code of Civil Procedure (CPC) , 1908 (Under Review).txt': 'CPC_1908',
    'Code of Criminal Procedure (CrPC), 1898 (Under Review).txt': 'CRPC_1898',
    'Anti Terrorism Act (ATA),1997.txt': 'ATA_1997',
    'Anti-Money Laundering (AML) Act, 2010.txt': 'AMLA_2010',
    'Banking Companies Ordinance, 1962.txt': 'BCO_1962',
    'Control of Narcotic Substances Act (CNSA), 1997.txt': 'CNSA_1997',
    'Qanun-e-Shahadat Order, 1984 (QSO).txt': 'QSO_1984',
    'Specific Relief Act, 1877.txt': 'SRA_1877',
    'Transfer of Property Act, 1882.txt': 'TPA_1882',
    'Muslim Family Laws Ordinance, 1961.txt': 'MFLO_1961',
    'Guardians and Wards Act, 1890.txt': 'GWA_1890',
    'Companies Act, 2017.txt': 'COMPANIES_2017',
    'Customs Act, 1969 (Same as on the official website of FBR dated 30-06-2025).txt': 'CUSTOMS_1969',
    'Sales Tax Act, 1990 (Same as on the official website of FBR dated 30-06-2026).txt': 'SALES_TAX_1990',
    'Income Tax Ordinance, 2001 (Same as on the official website of FBR dated 31-06-2026).txt': 'ITO_2001',
    'Court-Fees Act, 1870.txt': 'COURT_FEES_1870',
    'Elections Act, 2017.txt': 'ELECTIONS_ACT_2017',
    'Negotiable Instruments Act, 1881.txt': 'NIA_1881',
    'State Bank of Pakistan (SBP) Act, 1956.txt': 'SBP_1956',
    'Securities and Exchange Commission of Pakistan Act, 1997.txt': 'SECP_1997',
    'Prevention of Electronic Crimes Act, 2016.txt': 'PECA_2016',
    'Industrial Relations Act, 2012.txt': 'IRA_2012',
    'Limitation Act, 1908.txt': 'LIMITATION_1908',
    'Registration Act, 1908.txt': 'REGISTRATION_1908',
    'Stamp Act, 1899.txt': 'STAMP_1899',
    'Succession Act, 1925.txt': 'SUCCESSION_1925',
    'Contract Act, 1872.txt': 'CONTRACT_1872',
    'Sale of Goods Act, 1930.txt': 'SALE_OF_GOODS_1930',
    'Partnership Act, 1932.txt': 'PARTNERSHIP_1932',
    'Arbitration Act, 1940.txt': 'ARBITRATION_1940',
    'Recognition and Enforcement (Arbitration Agreement and Foreign Arbitral) Act, 2011.txt': 'ARBITRATION_2011',
    'Easements Act, 1882.txt': 'EASEMENTS_1882',
    'Land Acquisition Act, 1894.txt': 'LAND_ACQUISITION_1894',
    'Explosive Substances Act,1908.txt': 'EXPLOSIVE_SUBSTANCES_1908',
    'Offence of Qazf (Enforcement of Hadd) Ordinance, 1979.txt': 'HUDOOD_QAZF_1979',
    'Offence of Zina (Enforcement of Hudood) Ordinance,1979.txt': 'HUDOOD_ZINA_1979',
    'Prohibition (Enforcement of Hadd) Order, 1979.txt': 'PROHIBITION_HADD_1979',
    'Prevention of Trafficking In Persons Act, 2018.txt': 'HUMAN_TRAFFICKING_2018',
    "Enforcement of Women's Property Rights Act, 2020.txt": 'WOMEN_PROPERTY_RIGHTS_2020',
    'The Family Courts Act, 1964.txt': 'FAMILY_COURTS_1964',
    'West Pakistan Civil Courts Ordinance, 1962.txt': 'CIVIL_COURTS_1962',
    'West Pakistan Land-Revenue Act, 1967.txt': 'LAND_REVENUE_1967',
    'West Pakistan Maintenance of Public Order Ordinance, 1960.txt': 'MPO_1960',
    'West Pakistan Muslim Personal Law (Shariat) Application Act, 1962.txt': 'SHARIAT_APPLICATION_1962',
    'Police Order, 2002.txt': 'POLICE_ORDER_2002',
    'Juvenile Justice System Act, 2018.txt': 'JUVENILE_JUSTICE_2018',
    'Illegal Dispossession Act, 2005.txt': 'ILLEGAL_DISPOSSESSION_2005',
    'Defamation Ordinance, 2002.txt': 'DEFAMATION_2002',
    'Dowry and Bridal Gifts (Restriction) Act, 1976.txt': 'DOWRY_RESTRICTION_1976',
    'Federal Investigation Agency Act (FIA), 1974.txt': 'FIA_1974',
    'Prevention of Corruption Act, 1947.txt': 'PCA_1947',
    'Federal Excise Act, 2005 (Same as on the official website of FBR dated 30-06-2026).txt': 'FEDERAL_EXCISE_2005',
    'Islamabad Rent Restriction Ordinance, 2001.txt': 'ISLAMABAD_RENT_2001',
    'General Clauses Act, 1897.txt': 'GENERAL_CLAUSES_1897',
    'Oath Act, 1873.txt': 'OATHS_1873',
    'Official Secrets Act, 1923.txt': 'OFFICIAL_SECRETS_1923',
    'Payment of Wages Act, 1936.txt': 'PAYMENT_WAGES_1936',
    'Partition Act, 1893.txt': 'PARTITION_1893',
    'Patents Ordinance, 2000.txt': 'PATENTS_2000',
    'Railways Act, 1890.txt': 'RAILWAYS_1890',
    'Suits Valuation Act, 1887.txt': 'SUITS_VALUATION_1887',
    'Trade Marks Ordinance, 2001.txt': 'TRADEMARKS_2001',
    'Charitable and Religious Trusts Act, 1920.txt': 'TRUSTS_1882',
    'Industrial and Commercial Employment (Standing Orders) Ordinance, 1968.txt': 'STANDING_ORDERS_1968',
    'Civil Servants Act, 1973.txt': 'CIVIL_SERVANTS_1973',
    'Copyright Ordinance, 1962.txt': 'COPYRIGHT_1962',
    'Benami Transactions (Prohibition) Act, 2017.txt': 'BENAMI_2017',
    'Cantonments Rent Restriction Act, 1963.txt': 'CANTONMENT_RENT_1963',
    'Child Marriage Restraint Act, 1929.txt': 'CHILD_MARRIAGE_1929',
    'Christian Marriage Act, 1872.txt': 'CHRISTIAN_MARRIAGE_1872',
    'Hindu Marriage Act, 2017.txt': 'HINDU_MARRIAGE_2017',
    'Dissolution of Muslim Marriages Act, 1939.txt': 'DMMA_1939',
    'Drug Regulatory Authority Act, 2012.txt': 'DRAP_2012',
    'Drugs Act, 1976.txt': 'DRUGS_1976',
    'Electronic Transactions Ordinance, 2002.txt': 'ETO_2002',
    'Evacuee Property and Displaced Persons Laws (Repeal) Act, 1975.txt': 'EVACUEE_PROPERTY_1957',
    'Evacuee Trust Properties (Management and Disposal) Act, 1975.txt': 'EVACUEE_TRUST_1975',
    'Extradition Act, 1972.txt': 'EXTRADITION_1972',
    'Foreign Private Investment (Promotion and Protection) Act, 1976.txt': 'INVESTMENT_PROTECTION_1976',
    'Majority Act, 1875.txt': 'MAJORITY_1875',
    'Mental Health Ordinance, 2001.txt': 'MENTAL_HEALTH_2001',
    'Provincial Motor Vehicles Ordinance, 1965.txt': 'MOTOR_VEHICLES_1965',
    'Provincial Insolvency Act, 1920.txt': 'PROVINCIAL_INSOLVENCY_1920',
    'Supreme Court (Practice and Procedure) Act, 2023.txt': 'SC_PRACTICE_PROCEDURE_2023',
    'Service Tribunals Act, 1973.txt': 'SERVICES_TRIBUNALS_1973',
    "Bankers' Books Evidence Act, 1891.txt": 'BANKERS_BOOKS_1891',
    'Legal Practitioners and Bar Councils Act, 1973.txt': 'BAR_COUNCILS_1973',
    'Defence Housing Authority Islamabad Act, 2013.txt': 'DEFENCE_HOUSING_2013',
    'Divorce Act,1869.txt': 'DIVORCE_1869',
    'Domestic Violence (Prevention and Protection) Act, 2026.txt': 'DOMESTIC_VIOLENCE_2020',
    'Pakistan Environmental Protection Act, 1997.txt': 'ENVIRONMENTAL_1997',
    'Federal Board of Revenue Act, 2007 (extracted from Finance Act, 2007).txt': 'FBR_2007',
    'Insurance Act,1938(Act No. IV of 1938)(Repealed by Ord. XXXIX of 2000 s.168).txt': 'INSURANCE_2000',
    'Regulation of Generation Transmission and Distribution of Electric Power Act, 1997.txt': 'NEPRA_1997',
    'Oil and Gas Development Corporation (Re-Organization) Ordinance, 2001.txt': 'OGRA_2002',
    'Passports Act, 1974.txt': 'PASSPORT_1974',
    'Pakistan Electronic Media Regulatory Authority Ordinance (PEMRA), 2002.txt': 'PEMRA_2002',
    'Public Procurement Regulatory Authority Ordinance (PPRA), 2002.txt': 'PUBLIC_PROCUREMENT_2009',
    'Constitution of the Islamic Republic of Pakistan.txt': 'CONST_1973',
    'Evidence(Act I of 1872)(Repeal by P.o.10 of 1984).txt': 'EVIDENCE_1872',
    'Companies Ordinance, 1984 (Repealed by Act XIX of 2017).txt': 'COMPANIES_1984',
    'Arms Act, 1878.txt': 'ARMS_1965',
    'Anti-Rape (Investigation and Trial) Act, 2021.txt': 'ANTI_RAPE_2021',
    "Workmen's Compensation Act, 1923.txt": 'WORKMENS_COMPENSATION_1923'
}

# Acts that use ART instead of SEC
ARTICLE_ACTS = {'CONST_1973', 'QSO_1984', 'POLICE_ORDER_2002', 'PROHIBITION_HADD_1979'}

# Aliases that existed as duplicate act files in statutes_v2:
V2_ALIASES = {
    'AMLA_2010': ['ANTI_MONEY_LAUNDERING_2010'],
    'COMPANIES_2017': ['COMPANIES_ACT_2017'],
    'NIA_1881': ['NI_ACT_1881'],
    'CONST_1973': ['CONST_26TH_AMEND_2024'],
}

# ---------------------------------------------------------
# 2. Text Cleaner & Footnote Extractor
# ---------------------------------------------------------
def clean_section_text(raw_text):
    """
    Cleans raw statutory section text according to Phase 1 rules:
    - Extracts footnote lines to amendment_notes
    - Removes page footers & headers
    - Strips inline amendment markers (e.g. 3[cooperative] -> cooperative) and stray brackets
    - Rebinds mid-sentence line wraps
    - Normalizes willful/wilful spelling
    """
    amendment_notes = []
    lines = raw_text.splitlines()
    clean_lines = []

    re_footnote = re.compile(
        r'^\s*(?:\d+[\*]?\s*)?(?:Ins\.|Subs\.?|Added|Omitted|Replaced|Renumbered|Amended|Deleted|New\s+section|Words?)\s+(?:by|omitted|inserted|substituted|dated|under|vide)\b',
        re.IGNORECASE
    )
    re_footnote_num = re.compile(
        r'^\s*\d+[\*]?\s*(?:Ins|Subs|Added|Omitted|Deleted|Words)\b',
        re.IGNORECASE
    )
    re_page_footer = re.compile(r'^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*$', re.IGNORECASE)
    re_gazette_header = re.compile(r'^\s*\[Part\s+I[^\n\]]*\]\s*$', re.IGNORECASE)

    in_footnote_block = False

    for line in lines:
        s_line = line.strip()
        if not s_line:
            clean_lines.append("")
            in_footnote_block = False
            continue

        if re_page_footer.match(s_line) or re_gazette_header.match(s_line):
            continue

        if re_footnote.match(s_line) or re_footnote_num.match(s_line):
            amendment_notes.append(s_line)
            in_footnote_block = True
            continue
        elif in_footnote_block and (s_line.startswith("(") or "Ordinance" in s_line or "Act" in s_line or "s." in s_line) and not s_line.startswith("Provided"):
            if amendment_notes:
                amendment_notes[-1] += " " + s_line
            else:
                amendment_notes.append(s_line)
            continue
        else:
            in_footnote_block = False

        clean_lines.append(line)

    text = "\n".join(clean_lines)

    # Strip inline amendment markers
    text = re.sub(r'\d*\[\s*\*+\s*\]', '', text)
    text = re.sub(r'\d*\[\s*(\([a-zA-Z0-9]+\))\s*', r'\1 ', text)
    text = re.sub(r'\d*\[([^\]]+)\]', r'\1', text)
    text = text.replace("[", "").replace("]", "")

    # Soft unwrap lines broken mid-sentence
    paragraphs = text.split("\n\n")
    unwrapped_paras = []
    for para in paragraphs:
        p_lines = [l.strip() for l in para.splitlines() if l.strip()]
        if not p_lines:
            continue
        merged = []
        for l in p_lines:
            is_new_clause = bool(re.match(r'^(?:\([a-zA-Z0-9]+\)|\d+\.|Provided\b)', l))
            if merged and not is_new_clause and not merged[-1].endswith((".", ":", ";")):
                if merged[-1].endswith("-"):
                    merged[-1] = merged[-1][:-1] + l
                else:
                    merged[-1] = merged[-1] + " " + l
            else:
                merged.append(l)
        unwrapped_paras.append("\n".join(merged))

    cleaned_text = "\n\n".join(unwrapped_paras).strip()

    # Spelling normalization: normalize "wilful" -> "willful" in cleaned text
    cleaned_text = re.sub(r'\bwilful\b', 'willful', cleaned_text, flags=re.IGNORECASE)

    return cleaned_text, amendment_notes

# ---------------------------------------------------------
# 3. Enactment Start & Section Parser
# ---------------------------------------------------------
def find_enactment_start(text):
    enact_patterns = [
        r'(?:pleased\s+to\s+make(?:\s+and\s+promulgate)?\s+the\s+following\s+(?:Ordinance|Order|Act|Regulations)\s*[:\—\-])',
        r'(?:It\s+is\s+hereby\s+enacted\s+as\s+follows\s*[:\—\-])',
        r'(?:NOW,\s+THEREFORE,[\s\S]*?follows\s*[:\—\-])',
    ]
    for pat in enact_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.end()

    contents_pos = text.find("CONTENTS")
    if contents_pos != -1:
        matches = list(re.finditer(r'(?:^|\n)\s*1\.\s+Short\s+title', text, re.IGNORECASE))
        if len(matches) > 1:
            return matches[1].start()
        elif len(matches) == 1 and matches[0].start() > contents_pos + 100:
            return matches[0].start()

    m1 = re.search(r'(?:^|\n)\s*1\.\s+(?:Short\s+title|Title)', text, re.IGNORECASE)
    if m1:
        return m1.start()

    return 0

def get_canonical_act_code(filename):
    """Returns canonical act code for a PC file, strictly preferring v2 act codes."""
    if filename in V2_PRIMARY_MAP:
        return V2_PRIMARY_MAP[filename]

    name = filename.replace('.txt', '')
    name_clean = re.sub(r'\s*\([^)]*\)', '', name)
    m_year = re.search(r'\b(18\d\d|19\d\d|20\d\d)\b', name_clean)
    year = m_year.group(1) if m_year else ""

    name_clean = re.sub(r'\b(18\d\d|19\d\d|20\d\d)\b', '', name_clean)
    name_clean = re.sub(r'\b(Act|Ordinance|Order|Code|Regulations)\b', '', name_clean, flags=re.I)

    words = re.findall(r'[A-Za-z0-9]+', name_clean)
    stop_words = {'the', 'of', 'and', 'in', 'for', 'a', 'an', 'to', 'on', 'with', 'by'}
    sig_words = [w.upper() for w in words if w.lower() not in stop_words]
    slug = "_".join(sig_words[:4])
    if year:
        return f"{slug}_{year}"
    return slug

def parse_statute_file(file_path):
    filename = file_path.name
    size = file_path.stat().st_size

    if size == 0:
        return None, "0_byte_skipped"

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 47 Repealed Acts
    if size < 600 and ("THIS LAW HAS BEEN REPEALED" in content or "repeal" in content.lower() or "repealed" in filename.lower()):
        m_rep = re.search(r'\((Repealed?[^\)]+)\)', filename, re.I)
        rep_note = m_rep.group(1) if m_rep else content.strip()
        act_code = get_canonical_act_code(filename)

        record = {
            "canonical_id": f"{act_code}_REPEALED",
            "act": act_code,
            "act_code": act_code,
            "act_name": filename.replace('.txt', ''),
            "section": "repealed",
            "primary_num": "0",
            "heading": "Repealed",
            "title": "Repealed Enactment",
            "provision_type": "repeal_notice",
            "text": "THIS LAW HAS BEEN REPEALED",
            "raw_text": content.strip(),
            "amendment_notes": [f"THIS LAW HAS BEEN REPEALED: {rep_note}"],
            "former_labels": [],
            "in_force": False,
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "text_layer_extracted"
        }
        return [record], "repealed"

    # Substantive Act
    act_code = get_canonical_act_code(filename)
    act_name = filename.replace('.txt', '')
    prefix = "ART" if act_code in ARTICLE_ACTS else "SEC"
    sub_start = find_enactment_start(content)
    sub_text = content[sub_start:]

    sec_num_pat = re.compile(
        r'(?:^|\n)\s*(?:\d+\[)?\s*([0-9]{1,4}[A-Z]{0,2}(?:-[A-Z]{1,2})?)\s*(?:\.|\—|\:|\.\s*[\—\-])\s*(?![\*\s]*(?:Ins\.|Subs\.|Added|Omitted|Deleted|New\s+section|Replaced|ibid\b))([^\n\r]*)'
    )

    matches = list(sec_num_pat.finditer(sub_text))
    if not matches:
        clean_text, notes = clean_section_text(sub_text)
        record = {
            "canonical_id": f"{act_code}_FULL",
            "act": act_code,
            "act_code": act_code,
            "act_name": act_name,
            "section": "full",
            "primary_num": "1",
            "heading": act_name,
            "title": act_name,
            "provision_type": "article" if prefix == "ART" else "section",
            "text": clean_text,
            "raw_text": sub_text.strip(),
            "amendment_notes": notes,
            "former_labels": [],
            "in_force": True,
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "text_layer_extracted"
        }
        return [record], "substantive"

    records = []
    last_primary = 0
    for i, m in enumerate(matches):
        raw_num = m.group(1)
        heading_line = m.group(2).strip()
        heading = re.split(r'[\.\—\-\:]', heading_line)[0].strip()
        if not heading:
            heading = f"{'Article' if prefix == 'ART' else 'Section'} {raw_num}"

        m_num = re.match(r'^(\d+)', raw_num)
        primary = int(m_num.group(1)) if m_num else 0

        # Discard false positive list items inside high sections
        if primary < last_primary and primary < 3 and last_primary > 5:
            continue

        start_pos = m.start()
        end_pos = matches[i+1].start() if i+1 < len(matches) else len(sub_text)
        raw_sec = sub_text[start_pos:end_pos].strip()

        clean_text, notes = clean_section_text(raw_sec)
        canonical_id = f"{act_code}_{prefix}_{raw_num}"

        sec_record = {
            "canonical_id": canonical_id,
            "act": act_code,
            "act_code": act_code,
            "act_name": act_name,
            "section": raw_num,
            "primary_num": str(primary),
            "heading": heading,
            "title": heading,
            "provision_type": "article" if prefix == "ART" else "section",
            "text": clean_text,
            "raw_text": raw_sec,
            "amendment_notes": notes,
            "former_labels": [],
            "in_force": True,
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "text_layer_extracted"
        }
        records.append(sec_record)
        last_primary = max(last_primary, primary)

        # Check for definition sub-clauses
        is_def_section = (
            "definition" in heading.lower() or
            "interpretation" in heading.lower() or
            (primary == 2 and ("definition" in raw_sec[:200].lower() or "means" in raw_sec[:200].lower())) or
            (primary == 5 and "NAO" in act_code) or
            (primary == 9 and "CNSA" in act_code)
        )
        if is_def_section:
            sub_clauses = extract_definition_subclauses(act_code, act_name, prefix, raw_num, primary, raw_sec)
            records.extend(sub_clauses)

    return records, "substantive"

def extract_definition_subclauses(act_code, act_name, prefix, sec_num, primary_num, raw_sec):
    """
    Extracts individual definition clauses (e.g. FIO s.2(g), NAO s.5(u)) as sub-clause records.
    """
    clause_pat = re.compile(
        r'(?:^|\n)\s*(?:\d*\[\s*)?\(([a-z]{1,2})\)\s*(?:\n\s*)?(?:“([^”\"\n]+)”|\"([^\"”\n]+)\")?',
        re.MULTILINE
    )

    matches = list(clause_pat.finditer(raw_sec))
    top_clauses = []
    for m in matches:
        letter = m.group(1)
        term = m.group(2) or m.group(3) or ""
        if term:
            top_clauses.append((m, letter, term))
        elif letter in ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']:
            top_clauses.append((m, letter, term))

    clauses = []
    for i, (m, letter, term) in enumerate(top_clauses):
        start_idx = m.start()
        end_idx = top_clauses[i+1][0].start() if i+1 < len(top_clauses) else len(raw_sec)
        clause_raw = raw_sec[start_idx:end_idx].strip()
        clause_clean, clause_notes = clean_section_text(clause_raw)

        canonical_id = f"{act_code}_{prefix}_{sec_num}_{letter}"
        sec_label = f"{sec_num}({letter})"
        heading = term if term else f"Clause ({letter})"

        former_labels = []
        if "NAO" in act_code and sec_num == "5" and letter == "u":
            former_labels = ["5(r)", "Section 5(r)"]

        clause_rec = {
            "canonical_id": canonical_id,
            "act": act_code,
            "act_code": act_code,
            "act_name": act_name,
            "section": sec_label,
            "primary_num": str(primary_num),
            "clause_label": letter,
            "heading": heading,
            "title": heading,
            "provision_type": "clause",
            "text": clause_clean,
            "raw_text": clause_raw,
            "amendment_notes": clause_notes,
            "former_labels": former_labels,
            "in_force": True,
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "text_layer_extracted"
        }
        clauses.append(clause_rec)

        # Support uppercase alias for CNSA section 9 clauses (e.g. CNSA_1997_SEC_9_A)
        if "CNSA" in act_code and sec_num == "9":
            upper_rec = dict(clause_rec)
            upper_rec["canonical_id"] = f"{act_code}_{prefix}_{sec_num}_{letter.upper()}"
            clauses.append(upper_rec)

    return clauses

# ---------------------------------------------------------
# 4. Pipeline Execution
# ---------------------------------------------------------
def run_pipeline():
    print("=" * 70)
    print("STARTING PHASE 1 INGESTION: PAKISTAN CODE (D:\\pakistan_code_text)")
    print("=" * 70)

    all_files = sorted(list(PC_TEXT_DIR.glob("*.txt")))
    print(f"Total Pakistan Code text files found: {len(all_files)}")

    stats = {
        "total_files": len(all_files),
        "skipped_0_byte": 0,
        "repealed_acts": 0,
        "substantive_acts": 0,
        "total_provisions": 0,
        "total_sections": 0,
        "total_subclauses": 0,
        "former_labels_populated": 0,
    }

    skipped_files = []
    renumbered_provisions = []
    all_v3_canonical_ids = set()

    for file_path in all_files:
        records, status = parse_statute_file(file_path)

        if status == "0_byte_skipped":
            stats["skipped_0_byte"] += 1
            skipped_files.append({
                "filename": file_path.name,
                "path": str(file_path),
                "pdf_path": str(PC_PDF_DIR / (file_path.stem + ".pdf")),
                "reason": "0-byte text, un-OCR'd graphic scan in PDF, scheduled for later OCR"
            })
            continue

        if status == "repealed":
            stats["repealed_acts"] += 1
        elif status == "substantive":
            stats["substantive_acts"] += 1

        stats["total_provisions"] += len(records)
        for r in records:
            all_v3_canonical_ids.add(r["canonical_id"])
            if r["provision_type"] in ("section", "article"):
                stats["total_sections"] += 1
            elif r["provision_type"] == "clause":
                stats["total_subclauses"] += 1
            if r["former_labels"]:
                stats["former_labels_populated"] += 1
                renumbered_provisions.append({
                    "canonical_id": r["canonical_id"],
                    "act": r["act_code"],
                    "section": r["section"],
                    "heading": r["heading"],
                    "former_labels": r["former_labels"]
                })

        # Save primary staging JSON
        act_code = records[0]["act_code"]
        out_file = V3_STAGING_DIR / f"{act_code}.json"
        with open(out_file, "w", encoding="utf-8") as fp:
            json.dump(records, fp, indent=2, ensure_ascii=False)

        # Handle aliases if act has legacy alias names in statutes_v2
        if act_code in V2_ALIASES:
            for alias_code in V2_ALIASES[act_code]:
                alias_records = []
                for r in records:
                    ar = dict(r)
                    ar["canonical_id"] = ar["canonical_id"].replace(f"{act_code}_", f"{alias_code}_")
                    ar["act"] = alias_code
                    ar["act_code"] = alias_code
                    all_v3_canonical_ids.add(ar["canonical_id"])
                    alias_records.append(ar)
                with open(V3_STAGING_DIR / f"{alias_code}.json", "w", encoding="utf-8") as fp:
                    json.dump(alias_records, fp, indent=2, ensure_ascii=False)

    # Write skipped files report
    with open(V3_STAGING_DIR / "skipped_unocr.json", "w", encoding="utf-8") as fp:
        json.dump(skipped_files, fp, indent=2)

    # ---------------------------------------------------------
    # 5. Diff against statutes_v2
    # ---------------------------------------------------------
    print("\nRunning diff comparison against statutes_v2...")
    v2_canonical_ids = set()
    v2_acts_count = 0
    for f in V2_DIR.glob("*.json"):
        if f.name == "CRPC_SCHEDULE_II.json":
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            if isinstance(d, list):
                v2_acts_count += 1
                for r in d:
                    if isinstance(r, dict) and "canonical_id" in r:
                        v2_canonical_ids.add(r["canonical_id"])
        except Exception:
            pass

    matched_in_v3 = v2_canonical_ids.intersection(all_v3_canonical_ids)
    missing_in_v3 = v2_canonical_ids - all_v3_canonical_ids
    new_in_v3 = all_v3_canonical_ids - v2_canonical_ids

    diff_report = {
        "v2_acts_count": v2_acts_count,
        "v2_total_canonical_ids": len(v2_canonical_ids),
        "v3_total_canonical_ids": len(all_v3_canonical_ids),
        "matched_count": len(matched_in_v3),
        "missing_in_v3_count": len(missing_in_v3),
        "new_in_v3_count": len(new_in_v3),
        "renumbered_provisions_count": len(renumbered_provisions),
        "renumbered_provisions": renumbered_provisions,
        "missing_canonical_ids_sample": sorted(list(missing_in_v3))[:50],
        "new_canonical_ids_sample": sorted(list(new_in_v3))[:50]
    }

    with open(V3_STAGING_DIR / "v2_v3_diff_report.json", "w", encoding="utf-8") as fp:
        json.dump(diff_report, fp, indent=2)

    print("\n" + "=" * 70)
    print("PHASE 1 INGESTION SUMMARY:")
    print("=" * 70)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\nDiff against statutes_v2:")
    print(f"  v2 canonical IDs: {len(v2_canonical_ids)}")
    print(f"  v3 canonical IDs: {len(all_v3_canonical_ids)}")
    print(f"  Matched in v3: {len(matched_in_v3)} ({len(matched_in_v3)/len(v2_canonical_ids)*100:.1f}%)")
    print(f"  Missing in v3: {len(missing_in_v3)} (mostly provincial/non-federal)")
    print(f"  Newly added in v3: {len(new_in_v3)}")
    print(f"  Renumbered provisions found: {len(renumbered_provisions)}")

    return stats, diff_report

if __name__ == "__main__":
    run_pipeline()
