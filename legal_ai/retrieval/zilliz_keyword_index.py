"""
legal_ai/retrieval/zilliz_keyword_index.py

Keyword (BM25) search over every judgment chunk in Zilliz (`judgments_v1`, ~1.77M
chunks), using the collection's in-engine BM25 function on the `sparse` field.
It replaces the Turso FTS5 index (141k cases) and keeps the same interface as
`hybrid_search.BM25Index`, so existing callers work unchanged:

    index.search(query, top_k) -> List[(doc_id, score, metadata)]
    index.corpus_size          -> int (> 0 when usable)

doc_id is the Zilliz `case_key` (e.g. "2020_PCRLJ_LHC_1445"), the same id the
Zilliz vector lane returns, so keyword and vector hits fuse on one key.
Falls back to the in-memory index (if provided) when Zilliz is unavailable.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_COURTS = {
    "SC": "Supreme Court of Pakistan",
    "FSC": "Federal Shariat Court",
    "LHC": "Lahore High Court",
    "SHC": "Sindh High Court",
    "PHC": "Peshawar High Court",
    "BHC": "Balochistan High Court",
    "IHC": "Islamabad High Court",
    "AJKHC": "High Court of Azad Jammu and Kashmir",
    "AJKSC": "Supreme Court of Azad Jammu and Kashmir",
    "GBSAC": "Supreme Appellate Court Gilgit-Baltistan",
    "GBCC": "Chief Court Gilgit-Baltistan",
}
_MAX_QUERY_CHARS = 600
_OUTPUT_FIELDS = ["case_key", "citation", "journal", "year", "court_code", "content_level", "section", "text"]


def keyword_backend() -> str:
    return os.environ.get("KEYWORD_SEARCH_BACKEND", "zilliz_bm25").strip().lower()


def wrap_keyword_index(in_memory_index: Any) -> Any:
    """
    Returns the keyword index production should use: Zilliz BM25 over the full
    corpus, with the in-memory pickle (if loaded) as fallback.
    Set KEYWORD_SEARCH_BACKEND=pickle to use only the in-memory index.
    """
    if keyword_backend() == "pickle":
        return in_memory_index
    if isinstance(in_memory_index, ZillizKeywordIndex):
        return in_memory_index
    return ZillizKeywordIndex(fallback=in_memory_index)


class ZillizKeywordIndex:
    """BM25Index-compatible keyword search over Zilliz's BM25 sparse field."""

    def __init__(self, fallback: Any = None, timeout: float = 6.0, corpus_size_hint: int = 191_872):
        self.fallback = fallback
        self.timeout = timeout
        self._corpus_size_hint = corpus_size_hint
        self.last_backend: str = "none"
        self.last_latency_ms: float = 0.0

    @property
    def corpus_size(self) -> int:
        # Callers guard on corpus_size > 0. Zilliz availability is checked per query.
        return self._corpus_size_hint

    @property
    def doc_metadata(self) -> List[Dict[str, Any]]:
        # memo_verifier builds a known-citation set from this; keep the fallback's.
        return list(getattr(self.fallback, "doc_metadata", None) or [])

    def search(self, query: str, top_k: int = 40) -> List[Tuple[str, float, Dict[str, Any]]]:
        q = " ".join(str(query or "").split())[:_MAX_QUERY_CHARS]
        results = self._search_zilliz(q, top_k) if q else []
        if results:
            self.last_backend = "zilliz_bm25"
            return results
        if self.fallback is not None and getattr(self.fallback, "corpus_size", 0) > 0:
            self.last_backend = "in_memory_bm25_fallback"
            try:
                return self.fallback.search(query, top_k=top_k)
            except Exception as err:  # pragma: no cover - defensive
                logger.warning(f"[ZillizBM25] fallback BM25 failed: {err}")
        self.last_backend = "none"
        return []

    def _search_zilliz(self, query: str, top_k: int) -> List[Tuple[str, float, Dict[str, Any]]]:
        try:
            from legal_ai.config import get_zilliz_client, ZILLIZ_COLLECTION
            from legal_ai.retrieval.zilliz_search import is_zilliz_circuit_open
            from core.hierarchical_legal_chunker import HierarchicalLegalChunker
        except Exception as err:  # pragma: no cover
            logger.warning(f"[ZillizBM25] import error: {err}")
            return []
        if is_zilliz_circuit_open():
            return []
        client = get_zilliz_client()
        if client is None:
            return []
        t0 = time.time()
        try:
            res = client.search(
                collection_name=ZILLIZ_COLLECTION,
                data=[query],
                anns_field="sparse",
                search_params={"metric_type": "BM25"},
                limit=int(top_k),
                group_by_field="case_key",
                output_fields=_OUTPUT_FIELDS,
                timeout=self.timeout,
            )
        except Exception as err:
            logger.warning(f"[ZillizBM25] query error: {err} (q={query[:120]})")
            return []
        finally:
            self.last_latency_ms = (time.time() - t0) * 1000

        out: List[Tuple[str, float, Dict[str, Any]]] = []
        for hit in (res[0] if res else []):
            ent = hit.get("entity", {}) if isinstance(hit, dict) else {}
            case_key = str(ent.get("case_key") or "")
            if not case_key:
                continue
            citation = str(ent.get("citation") or case_key.replace("_", " "))
            text = HierarchicalLegalChunker.clean_portal_debris(ent.get("text") or "")
            meta = {
                "case_id": case_key,
                "citation": citation,
                "neutral_citation": citation,
                "title": citation,
                "case_title": citation,
                "court": _COURTS.get(str(ent.get("court_code") or "").upper(), "High Court"),
                "year": ent.get("year"),
                "journal": ent.get("journal"),
                "text": text,
                "content_type": "full_text" if ent.get("section") not in (None, "", "headnote") else "headnote",
                "content_level": ent.get("content_level"),
                "segment_type": ent.get("section"),
                "chunk_index": 0,
                "retrieval_backend": "zilliz_bm25",
            }
            out.append((case_key, float(hit.get("distance") or 0.0), meta))
        return out
