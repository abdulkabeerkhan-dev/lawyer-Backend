"""
tests/test_digilawyer_search_and_assistants.py

Comprehensive Parity Tests for DigiLawyer Search & Assistants:
1. Statute Search (Directory of Acts & Section lookup)
2. Judgment Search - 3 Modes:
   - Citation Search (Pinpoint by Year, Journal, Page)
   - Keyword Search (Term & Party name with filters)
   - Intelligent Search (Semantic vector retrieval)
3. Specialized Assistants:
   - Ark AI (Legal Research Assistant)
   - Mike AI (Legal Drafting Assistant)
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from main import app, jobs_store


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_statute_directory(client):
    """Verifies GET /api/statutes returns directory of available acts."""
    response = client.get("/api/statutes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 10
    act_codes = [a["act_code"] for a in data]
    assert "PPC_1860" in act_codes
    assert "CRPC_1898" in act_codes
    assert "CPC_1908" in act_codes
    assert "CONST_1973" in act_codes
    assert "PRPA_2009" in act_codes


def test_statute_search_get(client):
    """Verifies GET /api/search/statutes with query returns matching provisions."""
    response = client.get("/api/search/statutes?query=Penal Code 489-F")
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] > 0
    top = data["results"][0]
    assert top["canonical_id"] == "PPC_1860_SEC_489F"
    assert "Dishonestly issuing a cheque" in top["title"]
    assert top["has_text"] is True


def test_statute_search_post(client):
    """Verifies POST /api/search/statutes with query."""
    response = client.post("/api/search/statutes", json={"query": "Section 19 Punjab Rented Premises"})
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] > 0
    top = data["results"][0]
    assert top["canonical_id"] == "PRPA_2009_SEC_19"
    assert "application" in top["title"].lower()


def test_statute_single_provision_lookup(client):
    """Verifies GET /api/statutes/{canonical_id} returns full text."""
    response = client.get("/api/statutes/PPC_1860_SEC_489F")
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_id"] == "PPC_1860_SEC_489F"
    assert "489F" in data["primary_num"]
    assert "dishonestly issues a cheque" in data["text"].lower()


def test_judgment_search_by_citation(client):
    """Verifies POST /api/search/judgments/citation pinpoints exact case."""
    response = client.post("/api/search/judgments/citation", json={
        "year": 2012,
        "journal": "SCMR",
        "page": 91
    })
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert len(data["results"]) >= 1
    top = data["results"][0]
    assert "2012 SCMR 91" in top["citation"]
    assert "Malik Abdul Aziz Awan" in top["title"]
    assert top["court"] == "Supreme Court of Pakistan"
    assert top["pdf_url"] is not None


def test_judgment_search_by_keyword(client):
    """Verifies POST /api/search/judgments/keyword returns matching precedents."""
    response = client.post("/api/search/judgments/keyword", json={
        "query": "commercial tenancy eviction",
        "limit": 5
    })
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] > 0
    assert len(data["results"]) > 0
    top = data["results"][0]
    assert top["citation"] is not None
    assert top["pdf_url"] is not None


def test_unified_judgment_search_modes(client):
    """Verifies POST /api/search/judgments with mode=citation and mode=keyword."""
    # 1. Citation mode
    res_cit = client.post("/api/search/judgments", json={
        "mode": "citation",
        "year": 2012,
        "journal": "SCMR",
        "page": 91
    })
    assert res_cit.status_code == 200
    assert res_cit.json()["found"] is True

    # 2. Keyword mode
    res_kw = client.post("/api/search/judgments", json={
        "mode": "keyword",
        "query": "bail after arrest 497"
    })
    assert res_kw.status_code == 200
    assert res_kw.json()["total_matches"] > 0


def test_assistants_endpoints(client, monkeypatch):
    """Verifies Ark AI and Mike AI assistant endpoints tag query requests appropriately."""
    async def fake_process_query_job(*args, **kwargs):
        pass
    monkeypatch.setattr("main.process_query_job", fake_process_query_job)
    headers = {"Authorization": "Bearer mock_clerk_user_id_dev_run"}
    
    # 1. Ark AI (Research)
    res_ark = client.post("/api/assistants/ark", json={
        "query_text": "Is the husband's consent legally required for a wife to obtain khula in Pakistan?"
    }, headers=headers)
    assert res_ark.status_code == 200
    data_ark = res_ark.json()
    assert data_ark["assistant"] == "ark"
    assert data_ark["role"] == "Legal Research Assistant"
    assert "job_id" in data_ark

    # 2. Mike AI (Drafting)
    res_mike = client.post("/api/assistants/mike", json={
        "query_text": "Draft a quashment petition under Section 561-A CrPC against FIR for dishonour of cheque"
    }, headers=headers)
    assert res_mike.status_code == 200
    data_mike = res_mike.json()
    assert data_mike["assistant"] == "mike"
    assert data_mike["role"] == "Legal Drafting Assistant"
    assert "job_id" in data_mike
