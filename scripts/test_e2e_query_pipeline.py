import os
import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["ENVIRONMENT"] = "test"
os.environ["SKIP_TURSO_DRIFT_CHECK"] = "1"

from pydantic import BaseModel

class DummyRequest(BaseModel):
    query_text: str
    query: str = ""
    messages: list = []
    assistant: str = "jurist"
    category: str = "research"

async def test_end_to_end():
    print("=" * 70)
    print("TESTING FULL PIPELINE END-TO-END (process_query_job_legal_ai)")
    print("=" * 70)

    from legal_ai.query_engine.query_processor import process_query_job_legal_ai

    job_id = "test_job_willful_default"
    jobs_store = {
        job_id: {
            "status": "running",
            "stage": "starting",
            "created_at": None,
            "user_id": "test_user_123"
        }
    }
    req = DummyRequest(query_text="What constitutes willful default under Pakistani law?")

    print("\nExecuting process_query_job_legal_ai...")
    try:
        await process_query_job_legal_ai(
            job_id=job_id,
            request=req,
            authenticated_user_id="test_user_123",
            jobs_store=jobs_store,
            supabase=None
        )
        print("\nJob completed successfully!")
        status = jobs_store[job_id].get("status")
        stage = jobs_store[job_id].get("stage")
        result = jobs_store[job_id].get("result", {})
        print(f"Status: {status} | Stage: {stage}")

        if isinstance(result, dict):
            answer = result.get("answer") or result.get("model_answer") or result.get("response") or ""
            print(f"Answer length: {len(answer)}")
            print("\n--- Answer Excerpt (first 1000 chars) ---")
            print(answer[:1000])

            citations = result.get("citations", [])
            print(f"\nCitations count: {len(citations)}")
            for c in citations[:5]:
                print(f"  - {c}")

            # Check if FIO 2001 or Section 2(g) or NAO 1999 are mentioned
            has_fio = "Financial Institutions" in answer or "FIO" in answer or "2(g)" in answer
            has_nao = "National Accountability" in answer or "NAO" in answer or "5(u)" in answer
            print(f"\nFIO 2001 Cited in Answer: {has_fio}")
            print(f"NAO 1999 Cited in Answer: {has_nao}")

    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_end_to_end())
