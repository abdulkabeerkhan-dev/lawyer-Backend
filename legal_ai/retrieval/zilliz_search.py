"""
legal_ai/retrieval/zilliz_search.py

Production Hybrid Search Driver for Pakistani Court Judgments on Zilliz Cloud.
Leverages Voyage AI (voyage-4-large) 1024-dimension embeddings, in-engine BM25 sparse vectors,
Reciprocal Rank Fusion (RRF), native case grouping (group_by_field="case_key"),
and Constitutional judicial hierarchy authority priors (Articles 189 & 201).

Follows docs/ZILLIZ_MIGRATION_PLAN.md §10, §11, §12.
"""

import os
import sys
import re
import math
import time
import asyncio
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Tuple, Set, Union

from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker

from legal_ai.config import (
    get_zilliz_client,
    ZILLIZ_COLLECTION,
    get_voyage_embedding,
    VOYAGE_MODEL,
    VOYAGE_API_KEY,
)
from legal_ai.ranking.court_weighting import normalize_court_name
from core.provider_ledger import ProviderStatus, record_provider_event

logger = logging.getLogger(__name__)

# Project root path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SQLITE_DB_PATH = os.path.join(PROJECT_ROOT, "data", "cases_v2.db")

# Zilliz Circuit Breaker to fast-fail on auth or connection errors
_ZILLIZ_CIRCUIT_TRIPPED_UNTIL: float = 0.0
_ZILLIZ_CIRCUIT_REASON: str = ""
_ZILLIZ_PROBE_CACHE: Dict[str, Any] = {"checked_at": 0.0, "result": None}
_ZILLIZ_PROBE_TTL_S: float = 60.0


def is_zilliz_circuit_open() -> bool:
    """Returns True if the Zilliz circuit breaker is active."""
    return time.time() < _ZILLIZ_CIRCUIT_TRIPPED_UNTIL


def trip_zilliz_circuit(duration: float = 60.0, reason: str = "") -> None:
    """Trips the Zilliz circuit breaker to avoid cascading timeouts and thread storms."""
    global _ZILLIZ_CIRCUIT_TRIPPED_UNTIL, _ZILLIZ_CIRCUIT_REASON
    _ZILLIZ_CIRCUIT_TRIPPED_UNTIL = time.time() + duration
    _ZILLIZ_CIRCUIT_REASON = reason
    logger.warning(f"⚠️ [ZillizSearch] CIRCUIT BREAKER TRIPPED for {duration}s: {reason}")


def probe_zilliz(force: bool = False) -> Dict[str, Any]:
    """
    Health check probe for Zilliz Cloud, reporting collection status and live row count.
    Used by /health endpoint (matching probe_pinecone).
    """
    global _ZILLIZ_PROBE_CACHE
    now = time.time()
    cached = _ZILLIZ_PROBE_CACHE.get("result")
    if cached is not None and not force and (now - _ZILLIZ_PROBE_CACHE["checked_at"] < _ZILLIZ_PROBE_TTL_S):
        return cached

    uri = os.environ.get("ZILLIZ_URI")
    token = os.environ.get("ZILLIZ_TOKEN")
    if not uri or not token:
        result = {"ok": False, "error": "ZILLIZ_URI or ZILLIZ_TOKEN not set"}
        _ZILLIZ_PROBE_CACHE.update(checked_at=now, result=result)
        return result

    client = get_zilliz_client()
    if client is None:
        result = {"ok": False, "error": "Zilliz client failed to initialize"}
        _ZILLIZ_PROBE_CACHE.update(checked_at=now, result=result)
        return result

    try:
        res = client.query(
            collection_name=ZILLIZ_COLLECTION,
            output_fields=["count(*)"]
        )
        row_count = res[0].get("count(*)", 0) if res else 0
        result = {
            "ok": bool(row_count > 0),
            "collection": ZILLIZ_COLLECTION,
            "row_count": row_count,
            "status": "connected"
        }
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"⚠️ [ZillizSearch] Health probe failed: {err_msg}")
        result = {"ok": False, "collection": ZILLIZ_COLLECTION, "error": err_msg}

    _ZILLIZ_PROBE_CACHE.update(checked_at=now, result=result)
    return result


def get_case_metadata_from_sqlite(case_key: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches rich case metadata, parties, judges, and clean judgment/headnote text
    from the local SQLite cases_v2 database.
    """
    target_path = db_path or SQLITE_DB_PATH
    if not os.path.exists(target_path):
        return None

    try:
        conn = sqlite3.connect(target_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT case_key, citation, journal, year, court_code, court_name,
                   court_level, page, parties, judge, content_level,
                   headnote_text, judgment_text, domain, cited_by_count, statutes
            FROM cases_v2 WHERE case_key = ?
            """,
            (case_key,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.debug(f"[ZillizSearch] SQLite metadata lookup failed for {case_key}: {e}")
        return None


def calculate_authority_score(
    rrf_score: float,
    court_level: int,
    cited_by_count: int,
) -> float:
    """
    Calculates final composite relevance score based on RRF match score
    and Constitutional judicial hierarchy weights (Articles 189 & 201).
    """
    # Constitutional Tier Weight:
    # Supreme Court (Level 1) = 1.30 (binding on all Pakistani courts)
    # High Courts (Level 2)   = 1.10 (binding on provincial subordinate courts)
    # Tribunals / District    = 1.00
    if court_level == 1:
        court_mult = 1.30
    elif court_level == 2:
        court_mult = 1.10
    else:
        court_mult = 1.00

    # Inbound citation frequency boost: log-scaled, capped
    citation_boost = 1.0 + 0.05 * min(10.0, math.log(1 + max(0, cited_by_count)))

    return rrf_score * court_mult * citation_boost


async def search_zilliz_hybrid(
    query_text: str,
    top_k: int = 40,
    min_similarity: float = 0.0,
    query_plan: Optional[Any] = None,
    filter_expr: Optional[str] = None,
    timeout_seconds: float = 12.0
) -> List[Dict[str, Any]]:
    """
    Executes hybrid dense (Voyage-4-large) + sparse (in-engine BM25) search on Zilliz Cloud,
    grouped by case_key, with Constitutional court authority weighting.
    
    100% compatible with candidate return shape expected by unified_orchestrator.
    """
    if not query_text or is_zilliz_circuit_open():
        return []

    client = get_zilliz_client()
    if not client:
        record_provider_event("Zilliz", ProviderStatus.PROVIDER_DOWN, message="Zilliz client unavailable.")
        return []

    # 1. Generate query embedding with voyage-4-large
    query_vector: Optional[List[float]] = None
    try:
        query_vector = await asyncio.wait_for(
            get_voyage_embedding(query_text, input_type="query"),
            timeout=8.0
        )
    except Exception as emb_err:
        logger.warning(f"⚠️ [ZillizSearch] Voyage embedding failed, falling back to sparse-only: {emb_err}")

    # 2. Build search requests
    def _execute_search():
        if query_vector is not None:
            # Multi-vector Hybrid Search with RRFRanker
            req_dense = AnnSearchRequest(
                data=[query_vector],
                anns_field="dense",
                param={"metric_type": "COSINE"},
                limit=top_k * 2,
                expr=filter_expr
            )
            req_sparse = AnnSearchRequest(
                data=[query_text],
                anns_field="sparse",
                param={"metric_type": "BM25"},
                limit=top_k * 2,
                expr=filter_expr
            )
            raw_res = client.hybrid_search(
                collection_name=ZILLIZ_COLLECTION,
                reqs=[req_dense, req_sparse],
                ranker=RRFRanker(k=60),
                limit=top_k * 2,
                group_by_field="case_key",
                output_fields=[
                    "case_key", "citation", "section", "court_level",
                    "cited_by_count", "domain", "statutes", "text"
                ]
            )
        else:
            # Fallback: Sparse-only BM25 search
            raw_res = client.search(
                collection_name=ZILLIZ_COLLECTION,
                data=[query_text],
                anns_field="sparse",
                limit=top_k * 2,
                group_by_field="case_key",
                filter=filter_expr,
                output_fields=[
                    "case_key", "citation", "section", "court_level",
                    "cited_by_count", "domain", "statutes", "text"
                ]
            )
        return raw_res[0] if raw_res else []

    # 3. Execute in background thread with timeout
    try:
        loop = asyncio.get_running_loop()
        hits = await asyncio.wait_for(
            loop.run_in_executor(None, _execute_search),
            timeout=timeout_seconds
        )
        record_provider_event(
            "Zilliz",
            ProviderStatus.SUCCESS if hits else ProviderStatus.EMPTY,
            result_count=len(hits),
        )
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ [ZillizSearch] Search timed out after {timeout_seconds}s")
        record_provider_event("Zilliz", ProviderStatus.TIMEOUT, message=f"Timeout after {timeout_seconds}s")
        return []
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"⚠️ [ZillizSearch] Query error: {err_msg}")
        if any(tok in err_msg for tok in ("illegal connection params", "Fail connecting", "UNAUTHENTICATED")):
            trip_zilliz_circuit(60.0, err_msg)
            record_provider_event("Zilliz", ProviderStatus.PROVIDER_DOWN, message=err_msg)
        else:
            record_provider_event("Zilliz", ProviderStatus.ERROR, message=err_msg)
        return []

    # 4. Score and format candidates
    candidates: List[Dict[str, Any]] = []
    for h in hits:
        ent = h.get("entity", {})
        case_key = ent.get("case_key") or ""
        citation = ent.get("citation") or case_key
        section = ent.get("section") or "headnote"
        text = ent.get("text") or ""
        court_level = int(ent.get("court_level") or 3)
        cited_by = int(ent.get("cited_by_count") or 0)
        domain = ent.get("domain") or "general"
        statutes = ent.get("statutes") or []

        rrf_score = float(h.get("distance", 0.0))
        final_score = calculate_authority_score(rrf_score, court_level, cited_by)

        # Lookup rich metadata from local SQLite
        db_meta = get_case_metadata_from_sqlite(case_key)
        if db_meta:
            title = db_meta.get("parties") or citation
            court = db_meta.get("court_name") or "Supreme Court of Pakistan" if court_level == 1 else "High Court"
            year = db_meta.get("year") or 2020
            content_type = db_meta.get("content_level") or "headnote"
            full_text = db_meta.get("judgment_text") or text
        else:
            title = citation
            court = "Supreme Court of Pakistan" if court_level == 1 else "High Court"
            year = 2020
            content_type = "headnote"
            full_text = text

        court = normalize_court_name(court, citation=citation)

        cand = {
            "id": f"{case_key}:{section}",
            "case_id": case_key,
            "case_key": case_key,
            "score": final_score,
            "dense_score": rrf_score,
            "sparse_score": 0.0,
            "rrf_score": rrf_score,
            "source_type": "Zilliz",
            "citation": citation,
            "title": title,
            "case_name": title,
            "court": court,
            "court_level": court_level,
            "year": year,
            "content_type": content_type,
            "segment_type": section,
            "domain": domain,
            "legal_domain": domain,
            "subdomain": "general",
            "statutes_cited": statutes,
            "preview": text[:400],
            "text": full_text if content_type == "full_judgment" and len(full_text) > len(text) else text,
            "metadata": {
                "case_key": case_key,
                "court_level": court_level,
                "cited_by_count": cited_by,
                "section": section,
                "domain": domain,
                "statutes": statutes,
            }
        }
        candidates.append(cand)

    # Sort by authority-weighted final score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]


async def search_zilliz_dense(
    query_text: str,
    top_k: int = 40,
    min_similarity: float = 0.0,
    query_plan: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Direct drop-in replacement for search_pinecone_dense.
    Routes to search_zilliz_hybrid for best retrieval quality.
    """
    return await search_zilliz_hybrid(
        query_text=query_text,
        top_k=top_k,
        min_similarity=min_similarity,
        query_plan=query_plan
    )


# Drop-in alias for existing imports
search_pinecone_dense = search_zilliz_hybrid
