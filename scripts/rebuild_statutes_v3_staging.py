import os
import sys
import json
import re
from pathlib import Path
from collections import defaultdict, Counter

ROOT_DIR = Path(r"d:\lawyer-Backend")
PC_TEXT_DIR = Path(r"D:\pakistan_code_text")
V2_DIR = ROOT_DIR / "data" / "statutes_v2"
V3_STAGING_DIR = ROOT_DIR / "data" / "statutes_v3_staging"
REPORTS_DIR = ROOT_DIR / "reports"

V3_STAGING_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------
# Canonical Act Codes & Mappings
# ---------------------------------------------------------
V2_PRIMARY_MAP = {
    'Financial Institutions (Recovery of Finances) Ordinance, 2001.txt': 'FIO_2001',
    'National Accountability Ordinance, 1999.txt': 'NAO_1999',
    'Pakistan Penal Code (PPC),1860 (Under Review).txt': 'PPC_1860',
    'Code of Civil Procedure (CPC) , 1908 (Under Review).txt': 'CPC_1908',
    'Code of Criminal Procedure (CrPC), 1898 (Under Review).txt': 'CRPC_1898',
    'Constitution of the Islamic Republic of Pakistan.txt': 'CONST_1973',
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
    'Companies Ordinance, 1984 (Repealed by Act XIX of 2017).txt': 'COMPANIES_1984',
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
}

ARTICLE_ACTS = {'CONST_1973', 'QSO_1984', 'POLICE_ORDER_2002', 'PROHIBITION_HADD_1979'}

REPLACED_CROSSWALK = {
    "COMPANIES_2017": (["COMPANIES_1984 (s.509(1))"], None),
    "COMPANIES_1984": (["COMPANIES_1913 (s.508)"], "COMPANIES_2017 (s.509(1))"),
    "ITO_2001": (["ITO_1979 (s.239(1))"], None),
    "SALES_TAX_1990": (["SALES_TAX_1951 (s.75(1))"], None),
    "FIO_2001": ([
        "Banking Companies (Recovery of Loans, Advances, Credits and Finances) Act, 1997 (s.29(1))",
        "BANKING_TRIBUNALS_1984 (s.29(1))",
        "BANKING_RECOVERY_1979 (s.29(1))"
    ], None),
    "NAO_1999": (["EHTESAB_1997 (s.35(1))"], None),
    "ELECTIONS_ACT_2017": (["ROPA_1976 (s.241(1))", "POLITICAL_PARTIES_2002 (s.241(1))", "ELECTORAL_ROLLS_1974 (s.241(1))"], None),
    "IRA_2012": (["IRA_2008 (s.87)", "IRO_2002 (s.87)", "IRO_1969 (s.87)"], None),
    "JUVENILE_JUSTICE_2018": (["JJSO_2000 (s.23)"], None),
    "ARBITRATION_2011": (["Arbitration (Protocol and Convention) Act, 1937 (s.11(1))", "Recognition and Enforcement Ordinance, 1948 (s.11(1))"], None),
}

# Load relettered mappings
relettered_path = REPORTS_DIR / "relettered.json"
RELETTERED_MAP = {}
if relettered_path.exists():
    try:
        with open(relettered_path, "r", encoding="utf-8") as fp:
            for item in json.load(fp):
                key = (item["act"], item["new_label"])
                RELETTERED_MAP[key] = [item["old_label"]]
    except Exception:
        pass

# Always ensure NAO 5(u) mapping
RELETTERED_MAP[("NAO_1999", "5(u)")] = ["5(r)", "Section 5(r)"]

# Load domain mapping
domain_mapping_path = REPORTS_DIR / "act_domain_mapping.json"
DOMAIN_MAP = {}
if domain_mapping_path.exists():
    try:
        with open(domain_mapping_path, "r", encoding="utf-8") as fp:
            DOMAIN_MAP = json.load(fp)
    except Exception:
        pass


def clean_section_text(raw_text):
    """Clean section text, moving footnotes and removing headers/footers without eating substantive digits."""
    re_page_footer = re.compile(r'^\s*Page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE)
    re_gazette_header = re.compile(r'^\s*(?:THE\s+GAZETTE\s+OF\s+PAKISTAN|EXTRAORDINARY|PART\s+[IVX]+)\s*$', re.IGNORECASE)
    re_running_header = re.compile(r'^\s*(?:Chapter|Part)\s+[IVX0-9]+.*?_{3,}\s*$', re.IGNORECASE)
    re_page_num_alone = re.compile(r'^\s*\d{1,4}\s*$')
    re_footnote_line = re.compile(
        r'^\s*\d+\s*(?:\[\s*\d*\s*\]\s*)?(?:Ins\.|Subs\.|Added|Omitted|Deleted|New\s+section|Replaced|For\s+the|The\s+words|Words?|Clause|Sub-section|Section|Proviso|Paragraph|Full\s+stop|Comma|In\s+section|Under\s+the|\*|Ommited)\b',
        re.IGNORECASE
    )

    lines = raw_text.splitlines()
    clean_lines = []
    amendment_notes = []
    in_footnote_block = False

    for line in lines:
        s_line = line.strip()
        if not s_line:
            clean_lines.append("")
            in_footnote_block = False
            continue

        if re_page_footer.match(s_line) or re_gazette_header.match(s_line) or re_running_header.match(s_line) or re_page_num_alone.match(s_line):
            continue

        if re_footnote_line.match(s_line):
            amendment_notes.append(s_line)
            in_footnote_block = True
            continue
        elif in_footnote_block and (s_line.startswith("(") or "Ordinance" in s_line or "Act" in s_line or "s." in s_line or "w.e.f." in s_line) and not s_line.startswith("Provided"):
            if amendment_notes:
                amendment_notes[-1] += " " + s_line
            else:
                amendment_notes.append(s_line)
            continue
        else:
            in_footnote_block = False

        clean_lines.append(line)

    text = "\n".join(clean_lines)

    # 1. Disentangle footnote markers from preceding words/numbers:
    # (a) singular section/article/rule/clause/order + number + footnote: 'section 1215[' -> 'section 121 ['
    # Note: Use singular keyword so plural nouns like "rules 32[" are treated as footnote 32, not "rule 3"
    text = re.sub(r'\b(section|article|sub-section|rule|order|clause)\s+(\d{1,4})(\d{1,2})\[', r'\1 \2 [', text, flags=re.IGNORECASE)
    # (b) 4-digit years: '19731[' -> '1973 ['
    text = re.sub(r'\b(18\d\d|19\d\d|20\d\d)(\d{1,2})\[', r'\1 [', text)
    # (c) words directly touching footnote digit: 'Commissioner1[' -> 'Commissioner ['
    text = re.sub(r'([a-zA-Z])(\d{1,2})\[', r'\1 [', text)

    # 2. Footnote markers before [: e.g. ' 5[' -> ' [' (ONLY digits directly glued to [)
    text = re.sub(r'(?:^|(?<=[\s\(\,\.\;\:\—\-\"]))(\d{1,3})\[', ' [', text)

    # 3. Strip omission markers [* * *] or [***] or [   ]
    text = re.sub(r'\[\s*\*+\s*\]', '', text)
    text = re.sub(r'\[\s*\]', '', text)

    # 4. Unwrap amended text: [something] -> something
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)
    text = text.replace("[", "").replace("]", "")
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r',\s*or\s*,', ' or ', text)

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
    cleaned_text = re.sub(r'\bwilful\b', 'willful', cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
    cleaned_text = re.sub(r',\s*,+', ',', cleaned_text)
    cleaned_text = re.sub(r'\s*,\s*\.', '.', cleaned_text)

    return cleaned_text, amendment_notes


def get_canonical_act_code(filename):
    if filename in V2_PRIMARY_MAP:
        return V2_PRIMARY_MAP[filename]

    name = filename.replace('.txt', '')
    # Strip known editorial annotations in parentheses
    name_clean = re.sub(r'\s*\((?:Under Review|Repealed[^)]*|Same as on[^)]*)\)', '', name, flags=re.I)
    m_year = re.search(r'\b(18\d\d|19\d\d|20\d\d)\b', name_clean)
    year = m_year.group(1) if m_year else ""

    is_ord = bool(re.search(r'\bOrdinance\b', name_clean, flags=re.I))
    name_clean = re.sub(r'\b(18\d\d|19\d\d|20\d\d)\b', '', name_clean)
    name_clean = re.sub(r'\b(Act|Ordinance|Order|Code|Regulations)\b', '', name_clean, flags=re.I)

    words = re.findall(r'[A-Za-z0-9]+', name_clean)
    stop_words = {'the', 'of', 'and', 'in', 'for', 'a', 'an', 'to', 'on', 'with', 'by'}
    sig_words = [w.upper() for w in words if w.lower() not in stop_words]
    slug = "_".join(sig_words[:5])
    if is_ord and not slug.endswith("ORD"):
        slug = f"{slug}_ORD"
    if year:
        return f"{slug}_{year}"
    return slug


def parse_and_strip_toc(act_code, content):
    """
    Identifies and records Table of Contents (for G2), then returns (toc_entries, substantive_text).
    """
    has_toc = False
    sub_start = 0
    toc_entries = []

    contents_pos = content.find("CONTENTS")

    if act_code == "CUSTOMS_1969" and contents_pos != -1:
        m_preamble = re.search(r'\b(An\s+Act\s+to\s+consolidate|WHEREAS\s+it\s+is\s+expedient|Preamble)\b', content[contents_pos:], re.I)
        if m_preamble:
            has_toc = True
            sub_start = contents_pos + m_preamble.start()
            toc_text = content[contents_pos:sub_start]
            raw_lines = [l.strip() for l in toc_text.splitlines() if l.strip()]
            sec_pat = re.compile(r'^([0-9]{1,3}[A-Z]{0,4})\.?$')
            i = 0
            while i < len(raw_lines):
                line = raw_lines[i]
                if line.upper() in ["CONTENTS", "SECTION", "PAGE", "NO.", "THE CUSTOMS ACT, 1969", "THE CUSTOMS ACT,1969"] or re.match(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$', line, re.I) or re.match(r'^CHAPTER\s+[IVXLCDM]+', line, re.I):
                    i += 1
                    continue
                m = sec_pat.match(line)
                if m:
                    sec_num = m.group(1)
                    i += 1
                    desc_parts = []
                    while i < len(raw_lines):
                        nxt = raw_lines[i]
                        if nxt.isdigit() and int(nxt) <= 350:
                            i += 1
                            break
                        if sec_pat.match(nxt):
                            break
                        desc_parts.append(nxt)
                        i += 1
                    desc = " ".join(desc_parts)
                    toc_entries.append((sec_num, desc))
                else:
                    i += 1
            return toc_entries, content[sub_start:]

    elif act_code == "CONST_1973":
        m_preamble = re.search(r'\bPREAMBLE\b', content, re.IGNORECASE)
        if m_preamble:
            has_toc = True
            sub_start = m_preamble.start()
    else:
        m1_list = list(re.finditer(r'(?:^|\n)\s*(?:[\*\#\d\[\]\s]*)\b1\.\s+(?:Short\s+title|Title)', content, re.IGNORECASE))
        if len(m1_list) > 1:
            has_toc = True
            sub_start = m1_list[1].start()
        elif contents_pos != -1:
            m_enact = re.search(r'(?:It\s+is\s+(?:hereby\s+)?enacted\s+as\s+follows|NOW,\s+THEREFORE|Preamble\.\s*WHEREAS)', content[contents_pos:], re.IGNORECASE)
            if m_enact:
                has_toc = True
                sub_start = contents_pos + m_enact.end()
            elif len(m1_list) == 1 and m1_list[0].start() > contents_pos:
                has_toc = True
                sub_start = m1_list[0].start()

    if has_toc:
        toc_text = content[:sub_start]
        toc_pat = re.compile(r'(?:^|\n)\s*([0-9]{1,4}[A-Z]{0,2})\.\s*\n?\s*([^\n\r]+)')
        for m in toc_pat.finditer(toc_text):
            num = m.group(1).strip()
            title = m.group(2).strip()
            if not title.lower().startswith("page ") and not "chapter" in title.lower() and not "part" in title.lower():
                toc_entries.append((num, title))
    else:
        sub_start = 0

    substantive_text = content[sub_start:]
    return toc_entries, substantive_text


def split_schedules(act_code, sub_text):
    """
    Separates substantive sections from Schedules appended at the end.
    Only splits on standalone Schedule headers that occur in the second half of the document.
    """
    pat = re.compile(
        r'(?:^|\n)\s*(?:\d*\[\s*)?(?:(?:THE\s+)?(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH|[0-9]+(?:st|nd|rd|th)?)\s+SCHEDULE|(?:THE\s+)?SCHEDULE\s+(?:[IVXLCDM]+|[0-9]+)|(?:THE\s+)?SCHEDULE\s*$)',
        re.IGNORECASE
    )
    matches = list(pat.finditer(sub_text))
    for m in matches:
        if m.start() > len(sub_text) * 0.45:
            pre = sub_text[max(0, m.start()-60):m.start()].strip().lower()
            last_word = pre.split()[-1] if pre.split() else ''
            if last_word in ['and', 'or', 'in', 'to', 'under', 'the', 'a', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth', 'section', 'sub-section', 'clause', 'specified', 'from', 'of', 'with']:
                continue
            line = sub_text[m.start():sub_text.find('\n', m.start()+1)].strip()
            if line.endswith(('.]', '.)', ']', ')', ',')):
                continue
            return sub_text[:m.start()], sub_text[m.start():]
    return sub_text, ""


def extract_definition_subclauses(act_code, act_name, prefix, sec_num, primary_num, raw_sec):
    """Extracts sub-clauses for definition sections (e.g. FIO s.2(g), NAO s.5(u))."""
    clause_pat = re.compile(
        r'(?:^|\n)\s*(?:\d*\[\s*)?\(([a-z]{1,2})\)\s*(?:\n\s*)?(?:“([^”\"\n]+)”|\"([^\"”\n]+)\")?',
        re.MULTILINE
    )

    matches = list(clause_pat.finditer(raw_sec))
    top_clauses = []
    for m in matches:
        letter = m.group(1)
        term = m.group(2) or m.group(3) or ""
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

        former_labels = RELETTERED_MAP.get((act_code, sec_label), [])

        domain_info = DOMAIN_MAP.get(act_code, {})
        domain = domain_info.get("domain", "other")
        forum = domain_info.get("forum", "Court")

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
            "domain": domain,
            "forum": forum,
            "provision_type": "clause",
            "text": clause_clean,
            "raw_text": clause_raw,
            "amendment_notes": clause_notes,
            "former_labels": former_labels,
            "in_force": False if act_code == "COMPANIES_1984" else True,
            "omitted": False,
            "historical": (act_code == "COMPANIES_1984"),
            "source": "pakistan_code",
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "ingested_unreviewed",
            "text_as_of": "current amended text as of the Pakistan Code scrape date"
        }
        clauses.append(clause_rec)

    return clauses


def parse_statute_file(file_path):
    filename = file_path.name
    size = file_path.stat().st_size

    if size == 0:
        return None, [], "0_byte_skipped"

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 47 Repealed Acts
    if size < 600 and ("THIS LAW HAS BEEN REPEALED" in content or "repeal" in content.lower() or "repealed" in filename.lower()):
        m_rep = re.search(r'\((Repealed?[^\)]+)\)', filename, re.I)
        rep_note = m_rep.group(1) if m_rep else content.strip()
        act_code = get_canonical_act_code(filename)
        domain_info = DOMAIN_MAP.get(act_code, {})
        domain = domain_info.get("domain", "other")
        forum = domain_info.get("forum", "Court")

        record = {
            "canonical_id": f"{act_code}_REPEALED",
            "act": act_code,
            "act_code": act_code,
            "act_name": filename.replace('.txt', ''),
            "section": "repealed",
            "primary_num": "0",
            "heading": "Repealed",
            "title": "Repealed Enactment",
            "domain": domain,
            "forum": forum,
            "provision_type": "repeal_notice",
            "text": "THIS LAW HAS BEEN REPEALED",
            "raw_text": content.strip(),
            "amendment_notes": [f"THIS LAW HAS BEEN REPEALED: {rep_note}"],
            "former_labels": [],
            "in_force": False,
            "historical": False,
            "source": "pakistan_code",
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "ingested_unreviewed",
            "text_as_of": "current amended text as of the Pakistan Code scrape date"
        }
        return [record], [], "repealed"

    # Substantive Act
    act_code = get_canonical_act_code(filename)
    act_name = filename.replace('.txt', '')
    prefix = "ART" if act_code in ARTICLE_ACTS else "SEC"
    domain_info = DOMAIN_MAP.get(act_code, {})
    domain = domain_info.get("domain", "other")
    forum = domain_info.get("forum", "Court")

    # 1. Extract and Strip Table of Contents
    toc_entries, substantive_text = parse_and_strip_toc(act_code, content)
    toc_nums = set(t[0] for t in toc_entries) if toc_entries else set()

    # 2. Split Schedules from Body
    body_text, schedules_text = split_schedules(act_code, substantive_text)

    # Improved regex supporting nested brackets, curly braces, asterisks, footnotes, and OCR typo (4l7)
    sec_num_pat = re.compile(
        r'(?:^|\n)\s*(?:[\*\#\{\[\d\s]*)\b([0-9]{1,4}[A-Za-z]{0,2}(?:-[A-Za-z]{1,2})?|[0-9]+l[0-9]+)\s*(?:\.|\—|\:|\.\s*[\—\-])\s*(?![\*\s]*(?:Ins\.|Subs\.|Added|Omitted|Deleted|New\s+section|Replaced|ibid\b))([^\n\r]*)'
    )

    records = []
    seen_sec_ids = set()
    matches = list(sec_num_pat.finditer(body_text))

    cross_entry = REPLACED_CROSSWALK.get(act_code, ([], None))
    supersedes = cross_entry[0]
    superseded_by = cross_entry[1]

    if not matches:
        clean_text, notes = clean_section_text(body_text)
        record = {
            "canonical_id": f"{act_code}_FULL",
            "act": act_code,
            "act_code": act_code,
            "act_name": act_name,
            "section": "full",
            "primary_num": "1",
            "heading": act_name,
            "title": act_name,
            "domain": domain,
            "forum": forum,
            "provision_type": "article" if prefix == "ART" else "section",
            "text": clean_text,
            "raw_text": body_text.strip(),
            "amendment_notes": notes,
            "former_labels": [],
            "supersedes": supersedes,
            "superseded_by": superseded_by,
            "in_force": True,
            "omitted": False,
            "historical": False,
            "source": "pakistan_code",
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "ingested_unreviewed",
            "text_as_of": "current amended text as of the Pakistan Code scrape date"
        }
        return [record], toc_entries, "substantive"

    for i, m in enumerate(matches):
        if m.start() > 0:
            pre = body_text[max(0, m.start()-60):m.start()].strip().lower()
            last_word = pre.split()[-1] if pre.split() else ''
            if last_word in ['section', 'sub-section', 'article', 'clause', 'order', 'rule', 'under', 'read', 'with', 'and', 'or', 'of', 'in', 'to', 'from', 'as', 'than']:
                continue

        raw_num = re.sub(r'(\d)l(\d)', r'\g<1>1\g<2>', m.group(1)).upper()
        heading_line = m.group(2).strip()

        # Normalize prepended footnote digits if present (verified against sequence)
        if len(raw_num) >= 4 and raw_num[0] in '123456789':
            sub = raw_num[1:]
            cand_sec = int(sub) if sub.isdigit() else 0
            if sub in toc_nums:
                raw_num = sub
            elif (act_code == 'PPC_1860' and sub.isdigit() and int(sub) <= 511) or (act_code == 'CRPC_1898' and sub.isdigit() and int(sub) <= 565):
                prev_p = int(records[-1]["primary_num"]) if records and records[-1].get("primary_num", "").isdigit() else 0
                if prev_p > 0 and abs(cand_sec - prev_p) <= 2:
                    raw_num = sub
        if act_code == 'CONST_1973' and raw_num == '11' and m.start() < 5000:
            raw_num = '1'

        heading = re.split(r'[\.\—\-\:]', heading_line)[0].strip()

        m_num = re.match(r'^(\d+)', raw_num)
        primary = int(m_num.group(1)) if m_num else 0

        # Filter out 4-digit years matching as sections (e.g. 1940, 1951)
        if primary >= 1800 and primary <= 2099 and raw_num not in toc_nums:
            continue
        if primary > 650 and raw_num not in toc_nums:
            continue

        start_pos = m.start()
        end_pos = matches[i+1].start() if i+1 < len(matches) else len(body_text)
        raw_sec = body_text[start_pos:end_pos].strip()

        if not heading or heading.lower().startswith("section") or heading.lower().startswith("article"):
            for line in raw_sec.splitlines():
                s = line.strip()
                if s and not s.startswith(raw_num) and not s.isdigit() and len(s) > 3:
                    heading = re.split(r'[\.\—\-\:]', s)[0].strip()
                    break
        if not heading:
            heading = f"{'Article' if prefix == 'ART' else 'Section'} {raw_num}"

        clean_text, notes = clean_section_text(raw_sec)

        if act_code == 'SALES_TAX_1990' and raw_num == '11':
            heading = "Assessment of tax and recovery of tax not levied or short levied [Omitted]"
            clean_text = "11. *** [Section 11 omitted by the Finance Act, 2024 (earlier substituted by Finance Act 2012; previously Assessment of tax and recovery of tax not levied or short levied or erroneously refunded)]."

        clean_low = clean_text.strip().lower()
        is_omitted_stub = (
            clean_low in ["omitted", "repealed", "[omitted]", "[repealed]", "[omitted].", "[repealed].", "***", "[***]"] or
            (len(clean_low) < 220 and any(w in clean_low for w in ["omitted by", "repealed by", "rep. by", "deleted by", "[omitted", "[repealed", "omitted."])) or
            (act_code == 'SALES_TAX_1990' and raw_num == '11')
        )

        # Gate G3: filter out TOC leftovers where cleaned text equals only heading or is too short without being an omitted stub
        if not is_omitted_stub and (len(clean_text.strip()) <= len(heading.strip()) + 5 or clean_text.strip().lower() == heading.strip().lower() or len(clean_text.strip()) < 15):
            continue

        canonical_id = f"{act_code}_{prefix}_{raw_num}"

        # Gate G1: Ensure zero duplicate canonical IDs within act
        if canonical_id in seen_sec_ids:
            continue
        seen_sec_ids.add(canonical_id)

        former_labels = RELETTERED_MAP.get((act_code, raw_num), [])

        is_historical = (act_code == "COMPANIES_1984")
        in_force_val = False if (is_historical or is_omitted_stub) else True

        sec_record = {
            "canonical_id": canonical_id,
            "act": act_code,
            "act_code": act_code,
            "act_name": act_name,
            "section": raw_num,
            "primary_num": str(primary),
            "heading": heading,
            "title": heading,
            "domain": domain,
            "forum": forum,
            "provision_type": "article" if prefix == "ART" else "section",
            "text": clean_text,
            "raw_text": raw_sec,
            "amendment_notes": notes,
            "former_labels": former_labels,
            "supersedes": supersedes,
            "superseded_by": superseded_by,
            "in_force": in_force_val,
            "omitted": is_omitted_stub,
            "historical": is_historical,
            "source": "pakistan_code",
            "source_format": "txt",
            "jurisdiction": "federal",
            "tier": "ingested_unreviewed",
            "text_as_of": "current amended text as of the Pakistan Code scrape date"
        }
        records.append(sec_record)

        # Extract definition sub-clauses
        is_def_section = (
            (primary == 2 and ("FIO" in act_code or "CPC" in act_code or "COMPANIES" in act_code or "ITO" in act_code)) or
            (primary == 4 and "CRPC" in act_code) or
            (primary == 5 and "NAO" in act_code)
        )
        if is_def_section:
            sub_clauses = extract_definition_subclauses(act_code, act_name, prefix, raw_num, primary, raw_sec)
            for sc in sub_clauses:
                if sc["canonical_id"] not in seen_sec_ids:
                    seen_sec_ids.add(sc["canonical_id"])
                    records.append(sc)

    # 3. Parse Schedules (if any) using collision-free ID scheme
    if schedules_text:
        sch_matches = list(sec_num_pat.finditer(schedules_text))
        for i, m in enumerate(sch_matches):
            raw_num = m.group(1)
            heading_line = m.group(2).strip()
            heading = re.split(r'[\.\—\-\:]', heading_line)[0].strip() or f"Entry {raw_num}"
            start_pos = m.start()
            end_pos = sch_matches[i+1].start() if i+1 < len(sch_matches) else len(schedules_text)
            raw_entry = schedules_text[start_pos:end_pos].strip()

            clean_text, notes = clean_section_text(raw_entry)
            if len(clean_text.strip()) <= len(heading.strip()) + 5 or clean_text.strip().lower() == heading.strip().lower() or len(clean_text.strip()) < 15:
                continue

            sch_id = f"{act_code}_SCH_ENTRY_{raw_num}"
            if sch_id in seen_sec_ids:
                sch_id = f"{act_code}_SCH_ENTRY_{raw_num}_{i+1}"
            if sch_id in seen_sec_ids:
                continue
            seen_sec_ids.add(sch_id)

            sch_rec = {
                "canonical_id": sch_id,
                "act": act_code,
                "act_code": act_code,
                "act_name": act_name,
                "section": f"Schedule Entry {raw_num}",
                "primary_num": raw_num,
                "heading": heading,
                "title": heading,
                "domain": domain,
                "forum": forum,
                "provision_type": "schedule_entry",
                "text": clean_text,
                "raw_text": raw_entry,
                "amendment_notes": notes,
                "former_labels": [],
                "supersedes": supersedes,
                "superseded_by": superseded_by,
                "in_force": False if act_code == "COMPANIES_1984" else True,
                "omitted": False,
                "historical": (act_code == "COMPANIES_1984"),
                "source": "pakistan_code",
                "source_format": "txt",
                "jurisdiction": "federal",
                "tier": "ingested_unreviewed",
                "text_as_of": "current amended text as of the Pakistan Code scrape date"
            }
            records.append(sch_rec)

    return records, toc_entries, "substantive"


def ingest_legacy_records(existing_v3_ids):
    """
    Ingests the 957 v2-only IDs (CPC Orders, Limitation Act, provincial acts, court rules, CRPC_SCHEDULE_II).
    """
    print("\nIngesting legacy v2-only records...")
    legacy_records = []

    for fpath in V2_DIR.glob("*.json"):
        act_slug = fpath.stem
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            continue

        if isinstance(data, list):
            for r in data:
                cid = r.get("canonical_id")
                if cid and cid not in existing_v3_ids:
                    clean_text, notes = clean_section_text(r.get("text", ""))
                    rec = dict(r)
                    rec_act = rec.get("act_code") or rec.get("act") or act_slug
                    dom_info = DOMAIN_MAP.get(rec_act, {})
                    rec["domain"] = rec.get("domain") or dom_info.get("domain", "other")
                    rec["forum"] = rec.get("forum") or dom_info.get("forum", "Court")
                    rec["text"] = clean_text
                    rec["raw_text"] = r.get("text", "")
                    rec["amendment_notes"] = notes
                    rec["source"] = "statutes_v2_legacy"
                    rec["source_format"] = "json"
                    rec["tier"] = "ingested_unreviewed"
                    rec["text_as_of"] = "statutes_v2_baseline"
                    rec["in_force"] = True
                    rec["omitted"] = False
                    rec["historical"] = False
                    rec["supersedes"] = []
                    rec["superseded_by"] = None
                    legacy_records.append(rec)
                    existing_v3_ids.add(cid)
        elif isinstance(data, dict) and act_slug == "CRPC_SCHEDULE_II":
            for off_key, off_val in data.items():
                cid = f"CRPC_1898_SCH_II_{off_key.replace('-', '_')}"
                if cid not in existing_v3_ids:
                    txt = json.dumps(off_val, indent=2) if isinstance(off_val, dict) else str(off_val)
                    rec = {
                        "canonical_id": cid,
                        "act": "CRPC_1898",
                        "act_code": "CRPC_1898",
                        "act_name": "Code of Criminal Procedure, 1898",
                        "section": f"Schedule II for Section {off_key}",
                        "primary_num": off_key,
                        "heading": f"Schedule II Offence Classification: Section {off_key}",
                        "title": f"Schedule II Offence: Section {off_key}",
                        "domain": "criminal",
                        "forum": "Court of Session / Judicial Magistrate / High Court",
                        "provision_type": "schedule_entry",
                        "text": txt,
                        "raw_text": txt,
                        "amendment_notes": [],
                        "former_labels": [],
                        "supersedes": [],
                        "superseded_by": None,
                        "in_force": True,
                        "omitted": False,
                        "historical": False,
                        "source": "statutes_v2_legacy",
                        "source_format": "json",
                        "tier": "ingested_unreviewed",
                        "text_as_of": "statutes_v2_baseline"
                    }
                    legacy_records.append(rec)
                    existing_v3_ids.add(cid)

    # Save legacy records into a dedicated staging file
    with open(V3_STAGING_DIR / "statutes_v2_legacy.json", "w", encoding="utf-8") as fp:
        json.dump(legacy_records, fp, indent=2, ensure_ascii=False)

    print(f"Ingested {len(legacy_records)} legacy records into data/statutes_v3_staging/statutes_v2_legacy.json")
    return legacy_records


def run():
    print("=" * 70)
    print("REBUILDING STATUTES V3 STAGING (PHASE 1B)")
    print("=" * 70)

    # Clear previous staging files
    for f in V3_STAGING_DIR.glob("*.json"):
        try:
            f.unlink()
        except Exception:
            pass

    all_files = sorted(list(PC_TEXT_DIR.glob("*.txt")))
    print(f"Total Pakistan Code text files: {len(all_files)}")

    all_canonical_ids = set()
    total_records = 0
    all_toc_reports = {}
    g3_violations = 0

    for file_path in all_files:
        records, toc_entries, status = parse_statute_file(file_path)
        if not records:
            continue

        act_code = records[0]["act_code"]

        # Track TOC entries for Gate G2
        if toc_entries:
            parsed_nums = set(r["section"] for r in records)
            toc_nums = set(t[0] for t in toc_entries)
            matched = toc_nums & parsed_nums
            missing = toc_nums - parsed_nums
            extra = parsed_nums - toc_nums
            all_toc_reports[act_code] = {
                "act_name": records[0]["act_name"],
                "toc_count": len(toc_entries),
                "parsed_count": len(records),
                "matched_count": len(matched),
                "missing_count": len(missing),
                "missing_sections": sorted(list(missing), key=lambda x: (len(x), x))[:20],
                "extra_sections_count": len(extra)
            }

        # Check Gate G3 violations (TOC leftovers on active records)
        for r in records:
            if not r.get("omitted", False) and (len(r["text"].strip()) <= len(r["heading"].strip()) + 5 or r["text"].strip().lower() == r["heading"].strip().lower()):
                g3_violations += 1

        # Check duplicate canonical_ids
        for r in records:
            cid = r["canonical_id"]
            if cid in all_canonical_ids:
                print(f"FATAL COLLISION DETECTED: {cid}")
            all_canonical_ids.add(cid)

        total_records += len(records)

        # Save to staging JSON
        out_path = V3_STAGING_DIR / f"{act_code}.json"
        with open(out_path, "w", encoding="utf-8") as fp:
            json.dump(records, fp, indent=2, ensure_ascii=False)

    print(f"\nPakistan Code Ingestion Complete: {total_records:,} provisions across {len(all_files)} files.")
    print(f"Unique canonical IDs from PC: {len(all_canonical_ids):,}")

    # Ingest legacy records
    legacy_recs = ingest_legacy_records(all_canonical_ids)
    total_records += len(legacy_recs)

    # Save Gate G2 TOC validation report
    with open(REPORTS_DIR / "toc_validation_report.json", "w", encoding="utf-8") as fp:
        json.dump(all_toc_reports, fp, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("GATES VALIDATION RESULTS")
    print("=" * 70)
    print(f"G1. Zero duplicate canonical IDs: {'PASS (0 duplicates)' if len(all_canonical_ids) == total_records else 'FAIL'}")
    print(f"    Final Unique Canonical ID Count: {len(all_canonical_ids):,}")
    print(f"G2. TOC Check: Saved report to reports/toc_validation_report.json ({len(all_toc_reports)} acts with TOC)")
    print(f"G3. No text equals only heading: {'PASS (0 violations)' if g3_violations == 0 else f'FAIL ({g3_violations} violations)'}")

if __name__ == "__main__":
    run()
