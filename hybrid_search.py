"""
Hybrid Search Engine — Dense (Pinecone) + Sparse (BM25) with Reciprocal Rank Fusion

This module provides a universal hybrid retrieval pipeline that combines
Voyage-law-2 dense vector search via Pinecone with client-side BM25 sparse
keyword matching, fused via Reciprocal Rank Fusion (RRF).

Universal implementation across all legal subject areas.
"""

import os
import re
import sys
import pickle
import logging
from typing import List, Dict, Any, Tuple, Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger("hybrid_search")

# ---------------------------------------------------------------------------
# Legal-aware tokenizer (universal, not domain-specific)
# ---------------------------------------------------------------------------
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "be", "as", "was", "were",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "this",
    "that", "these", "those", "there", "here", "where", "when", "how",
    "what", "which", "who", "whom", "whose", "not", "no", "nor", "so",
    "if", "then", "than", "too", "very", "just", "also", "about", "above",
    "after", "before", "between", "into", "through", "during", "each",
    "some", "such", "only", "own", "same", "other", "its", "his", "her",
    "their", "our", "my", "your", "am", "are",
})

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+(?:[-/.][a-zA-Z0-9]+)*")


def tokenize_legal_text(text: str) -> List[str]:
    """
    Tokenize legal text for BM25. Preserves citations, section numbers,
    statutory tags, and legal terminology. Lowercases tokens.
    """
    if not text:
        return []
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


# ---------------------------------------------------------------------------
# BM25 Index
# ---------------------------------------------------------------------------
class BM25Index:
    """
    Pre-fitted BM25 index over judgment text chunks.
    Serializable to disk for fast startup.
    """

    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.doc_ids: List[str] = []          # vector IDs
        self.doc_metadata: List[Dict] = []    # metadata dicts
        self.corpus_size: int = 0

    def fit(self, documents: List[Dict[str, Any]]) -> None:
        """
        Fit BM25 on a list of documents.
        Each document must have: {"id": str, "text": str, "metadata": dict}
        """
        tokenized_corpus = []
        self.doc_ids = []
        self.doc_metadata = []

        for doc in documents:
            text = doc.get("text") or doc.get("text_content") or ""
            tokens = tokenize_legal_text(text)
            if not tokens:
                continue
            tokenized_corpus.append(tokens)
            self.doc_ids.append(str(doc["id"]))
            self.doc_metadata.append(doc.get("metadata", {}))

        if tokenized_corpus:
            self.bm25 = BM25Okapi(tokenized_corpus)
            self.corpus_size = len(tokenized_corpus)
            logger.info(f"BM25 index fitted on {self.corpus_size} documents")
        else:
            logger.warning("BM25 index fitted on 0 documents — corpus was empty")

    def search(self, query: str, top_k: int = 40) -> List[Tuple[str, float, Dict]]:
        """
        Search the BM25 index. Returns [(doc_id, bm25_score, metadata), ...]
        sorted by descending BM25 score.
        """
        if not self.bm25 or self.corpus_size == 0:
            return []

        query_tokens = tokenize_legal_text(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((
                    self.doc_ids[idx],
                    float(scores[idx]),
                    self.doc_metadata[idx]
                ))

        return results

    def save(self, path: str) -> None:
        """Serialize the fitted BM25 index to disk."""
        data = {
            "bm25": self.bm25,
            "doc_ids": self.doc_ids,
            "doc_metadata": self.doc_metadata,
            "corpus_size": self.corpus_size,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        logger.info(f"BM25 index saved to {path} ({size_mb:.1f} MB, {self.corpus_size} docs)")

    @classmethod
    def load(cls, path: str) -> "BM25Index":
        """Load a pre-built BM25 index from disk."""
        idx = cls()
        with open(path, "rb") as f:
            data = pickle.load(f)
        idx.bm25 = data["bm25"]
        idx.doc_ids = data["doc_ids"]
        idx.doc_metadata = data["doc_metadata"]
        idx.corpus_size = data["corpus_size"]
        logger.info(f"BM25 index loaded from {path} ({idx.corpus_size} docs)")
        return idx


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------
def reciprocal_rank_fusion(
    dense_results: List[Tuple[str, float, Dict]],
    sparse_results: List[Tuple[str, float, Dict]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    Merge two ranked result lists via Reciprocal Rank Fusion.

    RRF(d) = sum over each ranker r: 1 / (k + rank_r(d))
    """
    rrf_scores: Dict[str, float] = {}
    dense_scores: Dict[str, float] = {}
    sparse_scores: Dict[str, float] = {}
    dense_ranks: Dict[str, int] = {}
    sparse_ranks: Dict[str, int] = {}
    metadata_map: Dict[str, Dict] = {}

    for rank, (doc_id, score, meta) in enumerate(dense_results):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        dense_scores[doc_id] = score
        dense_ranks[doc_id] = rank + 1
        metadata_map[doc_id] = meta

    for rank, (doc_id, score, meta) in enumerate(sparse_results):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        sparse_scores[doc_id] = score
        sparse_ranks[doc_id] = rank + 1
        if doc_id not in metadata_map:
            metadata_map[doc_id] = meta

    sorted_ids = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)

    results = []
    for doc_id in sorted_ids:
        results.append({
            "id": doc_id,
            "score": rrf_scores[doc_id],  # Unified candidate score
            "rrf_score": rrf_scores[doc_id],
            "similarity_score": dense_scores.get(doc_id, 0.0),
            "dense_score": dense_scores.get(doc_id, 0.0),
            "sparse_score": sparse_scores.get(doc_id, 0.0),
            "dense_rank": dense_ranks.get(doc_id, 0),
            "sparse_rank": sparse_ranks.get(doc_id, 0),
            "metadata": metadata_map.get(doc_id, {}),
        })

    return results


# ---------------------------------------------------------------------------
# Hybrid Search Engine
# ---------------------------------------------------------------------------
class HybridSearchEngine:
    """
    Combines Pinecone dense vector search with client-side BM25 sparse search,
    merging results via Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, bm25_index: Optional[BM25Index] = None, rrf_k: int = 60):
        self.bm25_index = bm25_index
        self.rrf_k = rrf_k

    def search(
        self,
        pinecone_index,
        query_vector: List[float],
        query_text: str,
        top_k: int = 40,
        namespace: str = "judgments",
        pinecone_filter: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute hybrid search: dense Pinecone query + BM25 sparse query + RRF fusion.
        """
        dense_results = self._dense_search(
            pinecone_index, query_vector, top_k, namespace, pinecone_filter
        )

        sparse_results = []
        if self.bm25_index and self.bm25_index.corpus_size > 0:
            sparse_results = self.bm25_index.search(query_text, top_k=top_k)

        if not dense_results and not sparse_results:
            return []

        fused = reciprocal_rank_fusion(dense_results, sparse_results, k=self.rrf_k)
        return fused[:top_k]

    def _dense_search(
        self,
        pinecone_index,
        query_vector: List[float],
        top_k: int,
        namespace: str,
        pinecone_filter: Optional[Dict],
    ) -> List[Tuple[str, float, Dict]]:
        if not pinecone_index or not query_vector:
            return []

        query_params: Dict[str, Any] = {
            "namespace": namespace,
            "vector": query_vector,
            "top_k": top_k,
            "include_metadata": True,
        }
        if pinecone_filter:
            query_params["filter"] = pinecone_filter

        try:
            res = pinecone_index.query(**query_params)
            raw_matches = (
                res.get("matches", []) if isinstance(res, dict)
                else getattr(res, "matches", []) or []
            )

            if not raw_matches and pinecone_filter:
                query_params.pop("filter", None)
                res = pinecone_index.query(**query_params)
                raw_matches = (
                    res.get("matches", []) if isinstance(res, dict)
                    else getattr(res, "matches", []) or []
                )
        except Exception as e:
            logger.warning(f"Pinecone query error ({pinecone_filter}): {e}")
            query_params.pop("filter", None)
            try:
                res = pinecone_index.query(**query_params)
                raw_matches = (
                    res.get("matches", []) if isinstance(res, dict)
                    else getattr(res, "matches", []) or []
                )
            except Exception as e2:
                logger.error(f"Pinecone dense search failed: {e2}")
                return []

        results = []
        for m in raw_matches:
            doc_id = m.get("id", "") if isinstance(m, dict) else getattr(m, "id", "")
            score = float(
                m.get("score", 0.0) if isinstance(m, dict) else getattr(m, "score", 0.0)
            )
            meta = (
                m.get("metadata", {}) if isinstance(m, dict)
                else getattr(m, "metadata", {}) or {}
            )
            results.append((doc_id, score, meta))

        return results
