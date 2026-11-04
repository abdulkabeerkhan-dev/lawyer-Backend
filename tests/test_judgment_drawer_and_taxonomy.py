import pytest
from fastapi.testclient import TestClient
import main
from main import app, find_judgment_by_id_or_canonical, clean_court_name, infer_court_from_citation
from core.court_taxonomy import get_effective_court
from core.statute_currency import detect_statutory_provisions_in_query
from core.legal_query_planner import create_deterministic_fallback_plan


def test_apex_citation_court_taxonomy():
    # 1. Docket and citation styles for SCMR must always be Supreme Court of Pakistan
    rec_docket = {"case_id": "1986_SCMR_1496", "court_name": "Lahore High Court"}
    assert get_effective_court(rec_docket) == "Supreme Court of Pakistan"

    rec_space = {"citation": "2003 SCMR 1050", "court": "High Court"}
    assert get_effective_court(rec_space) == "Supreme Court of Pakistan"

    rec_pld_sc = {"citation": "PLD 2020 SC 1", "court_name": "Court of Record"}
    assert get_effective_court(rec_pld_sc) == "Supreme Court of Pakistan"

    # 2. High Court law reports must resolve to High Courts
    rec_ylr = {"case_id": "2016_YLR_2355", "court": "LAHORE-HIGH-COURT-LAHORE"}
    assert get_effective_court(rec_ylr) == "Lahore High Court"

    rec_clc = {"citation": "2010 CLC 1578", "court_name": "High Court of Sindh"}
    assert get_effective_court(rec_clc) == "High Court of Sindh"

    rec_pesh = {"case_id": "2018_CLC_497", "court": "PESHAWAR-HIGH-COURT"}
    assert get_effective_court(rec_pesh) == "Peshawar High Court"


def test_clean_and_infer_court_apex_guard():
    assert clean_court_name("Lahore High Court", title="ALLAH BAKHSH VS IRSHAD BEGUM", case_id="1986_SCMR_1496") == "Supreme Court of Pakistan"
    assert infer_court_from_citation("2003 SCMR 1050", court_hint="High Court") == "Supreme Court of Pakistan"
    assert infer_court_from_citation("1986_SCMR_1496", court_hint="Lahore High Court") == "Supreme Court of Pakistan"


def test_statutory_detection_for_decree_fraud():
    q = "A decree was obtained against my client in a civil suit by fraud and misrepresentation. What remedy is available under the Code of Civil Procedure, what is the limitation period, and how does it differ from filing an appeal?"
    provs = detect_statutory_provisions_in_query(q)
    cids = [cid for cid, act in provs]
    assert "CPC_1908_SEC_12" in cids
    assert "LIMITATION_1908_ART_181" in cids
    assert "CPC_1908_SEC_96" in cids


def test_query_planner_decree_fraud():
    q = "A decree was obtained against my client in a civil suit by fraud and misrepresentation. What remedy is available under the Code of Civil Procedure, what is the limitation period, and how does it differ from filing an appeal?"
    plan = create_deterministic_fallback_plan(q)
    assert plan.primary_domain == "civil"
    assert "Section 12(2) CPC" in plan.procedural_remedy or "Section 12(2)" in plan.procedural_remedy
    assert any("12(2)" in p for p in plan.statutory_provisions)
    assert any(l.lane == "sec12_2_decree_fraud" for l in plan.search_lanes)


def test_public_judgment_endpoint_drawer_no_401():
    client = TestClient(app)
    # Test without Authorization header (Lovable slide-out drawer)
    resp = client.get("/judgment/2016_YLR_2355")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "2016_YLR_2355"
    assert "FAQIR MUHAMMAD" in data["case_title"]
    assert data["court_name"] == "Lahore High Court"
    assert len(data.get("full_text", "")) > 500
    assert len(data.get("order_text", "")) > 100
    assert "pdf_url" in data and len(data["pdf_url"]) > 0


def test_public_api_judgment_endpoint_no_401():
    client = TestClient(app)
    resp = client.get("/api/judgments/2016_YLR_2355")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "2016_YLR_2355"
