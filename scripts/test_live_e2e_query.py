"""
scripts/test_live_e2e_query.py

Executes a live, end-to-end legal query through the complete production pipeline:
- Query Planning & Legal Domain Classification
- Multi-lane Retrieval (Pinecone segmented-v1, Supabase structured FTS, BM25)
- Voyage AI rerank-2 neural scoring
- Trust Gate verification & Statutory injection
- Full legal memorandum synthesis & validation
"""

import sys
import os
import uuid
import time
import argparse
import asyncio
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import QueryRequest
from legal_ai.query_engine.query_processor import process_query_job_legal_ai
from legal_ai.config import get_supabase_client

DEFAULT_QUERY = (
    "What are the rights and remedies of a co-sharer in joint family immovable property to seek "
    "partition under the Partition Act, 1893 and Civil Procedure Code, 1908, "
    "and whether a partial partition of joint property is maintainable under Pakistani superior court precedents?"
)

def parse_args():
    parser = argparse.ArgumentParser(description="Live End-to-End Query Verification")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Legal query text to evaluate")
    return parser.parse_args()

async def run_query(query_text: str):
    job_id = str(uuid.uuid4())
    print("=" * 80)
    print("🚀 STARTING LIVE END-TO-END LEGAL PIPELINE TEST")
    print("=" * 80)
    print(f"Query: {query_text}\n")
    print(f"Job ID: {job_id}")

    req = QueryRequest(query_text=query_text)
    jobs_store = {
        job_id: {
            "status": "pending",
            "stage": "starting",
            "user_id": "test_e2e_live_user"
        }
    }

    start_time = time.time()
    caught_exception = None
    try:
        await process_query_job_legal_ai(
            job_id,
            req,
            "test_e2e_live_user",
            jobs_store,
            supabase=None
        )
    except Exception as e:
        caught_exception = e
        print(f"\n[PIPELINE NOTICE] Exception caught: {e}")

    elapsed = time.time() - start_time
    job_entry = jobs_store.get(job_id, {})
    status = job_entry.get("status")
    stage = job_entry.get("stage")
    error = job_entry.get("error")
    result = job_entry.get("result") or {}
    report = job_entry.get("verification_report") or (getattr(caught_exception, "verification_report", None) if caught_exception else {})
    unverified_memo = job_entry.get("unverified_memo") or (caught_exception.blocked_payload.get("unverified_memo") if caught_exception and hasattr(caught_exception, "blocked_payload") and isinstance(caught_exception.blocked_payload, dict) else "")

    print("\n" + "=" * 80)
    print(f"📊 PIPELINE EXECUTION SUMMARY (Total Elapsed: {elapsed:.2f}s)")
    print("=" * 80)
    print(f"Final Status: {status}")
    print(f"Final Stage: {stage}")

    if error:
        print(f"Error Message: {error}")
        print(f"Error Category: {job_entry.get('error_category')}")
        print(f"Safe Reason: {job_entry.get('safe_reason')}")

    citations = result.get("citations", []) or job_entry.get("unverified_citations", [])
    precedents = result.get("precedent_cards", []) or job_entry.get("precedent_cards", [])
    memo = result.get("answer") or result.get("model_answer") or unverified_memo or ""

    print(f"\nRetrieved / Referenced Citations ({len(citations)}):")
    for c in citations:
        print(f"  • {c}")

    print(f"\nAdmitted Precedent Cards ({len(precedents)}):")
    for p in precedents:
        cid = p.get("case_id") or p.get("id") or "N/A"
        cit = p.get("citation") or cid
        title = p.get("case_title") or p.get("title") or "N/A"
        court = p.get("court") or "N/A"
        domain = p.get("domain") or p.get("metadata", {}).get("domain") or "N/A"
        print(f"  • [{cit}] {title} ({court}) | Domain: {domain}")

    if report and isinstance(report, dict):
        failures = report.get("failures", [])
        print(f"\nVerification Gate Violations ({len(failures)} total):")
        for f in failures[:8]:
            cat = f.get("category") or f.get("type")
            reason = f.get("issue") or f.get("reason")
            span = f.get("span") or f.get("unsupported_term") or ""
            print(f"  - [{cat}] {reason} (Span: {span[:50]})")

    print("\n" + "=" * 80)
    print("📝 SYNTHESIZED LEGAL MEMORANDUM OUTPUT:")
    print("=" * 80)
    if memo:
        print(memo)
    else:
        print("[No synthesized memorandum output produced]")
    print("=" * 80)

    return status == "done"

if __name__ == "__main__":
    args = parse_args()
    success = asyncio.run(run_query(args.query))
    sys.exit(0 if success else 1)
