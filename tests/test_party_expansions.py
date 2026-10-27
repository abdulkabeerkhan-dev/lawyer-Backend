"""
tests/test_party_expansions.py

Tests proving that Pakistani institutional acronyms (SECP, PPRA, FBR, SBP, etc.),
honorific prefixes (Dr., Mst., Malik, etc.), and preposition connector phrases
(From, In, As per, etc.) are properly normalized in MemoVerifier so authentic
Pakistani authorities are not falsely flagged as unverified, while synthetic
hallucinated authorities (such as Zulfiqar Textile Mills) remain strictly blocked.
"""

import pytest
from legal_ai.verification.memo_verifier import MemoVerifier, verify_memorandum_text, get_party_variants


def test_preposition_stripping_in_case_extraction():
    mv = MemoVerifier()
    text = (
        "From Dr. SAQUIB YUSUF v. PPRA, the court held that service regulations apply.\n"
        "From GRENLIT STUDIO v. SECP, the commission exercised regulatory powers.\n"
        "As held in Al-Haaj Malik Muhammad Ashraf v. Javed Akhtar, co-owners have distinct rights."
    )
    auths = mv.extract_case_authorities(text)
    case_titles = [a for a in auths if a["type"] == "case_title"]
    
    p1_list = [c["p1"] for c in case_titles]
    spans = [c["span"] for c in case_titles]
    
    assert "Dr. SAQUIB YUSUF" in p1_list
    assert "From Dr. SAQUIB YUSUF" not in p1_list
    assert "Dr. SAQUIB YUSUF v. PPRA" in spans
    
    assert "GRENLIT STUDIO" in p1_list
    assert "From GRENLIT STUDIO" not in p1_list
    assert "GRENLIT STUDIO v. SECP" in spans
    
    assert "Al-Haaj Malik Muhammad Ashraf" in p1_list


def test_pakistani_institutional_acronym_variants():
    secp_vars = get_party_variants("SECP")
    assert any("SECURITIES" in v and "COMMISSION" in v for v in secp_vars)
    
    ppra_vars = get_party_variants("PPRA")
    assert "PUBLIC PROCUREMENT REGULATORY AUTHORITY" in ppra_vars
    
    fbr_vars = get_party_variants("FBR")
    assert "FEDERAL BOARD OF REVENUE" in fbr_vars
    
    sbp_vars = get_party_variants("SBP")
    assert "STATE BANK OF PAKISTAN" in sbp_vars


def test_grenlit_studio_v_secp_verifies_cleanly():
    mv = MemoVerifier()
    auth = {
        "type": "case_title",
        "p1": "GRENLIT STUDIO",
        "p2": "SECP",
        "span": "GRENLIT STUDIO v. SECP"
    }
    assert mv.verify_case_authority(auth) is True


def test_saquib_yusuf_v_ppra_verifies_with_extra_authority():
    mv = MemoVerifier()
    mv.ingest_extra_authorities([{
        "citation": "2026 PLC(CS) 102",
        "case_title": "Dr. SAQUIB YUSUF, DIRECTOR (HR) v. PUBLIC PROCUREMENT REGULATORY AUTHORITY (PPRA)",
        "court": "Islamabad High Court"
    }])
    auth = {
        "type": "case_title",
        "p1": "Dr. SAQUIB YUSUF",
        "p2": "PPRA",
        "span": "Dr. SAQUIB YUSUF v. PPRA"
    }
    assert mv.verify_case_authority(auth) is True


def test_synthetic_case_remains_blocked():
    mv = MemoVerifier()
    fake_auth = {
        "type": "case_title",
        "p1": "Zulfiqar Textile Mills",
        "p2": "Bank of the Indus Valley",
        "span": "Zulfiqar Textile Mills v. Bank of the Indus Valley"
    }
    assert mv.verify_case_authority(fake_auth) is False
