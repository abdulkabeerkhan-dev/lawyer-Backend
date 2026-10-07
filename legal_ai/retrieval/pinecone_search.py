"""
legal_ai/retrieval/pinecone_search.py

Dense Semantic Vector Search driver for Pakistani Court Judgments.
Leverages Voyage AI (voyage-law-2) 1024-dimension embeddings and Pinecone vector store.
"""

import sys
import re
from typing import Dict, List, Any, Optional
from legal_ai.config import get_pinecone_index, PINECONE_NAMESPACE, get_voyage_embedding
from legal_ai.ranking.court_weighting import normalize_court_name


async def search_pinecone_dense(
    query_text: str,
    top_k: int = 40,
    min_similarity: float = 0.40
) -> List[Dict[str, Any]]:
    """
    Computes dense query embedding and searches Pinecone index.
    Returns matched judgment chunks tagged with source_type="Pinecone".
    """
    index = get_pinecone_index()
    if not index or not query_text:
        return []

    try:
        query_vector = await get_voyage_embedding(query_text)
    except Exception as emb_err:
        print(f"⚠️ [PineconeSearch] Voyage embedding error: {emb_err}", file=sys.stderr)
        return []

    try:
        res = index.query(
            namespace=PINECONE_NAMESPACE,
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
    except Exception as q_err:
        print(f"⚠️ [PineconeSearch] Pinecone query error: {q_err}", file=sys.stderr)
        return []

    candidates: List[Dict[str, Any]] = []
    matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])

    for m in matches:
        m_dict = dict(m) if isinstance(m, dict) else {"id": getattr(m, "id", ""), "score": getattr(m, "score", 0.0), "metadata": getattr(m, "metadata", {})}
        score = float(m_dict.get("score", 0.0))
        if score < min_similarity:
            continue

        meta = m_dict.get("metadata", {})
        cid = str(meta.get("case_id") or meta.get("id") or m_dict.get("id", "")).strip()
        title = str(meta.get("title") or meta.get("case_title") or "Precedent on Record").strip()
        cit = str(meta.get("citation") or meta.get("neutral_citation") or cid).strip()
        raw_court = str(meta.get("court") or meta.get("court_name") or "Supreme Court of Pakistan").strip()
        court = normalize_court_name(raw_court)
        text = str(meta.get("text") or meta.get("full_text") or meta.get("text_preview") or "").strip()
        content_type = str(meta.get("content_type") or "full_text").lower()

        # Extract year
        year = meta.get("year")
        if not year:
            m_year = re.search(r'\b(19\d{2}|20\d{2})\b', f"{cit} {title}")
            year = int(m_year.group(1)) if m_year else 2020

        candidates.append({
            "id": cid,
            "score": score,
            "dense_score": score,
            "sparse_score": 0.0,
            "rrf_score": 0.0,
            "source_type": "Pinecone",
            "citation": cit,
            "title": title,
            "case_name": title,
            "court": court,
            "year": year,
            "content_type": content_type,
            "preview": text[:400],
            "metadata": meta
        })

    return candidates
