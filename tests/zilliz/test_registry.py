"""
tests/zilliz/test_registry.py

Unit tests for scripts/zilliz/build_registry.py.
Tests:
- Citation parsing (including PCrLJ, PLC(CS), PLD court variants)
- Court mapping to hierarchy levels 1-4
- Junk detection (error codes, server error, short text)
- Duplicate preference resolution
- case_key determinism and cross-court distinction
- Parallel report deduplication
"""

import os
import sys
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.zilliz.build_registry import (
    normalize_journal,
    map_court,
    parse_citation_and_title,
    is_junk_text,
    is_full_judgment,
    classify_case_content,
    candidate_preference_score,
    compute_text_hash,
)


def test_normalize_journal():
    assert normalize_journal("SCMR") == "SCMR"
    assert normalize_journal("PLD") == "PLD"
    assert normalize_journal("MLD") == "MLD"
    assert normalize_journal("YLR") == "YLR"
    assert normalize_journal("PCrLJ") == "PCRLJ"
    assert normalize_journal("P.Cr.L.J") == "PCRLJ"
    assert normalize_journal("P Cr. L. J") == "PCRLJ"
    assert normalize_journal("PCRLJ") == "PCRLJ"
    assert normalize_journal("CLC") == "CLC"
    assert normalize_journal("PLC") == "PLC"
    assert normalize_journal("PLC (C.S.)") == "PLC(CS)"
    assert normalize_journal("PLC(CS)") == "PLC(CS)"
    assert normalize_journal("CLD") == "CLD"
    assert normalize_journal("PTD") == "PTD"
    assert normalize_journal("GBLR") == "GBLR"


def test_parse_citation_and_title():
    # Standard SCMR
    raw1 = "259\t2021 SCMR 1463\tFAISALABAD ELECTRIC SUPPLY COMPANY LIMITED. VS The FEDERATION OF PAKISTAN - Honorable Justice Munib Akhtar - Mian Ashiq Hussain\tSUPREME-COURT"
    res1 = parse_citation_and_title(raw1)
    assert res1 is not None
    assert res1["year"] == 2021
    assert res1["journal"] == "SCMR"
    assert res1["page"] == "1463"
    assert res1["citation"] == "2021 SCMR 1463"
    assert "Munib Akhtar" in res1["judge"]
    assert res1["court_raw"] == "SUPREME-COURT"

    # PLD with page suffix
    raw2 = "1\t2024 PLD 1A\tABC VS XYZ - Honorable Justice Ali - Counsel A\tKARACHI-HIGH-COURT-SINDH"
    res2 = parse_citation_and_title(raw2)
    assert res2 is not None
    assert res2["year"] == 2024
    assert res2["journal"] == "PLD"
    assert res2["page"] == "1A"
    assert res2["citation"] == "2024 PLD 1A"

    # PLC(CS) variant
    raw3 = "10\t1994 PLC (C.S.) 123\tGOVT VS WORKER - \tLABOUR-APPELLATE-TRIBUNAL-PUNJAB"
    res3 = parse_citation_and_title(raw3)
    assert res3 is not None
    assert res3["year"] == 1994
    assert res3["journal"] == "PLC(CS)"
    assert res3["page"] == "123"

    # PCrLJ variant
    raw4 = "5\t2005 P Cr. L. J 45\tSTATE VS ACCUSED\tLAHORE-HIGH-COURT-LAHORE"
    res4 = parse_citation_and_title(raw4)
    assert res4 is not None
    assert res4["year"] == 2005
    assert res4["journal"] == "PCRLJ"
    assert res4["page"] == "45"

    # Missing court column (3 tabs)
    raw5 = "129\t2005 SCMR 816\tMAQSOOD VS GOVT - Justice IFTIKHAR"
    res5 = parse_citation_and_title(raw5)
    assert res5 is not None
    assert res5["year"] == 2005
    assert res5["journal"] == "SCMR"
    assert res5["court_raw"] == ""

    # Invalid / unparsable rows
    assert parse_citation_and_title("PLC 1994 Case 1") is None
    assert parse_citation_and_title("in which the Indian Supreme Court") is None
    assert parse_citation_and_title("") is None


def test_map_court():
    # Supreme Court (Level 1)
    assert map_court("SUPREME-COURT") == ("SC", 1)
    # Empty court with SCMR journal defaults to SC
    assert map_court("", "SCMR") == ("SC", 1)

    # Federal Shariat Court (Level 2)
    assert map_court("FEDERAL-SHARIAT-COURT") == ("FSC", 2)

    # High Courts (Level 3)
    assert map_court("LAHORE-HIGH-COURT-LAHORE") == ("LHC", 3)
    assert map_court("BAGHDAD-UL-JADID") == ("LHC", 3)
    assert map_court("KARACHI-HIGH-COURT-SINDH") == ("SHC", 3)
    assert map_court("PESHAWAR-HIGH-COURT") == ("PHC", 3)
    assert map_court("QUETTA-HIGH-COURT-BALOCHISTAN") == ("BHC", 3)
    assert map_court("ISLAMABAD") == ("IHC", 3)
    assert map_court("ISLAMABAD-HIGH-COURT") == ("IHC", 3)
    assert map_court("HIGH-COURT-AZAD-KASHMIR") == ("AJKHC", 3)

    # GB Supreme Appellate Court (Level 3)
    assert map_court("SUPREME-APPELLATE-COURT") == ("GBSAC", 3)
    assert map_court("SUPREME-APPELATE-COURT-GILGIT") == ("GBSAC", 3)
    assert map_court("GILGIT-BALTISTAN-SUPREME-APPELLATE-COURT") == ("GBSAC", 3)
    assert map_court("", "GBLR") == ("GBSAC", 3)

    # Unknown / Tribunals (Level 4, OTHER)
    assert map_court("LABOUR-APPELLATE-TRIBUNAL-PUNJAB") == ("OTHER", 4)
    assert map_court("CUSTOMS-APPELLATE-TRIBUNAL-LAHORE") == ("OTHER", 4)
    assert map_court("SOME-RANDOM-TRIBUNAL") == ("OTHER", 4)


def test_junk_detection():
    # Short text (< 200 chars)
    assert is_junk_text("Short text") is True
    assert is_junk_text("a" * 199) is True
    assert is_junk_text("a" * 200) is False

    # Server error pages
    assert is_junk_text("Server Error in '/' Application. Something went wrong here" + "x" * 200) is True
    assert is_junk_text("Error Code:700 Internal Failure" + "x" * 200) is True
    assert is_junk_text("Something went wrong with the database connection" + "x" * 200) is True

    # Valid legal text
    valid_text = "S. 497---Criminal Procedure Code 1898---Bail, grant of---Offence under section 302 PPC---" + "x" * 300
    assert is_junk_text(valid_text) is False


def test_full_judgment_detection():
    # Too short (< 6000 chars)
    short_judg = "Present: Umar Ata Bandial, J\nCivil Petition No. 12 of 2021\n" + "x" * 5000
    assert is_full_judgment(short_judg) is False

    # Missing bench
    no_bench = "Civil Petition No. 12 of 2021\n" + "x" * 7000
    assert is_full_judgment(no_bench) is False

    # Missing case number
    no_case_no = "Present: Umar Ata Bandial, J\n" + "x" * 7000
    assert is_full_judgment(no_case_no) is False

    # Complete full judgment
    valid_judg = (
        "Present: Umar Ata Bandial and Syed Mansoor Ali Shah, JJ\n\n"
        "Civil Petition No. 3145-L of 2019, decided on 27th May, 2021.\n\n"
        "JUDGMENT:\n" + ("The petitioner entered into a contract with the respondent. " * 200)
    )
    assert is_full_judgment(valid_judg) is True


def test_case_key_determinism_and_cross_court():
    # Determinism: same input gives exact same key
    p1 = parse_citation_and_title("1\t2024 PLD 1\tParty A VS Party B\tSUPREME-COURT")
    c1, _ = map_court(p1["court_raw"], p1["journal"])
    key1 = f"{p1['year']}_{p1['journal']}_{c1}_{p1['page']}"
    assert key1 == "2024_PLD_SC_1"

    # Cross-court citations kept distinct (spec §2: 3,711 citations shared across courts)
    p2 = parse_citation_and_title("2\t2024 PLD 1\tParty C VS Party D\tFEDERAL-SHARIAT-COURT")
    c2, _ = map_court(p2["court_raw"], p2["journal"])
    key2 = f"{p2['year']}_{p2['journal']}_{c2}_{p2['page']}"
    assert key2 == "2024_PLD_FSC_1"

    p3 = parse_citation_and_title("3\t2024 PLD 1\tParty E VS Party F\tLAHORE-HIGH-COURT-LAHORE")
    c3, _ = map_court(p3["court_raw"], p3["journal"])
    key3 = f"{p3['year']}_{p3['journal']}_{c3}_{p3['page']}"
    assert key3 == "2024_PLD_LHC_1"

    assert len({key1, key2, key3}) == 3


def test_duplicate_preference_score():
    # Order: (1) not junk, (2) full judgment, (3) longest cleaned text, (4) latest Scraped At
    cand_junk = {
        "is_junk": True,
        "content_level": "headnote_only",
        "judgment_text": "",
        "headnote_text": "",
        "scraped_at": "2026-09-01 10:00:00",
    }
    cand_headnote_short = {
        "is_junk": False,
        "content_level": "headnote_only",
        "judgment_text": "",
        "headnote_text": "x" * 500,
        "scraped_at": "2026-08-01 10:00:00",
    }
    cand_headnote_long = {
        "is_junk": False,
        "content_level": "headnote_only",
        "judgment_text": "",
        "headnote_text": "x" * 2000,
        "scraped_at": "2026-08-01 10:00:00",
    }
    cand_full_judgment = {
        "is_junk": False,
        "content_level": "full_judgment",
        "judgment_text": "x" * 10000,
        "headnote_text": "x" * 500,
        "scraped_at": "2026-07-01 10:00:00",
    }

    # Non-junk beats junk
    assert candidate_preference_score(cand_headnote_short) > candidate_preference_score(cand_junk)
    # Long headnote beats short headnote
    assert candidate_preference_score(cand_headnote_long) > candidate_preference_score(cand_headnote_short)
    # Full judgment beats headnote (even if headnote scraped later)
    assert candidate_preference_score(cand_full_judgment) > candidate_preference_score(cand_headnote_long)


def test_parallel_report_deduplication():
    # Same judgment text reported in SCMR and PLD
    text = (
        "Present: Umar Ata Bandial, CJ\nCivil Petition No. 1 of 2023\n"
        "This petition raises an important question of constitutional law. " * 50
    )
    hash_scmr = compute_text_hash(text)
    hash_pld = compute_text_hash(text)
    assert hash_scmr == hash_pld
