"""
tests/test_order113_statute_lookup.py

ORDER 1.13 - ITEM 3: DETERMINISTIC STATUTE LOOKUP MODE TESTS
Verifies that:
1. "what does section 22 of fio say" returns stored text, tier='disputed', banners, hash, no model call.
2. "what does section 489-f of ppc say" returns stored text, source page, hash, no model call.
3. "what does section 415 of ppc say" returns stored text, source page, hash, no model call.
4. "what does section 497 of crpc say" returns stored text, source page, hash, no model call.
5. Missing provision returns "not in verified store" (never "does not exist").
6. Quarantined act returns quarantine isolation notice.
7. Used as deterministic fallback when a memo is blocked.
"""

import pytest
from core.statute_lookup import (
    statute_lookup,
    is_statute_lookup_query,
    get_verified_statute_fallback
)

def test_query_detection():
    assert is_statute_lookup_query("What does section 22 of the Financial Institutions Ordinance say?")
    assert is_statute_lookup_query("What does section 489-F of PPC say?")
    assert is_statute_lookup_query("What does section 497 of CrPC say?")
    assert is_statute_lookup_query("Text of section 415 PPC")

def test_lookup_fio_s22():
    res = statute_lookup("What does section 22 of the Financial Institutions Ordinance, 2001 say?")
    assert res["status"] == "success"
    assert res["canonical_id"] == "FIO_2001_SEC_22"
    assert res["tier"] == "disputed"
    assert "23" in str(res["source_page"])
    assert res["content_hash"] is not None
    assert len(res["banners"]) > 0
    assert "DISPUTED STATUTORY TEXT" in res["banners"][0]
    assert "22. Appeal." in res["statutory_text"]
    assert res["no_model_call"] is True

def test_lookup_ppc_489f():
    res = statute_lookup("What does section 489-F of PPC say?")
    assert res["status"] == "success"
    assert res["canonical_id"] == "PPC_1860_SEC_489F"
    assert res["content_hash"] is not None
    assert "dishonestly issues a cheque" in res["statutory_text"]
    assert res["no_model_call"] is True

def test_lookup_ppc_415():
    res = statute_lookup("What does section 415 of PPC say?")
    assert res["status"] == "success"
    assert res["canonical_id"] == "PPC_1860_SEC_415"
    assert res["content_hash"] is not None
    assert "dishonestly" in res["statutory_text"]  # Verified OCR fix: not 'dishonest1y'
    assert res["no_model_call"] is True

def test_lookup_crpc_497():
    res = statute_lookup("What does section 497 of CrPC say?")
    assert res["status"] == "success"
    assert res["canonical_id"] == "CRPC_1898_SEC_497"
    assert res["source_page"] in (167, "167")
    assert res["content_hash"] is not None
    assert "non-bailable offence" in res["statutory_text"]
    assert res["no_model_call"] is True

def test_lookup_missing_provision():
    res = statute_lookup("What does section 61 of the Financial Institutions Ordinance say?")
    assert res["status"] == "not_in_store"
    assert "not in verified store" in res["message"].lower()
    assert "does not exist" not in res["message"].lower()
    assert res["no_model_call"] is True

def test_lookup_quarantined_act():
    res = statute_lookup("What does section 3 of PECA say?")
    assert res["status"] == "quarantined"
    assert res["is_quarantined"] is True
    assert "quarantined" in res["message"].lower()
    assert res["no_model_call"] is True

def test_verified_statute_fallback():
    fallback = get_verified_statute_fallback("What does section 22 of FIO say?")
    assert len(fallback) == 1
    assert fallback[0]["canonical_id"] == "FIO_2001_SEC_22"
    assert fallback[0]["is_disputed"] is True
    assert "DISPUTED STATUTORY TEXT" in fallback[0]["text"]
