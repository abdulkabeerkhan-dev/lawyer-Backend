"""
Retrieval eval for Section, run against the real pipeline in main.py.

Adapted from Lawglance's eval/retrieval_eval.py (Apache 2.0). Structural
change from theirs: Lawglance scores a single Chroma retriever against exact
chunk text. Section scores LegalSearchPipeline.search_precedents() (Pinecone
+ voyage-law-2 + the strict/fallback threshold logic in main.py) against
citations, and separately scores the should_refuse items that Lawglance's
domain (Indian constitutional text) doesn't need at all.

Usage:
    python -m eval.retrieval_eval

Run this after ANY change to: FALLBACK_FLOOR / STRICT_THRESHOLD,
expand_legal_query_doctrinally, chunking, _build_metadata_filter, or the
embedding model. It would have caught the FALLBACK_FLOOR regression
(Section 9 CPC starting to return ungrounded candidates) automatically
instead of needing a manual query-by-query audit.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# --- adjust this path to wherever your backend actually lives ---
sys.path.insert(0, r"c:\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master")

from main import get_voyage_embedding, global_search_pipeline, pinecone_index, PINECONE_NAMESPACE, expand_legal_query_doctrinally  # noqa: E402

from eval.golden_set import GoldenQAItem, load_golden_qa_set  # noqa: E402
from eval.metrics import (  # noqa: E402
    mean_reciprocal_rank,
    rank_of_correct_chunk,
    recall,
    recall_confidence_interval,
    refusal_accuracy,
)

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

GOLDEN_QA_PATH = Path(__file__).parent / "golden_qa.json"


async def retrieve_citations(question: str) -> list[str]:
    """Run one query through the real pipeline and return the citations of
    whatever candidates survive strict+fallback filtering — i.e. exactly
    what would be handed to Claude as grounding context.
    """
    search_query, is_doctrinally_expanded = expand_legal_query_doctrinally(question, return_flag=True)
    candidates = []
    for attempt in range(5):
        try:
            vector = await get_voyage_embedding(search_query)
            candidates = global_search_pipeline.search_precedents(
                vector_index=pinecone_index,
                query_vector=vector,
                namespace=PINECONE_NAMESPACE,
                clean_query=search_query,
                is_doctrinally_expanded=is_doctrinally_expanded
            )
            if candidates or attempt == 4:
                break
            await asyncio.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Retrying retrieve_citations ({attempt+1}/5): {e}")
            await asyncio.sleep(2)
            
    citations = []
    for c in candidates:
        meta = c.get("metadata", {})
        cit = meta.get("citation") or meta.get("neutral_citation") or meta.get("case_id")
        if cit:
            citations.append(cit)
    return citations


async def run_eval(golden_set: list[GoldenQAItem]) -> None:
    findable_items = [item for item in golden_set if not item.should_refuse]
    refuse_items = [item for item in golden_set if item.should_refuse]

    # --- score the "should find X" items ---
    ranks: list[int | None] = []
    print("=" * 70)
    print("FINDABILITY CHECKS (should retrieve a specific citation)")
    print("=" * 70)
    for item in findable_items:
        citations = await retrieve_citations(item.question)
        r = rank_of_correct_chunk(citations, item.expected_citation)
        ranks.append(r)
        status = f"rank {r}" if r else "NOT FOUND"
        flag = "  " if r else "❌"
        print(f"{flag} [{status:>10}] {item.question[:70]}")
        if not r:
            print(f"     expected: {item.expected_citation}")
            print(f"     got: {citations[:5]}")

    if ranks:
        print()
        lo, hi = recall_confidence_interval(ranks)
        print(f"Recall: {recall(ranks):.2%}  (95% CI: {lo:.2%}–{hi:.2%})")
        print(f"MRR:    {mean_reciprocal_rank(ranks):.3f}")

    # --- score the "should refuse / find nothing groundable" items ---
    refusal_results: list[bool] = []
    print()
    print("=" * 70)
    print("REFUSAL CHECKS (should NOT surface any groundable candidate)")
    print("=" * 70)
    for item in refuse_items:
        citations = await retrieve_citations(item.question)
        correctly_refused = len(citations) == 0
        refusal_results.append(correctly_refused)
        flag = "  " if correctly_refused else "🚨"
        status = "REFUSED (correct)" if correctly_refused else "SURFACED CANDIDATES (bug)"
        print(f"{flag} [{status}] {item.question[:70]}")
        if not correctly_refused:
            print(f"     WRONGLY GROUNDED ON: {citations}")
            print(f"     notes: {item.notes}")

    if refusal_results:
        print()
        print(f"Refusal accuracy: {refusal_accuracy(refusal_results):.2%}")
        if not all(refusal_results):
            print()
            print("🚨 At least one should-refuse case is now surfacing candidates.")
            print("   This is the exact failure mode from the FALLBACK_FLOOR regression.")
            print("   Do not ship until this is back to 100%.")


def main() -> None:
    golden_set = load_golden_qa_set(GOLDEN_QA_PATH)
    asyncio.run(run_eval(golden_set))


if __name__ == "__main__":
    main()
