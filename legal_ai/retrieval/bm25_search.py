"""
legal_ai/retrieval/bm25_search.py

Local Sparse BM25 Keyword Search driver for Pakistani Legal AI Corpus.
Scores 40,575 indexed judgment chunks for exact statutory phrases and terms.
"""

import sys
import re
import os
import gc
import threading
from typing import Dict, List, Any, Optional
from legal_ai.ranking.court_weighting import normalize_court_name


_GLOBAL_BM25_INSTANCE = None
_BM25_LOCK = threading.Lock()


def set_bm25_index_instance(instance: Any) -> None:
    """Explicitly injects or overrides the global singleton BM25 instance."""
    global _GLOBAL_BM25_INSTANCE
    with _BM25_LOCK:
        _GLOBAL_BM25_INSTANCE = instance


def get_bm25_index_instance() -> Any:
    """
    Returns the thread-safe global singleton BM25 index instance.
    Reuses main.global_bm25_index if already loaded to eliminate duplicate RAM usage.
    """
    global _GLOBAL_BM25_INSTANCE
    from legal_ai.retrieval.turso_fts_index import wrap_keyword_index

    if os.environ.get("RENDER") or os.environ.get("DISABLE_IN_MEMORY_BM25", "").lower() in ("true", "1", "yes"):
        # No in-memory pickle on low-memory hosts; keyword search runs on Turso FTS.
        with _BM25_LOCK:
            if _GLOBAL_BM25_INSTANCE is None:
                _GLOBAL_BM25_INSTANCE = wrap_keyword_index(None)
        return _GLOBAL_BM25_INSTANCE

    if _GLOBAL_BM25_INSTANCE is not None:
        return _GLOBAL_BM25_INSTANCE

    with _BM25_LOCK:
        if _GLOBAL_BM25_INSTANCE is not None:
            return _GLOBAL_BM25_INSTANCE

        # Check if main.py has already loaded the global index
        main_mod = sys.modules.get("main")
        if main_mod is not None:
            main_idx = getattr(main_mod, "global_bm25_index", None)
            if main_idx is not None:
                _GLOBAL_BM25_INSTANCE = main_idx
                return _GLOBAL_BM25_INSTANCE

        try:
            from hybrid_search import BM25Index
            idx_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bm25_index.pkl")
            if os.path.exists(idx_path):
                _GLOBAL_BM25_INSTANCE = wrap_keyword_index(BM25Index.load(idx_path))
                gc.collect()
        except Exception as err:
            print(f"⚠️ [BM25Search] Error loading BM25 index: {err}", file=sys.stderr)

    return _GLOBAL_BM25_INSTANCE


def search_bm25_sparse(
    query_text: str,
    top_k: int = 40,
    bm25_index_instance: Any = None
) -> List[Dict[str, Any]]:
    """
    Executes BM25 keyword retrieval across the local corpus chunks.
    """
    if not query_text:
        return []

    # Obtain BM25 index if not passed directly
    if bm25_index_instance is None:
        bm25_index_instance = get_bm25_index_instance()

    if not bm25_index_instance:
        return []

    try:
        raw_results = bm25_index_instance.search(query_text, top_k=top_k)
    except Exception as b_err:
        print(f"⚠️ [BM25Search] Search error for query of length {len(query_text)}: {b_err}", file=sys.stderr)
        return []

    candidates: List[Dict[str, Any]] = []
    for r in raw_results:
        # Result tuple: (chunk_id, score, meta) or dict
        if isinstance(r, dict):
            cid = str(r.get("case_id") or r.get("id") or "")
            score = float(r.get("score", 0.0))
            meta = r.get("metadata", {})
        elif isinstance(r, (tuple, list)) and len(r) >= 3:
            cid = str(r[0])
            score = float(r[1])
            meta = r[2] if isinstance(r[2], dict) else {}
        else:
            continue

        title = str(meta.get("title") or meta.get("case_title") or "Precedent on Record").strip()
        cit = str(meta.get("citation") or meta.get("neutral_citation") or cid).strip()
        raw_court = str(meta.get("court") or meta.get("court_name") or "Supreme Court of Pakistan").strip()
        court = normalize_court_name(raw_court)
        text = str(meta.get("text") or meta.get("full_text") or meta.get("snippet") or "").strip()
        content_type = str(meta.get("content_type") or "full_text").lower()

        year = meta.get("year")
        if not year:
            m_year = re.search(r'\b(19\d{2}|20\d{2})\b', f"{cit} {title}")
            year = int(m_year.group(1)) if m_year else 2020

        clean_case_id = str(meta.get("case_id") or "").strip()
        if not clean_case_id:
            clean_case_id = re.sub(r'(_chk_\d+|_chunk_\d+|#c\d+)$', '', str(cid), flags=re.IGNORECASE).strip()
        final_id = clean_case_id or cid

        candidates.append({
            "id": final_id,
            "case_id": final_id,
            "chunk_id": cid,
            "score": score,
            "dense_score": 0.0,
            "sparse_score": score,
            "bm25_score": score,
            "rrf_score": 0.0,
            "source_type": "BM25",
            "citation": cit,
            "title": title,
            "case_name": title,
            "court": court,
            "year": year,
            "content_type": content_type,
            "preview": text[:1500] if text else "",
            "metadata": meta
        })

    return candidates
