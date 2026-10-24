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
import array
from typing import List, Dict, Any, Tuple, Optional, Union

import numpy as np
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
# Inverted Index BM25 (Ultra-Low Memory & Sub-Millisecond Retrieval)
# ---------------------------------------------------------------------------
class InvertedBM25:
    """
    Ultra-low-memory, high-throughput inverted index BM25 search engine.
    Scores 40k+ documents via vectorized numpy operations in sub-millisecond latency
    while reducing resident RAM from 384 MB down to ~40 MB.
    """
    def __init__(
        self,
        inverted: Dict[str, Tuple[Any, Any]],
        idf: Dict[str, float],
        doc_len: Any,
        avgdl: float,
        k1: float = 1.5,
        b: float = 0.75,
        corpus_size: int = 0
    ):
        self.inverted = inverted
        self.idf = idf
        self.doc_len = np.asarray(doc_len, dtype=np.float32)
        self.avgdl = float(avgdl)
        self.k1 = float(k1)
        self.b = float(b)
        self.corpus_size = int(corpus_size)

    def get_scores(self, query_tokens: List[str]) -> np.ndarray:
        scores = np.zeros(self.corpus_size, dtype=np.float32)
        k1 = self.k1
        b = self.b
        avgdl = self.avgdl
        for q in query_tokens:
            posting = self.inverted.get(q)
            if not posting:
                continue
            docs = np.asarray(posting[0])
            freqs = np.asarray(posting[1], dtype=np.float32)
            q_idf = self.idf.get(q, 0.0)
            d_len = self.doc_len[docs]
            denom = freqs + k1 * (1.0 - b + b * (d_len / avgdl))
            scores[docs] += q_idf * (freqs * (k1 + 1.0)) / denom
        return scores


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

    def to_compact(self) -> Dict[str, Any]:
        """Convert BM25Okapi or existing index into a compact inverted index payload."""
        if isinstance(self.bm25, InvertedBM25):
            inverted = self.bm25.inverted
            idf = self.bm25.idf
            doc_len = array.array('I', [int(x) for x in self.bm25.doc_len])
            avgdl = self.bm25.avgdl
            k1 = self.bm25.k1
            b = self.bm25.b
        elif self.bm25 and hasattr(self.bm25, "doc_freqs"):
            inverted = {}
            for doc_idx, freq_map in enumerate(self.bm25.doc_freqs):
                for word, count in freq_map.items():
                    if word not in inverted:
                        inverted[word] = (array.array('I'), array.array('H'))
                    inverted[word][0].append(doc_idx)
                    inverted[word][1].append(min(count, 65535))
            idf = getattr(self.bm25, "idf", {})
            doc_len = array.array('I', getattr(self.bm25, "doc_len", []))
            avgdl = getattr(self.bm25, "avgdl", 0.0)
            k1 = getattr(self.bm25, "k1", 1.5)
            b = getattr(self.bm25, "b", 0.75)
        else:
            raise ValueError("No valid BM25 model to compact")

        compact_meta = []
        for m in self.doc_metadata:
            compact_meta.append({
                'case_id': m.get('case_id', ''),
                'citation': m.get('citation', ''),
                'case_title': m.get('case_title', '') or m.get('title', ''),
                'court': m.get('court', ''),
                'decision_date': m.get('decision_date', ''),
                'sections': m.get('sections', ''),
                'statutes': m.get('statutes', ''),
                'chunk_index': m.get('chunk_index', 0),
                'content_type': m.get('content_type', 'full_text'),
                'year': m.get('year', 0),
                'text': (m.get('text', '') or '')[:300]
            })

        return {
            "inverted": inverted,
            "idf": idf,
            "doc_len": doc_len,
            "avgdl": avgdl,
            "k1": k1,
            "b": b,
            "corpus_size": self.corpus_size,
            "doc_ids": self.doc_ids,
            "doc_metadata": compact_meta
        }

    def save(self, path: str, compact: bool = True) -> None:
        """Serialize the fitted BM25 index to disk (compact inverted format by default)."""
        if compact:
            data = self.to_compact()
        else:
            data = {
                "bm25": self.bm25,
                "doc_ids": self.doc_ids,
                "doc_metadata": self.doc_metadata,
                "corpus_size": self.corpus_size,
            }
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        logger.info(f"BM25 index saved to {path} ({size_mb:.1f} MB, {self.corpus_size} docs, compact={compact})")

    @classmethod
    def load(cls, path: str) -> "BM25Index":
        """Load a pre-built BM25 index from disk (supports both compact inverted and legacy formats)."""
        idx = cls()
        with open(path, "rb") as f:
            data = pickle.load(f)
        if "inverted" in data:
            idx.bm25 = InvertedBM25(
                inverted=data["inverted"],
                idf=data["idf"],
                doc_len=data["doc_len"],
                avgdl=data["avgdl"],
                k1=data.get("k1", 1.5),
                b=data.get("b", 0.75),
                corpus_size=data["corpus_size"]
            )
        else:
            idx.bm25 = data["bm25"]
        idx.doc_ids = data["doc_ids"]
        idx.doc_metadata = data["doc_metadata"]
        idx.corpus_size = data["corpus_size"]
        logger.info(f"BM25 index loaded from {path} ({idx.corpus_size} docs, is_inverted={'inverted' in data})")
        return idx


# ---------------------------------------------------------------------------
# Judicial Hierarchy & Recency Re-weighting
# ---------------------------------------------------------------------------
import datetime
from core.court_taxonomy import COURT_AUTHORITY_WEIGHTS

def get_court_authority_weight(citation: str, court_name: str = "") -> float:
    """
    Under Article 189 of the Constitution of Pakistan, Supreme Court of Pakistan
    decisions are binding on all courts in Pakistan (1.35x multiplier).
    Recognized provincial High Court decisions under Article 201 bind subordinate
    courts in their respective province (1.10x multiplier).
    Statutory tribunals receive 0.95x multiplier.
    Historical/external courts (Privy Council, Dhaka High Court, Federal Court,
    AJK courts, Board of Revenue) and unresolved records receive a neutral 1.0x weight.
    """
    cit_upper = (citation or "").upper()
    court_upper = (court_name or "").upper()

    # 1. Check for non-Pakistani or pre-constitutional/special jurisdictions first -> neutral 1.0x
    neutral_courts = [
        "AZAD KASHMIR", "AJ&K", "AJK", "DHAKA", "DACCA", "EAST BENGAL", "EAST PAKISTAN",
        "PRIVY COUNCIL", "PRIVY-COUNCIL", "FEDERAL COURT", "FEDERAL-COURT",
        "BOARD OF REVENUE", "REVENUE", "INDIA", "UNRESOLVED", "COURT OF RECORD",
        "COURT NOT IDENTIFIED", "UNKNOWN", "FEDERAL CONSTITUTIONAL COURT", "FEDERAL-CONSTITUTIONAL-COURT"
    ]
    if any(nc in court_upper for nc in neutral_courts):
        return COURT_AUTHORITY_WEIGHTS["neutral"]

    # 2. Check for Tribunals / Ombudsman / Lower forum -> 0.95x
    tribunal_keywords = [
        "TRIBUNAL", "SERVICE TRIBUNAL", "APPELLATE TRIBUNAL", "FEDERAL TAX OMBUDSMAN",
        "FTO", "BANKING TRIBUNAL", "SPECIAL TRIBUNAL", "CUSTOMS APPELLATE", "ATIR",
        "ENVIRONMENTAL PROTECTION TRIBUNAL", "LABOUR APPELLATE TRIBUNAL"
    ]
    if any(tk in court_upper for tk in tribunal_keywords) or any(tk in cit_upper for tk in ["FTO", "ATIR", "TDAP"]):
        return COURT_AUTHORITY_WEIGHTS["tribunal"]

    # 3. Supreme Court of Pakistan (Apex binding precedent under Art. 189) -> 1.35x
    if "SUPREME COURT OF PAKISTAN" in court_upper:
        return COURT_AUTHORITY_WEIGHTS["supreme_court"]
    if "SCMR" in cit_upper or "PLD SC" in cit_upper or "PLD_SC_" in cit_upper:
        return COURT_AUTHORITY_WEIGHTS["supreme_court"]

    # 4. Recognized Pakistani High Courts under Art. 201 (LHC, SHC, PHC, BHC, IHC) -> 1.10x
    recognized_high_courts = [
        "LAHORE HIGH COURT", "HIGH COURT OF SINDH", "PESHAWAR HIGH COURT",
        "HIGH COURT OF BALOCHISTAN", "ISLAMABAD HIGH COURT"
    ]
    if any(hc in court_upper for hc in recognized_high_courts):
        return COURT_AUTHORITY_WEIGHTS["high_court"]

    # 5. Fallback on citation reporter if court_name was empty/unspecified -> 1.10x
    if not court_upper or court_upper in ("HIGH COURT", "COURT"):
        if any(h in cit_upper for h in ["PCRLJ", "CLC", "YLR", "MLD", "PTD", "PLC", "CLD", "PLJ", "NLR"]):
            return COURT_AUTHORITY_WEIGHTS["high_court"]

    return COURT_AUTHORITY_WEIGHTS["neutral"]


def extract_year_num(year_val: Any, citation: str = "", doc_id: str = "") -> int:
    """Extract 4-digit integer year from metadata, citation, or doc_id."""
    if isinstance(year_val, int) and year_val > 1800:
        return year_val
    if isinstance(year_val, str) and year_val.strip().isdigit():
        val = int(year_val.strip())
        if 1800 < val < 2100:
            return val
    m = re.search(r'\b(19\d\d|20\d\d)\b', f"{year_val} {citation} {doc_id}")
    if m:
        return int(m.group(1))
    return 0


def get_recency_weight(year_val: Any, citation: str = "", doc_id: str = "") -> float:
    """
    P1-4: Recency is governed by staged year-prioritized batch retrieval
    (Batch 1: 2026-2024, Batch 2: 2023-2021) and judicial hierarchy reranking,
    ensuring recency never causes a lower-court case to outrank an older binding
    Supreme Court authority.
    """
    return 1.0


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------
def reciprocal_rank_fusion(
    dense_results: List[Tuple[str, float, Dict]],
    sparse_results: List[Tuple[str, float, Dict]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    Merge two ranked result lists via Reciprocal Rank Fusion (RRF) with
    judicial hierarchy and recency re-weighting.

    RRF(d) = sum over each ranker r: 1 / (k + rank_r(d))
    FinalScore(d) = RRF(d) * CourtWeight(d) * RecencyWeight(d)
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

    results = []
    for doc_id in rrf_scores:
        meta = metadata_map.get(doc_id, {}) or {}
        cit = meta.get("citation", "") or meta.get("neutral_citation", "")
        from core.court_taxonomy import get_effective_court
        court = get_effective_court(meta) or ""
        raw_year = meta.get("year", 0) or meta.get("decision_date", "") or meta.get("date", "")
        court_weight = get_court_authority_weight(cit, court)

        recency_weight = get_recency_weight(raw_year, citation=cit, doc_id=doc_id)

        base_rrf = rrf_scores[doc_id]
        final_rank_score = base_rrf * court_weight * recency_weight

        results.append({
            "id": doc_id,
            "score": final_rank_score,  # Re-weighted candidate score
            "rrf_score": base_rrf,
            "final_rank_score": final_rank_score,
            "court_weight": court_weight,
            "recency_weight": recency_weight,
            "similarity_score": dense_scores.get(doc_id, 0.0),
            "dense_score": dense_scores.get(doc_id, 0.0),
            "sparse_score": sparse_scores.get(doc_id, 0.0),
            "dense_rank": dense_ranks.get(doc_id, 0),
            "sparse_rank": sparse_ranks.get(doc_id, 0),
            "metadata": meta,
        })

    # Sort final candidates by final_rank_score descending
    results.sort(key=lambda x: x["final_rank_score"], reverse=True)
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
        self.last_dense_count: int = 0
        self.last_sparse_count: int = 0

    def search_with_components(
        self,
        pinecone_index,
        query_vector: List[float],
        query_text: str,
        top_k: int = 40,
        namespace: str = "judgments",
        pinecone_filter: Optional[Dict] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[str, float, Dict]], List[Tuple[str, float, Dict]]]:
        """
        Execute hybrid search: dense Pinecone query + BM25 sparse query + RRF fusion.
        Returns (fused_results, dense_results, sparse_results).
        """
        dense_results = self._dense_search(
            pinecone_index, query_vector, top_k, namespace, pinecone_filter
        )
        self.last_dense_count = len(dense_results)

        sparse_results = []
        if self.bm25_index and self.bm25_index.corpus_size > 0:
            sparse_results = self.bm25_index.search(query_text, top_k=top_k)
        self.last_sparse_count = len(sparse_results)

        if not dense_results and not sparse_results:
            return [], dense_results, sparse_results

        fused = reciprocal_rank_fusion(dense_results, sparse_results, k=self.rrf_k)
        return fused[:top_k], dense_results, sparse_results

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
        fused, _, _ = self.search_with_components(
            pinecone_index, query_vector, query_text, top_k=top_k, namespace=namespace, pinecone_filter=pinecone_filter
        )
        return fused

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
