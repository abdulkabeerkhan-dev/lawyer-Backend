"""
scripts/verify_full_system_health.py

Comprehensive End-to-End Diagnostic and Health Audit for Pakistani Legal AI Platform.
Verifies all connections, engines, indexes, APIs, and pipelines:
1. Environment & Config
2. Zilliz Cloud (statutes_v3 & judgments_v1)
3. Voyage AI Embeddings
4. Turso Database (case_texts)
5. BM25 Local Sparse Index
6. Definitions Index (ambiguous terms & willful default)
7. Exact Statute Resolver & get_section()
8. Unified Multi-Lane Parallel Orchestrator (Rent, Criminal, Banking)
9. FastAPI Endpoints & Search Services
"""

import os
import sys
import time
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path('D:/lawyer-Backend')
load_dotenv(BASE_DIR / '.env')
sys.path.insert(0, str(BASE_DIR))

# Ensure flags are active
os.environ["USE_ZILLIZ_STATUTES"] = "true"
os.environ["ZILLIZ_STATUTES_COLLECTION"] = "statutes_v3"

report = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "checks": {},
    "status": "PASS"
}

def log_check(name: str, passed: bool, details: dict):
    report["checks"][name] = {
        "status": "PASS" if passed else "FAIL",
        "details": details
    }
    symbol = "✅" if passed else "❌"
    print(f"{symbol} [{name}]: {'PASSED' if passed else 'FAILED'}")
    for k, v in details.items():
        print(f"    • {k}: {v}")

async def run_diagnostics():
    print("=" * 80)
    print("RUNNING COMPREHENSIVE SYSTEM-WIDE HEALTH AUDIT")
    print("=" * 80)

    # -------------------------------------------------------------
    # 1. Environment & Config Audit
    # -------------------------------------------------------------
    env_keys = {
        "USE_ZILLIZ_STATUTES": os.environ.get("USE_ZILLIZ_STATUTES"),
        "ZILLIZ_STATUTES_COLLECTION": os.environ.get("ZILLIZ_STATUTES_COLLECTION"),
        "VECTOR_BACKEND": os.environ.get("VECTOR_BACKEND"),
        "ZILLIZ_URI": bool(os.environ.get("ZILLIZ_URI")),
        "ZILLIZ_TOKEN": bool(os.environ.get("ZILLIZ_TOKEN")),
        "VOYAGE_API_KEY": bool(os.environ.get("VOYAGE_API_KEY")),
        "TURSO_URL": bool(os.environ.get("TURSO_DATABASE_URL") or os.environ.get("TURSO_URL")),
        "TURSO_TOKEN": bool(os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("TURSO_TOKEN")),
    }
    env_passed = all([
        env_keys["USE_ZILLIZ_STATUTES"] in ("true", "1", "yes"),
        env_keys["ZILLIZ_STATUTES_COLLECTION"] == "statutes_v3",
        env_keys["ZILLIZ_URI"],
        env_keys["ZILLIZ_TOKEN"],
        env_keys["VOYAGE_API_KEY"]
    ])
    log_check("Environment & Credentials", env_passed, env_keys)

    # -------------------------------------------------------------
    # 2. Zilliz Cloud Connection (statutes_v3 & judgments_v1)
    # -------------------------------------------------------------
    from legal_ai.config import get_zilliz_client
    z_client = get_zilliz_client()
    z_passed = False
    z_details = {}
    if z_client:
        try:
            has_statutes = z_client.has_collection("statutes_v3")
            has_judgments = z_client.has_collection("judgments_v1")
            s_count = 0
            if has_statutes:
                res = z_client.query(collection_name="statutes_v3", output_fields=["count(*)"])
                s_count = res[0].get("count(*)", 0) if res else 0

            z_passed = has_statutes and has_judgments and s_count > 30000
            z_details = {
                "has_statutes_v3": has_statutes,
                "statutes_v3_row_count": s_count,
                "has_judgments_v1": has_judgments,
            }
        except Exception as e:
            z_details = {"error": str(e)}
    else:
        z_details = {"error": "Zilliz client could not be initialized"}
    log_check("Zilliz Cloud Clusters", z_passed, z_details)

    # -------------------------------------------------------------
    # 3. Voyage AI Embeddings API
    # -------------------------------------------------------------
    from legal_ai.config import get_voyage_embedding
    emb_passed = False
    emb_details = {}
    try:
        t0 = time.time()
        vec = await get_voyage_embedding("Pakistan Penal Code Section 302", input_type="query")
        lat = time.time() - t0
        emb_passed = isinstance(vec, list) and len(vec) == 1024
        emb_details = {
            "model": "voyage-4-large",
            "dimensions": len(vec) if vec else 0,
            "latency_seconds": round(lat, 3)
        }
    except Exception as e:
        emb_details = {"error": str(e)}
    log_check("Voyage AI 1024-d Embeddings", emb_passed, emb_details)

    # -------------------------------------------------------------
    # 4. Turso Database (case_texts)
    # -------------------------------------------------------------
    from core.turso_client import execute_turso_pipeline, is_turso_circuit_open
    turso_passed = False
    turso_details = {}
    try:
        t0 = time.time()
        t_res = execute_turso_pipeline([{"sql": "SELECT count(*) FROM case_texts"}])
        lat = time.time() - t0
        c_count = t_res[0]["rows"][0].get("count(*)", 0) if (t_res and "rows" in t_res[0]) else 0
        turso_passed = c_count > 100000
        turso_details = {
            "case_texts_count": c_count,
            "circuit_breaker_open": is_turso_circuit_open(),
            "latency_seconds": round(lat, 3)
        }
    except Exception as e:
        turso_details = {"error": str(e)}
    log_check("Turso Case Law Store", turso_passed, turso_details)

    # -------------------------------------------------------------
    # 5. BM25 Local Sparse Index
    # -------------------------------------------------------------
    from legal_ai.retrieval.bm25_search import search_bm25_sparse
    bm25_passed = False
    bm25_details = {}
    try:
        t0 = time.time()
        bm_hits = search_bm25_sparse("murder intention Section 302 PPC", top_k=5)
        lat = time.time() - t0
        bm25_passed = len(bm_hits) > 0
        bm25_details = {
            "hits_returned": len(bm_hits),
            "top_citation": bm_hits[0].get("citation") if bm_hits else None,
            "latency_seconds": round(lat, 3)
        }
    except Exception as e:
        bm25_details = {"error": str(e)}
    log_check("BM25 Inverted Lexical Index", bm25_passed, bm25_details)

    # -------------------------------------------------------------
    # 6. Definitions Index & Disambiguation
    # -------------------------------------------------------------
    def_passed = False
    def_details = {}
    def_path = BASE_DIR / "data" / "definitions_index.json"
    amb_path = BASE_DIR / "reports" / "ambiguous_terms.json"
    if def_path.exists() and amb_path.exists():
        try:
            with open(def_path, "r", encoding="utf-8") as f:
                def_idx = json.load(f)
            with open(amb_path, "r", encoding="utf-8") as f:
                amb_idx = json.load(f)

            wf = def_idx.get("willful default", [])
            wf_acts = [e.get("act_code") for e in wf]
            def_passed = len(def_idx) > 3500 and "FIO_2001" in wf_acts and "NAO_1999" in wf_acts
            def_details = {
                "total_defined_terms": len(def_idx),
                "ambiguous_terms_count": len(amb_idx),
                "willful_default_linked_acts": wf_acts
            }
        except Exception as e:
            def_details = {"error": str(e)}
    else:
        def_details = {"error": "Definitions index files missing"}
    log_check("Definitions & Ambiguity Index", def_passed, def_details)

    # -------------------------------------------------------------
    # 7. Exact Statute Resolver & get_section()
    # -------------------------------------------------------------
    from legal_ai.retrieval.statute_search import get_section
    resolver_cases = [
        ("PPC", "302", "PPC_1860_SEC_302"),
        ("CrPC", "497", "CRPC_1898_SEC_497"),
        ("Constitution", "199", "CONST_1973_ART_199"),
        ("FIO", "2(g)", "FIO_2001_SEC_2_g"),
        ("NAO", "5(u)", "NAO_1999_SEC_5_u"),
        ("CPC", "Order VII Rule 11", "CPC_1908_ORD_VII_R_11"),
        ("PRPA", "15", "PRPA_2009_SEC_15"),
    ]
    res_successes = []
    res_failures = []
    for act, sec, expected in resolver_cases:
        item = get_section(act, sec)
        cid = item.get("canonical_id") if item else None
        if cid == expected:
            res_successes.append(f"{act} {sec} -> {cid}")
        else:
            res_failures.append(f"{act} {sec} -> Got: {cid}, Expected: {expected}")

    res_passed = len(res_failures) == 0
    log_check("Exact Section Resolver", res_passed, {
        "verified_count": f"{len(res_successes)}/{len(resolver_cases)}",
        "failures": res_failures
    })

    # -------------------------------------------------------------
    # 8. Multi-Lane Parallel Orchestrator Across Key Legal Domains
    # -------------------------------------------------------------
    from legal_ai.retrieval.unified_orchestrator import retrieve_candidates_parallel
    from core.legal_query_planner import create_deterministic_fallback_plan

    test_queries = [
        ("Rent Eviction", "eviction notice to tenant for non-payment of rent"),
        ("Criminal Bail", "post-arrest bail in non-bailable murder offence 302 PPC 497 CrPC"),
        ("Banking Default", "willful default by company director on bank finance")
    ]
    orchestrator_results = {}
    orch_passed = True
    for label, q in test_queries:
        plan = create_deterministic_fallback_plan(q)
        t0 = time.time()
        cands, counts = await retrieve_candidates_parallel(q, query_plan=plan, top_k_per_engine=5)
        lat = time.time() - t0
        cases = [c for c in cands if not c.get("metadata", {}).get("is_statute", False)]
        statutes = [c for c in cands if c.get("metadata", {}).get("is_statute", False)]
        
        top_cases = [c.get("citation") or c.get("case_id") for c in cases[:3]]
        top_statutes = [c.get("citation") or c.get("case_id") for c in statutes[:3]]
        
        has_both = len(cases) > 0 and (len(statutes) > 0 or counts.get("count_statutory", 0) > 0)
        if not has_both:
            orch_passed = False

        orchestrator_results[label] = {
            "total_candidates": len(cands),
            "case_precedents_count": len(cases),
            "top_case_citations": top_cases,
            "statute_provisions_count": len(statutes),
            "top_statutes": top_statutes,
            "latency_seconds": round(lat, 3)
        }
    log_check("Multi-Lane Retrieval Orchestrator", orch_passed, orchestrator_results)

    # -------------------------------------------------------------
    # 9. FastAPI Search Service Endpoints
    # -------------------------------------------------------------
    from legal_ai.search.statute_search_service import search_statute_provisions, get_provision_full_text
    search_res = search_statute_provisions("eviction", limit=3)
    p_text = get_provision_full_text("PRPA_2009_SEC_15")
    svc_passed = (
        search_res.get("total_matches", 0) > 0
        and p_text is not None
        and len(p_text.get("text", "")) > 50
    )
    log_check("FastAPI Statute Search Service", svc_passed, {
        "matches_for_eviction": search_res.get("total_matches"),
        "top_match": search_res.get("results", [{}])[0].get("canonical_id") if search_res.get("results") else None,
        "verified_verbatim_text_loaded": bool(p_text and len(p_text.get("text", "")) > 50)
    })

    # -------------------------------------------------------------
    # Final Result
    # -------------------------------------------------------------
    all_passed = all(c["status"] == "PASS" for c in report["checks"].values())
    report["status"] = "ALL_SYSTEMS_OPERATIONAL" if all_passed else "DEGRADED"

    out_file = BASE_DIR / "reports" / "system_health_audit.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 80)
    print(f"FINAL AUDIT RESULT: {report['status']}")
    print(f"Detailed health audit saved to: {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
