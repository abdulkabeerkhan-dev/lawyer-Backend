import os
import sys
import re
import csv
import glob
import unicodedata

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

csv.field_size_limit(100 * 1024 * 1024)

INPUT_DIR = r"D:\missing_gaps_verified\CSVs"
OUTPUT_DIR = r"D:\missing_gaps_verified\cleaned_CSVs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PORTAL_NAV_PATTERN = re.compile(
    r'(?i)^\s*(?:Please Wait\s+)?Home\s*\n\s*Word\s*&\s*Phrases\s*\n.*?(?:Search\s*\n|Case Law Search\s*\n)',
    re.DOTALL
)

PORTAL_FOOTER_PATTERN = re.compile(
    r'(?i)Copyrights\s*©?\s*202\d\s*by\s*Oratier\s*Technologies.*?(?:Help\s*FAQ\'?s\s*Sitemap|$)',
    re.DOTALL
)

MODAL_HEADER_PATTERN = re.compile(
    r'^[×\s]*Case Description\s*Bookmark this Case\s*',
    re.IGNORECASE
)

SEARCH_SNIPPET_HEADER_PATTERN = re.compile(
    r'(?i)^\s*Citation Name:\s*.*?\nBookmark this Case\s*\n',
    re.DOTALL
)

COURT_NORMALIZATION = {
    'LAHORE-HIGH-COURT-LAHORE': 'Lahore High Court',
    'LAHORE-HIGH-COURT': 'Lahore High Court',
    'LAHORE': 'Lahore High Court',
    'KARACHI-HIGH-COURT-SINDH': 'High Court of Sindh',
    'SINDH-HIGH-COURT': 'High Court of Sindh',
    'KARACHI': 'High Court of Sindh',
    'PESHAWAR-HIGH-COURT': 'Peshawar High Court',
    'PESHAWAR': 'Peshawar High Court',
    'QUETTA-HIGH-COURT': 'High Court of Balochistan',
    'QUETTA': 'High Court of Balochistan',
    'ISLAMABAD-HIGH-COURT': 'Islamabad High Court',
    'ISLAMABAD': 'Islamabad High Court',
    'SUPREME-COURT': 'Supreme Court of Pakistan',
    'FEDERAL-SHARIAT-COURT': 'Federal Shariat Court',
    'DHAKA-HIGH-COURT': 'High Court of Dacca',
    'DACCA': 'High Court of Dacca',
    'BAGHDAD-UL-JADID': 'High Court of Judicature Baghdad-ul-Jadid',
    'INCOME-TAX-APPELLATE-TRIBUNAL-PAKISTAN': 'Income Tax Appellate Tribunal Pakistan',
}

def deep_clean_text(text: str) -> str:
    if not text:
        return ""
    
    # 1. Unicode replacement character, soft hyphens & zero-width artifacts
    text = text.replace('\ufffd', ' ').replace('\xad', '')
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    
    # 2. Spaces normalization
    text = re.sub(r'[\u00a0\u2002\u2003\u2009\u202f]', ' ', text)
    
    # 3. Unicode dashes and hyphens -> ASCII hyphens / dashes (fixes black box glyphs in PDFs)
    text = re.sub(r'[\u2010\u2011\u2012\u2212]', '-', text)
    text = re.sub(r'[\u2013\u2014\u2015]', '--', text)
    
    # 4. Unicode quotes -> ASCII quotes (fixes black box glyphs in PDFs)
    text = re.sub(r'[\u2018\u2019\u201a\u201b\u2032\u0060\u00b4]', "'", text)
    text = re.sub(r'[\u201c\u201d\u201e\u201f\u2033]', '"', text)
    
    # 5. Arabic / Urdu script blocks (render as black blocks in Type 1 fonts)
    text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+', ' ', text)
    
    # 6. Possessives and contractions with ? (e.g. petitioner?s -> petitioner's, don?t -> don't)
    text = re.sub(r'\b([A-Za-z]+)\?(s|t|ll|ve|re|d|m)\b', r"\1'\2", text)
    
    # 7. Common broken OCR syllable wraps (govern?ment -> government)
    common_syllable_joins = {
        'government', 'circumstances', 'therefore', 'section', 'possession',
        'consideration', 'constitution', 'application', 'proceedings', 'property',
        'fundamental', 'respondent', 'jurisdiction', 'commissioner', 'provisions',
        'amendment', 'dissolution', 'consequently', 'appellant', 'prosecution',
        'according', 'assessment', 'contention', 'defendants'
    }
    
    def fix_word(m):
        w = m.group(0)
        pure = w.replace('?', '')
        if pure.lower() in common_syllable_joins:
            return pure
        return w.replace('?', '-')
    
    text = re.sub(r'\b[A-Za-z]{2,}\?[A-Za-z]{2,}\b', fix_word, text)
    
    # 8. Consecutive question mark runs (OCR margin leader dots or corruption)
    # If at end of line before outcome: S. G. D. ??? Revision dismissed
    text = re.sub(r'([A-Za-z\.\/\-0-9]+)\s*\?{2,}\s*([A-Za-z]+)', r'\1 -- \2', text)
    # General runs of 2+ question marks
    text = re.sub(r'\?{2,}', ' ', text)
    
    # Clean redundant spaces per line
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in text.split('\n')]
    return '\n'.join(lines).strip()

def clean_portal_artifacts(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 1. Strip modal headers
    text = MODAL_HEADER_PATTERN.sub('', text)
    text = SEARCH_SNIPPET_HEADER_PATTERN.sub('', text)
    
    # 2. Strip portal navigation blocks (whether at start, middle, or end)
    text = re.sub(r'(?i)(?:\n|^)\s*(?:Please Wait\s+)?Home\s*\n\s*Word\s*&\s*Phrases\s*\n.*?(?:Case Law Search|Search)\s*\n', '\n', text, flags=re.DOTALL)
    # If portal nav appears near the end without trailing Search
    text = re.sub(r'(?i)\n+Home\s*\n\s*Word\s*&\s*Phrases\s*\n.*$', '', text, flags=re.DOTALL)
    
    # 3. Strip copyright footers and maintenance banners
    text = re.sub(r'(?i)\n*Copyrights\s*©?\s*202\d\s*by\s*Oratier\s*Technologies.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'(?i)^.*?(?:Copyrights ©|Oratier Technologies|Help FAQ\'?s Sitemap).*$', '', text, flags=re.MULTILINE)
    
    # 4. Remove lingering standalone artifact lines
    lines = [l.strip() for l in text.split('\n')]
    cleaned_lines = []
    skip_noise_words = {
        'bookmark this case', 'please wait', 'case description', '×',
        'word & phrases', 'legal terms', 'maxims', 'saved citations',
        'head notes on cases with complete judgements', 'monthly journals',
        'new statutes', 'latest caselaws', 'case law search', "help faq's sitemap"
    }
    for l in lines:
        if l.lower() in skip_noise_words:
            continue
        cleaned_lines.append(l)
    text = '\n'.join(cleaned_lines).strip()

    # 5. Apply deep clean to remove black marks and corrupted question marks
    return deep_clean_text(text)



def parse_metadata_and_split(journal: str, year: str, case_idx: str, raw_title: str, raw_hn: str, raw_body: str):
    clean_hn_raw = clean_portal_artifacts(raw_hn)
    clean_body_raw = clean_portal_artifacts(raw_body)

    # 1. Parse Title, Canonical Citation, and Court from raw_title
    extracted_citation = ""
    extracted_parties = ""
    extracted_court = ""

    title_clean = raw_title.strip()
    m_title = re.match(r'^\s*(\d+)?\s*(\d{4})\s+([A-Za-z\(\)\.\s]+?)\s+(\d+)\s+(.*?)(?:\s*-\s*(.*))?$', title_clean)
    if m_title:
        _, yr, jn, pg, parties, court = m_title.groups()
        jn_norm = re.sub(r'\s+', '', jn).upper()
        extracted_citation = f"{yr} {jn_norm} {pg}"
        extracted_parties = parties.strip()
        if court:
            court_slug = court.strip().upper()
            extracted_court = COURT_NORMALIZATION.get(court_slug, court.strip().title())
    else:
        extracted_citation = f"{year} {journal} Case #{case_idx}"
        extracted_parties = title_clean

    # 2. Check if modal had valid case report
    is_complete = True
    if not clean_hn_raw or clean_hn_raw.startswith('Please Wait') or len(clean_hn_raw) < 150:
        is_complete = False

    extracted_bench = ""
    extracted_docket = ""
    extracted_date = ""
    headnotes = ""
    judgment_body = ""

    if is_complete:
        lines = [l.strip() for l in clean_hn_raw.split('\n') if l.strip()]
        
        # Extract metadata from header lines of modal report
        for line in lines[1:18]:
            if line.startswith('[') and line.endswith(']') and not extracted_court:
                c_inner = line.strip('[]').strip()
                extracted_court = COURT_NORMALIZATION.get(c_inner.upper(), c_inner)
            elif re.match(r'^(Before|Present:)\s+', line, re.I) and not extracted_bench:
                extracted_bench = line.strip()
            elif not extracted_docket and re.search(r'\b(?:Appeal|Petition|Suit|Reference|Revision|Misc|C\.M\.|C\.P\.|W\.P\.|F\.A\.O\.).*?\b(?:No|No\.|Number)\s*[:\.\s]*[0-9]+', line, re.I):
                if not line.startswith(('-', '(', '1.', '2.', '3.')):
                    extracted_docket = line.strip()
                    m_d = re.search(r'decided on[:\s\-]+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})', line, re.I)
                    if m_d:
                        extracted_date = m_d.group(1).strip()
            elif not extracted_date and re.search(r'\bdecided on[:\s\-]+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})', line, re.I):
                m_d = re.search(r'decided on[:\s\-]+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})', line, re.I)
                if m_d:
                    extracted_date = m_d.group(1).strip()

        # Split Headnotes and Full Judgment
        m_split = re.search(r'\n\s*(JUDGMENT|ORDER|JUDGEMENT)\b', clean_hn_raw, re.IGNORECASE)
        if m_split:
            headnotes = clean_hn_raw[:m_split.start()].strip()
            judgment_body = clean_hn_raw[m_split.start():].strip()
        else:
            # If no explicit JUDGMENT header, look for hearing date or judge signature line
            m_hear = re.search(r'\n\s*(?:Date of hearing|Dates of hearing)[:\s\-]+[^\n]+\n', clean_hn_raw, re.I)
            if m_hear:
                headnotes = clean_hn_raw[:m_hear.end()].strip()
                judgment_body = clean_hn_raw[m_hear.end():].strip()
            else:
                headnotes = clean_hn_raw
                judgment_body = clean_hn_raw
    else:
        # Timeout record: use clean search snippet
        headnotes = clean_body_raw
        judgment_body = clean_body_raw

    # Format Parties cleanly
    if not extracted_parties or extracted_parties == "VS":
        extracted_parties = f"Case #{case_idx} ({extracted_citation})"
    else:
        extracted_parties = extracted_parties.replace(" VS ", " v. ").replace(" Versus ", " v. ").replace(" versus ", " v. ")

    # Format Citation
    if not extracted_citation:
        extracted_citation = f"{year} {journal} #{case_idx}"

    return {
        "journal": journal,
        "year": str(year),
        "case_index": str(case_idx),
        "citation": deep_clean_text(extracted_citation),
        "title": deep_clean_text(extracted_parties),
        "court": deep_clean_text(extracted_court),
        "bench": deep_clean_text(extracted_bench),
        "docket_number": deep_clean_text(extracted_docket),
        "decision_date": deep_clean_text(extracted_date),
        "headnotes": deep_clean_text(headnotes),
        "judgment_body": deep_clean_text(judgment_body),
        "is_complete": "True" if is_complete else "False"
    }


def clean_csv_file(input_csv_path: str):
    filename = os.path.basename(input_csv_path)
    base_name = filename.replace("_gap.csv", "_cleaned.csv")
    output_csv_path = os.path.join(OUTPUT_DIR, base_name)
    
    print(f"\nProcessing: {filename} -> {base_name}")
    
    seen_keys = set()
    cleaned_rows = []
    skipped_bad_rows = 0
    duplicate_rows = 0

    with open(input_csv_path, 'r', encoding='utf-8-sig', errors='replace') as fp:
        reader = csv.reader(fp)
        header = next(reader, None)
        
        for idx, row in enumerate(reader):
            if len(row) != 7:
                skipped_bad_rows += 1
                continue
            
            jn = row[0].strip()
            yr = row[1].strip()
            idx_str = row[2].strip()
            raw_title = row[3].strip()
            raw_hn = row[4].strip()
            raw_body = row[5].strip()

            dedup_key = (jn, yr, idx_str)
            if dedup_key in seen_keys:
                duplicate_rows += 1
                continue
            seen_keys.add(dedup_key)

            parsed = parse_metadata_and_split(jn, yr, idx_str, raw_title, raw_hn, raw_body)
            cleaned_rows.append(parsed)

    # Write cleaned CSV
    fieldnames = [
        "journal", "year", "case_index", "citation", "title", "court",
        "bench", "docket_number", "decision_date", "headnotes", "judgment_body", "is_complete"
    ]
    with open(output_csv_path, 'w', newline='', encoding='utf-8-sig') as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    complete_count = sum(1 for r in cleaned_rows if r["is_complete"] == "True")
    timeout_count = len(cleaned_rows) - complete_count
    print(f"  Finished {base_name}: {len(cleaned_rows):,} cases saved ({complete_count:,} complete judgments, {timeout_count:,} timeouts).")
    if skipped_bad_rows:
        print(f"  Skipped {skipped_bad_rows} malformed raw row fragments.")
    if duplicate_rows:
        print(f"  Skipped {duplicate_rows} duplicate keys.")
    return len(cleaned_rows)

def main():
    print("=" * 80)
    print("PAKISTAN LEGAL TEXT CLEANING & STRUCTURING PIPELINE")
    print(f"Input:  {INPUT_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 80)
    
    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    total_cleaned = 0
    for f in sorted(csv_files):
        count = clean_csv_file(f)
        total_cleaned += count

    print("\n" + "=" * 80)
    print(f"PIPELINE COMPLETE: Cleaned and structured {total_cleaned:,} judgments.")
    print("=" * 80)

if __name__ == "__main__":
    main()
