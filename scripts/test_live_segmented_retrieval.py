import os
import sys
import asyncio
from legal_ai.config import get_pinecone_index, get_voyage_embedding
from core.legal_query_planner import create_deterministic_fallback_plan

async def test_segmented_search():
    index = get_pinecone_index()
    
    queries = [
        ("CIV-PART-001", "Whether a co-sharer in joint ancestral land can seek preliminary decree for partition under Order XX Rule 18 CPC without including the entire joint estate?"),
        ("BEN-TRANS-001", "In a suit for partition, defendant co-sharer set up a benami claim under Section 4 Benami Transactions Act"),
        ("CRIM-FRAUD-001", "Pre-arrest bail under section 498 CrPC in case of fraud and dishonestly inducing delivery of property under section 420 PPC"),
        ("FAM-KHULA-001", "Dissolution of marriage by Khula and relinquishment of dower by wife under Family Courts Act 1964")
    ]
    
    for qid, q in queries:
        plan = create_deterministic_fallback_plan(q)
        domain = plan.primary_domain
        vec = await get_voyage_embedding(q)
        
        # Query segmented-v1 with domain filter
        res = index.query(
            namespace="segmented-v1",
            vector=vec,
            filter={"domain": {"$eq": domain}},
            top_k=3,
            include_metadata=True
        )
        
        print(f"\n==========================================")
        print(f"QUERY [{qid}] (Domain: {domain})")
        print(f"Query: {q[:75]}...")
        print(f"Matches in segmented-v1 (Domain filtered: {domain}):")
        for m in res.matches:
            meta = m.metadata
            print(f"  [{m.score:.4f}] {meta.get('citation')} ({meta.get('subdomain')}/{meta.get('segment_type')}) - {meta.get('case_title')[:50]}")

if __name__ == "__main__":
    asyncio.run(test_segmented_search())
