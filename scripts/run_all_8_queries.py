"""
scripts/run_all_8_queries.py

Executes all 8 queries (5 original acceptance queries + 3 unseen queries)
through the live production pipeline and saves their full output memos.
"""

import sys
import os
import json
import uuid
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import QueryRequest
from legal_ai.query_engine.query_processor import process_query_job_legal_ai

QUERIES = [
    {
        "id": 1,
        "title": "Cheque Bouncing under NI Act s.138 (Pakistan)",
        "query": "What is the procedure and punishment for cheque bouncing under Section 138 of the Negotiable Instruments Act in Pakistan?"
    },
    {
        "id": 2,
        "title": "Banking Court Auction under FIO 2001",
        "query": "Can a banking court execute a decree by auctioning mortgaged property without fresh proclamation under FIO 2001?"
    },
    {
        "id": 3,
        "title": "Orphaned Grandchild Inheritance under MFLO Section 4",
        "query": "Does an orphaned grandchild have a right to inherit from their grandfather's estate under Muslim Family Laws Ordinance 1961?"
    },
    {
        "id": 4,
        "title": "Auction Challenge Limitation under Order XXI Rule 90 CPC",
        "query": "What is the limitation period for challenging an auction sale under Order XXI Rule 90 CPC?"
    },
    {
        "id": 5,
        "title": "Unregistered Tenancy Eviction under PRPA 2009",
        "query": "Can an unregistered tenancy agreement be used to evict a tenant under Punjab Rented Premises Act 2009 in Lahore?"
    },
    {
        "id": 6,
        "title": "PPC Section 406 Criminal Breach of Trust & s.498 CrPC Bail",
        "query": "What are the essential ingredients of criminal breach of trust under Section 406 PPC, whether a commercial transaction or loan default constitutes an offence under Section 406 PPC, and what are the governing superior court principles for grant of pre-arrest bail under Section 498 CrPC?"
    },
    {
        "id": 7,
        "title": "Specific Relief Act 1877 Specific Performance & Readiness/Willingness",
        "query": "What are the essential conditions for obtaining a decree for specific performance of a contract for sale of immovable property under the Specific Relief Act, 1877, and what is the doctrine of readiness and willingness to perform in Pakistan?"
    },
    {
        "id": 8,
        "title": "Limitation on Promissory Note under Limitation Act 1908 & NI Act 1881",
        "query": "What is the limitation period for instituting a suit for recovery of money based on a promissory note under the Limitation Act, 1908 and the Negotiable Instruments Act, 1881 in Pakistan?"
    }
]


async def run_single(item: dict) -> dict:
    job_id = str(uuid.uuid4())
    req = QueryRequest(query_text=item["query"])
    jobs_store = {
        job_id: {
            "status": "pending",
            "stage": "starting",
            "user_id": "eval_round3"
        }
    }
    print(f"\n[{item['id']}/8] Running: {item['title']}...")
    await process_query_job_legal_ai(job_id, req, "eval_round3", jobs_store, supabase=None)
    job_entry = jobs_store.get(job_id, {})
    res = job_entry.get("result", {})
    memo = res.get("answer") or res.get("model_answer") or ""
    print(f"[{item['id']}/8] Done! Status: {job_entry.get('status')}, Memo length: {len(memo)} chars.")
    return {
        "id": item["id"],
        "title": item["title"],
        "query": item["query"],
        "status": job_entry.get("status"),
        "memo": memo,
        "precedent_count": len(res.get("precedent_cards", [])),
        "citations": [c.get("citation") for c in res.get("precedent_cards", []) if isinstance(c, dict)]
    }


async def main():
    results = []
    for item in QUERIES:
        res = await run_single(item)
        results.append(res)

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "all_8_memos_round3.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAll 8 queries completed! Saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
