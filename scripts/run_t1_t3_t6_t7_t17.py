"""
scripts/run_t1_t3_t6_t7_t17.py
Runs T1, T3, T6, T7, and T17 end-to-end and captures all 5 outputs.
"""
import sys
import os
import asyncio
import time
import uuid

os.environ["ENVIRONMENT"] = "test"
os.environ["ENABLE_DEV_AUTH_BYPASS"] = "true"
os.environ["USE_LEGAL_AI_PIPELINE"] = "true"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import QueryRequest
from legal_ai.query_engine.query_processor import process_query_job_legal_ai

QUERIES = [
    ("T1", "What is the limitation period for a suit to recover money lent?"),
    ("T3", "Can the court condone delay in filing a civil suit?"),
    ("T6", "Punishment for murder?"),
    ("T7", "How do I get bail in a non-bailable offence after arrest?"),
    ("T17", "What is the limitation under Section 57 of the Limitation Act?"),
]

async def execute_test_query(tag: str, query_text: str):
    job_id = str(uuid.uuid4())
    req = QueryRequest(query_text=query_text, assistant="jurist")
    jobs_store = {
        job_id: {
            "status": "pending",
            "stage": "starting",
            "user_id": "test_e2e_runner"
        }
    }

    t0 = time.time()
    caught_exception = None
    try:
        await process_query_job_legal_ai(
            job_id,
            req,
            "test_e2e_runner",
            jobs_store,
            supabase=None
        )
    except Exception as e:
        caught_exception = e

    elapsed = time.time() - t0
    job_entry = jobs_store.get(job_id, {})
    status = job_entry.get("status")
    result = job_entry.get("result") or {}
    report = job_entry.get("verification_report") or (getattr(caught_exception, "verification_report", None) if caught_exception else {})
    unverified_memo = job_entry.get("unverified_memo") or ""
    memo = result.get("answer") or result.get("model_answer") or unverified_memo or ""
    citations = result.get("citations", []) or job_entry.get("unverified_citations", [])
    precedents = result.get("precedent_cards", []) or job_entry.get("precedent_cards", [])

    print(f"\n{'#' * 80}")
    print(f"### OUTPUT FOR {tag}: \"{query_text}\"")
    print(f"{'#' * 80}")
    print(f"Status: {status} | Elapsed: {elapsed:.2f}s")
    if caught_exception:
        print(f"Exception: {caught_exception}")

    print(f"\nRetrieved / Referenced Citations ({len(citations)}):")
    for c in citations:
        print(f"  • {c}")

    print(f"\nAdmitted Precedent Cards ({len(precedents)}):")
    for p in precedents:
        cit = p.get("citation") or p.get("case_id") or "N/A"
        title = p.get("case_title") or p.get("title") or "N/A"
        court = p.get("court") or "N/A"
        domain = p.get("domain") or p.get("metadata", {}).get("domain") or "N/A"
        print(f"  • [{cit}] {title} ({court}) | Domain: {domain}")

    print(f"\nSynthesized Memorandum / Output:")
    print("-" * 60)
    if memo:
        print(memo)
    else:
        print("[No output generated]")
    print("-" * 60)

async def main():
    print("================================================================================")
    print("RUNNING 5 BENCHMARK QUERIES: T1, T3, T6, T7, T17")
    print("================================================================================")
    for tag, q in QUERIES:
        await execute_test_query(tag, q)

if __name__ == "__main__":
    asyncio.run(main())
