"""
tests/zilliz/test_zilliz_search.py

Unit tests for legal_ai.retrieval.zilliz_search module.
Tests probe_zilliz, SQLite metadata lookup, authority scoring, and hybrid search.
"""

import os
import sys
import pytest
import asyncio

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from legal_ai.retrieval.zilliz_search import (
    probe_zilliz,
    get_case_metadata_from_sqlite,
    calculate_authority_score,
    search_zilliz_hybrid,
    is_zilliz_circuit_open,
)


def test_probe_zilliz():
    """Verify health probe connects to judgments_v1 and reports exact row count."""
    res = probe_zilliz(force=True)
    assert res["ok"] is True
    assert res["collection"] == "judgments_v1"
    assert res["row_count"] == 1318565


def test_sqlite_metadata_lookup():
    """Verify SQLite case lookup returns clean metadata."""
    meta = get_case_metadata_from_sqlite("2024_SCMR_SC_14")
    assert meta is not None
    assert meta["citation"] == "2024 SCMR 14"
    assert "SALMAN MUSHTAQ" in meta["parties"].upper()
    assert meta["court_level"] == 1


def test_authority_scoring():
    """Verify Supreme Court (court_level=1) receives higher multiplier than subordinate courts."""
    base_rrf = 0.025
    sc_score = calculate_authority_score(base_rrf, court_level=1, cited_by_count=5)
    hc_score = calculate_authority_score(base_rrf, court_level=2, cited_by_count=5)
    sub_score = calculate_authority_score(base_rrf, court_level=3, cited_by_count=5)

    assert sc_score > hc_score > sub_score


def test_search_zilliz_hybrid_structure():
    """Verify search_zilliz_hybrid returns canonical candidate records."""
    query = "bail under section 497 CrPC murder 302"
    candidates = asyncio.run(search_zilliz_hybrid(query_text=query, top_k=5))

    assert isinstance(candidates, list)
    assert len(candidates) > 0

    c = candidates[0]
    required_keys = [
        "id", "case_id", "case_key", "score", "citation",
        "title", "court", "court_level", "year", "domain",
        "preview", "text", "source_type"
    ]
    for k in required_keys:
        assert k in c, f"Missing key {k} in candidate record"

    assert c["source_type"] == "Zilliz"
