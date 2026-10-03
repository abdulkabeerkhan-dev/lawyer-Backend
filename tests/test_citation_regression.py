import re
import sys
import unittest
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

fixtures = [
    # 1. Real database record
    {
        "id": "1992_PLD_LAH_11",
        "stored": "PLD 1992 Lah 11",
        "header": "P L D 1992 Lahore 63   Before Muhammad Ilyas, J   ANWAR CLUB and another --- Petitioners versus MUHAMMAD SARWAR --- Respondent Civil Revision No. 1269/1) of 1985, decided on 30th Sept",
        "expected_stored_page": "11",
        "expected_header_page": "63"
    },
    # 2. PLD 2004 Lah 35 vs 290
    {
        "id": "PLD_2004_Lah_35",
        "stored": "PLD 2004 Lah 35",
        "header": "P L D 2004 Lahore 290 Before Ch. Ijaz Ahmad, J Mst. SHAHIDA PARVEEN---Petitioner...",
        "expected_stored_page": "35",
        "expected_header_page": "290"
    },
    # 3. PLD 1995 SC 423 vs 546
    {
        "id": "PLD_1995_SC_423",
        "stored": "PLD 1995 SC 423",
        "header": "P L D 1995 Supreme Court 546 Present: Saiduzzaman Siddiqui, Fazal Ilahi Khan...",
        "expected_stored_page": "423",
        "expected_header_page": "546"
    },
    # 4. PLD 1991 Lah 385 vs 412
    {
        "id": "PLD_1991_Lah_385",
        "stored": "PLD 1991 Lah 385",
        "header": "P L D 1991 Lahore 412 Before Munir A. Shaikh, J ALLAH DITTA---Appellant...",
        "expected_stored_page": "385",
        "expected_header_page": "412"
    },
    # 5. PLD 1971 SC 197 vs 205
    {
        "id": "PLD_1971_SC_197",
        "stored": "PLD 1971 SC 197",
        "header": "P L D 1971 Supreme Court 205 Present: Hamoodur Rahman, C.J., Muhammad Yaqub Ali...",
        "expected_stored_page": "197",
        "expected_header_page": "205"
    },
    # 6. PLD 1980 Kar 112 vs 198
    {
        "id": "PLD_1980_Kar_112",
        "stored": "PLD 1980 Kar 112",
        "header": "P L D 1980 Karachi 198 Before Ajmal Mian, J NATIONAL BANK OF PAKISTAN...",
        "expected_stored_page": "112",
        "expected_header_page": "198"
    },
    # 7. PLD 1999 SC 102 vs 1026
    {
        "id": "PLD_1999_SC_102",
        "stored": "PLD 1999 SC 102",
        "header": "P L D 1999 Supreme Court 1026 Present: Irshad Hasan Khan, Nasir Aslam Zahid...",
        "expected_stored_page": "102",
        "expected_header_page": "1026"
    },
    # 8. 1970 PLD 33 vs 81
    {
        "id": "1970_PLD_33",
        "stored": "1970 PLD 33",
        "header": "P L D 1970 Lahore 81 Before Muhammad Akram, J PROVINCE OF WEST PAKISTAN...",
        "expected_stored_page": "33",
        "expected_header_page": "81"
    },
    # 9. 1998 PLC 240 vs 310
    {
        "id": "1998_PLC_240",
        "stored": "1998 PLC 240",
        "header": "1998 P L C 310 [Karachi] Before Sabihuddin Ahmed, J KARACHI PORT TRUST...",
        "expected_stored_page": "240",
        "expected_header_page": "310"
    },
    # 10. 2009 PLC 77 vs 190
    {
        "id": "2009_PLC_77",
        "stored": "2009 PLC 77",
        "header": "2009 P L C 190 [Lahore] Before Umar Ata Bandial, J...",
        "expected_stored_page": "77",
        "expected_header_page": "190"
    }
]

def extract_header_citation_details(header_raw):
    clean_header = re.sub(r'[\r\n\xa0]+', ' ', header_raw[:1000])
    
    # 1. Format: 'Citation Name: YYYY JOURNAL PAGE COURT'
    m_cit = re.search(r'Citation Name:\s*(\d{4})\s+([A-Za-z]+(?:\([A-Za-z]+\))?)\s+(\d+)', clean_header, re.IGNORECASE)
    if m_cit:
        return m_cit.group(1), m_cit.group(2).upper(), m_cit.group(3)

    # 2. Format: 'CITATION: YYYY JOURNAL PAGE'
    m_cit2 = re.search(r'CITATION:\s*(\d{4})\s+([A-Za-z]+(?:\([A-Za-z]+\))?)\s+(\d+)', clean_header, re.IGNORECASE)
    if m_cit2:
        return m_cit2.group(1), m_cit2.group(2).upper(), m_cit2.group(3)

    # 3. Traditional reporter header: '[P L D|SCMR|...] [YYYY] [Court] [PAGE]'
    journal_pat = r'(?:P\s*L\s*D|S\s*C\s*M\s*R|M\s*L\s*D|Y\s*L\s*R|C\s*L\s*C|P\s*C\s*r\s*L\s*J|P\s*T\s*D|P\s*L\s*C(?:\s*\(\s*C\s*\.?\s*S\s*\.?\s*\))?|C\s*L\s*D|G\s*B\s*L\s*R|R\s*L\s*D)'
    court_pat = r'(?:Lahore|Karachi|Peshawar|Islamabad|Supreme Court|High Court|Dacca|Quetta|Azad J & K|Service-Tribunal|Tribunal|\(W\.?\s*P\.?\)|\[[A-Za-z\s]+\])?'
    
    # Pattern A: Journal Year Court Page
    m_trad1 = re.search(rf'\b({journal_pat})\s+(\d{{4}})\s+{court_pat}\s*(\d{{1,5}})\b', clean_header, re.IGNORECASE)
    if m_trad1:
        j = re.sub(r'\s+', '', m_trad1.group(1).upper()).replace('RLD', 'PLD')
        return m_trad1.group(2), j, m_trad1.group(3)
        
    # Pattern B: Year Journal Court Page
    m_trad2 = re.search(rf'\b(\d{{4}})\s+({journal_pat})\s+{court_pat}\s*(\d{{1,5}})\b', clean_header, re.IGNORECASE)
    if m_trad2:
        j = re.sub(r'\s+', '', m_trad2.group(2).upper()).replace('RLD', 'PLD')
        return m_trad2.group(1), j, m_trad2.group(3)
        
    return None, None, None

def extract_stored_components(citation_str):
    cit_upper = re.sub(r'[^A-Z0-9]+', ' ', str(citation_str).upper()).strip()
    known_journals = ["SCMR", "PLD", "CLC", "PCRLJ", "MLD", "YLR", "PTD", "PLC", "CLD", "GBLR"]
    found_journal = None
    for j in known_journals:
        if re.search(rf'\b{j}\b', cit_upper):
            found_journal = j
            break
    m_year = re.search(r'\b(19\d{2}|20\d{2})\b', cit_upper)
    found_year = m_year.group(1) if m_year else None
    tokens = re.findall(r'\b\d+\b', cit_upper)
    found_page = None
    if tokens:
        if found_year and tokens[0] == found_year and len(tokens) > 1:
            found_page = tokens[-1]
        elif found_year and tokens[-1] == found_year and len(tokens) > 1:
            found_page = tokens[0]
        else:
            found_page = tokens[-1]
    return found_year, found_journal, found_page

def classify_citation_alignment(stored_citation: str, header_text: str) -> str:
    s_yr, s_jr, s_pg = extract_stored_components(stored_citation)
    h_yr, h_jr, h_pg = extract_header_citation_details(header_text)
    
    if not h_pg or not s_pg:
        return "unresolved_header"
        
    if s_pg != h_pg:
        return "true_page_mismatch"
        
    if s_jr and h_jr and s_jr != h_jr:
        return "reporter_mismatch"
        
    if s_yr and h_yr and s_yr != h_yr:
        return "year_mismatch"
        
    return "verified_match"


class TestCitationRegression(unittest.TestCase):
    """
    Unit test suite asserting strict page mismatch detection on 10 known regression fixtures.
    """

    def test_ten_known_page_mismatches_strictly_flagged(self):
        """All 10 fixtures where stored page != header page must classify as true_page_mismatch."""
        for fix in fixtures:
            with self.subTest(fixture_id=fix["id"]):
                s_yr, s_jr, s_pg = extract_stored_components(fix["stored"])
                h_yr, h_jr, h_pg = extract_header_citation_details(fix["header"])
                
                self.assertEqual(s_pg, fix["expected_stored_page"], f"Stored page parse failure for {fix['id']}")
                self.assertEqual(h_pg, fix["expected_header_page"], f"Header page parse failure for {fix['id']}")
                self.assertNotEqual(s_pg, h_pg, f"Pages should not match for {fix['id']}")
                
                category = classify_citation_alignment(fix["stored"], fix["header"])
                self.assertEqual(category, "true_page_mismatch", f"Fixture {fix['id']} was not classified as true_page_mismatch")

    def test_spaced_reporters_do_not_cause_false_mismatch(self):
        """Spaced letters like 'P L D' or 'S C M R' matching stored citation must not trigger mismatch."""
        valid_cases = [
            ("PLD 2002 SC 841", "P L D 2002 Supreme Court 841"),
            ("2015 SCMR 123", "2015 S C M R 123 Supreme Court"),
            ("2018 MLD 456", "2018 M L D 456 Lahore"),
            ("2020 YLR 789", "2020 Y L R 789 Karachi"),
        ]
        for stored, header in valid_cases:
            with self.subTest(stored=stored):
                cat = classify_citation_alignment(stored, header)
                self.assertEqual(cat, "verified_match", f"{stored} incorrectly flagged as {cat}")


if __name__ == "__main__":
    unittest.main()

