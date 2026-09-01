import os
import json
import asyncio
from dotenv import load_dotenv
import voyageai
from pinecone import Pinecone

load_dotenv()

# We can import main.py directly to use its internal functions
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import QueryRequest, process_query_job, jobs_store, pinecone_index

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "judgments")

voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

async def run_raw_retrieval(query_text, expected):
    print(f"\n[Raw Retrieval Test]")
    print(f"Query: {query_text}")
    print(f"Expected: {expected}")
    
    # Generate Voyage Embedding
    res = voyage_client.embed([query_text], model="voyage-law-2", input_type="query")
    query_vector = res.embeddings[0]
    
    # Query Pinecone
    matches = pinecone_index.query(
        vector=query_vector,
        top_k=10,
        namespace=NAMESPACE,
        include_metadata=True
    )
    
    chunks = matches.get("matches", [])
    if not chunks:
        print("[FAIL] No chunks retrieved.")
        return "Fail - No chunks"
        
    found_relevant = False
    print("Top 3 retrieved chunks snippets:")
    for i, c in enumerate(chunks[:3]):
        text = c.get('metadata', {}).get('text', '')
        print(f"  {i+1}: {text[:150].replace(chr(10), ' ')}...")
        
    print("Did these chunks answer the expected criteria? (Auto-evaluating based on keywords is hard, logging for manual review)")
    return "Logged for Review"


async def run_full_pipeline(query_text, q_type, expected):
    print(f"\n[{q_type.upper()} Test]")
    print(f"Query: {query_text}")
    print(f"Expected: {expected}")
    
    job_id = f"test_job_{hash(query_text)}"
    req = QueryRequest(query_text=query_text)
    
    jobs_store[job_id] = {"status": "pending", "user_id": "mock_clerk_user_id_dev_run"}
    
    # Call the background processor directly
    try:
        await process_query_job(job_id, req, "mock_clerk_user_id_dev_run")
        job = jobs_store.get(job_id)
        if job and job.get("status") == "done":
            resp = job.get('result', {}).get('answer', str(job.get('result')))
            print(f"[PASS] Success. Response snippet: {resp[:200]}...")
            return "Pass"
        else:
            err = job.get("error") if job else "Unknown"
            print(f"[FAIL] Job did not complete successfully. Error: {err}")
            return f"Fail - {err}"
    except Exception as e:
        print(f"[FAIL] Exception during processing: {e}")
        return f"Fail - Exception: {str(e)}"

async def main():
    print("Starting Benchmark Suite...")
    with open("benchmark_queries.json", "r", encoding="utf-8") as f:
        queries = json.load(f)
        
    results = []
    
    for q in queries:
        q_id = q["id"]
        q_text = q["query"]
        q_type = q["type"]
        q_expected = q["expected"]
        
        if q_type == "raw_retrieval":
            res = await run_raw_retrieval(q_text, q_expected)
        else:
            res = await run_full_pipeline(q_text, q_type, q_expected)
            
        results.append({
            "id": q_id,
            "status": res
        })
        
    print("\n--- Final Summary ---")
    for r in results:
        print(f"{r['id']}: {r['status']}")

if __name__ == "__main__":
    asyncio.run(main())
