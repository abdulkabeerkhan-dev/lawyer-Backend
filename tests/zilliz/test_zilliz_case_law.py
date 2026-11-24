"""
Unit tests for legal_ai.retrieval.zilliz_case_law (Zilliz mocked; no network).
"""
import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from legal_ai.retrieval import zilliz_case_law as zcl


def _plan(**kw):
    base = dict(primary_domain="criminal", legal_domain=["criminal"], provisions=["CRPC_1898_SEC_497", "Section 497 CrPC"])
    base.update(kw)
    return SimpleNamespace(**base)


def _cand(case_key, citation, domain="criminal", statutes=None, rrf=0.03, authority=1.0):
    return {
        "case_key": case_key, "case_id": case_key, "id": f"{case_key}:headnote",
        "citation": citation, "title": citation, "court": "Supreme Court of Pakistan",
        "year": 2020, "domain": domain, "statutes_cited": statutes or [],
        "rrf_score": rrf, "score": rrf * authority, "text": "body", "preview": "body",
        "content_type": "headnote", "metadata": {"case_key": case_key},
    }


def test_plan_domains_maps_planner_labels():
    assert zcl.plan_domains(_plan(primary_domain="banking", legal_domain=["banking"])) == ["banking_commercial"]
    assert zcl.plan_domains(_plan(primary_domain="taxation", legal_domain=[])) == ["tax_corporate"]
    assert zcl.plan_domains(_plan(primary_domain="general_legal", legal_domain=[])) == []


def test_plan_statute_ids_keeps_only_canonical_and_normalises_orders():
    plan = _plan(provisions=["CRPC_1898_SEC_497", "Section 497 CrPC", "CPC_1908_ORD_XX_R_18", "bad id; drop"])
    assert zcl.plan_statute_ids(plan) == ["CRPC_1898_SEC_497", "CPC_1908_O_XX_R_18"]


def test_build_lane_filters_has_plan_domain_and_open_lanes():
    lanes = dict(zcl.build_lane_filters(_plan()))
    assert lanes["plan"] == 'domain in ["criminal"] and array_contains_any(statutes, ["CRPC_1898_SEC_497"])'
    assert lanes["domain"] == 'domain in ["criminal"]'
    assert lanes["open"] is None


def test_build_lane_filters_without_plan_signal_is_open_only():
    lanes = zcl.build_lane_filters(_plan(primary_domain=None, legal_domain=[], provisions=[]))
    assert lanes == [("open", None)]


def test_fusion_prefers_on_topic_case_over_off_domain_open_hit():
    on_topic = _cand("2024_SCMR_SC_14", "2024 SCMR 14", statutes=["CRPC_1898_SEC_497"])
    off_topic = _cand("2026_CLD_292", "2026 CLD 292", domain="banking_commercial", authority=1.3)
    fused = zcl.fuse_lanes(
        [("plan", [on_topic]), ("domain", [on_topic]), ("open", [off_topic, on_topic])],
        ["CRPC_1898_SEC_497"],
    )
    assert [m["citation"] for m in fused] == ["2024 SCMR 14", "2026 CLD 292"]
    top = fused[0]
    assert top["retrieval_lanes"] == ["domain", "open", "plan"]
    assert top["plan_statute_hits"] == 1
    # Pinecone-compatible shape consumed by main.py
    assert top["id"] == "2024_SCMR_SC_14"
    assert top["metadata"]["citation"] == "2024 SCMR 14"
    assert top["metadata"]["court"] == "Supreme Court of Pakistan"
    assert top["metadata"]["year"] == 2024  # derived from citation, not the 2020 fallback


def test_retrieve_case_law_runs_every_query_lane_pair(monkeypatch):
    calls = []

    async def fake_search(query_text, top_k, filter_expr=None, **_):
        calls.append((query_text, filter_expr))
        if filter_expr and "array_contains_any" in filter_expr:
            return [_cand("A", "2024 SCMR 14", statutes=["CRPC_1898_SEC_497"])]
        # B outranks A on raw similarity in the broad lanes.
        return [_cand("B", "2010 SCMR 806"), _cand("A", "2024 SCMR 14", statutes=["CRPC_1898_SEC_497"])]

    monkeypatch.setattr(zcl, "search_zilliz_hybrid", fake_search)
    out = asyncio.run(zcl.retrieve_case_law(["bail in 302", "further inquiry"], _plan(), top_k=10))
    assert len(calls) == 6  # 2 queries x 3 lanes
    assert out[0]["case_key"] == "A"


def test_retrieve_case_law_survives_lane_failure(monkeypatch):
    async def flaky(query_text, top_k, filter_expr=None, **_):
        if filter_expr:
            raise RuntimeError("boom")
        return [_cand("B", "2010 SCMR 806")]

    monkeypatch.setattr(zcl, "search_zilliz_hybrid", flaky)
    out = asyncio.run(zcl.retrieve_case_law(["bail"], _plan()))
    assert [m["case_key"] for m in out] == ["B"]


def test_retrieve_relevant_statutes_prefers_plan_acts(monkeypatch):
    import legal_ai.retrieval.statute_search as ss

    async def fake_statutes(query, top_k=12, **_):
        return [
            {"canonical_id": "CRPC_1898_SEC_497", "act_code": "CRPC_1898", "domain": "criminal"},  # already in plan
            {"canonical_id": "FIO_2001_SEC_9", "act_code": "FIO_2001", "domain": "banking"},
            {"canonical_id": "CRPC_1898_SEC_498", "act_code": "CRPC_1898", "domain": "criminal", "text": "x"},
        ]

    monkeypatch.setattr(ss, "search_statutes_hybrid", fake_statutes)
    picked = asyncio.run(zcl.retrieve_relevant_statutes("bail", _plan()))
    assert [p["canonical_id"] for p in picked] == ["CRPC_1898_SEC_498"]


def test_statute_hit_to_verified_shape():
    v = zcl.statute_hit_to_verified({"canonical_id": "ppc_1860_sec_406", "act_name": "Pakistan Penal Code", "section": "406", "text": " t "})
    assert v["canonical_id"] == "PPC_1860_SEC_406"
    assert v["display_name"] == "Section 406, Pakistan Penal Code"
    assert v["text"] == "t"
