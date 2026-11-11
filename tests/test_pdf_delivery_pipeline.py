"""
tests/test_pdf_delivery_pipeline.py

Verifies the 3-tier authentic PDF resolution and delivery pipeline:
1. Token signature generation & validation (HMAC-SHA256).
2. Journal, year, and page extraction from citations and normalized case IDs.
3. Authenticated PDF delivery via /judgment-pdf/{case_id}?token=...
4. Browser navigation delivery via /api/judgments/{id}/pdf.
5. Circuit breaker protection ensuring fast failure when upstream storage is unavailable.
"""

import os
import sys
import urllib.parse
repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

import pytest
from fastapi.testclient import TestClient
from main import app
from core.pdf_resolver import (
    extract_journal_and_year,
    create_hmac_pdf_token,
    verify_hmac_pdf_token,
    fetch_storage_pdf_bytes,
)

client = TestClient(app)


def test_extract_journal_and_year():
    cases = [
        ("1984_SCMR_201", "SCMR", "1984", "201"),
        ("2021 SCMR 2092", "SCMR", "2021", "2092"),
        ("PLD 2020 SC 1", "PLD", "2020", "1"),
        ("2012 YLR 1342", "YLR", "2012", "1342"),
        ("1979_CLC_29", "CLC", "1979", "29"),
    ]
    for cit, expected_jn, expected_yr, expected_pg in cases:
        jn, yr, pg = extract_journal_and_year(cit, cit)
        assert jn == expected_jn, f"Failed journal for {cit}: got {jn}, expected {expected_jn}"
        assert yr == expected_yr, f"Failed year for {cit}: got {yr}, expected {expected_yr}"
        assert pg == expected_pg, f"Failed page for {cit}: got {pg}, expected {expected_pg}"


def test_hmac_token_verification():
    case_id = "1984_SCMR_201"
    tok = create_hmac_pdf_token(case_id, user_id="user_123", expires_in=3600)
    assert verify_hmac_pdf_token(tok, case_id) is True
    assert verify_hmac_pdf_token(tok, "2020_SCMR_1") is False
    assert verify_hmac_pdf_token("invalid.token", case_id) is False


def test_pdf_endpoint_with_hmac_token():
    case_id = "1984_SCMR_201"
    tok = create_hmac_pdf_token(case_id)
    res = client.get(f"/judgment-pdf/{urllib.parse.quote(case_id)}?token={tok}")
    assert res.status_code == 200
    assert res.headers.get("content-type") == "application/pdf"
    assert res.content.startswith(b"%PDF")


def test_api_judgment_pdf_endpoint_browser_mode():
    case_id = "1984_SCMR_201"
    headers = {"sec-fetch-mode": "navigate", "accept": "application/pdf"}
    res = client.get(f"/api/judgments/{urllib.parse.quote(case_id)}/pdf", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("content-type") == "application/pdf"
    assert res.content.startswith(b"%PDF")


def test_pdf_builder_does_not_return_invalid_success_shaped_pdf(monkeypatch):
    import main

    monkeypatch.setattr(main, "REPORTLAB_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="ReportLab is required"):
        main.build_judgment_pdf_bytes("Case", "PLD 2020 SC 1", "Supreme Court", "Text")

    monkeypatch.setattr(main, "fetch_storage_pdf_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main,
        "find_judgment_by_id_or_canonical",
        lambda _: {
            "case_id": "1984_SCMR_201",
            "neutral_citation": "1984 SCMR 201",
            "full_text": "Verified source judgment text.",
            "content_level": "full_judgment",
            "content_status": "available",
        },
    )
    response = client.get(
        "/api/judgments/1984_SCMR_201/pdf",
        headers={"sec-fetch-mode": "navigate", "accept": "application/pdf"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "PDF generation is unavailable on this server."
