"""
tests/test_order111_planner_and_claims.py

ORDER 1.11 - ITEM 1 TESTS:
1. Planner does not interpret calendar years as section numbers.
2. detect_statutory_provisions_in_query extracts only real sections, not act years.
3. verify_memo_statutory_claims accurately verifies all 7 subsections of FIO Section 22
   against authentic stored text without misclassifying them as missing external cross-references.
"""

import os
import sys
import json
import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from core.statute_currency import detect_statutory_provisions_in_query
from core.statutory_validator import parse_statutory_citation
from core.statute_claim_verifier import verify_memo_statutory_claims


def test_planner_does_not_parse_calendar_years_as_sections():
    # Bare years must never parse as valid statutory sections
    res_2001 = parse_statutory_citation("2001", context="Financial Institutions Ordinance, 2001")
    assert not res_2001.get("is_valid"), "Bare year 2001 must not be parsed as a section"

    res_1860 = parse_statutory_citation("1860", context="Pakistan Penal Code, 1860")
    assert not res_1860.get("is_valid"), "Bare year 1860 must not be parsed as a section"

    res_1908 = parse_statutory_citation("1908", context="Code of Civil Procedure, 1908")
    assert not res_1908.get("is_valid"), "Bare year 1908 must not be parsed as a section"


def test_query_detection_excludes_act_years():
    q = "What is the appeal procedure under Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001?"
    provisions = detect_statutory_provisions_in_query(q)
    cids = [cid for cid, act in provisions]
    assert "FIO_2001_SEC_22" in cids
    assert "FIO_2001_SEC_2001" not in cids, "Year 2001 must never be detected as FIO_2001_SEC_2001"
    assert len(cids) == 1


def test_fio_s22_subsections_verified_in_stored_text():
    # Load stored FIO Section 22
    fio_file = os.path.join(REPO_DIR, "data", "unified_statutes", "FIO_2001.json")
    with open(fio_file, "r", encoding="utf-8") as f:
        provisions = json.load(f)
    p22 = next(p for p in provisions if str(p.get("primary_num")) == "22")
    stored_map = {p22["canonical_id"]: p22["text"]}

    memo = """
## Relevant Provisions
Section 22(1) provides that an appeal may be preferred to the High Court within thirty days.
Section 22(2) requires notice to the respondent in accordance with Order XLIII Rule 3 CPC.
Section 22(3) governs deposit of the decretal amount and furnishing of security.
Section 22(4) mandates a bench of not less than two Judges and decision within ninety days.
Section 22(5) permits an appeal from a decree passed ex-parte.
Section 22(6) bars appeal from interlocutory orders except orders under Section 15(11), Section 15A(13) or Section 19(7).
Section 22(7) provides that any stay order automatically lapses after six months.

## Application to Query
Under Section 22(1), the appellant has 30 days to appeal.
Under Section 22(3), deposit in cash or security is required.
"""
    result = verify_memo_statutory_claims(memo, stored_map)
    assert result.passed is True
    assert len(result.violations) == 0

    verified_refs = {c.get("reference") for c in result.verified_claims if c.get("reference")}
    for sub in range(1, 8):
        assert f"Section 22({sub})" in verified_refs, f"Section 22({sub}) must be verified"
