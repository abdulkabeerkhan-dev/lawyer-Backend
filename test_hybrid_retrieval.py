"""
Integration Test for Universal Hybrid Search Pipeline:
- Dense vector retrieval (Voyage-law-2 / Pinecone)
- BM25 sparse keyword retrieval (BM25Okapi over 29,547 chunks)
- Reciprocal Rank Fusion (k=60)
- Generalized Dynamic Thresholding
- Universal Citation Interceptor
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

from hybrid_search import BM25Index, HybridSearchEngine, reciprocal_rank_fusion
from main import (
    CITATION_REGEX,
    extract_and_intercept_citation,
    global_search_pipeline,
    global_hybrid_engine,
    pinecone_index,
    get_voyage_embedding
)

def run_test():
    print("=============================================================")
    print("  TESTING UNIVERSAL HYBRID RETRIEVAL PIPELINE (DENSE + BM25) ")
    print("=============================================================")
    
    # Check BM25 index status
    bm25 = global_hybrid_engine.bm25_index
    if not bm25:
        print("[ERROR] BM25 index not loaded!")
        return False
    print(f"[OK] Loaded BM25 index with {bm25.corpus_size:,} chunks.")

    # 1. Test BM25 Keyword Search Standalone
    print("\n--- TEST 1: BM25 Sparse Search Standalone ---")
    query1 = "khula zar-i-khula dower restitution conjugal rights"
    bm25_hits = bm25.search(query1, top_k=5)
    print(f"Query: '{query1}' -> {len(bm25_hits)} hits:")
    for vid, score, meta in bm25_hits:
        cit = meta.get("citation") or meta.get("case_id")
        title = meta.get("case_title") or meta.get("title") or "Unknown"
        print(f"  [BM25 Score: {score:.2f}] {cit} - {title[:50]}")

    # 2. Test Universal Citation Interceptor embedded in sentence
    print("\n--- TEST 2: Universal Citation Interceptor (Embedded in sentence) ---")
    test_nl_queries = [
        "What was the precedent established in 2006 YLR 96 concerning wife's right to khula?",
        "Can a petitioner seek relief under 2013 SCMR 51 in a cheque bouncing case?",
        "Refer to PLD 1967 SC 97 on whether husband consent is mandatory"
    ]
    for nl_q in test_nl_queries:
        row, clean_topic = extract_and_intercept_citation(nl_q)
        print(f"\nQuery: '{nl_q}'")
        matches = [m.group(0) for m in CITATION_REGEX.finditer(nl_q)]
        print(f"  Detected Citations: {matches}")
        if row:
            cid = row.get("neutral_citation") or row.get("case_id")
            title = row.get("case_title") or row.get("title")
            print(f"  Intercept HIT: {cid} ({title})")
        else:
            print(f"  Intercept MISS (expected for uningested older judgments), fallback topic: '{clean_topic}'")

    # 3. Test Full Hybrid Search (Dense + BM25 + RRF)
    print("\n--- TEST 3: Full Universal Hybrid Search (RRF k=60) ---")
    import asyncio
    
    async def _search_pipeline_test():
        test_queries = [
            ("Khula dissolution of marriage dower zar-i-khula", True),
            ("Section 302 PPC private defence right of self defence plea", True),
            ("Can landlord evict tenant under section 9 CPC in Punjab?", False)
        ]
        
        for q, is_exp in test_queries:
            print(f"\nTesting: '{q}' (doctrinally_expanded={is_exp})")
            t0 = time.time()
            try:
                emb = await get_voyage_embedding(q)
                candidates = global_search_pipeline.search_precedents(
                    vector_index=pinecone_index,
                    query_vector=emb,
                    top_k=10,
                    clean_query=q,
                    is_doctrinally_expanded=is_exp
                )
                dt = time.time() - t0
                print(f"  Retrieved {len(candidates)} candidates in {dt:.2f}s:")
                for i, c in enumerate(candidates[:5]):
                    m = c.get("metadata", {})
                    dense_s = c.get("dense_score", c.get("similarity_score", 0.0))
                    sparse_s = c.get("sparse_score", 0.0)
                    rrf_s = c.get("rrf_score", c.get("score", 0.0))
                    cit = m.get("citation") or m.get("case_id") or c.get("id")
                    title = (m.get("case_title") or m.get("title") or "")[:45]
                    print(f"    #{i+1}: RRF={rrf_s:.5f} | Dense={dense_s:.4f} | BM25={sparse_s:.2f} | {cit} | {title}")
                
                if not candidates:
                    print("  --> HONEST REFUSAL PRESERVED (0 candidates qualify) [OK]")
            except Exception as e:
                print(f"  Query error: {e}")

    asyncio.run(_search_pipeline_test())
    print("\n=============================================================")
    print("  ALL HYBRID RETRIEVAL TESTS COMPLETED                       ")
    print("=============================================================")

if __name__ == "__main__":
    run_test()
