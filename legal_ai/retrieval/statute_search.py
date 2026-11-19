"""
legal_ai/retrieval/statute_search.py

Production Hybrid Search and Pinpoint Retrieval Driver for Pakistani Statutes on Zilliz Cloud (statutes_v3).
Leverages Voyage AI (voyage-4-large) 1024-dimension embeddings, in-engine BM25 sparse vectors,
Reciprocal Rank Fusion (RRF), spelling normalization (willful <-> wilful),
domain filtering, and seamless local fallback to UnifiedStatuteStore.
"""

import os
import re
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional

from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker

from legal_ai.config import (
    get_zilliz_client,
    get_voyage_embedding,
    VOYAGE_MODEL,
    VOYAGE_API_KEY,
)
from core.unified_statute_store import get_unified_statute_store

logger = logging.getLogger(__name__)

STATUTES_COLLECTION = os.environ.get("ZILLIZ_STATUTES_COLLECTION", "statutes_v3")

# Load citation alias mappings from report if present
_ALIAS_MAP: Dict[str, str] = {}
try:
    _report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "reports",
        "citation_reconciliation_report.json"
    )
    if os.path.exists(_report_path):
        with open(_report_path, "r", encoding="utf-8") as _rf:
            _rdata = json.load(_rf)
            _ALIAS_MAP = _rdata.get("proposed_aliases", {})
except Exception as _e:
    logger.debug(f"Could not load citation reconciliation aliases: {_e}")


def normalize_statute_query_spelling(query: str) -> str:
    """
    Normalizes spelling variations in statutory terms, specifically
    equating 'wilful' and 'willful' so both spellings match indexed tokens.
    """
    if not query:
        return ""
    # Equate wilful / willful to 'willful'
    norm = re.sub(r'\bwilful\b', 'willful', query, flags=re.IGNORECASE)
    norm = re.sub(r'\bwilfully\b', 'willfully', norm, flags=re.IGNORECASE)
    norm = re.sub(r'\bwilfulness\b', 'willfulness', norm, flags=re.IGNORECASE)
    return norm


def resolve_canonical_id_alias(cid: str) -> str:
    """Resolves canonical ID aliases e.g. CONST_1973_SEC_199 -> CONST_1973_ART_199."""
    if not cid:
        return ""
    clean = cid.strip().upper()
    return _ALIAS_MAP.get(clean, clean)


async def search_statutes_hybrid(
    query_text: str,
    top_k: int = 10,
    domain: Optional[str] = None,
    act_code: Optional[str] = None,
    in_force_only: bool = True,
    timeout_seconds: float = 8.0
) -> List[Dict[str, Any]]:
    """
    Executes hybrid dense (Voyage-4-large) + sparse (in-engine BM25) search on Zilliz Cloud
    against `statutes_v3`.
    
    If Zilliz Cloud is unavailable or query fails, seamlessly falls back to
    local UnifiedStatuteStore text search.
    """
    if not query_text or not query_text.strip():
        return []

    norm_query = normalize_statute_query_spelling(query_text.strip())

    # Build filter expression
    filters = []
    if in_force_only:
        filters.append("in_force == true")
    if domain:
        filters.append(f'domain == "{domain}"')
    if act_code:
        filters.append(f'act_code == "{act_code.upper()}"')
    filter_expr = " and ".join(filters) if filters else None

    client = get_zilliz_client()
    if client:
        try:
            # 1. Generate dense embedding via voyage-4-large
            query_vector: Optional[List[float]] = None
            try:
                query_vector = await asyncio.wait_for(
                    get_voyage_embedding(norm_query, input_type="query"),
                    timeout=6.0
                )
            except Exception as emb_err:
                logger.warning(f"[StatuteSearch] Voyage embedding failed, falling back to sparse: {emb_err}")

            def _execute_zilliz_search():
                if query_vector is not None:
                    dense_req = AnnSearchRequest(
                        data=[query_vector],
                        anns_field="dense",
                        param={"metric_type": "COSINE"},
                        limit=top_k * 2,
                        expr=filter_expr
                    )
                    sparse_req = AnnSearchRequest(
                        data=[norm_query],
                        anns_field="sparse",
                        param={"metric_type": "BM25"},
                        limit=top_k * 2,
                        expr=filter_expr
                    )
                    raw_res = client.hybrid_search(
                        collection_name=STATUTES_COLLECTION,
                        reqs=[dense_req, sparse_req],
                        ranker=RRFRanker(k=60),
                        limit=top_k,
                        output_fields=[
                            "canonical_id", "act_code", "act_name", "section",
                            "heading", "domain", "forum", "source", "tier",
                            "in_force", "provision_type", "text",
                            "supersedes", "superseded_by", "former_labels"
                        ]
                    )
                else:
                    raw_res = client.search(
                        collection_name=STATUTES_COLLECTION,
                        data=[norm_query],
                        anns_field="sparse",
                        limit=top_k,
                        filter=filter_expr,
                        output_fields=[
                            "canonical_id", "act_code", "act_name", "section",
                            "heading", "domain", "forum", "source", "tier",
                            "in_force", "provision_type", "text",
                            "supersedes", "superseded_by", "former_labels"
                        ]
                    )
                return raw_res[0] if raw_res else []

            loop = asyncio.get_running_loop()
            hits = await asyncio.wait_for(
                loop.run_in_executor(None, _execute_zilliz_search),
                timeout=timeout_seconds
            )

            if hits:
                results = []
                for h in hits:
                    ent = h.get("entity", {})
                    results.append({
                        "canonical_id": ent.get("canonical_id", ""),
                        "act_code": ent.get("act_code", ""),
                        "act_name": ent.get("act_name", ""),
                        "section": ent.get("section", ""),
                        "heading": ent.get("heading", ""),
                        "title": ent.get("heading", "") or f"Section {ent.get('section', '')}",
                        "domain": ent.get("domain", ""),
                        "forum": ent.get("forum", ""),
                        "provision_type": ent.get("provision_type", "section"),
                        "source": ent.get("source", "pakistan_code"),
                        "tier": ent.get("tier", "ingested_unreviewed"),
                        "in_force": ent.get("in_force", True),
                        "text": ent.get("text", ""),
                        "raw_text": ent.get("raw_text", ""),
                        "supersedes": ent.get("supersedes"),
                        "superseded_by": ent.get("superseded_by"),
                        "former_labels": ent.get("former_labels") or [],
                        "score": float(h.get("distance", 0.0)),
                    })
                return results

        except Exception as e:
            logger.warning(f"[StatuteSearch] Zilliz search failed, using local store fallback: {e}")

    # Fallback: Local search via UnifiedStatuteStore
    return search_statutes_local_fallback(norm_query, top_k=top_k, act_code=act_code)


def search_statutes_local_fallback(
    query_text: str,
    top_k: int = 10,
    act_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Local keyword-matching fallback over UnifiedStatuteStore provisions."""
    store = get_unified_statute_store()
    q_low = query_text.lower()
    q_terms = [t for t in q_low.split() if len(t) > 2]

    candidates = []
    for cid, rec in store._by_cid.items():
        if act_code and rec.get("act_code", "").upper() != act_code.upper():
            continue

        score = 0.0
        txt = (rec.get("text") or rec.get("text_raw") or "").lower()
        title = (rec.get("title") or rec.get("heading") or "").lower()

        if q_low in title:
            score += 10.0
        if q_low in txt:
            score += 5.0

        for t in q_terms:
            if t in title:
                score += 2.0
            if t in txt:
                score += 0.5

        if score > 0.0:
            candidates.append({
                "canonical_id": cid,
                "act_code": rec.get("act_code", ""),
                "act_name": rec.get("act_name", ""),
                "section": rec.get("section") or rec.get("primary_num", ""),
                "heading": rec.get("heading") or rec.get("title", ""),
                "title": rec.get("title") or rec.get("heading", ""),
                "domain": rec.get("domain", ""),
                "forum": rec.get("forum", ""),
                "provision_type": rec.get("provision_type", "section"),
                "source": rec.get("source", "pakistan_code"),
                "tier": rec.get("tier", "ingested_unreviewed"),
                "in_force": rec.get("in_force", True),
                "text": rec.get("text") or rec.get("text_raw", ""),
                "raw_text": rec.get("raw_text", ""),
                "score": score
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]


def get_statute_by_canonical_id(canonical_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves full provision details by canonical ID, resolving aliases
    and querying UnifiedStatuteStore or Zilliz Cloud.
    """
    if not canonical_id:
        return None

    resolved_cid = resolve_canonical_id_alias(canonical_id)
    store = get_unified_statute_store()
    rec = store.get_by_canonical_id(resolved_cid)
    if rec:
        return rec

    # Direct query to Zilliz if not in local memory
    client = get_zilliz_client()
    if client:
        try:
            hits = client.query(
                collection_name=STATUTES_COLLECTION,
                filter=f'canonical_id == "{resolved_cid}"',
                output_fields=[
                    "canonical_id", "act_code", "act_name", "section",
                    "heading", "domain", "forum", "source", "tier",
                    "in_force", "provision_type", "text",
                    "supersedes", "superseded_by", "former_labels"
                ],
                limit=1
            )
            if hits:
                return hits[0]
        except Exception as e:
            logger.debug(f"[StatuteSearch] Zilliz query for {resolved_cid} failed: {e}")

    return None
