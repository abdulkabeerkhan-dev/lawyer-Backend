"""
legal_ai/retrieval
"""

from legal_ai.retrieval.supabase_search import search_supabase_judgments
from legal_ai.retrieval.pinecone_search import search_pinecone_dense
from legal_ai.retrieval.bm25_search import search_bm25_sparse
from legal_ai.retrieval.external_search import search_external_judgments
from legal_ai.retrieval.unified_orchestrator import retrieve_candidates_parallel, merge_candidates_with_rrf

__all__ = [
    "search_supabase_judgments",
    "search_pinecone_dense",
    "search_bm25_sparse",
    "search_external_judgments",
    "retrieve_candidates_parallel",
    "merge_candidates_with_rrf"
]
