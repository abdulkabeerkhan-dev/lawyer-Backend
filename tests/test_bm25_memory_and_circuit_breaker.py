import os
import sys
import json
import time
import asyncio
import threading
import pytest
from unittest.mock import MagicMock, patch

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["ENVIRONMENT"] = "test"
os.environ["ENABLE_DEV_AUTH_BYPASS"] = "true"
os.environ["DISABLE_IN_MEMORY_BM25"] = "false"

from legal_ai.retrieval.bm25_search import (
    get_bm25_index_instance,
    set_bm25_index_instance,
    search_bm25_sparse
)
from core.legal_query_planner import analyze_legal_query


def test_bm25_singleton_thread_safety_and_sharing():
    """Verify that multiple threads concurrently accessing get_bm25_index_instance receive the same instance."""
    os.environ["DISABLE_IN_MEMORY_BM25"] = "false"
    mock_instance = MagicMock()
    mock_instance.corpus_size = 40575
    mock_instance.search.return_value = [("doc_1", 3.5, {"title": "Test Title", "citation": "2024 SCMR 1", "court": "Supreme Court of Pakistan"})]

    # Explicitly set singleton
    set_bm25_index_instance(mock_instance)

    instances = []
    def _worker():
        for _ in range(50):
            inst = get_bm25_index_instance()
            instances.append(inst)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 400
    for inst in instances:
        assert inst is mock_instance

    # Test search_bm25_sparse uses shared instance
    res = search_bm25_sparse("banking recovery", top_k=5)
    assert len(res) == 1
    assert res[0]["citation"] == "2024 SCMR 1"


def test_planner_resilient_json_parsing():
    """Verify that Claude responses with markdown fences or trailing commas are successfully parsed."""
    async def _run():
        # Malformed LLM response with markdown fence and trailing commas
        malformed_llm_json = """Here is the query plan:
```json
{
  "primary_domain": "banking_and_finance",
  "controlling_provisions": ["FIO_2001_SEC_22"],
  "factual_intent": "Banking court appeal procedure and limitation period",
  "doctrinal_intent": "Maintainability of appeal under Section 22 FIO",
  "procedural_intent": "Statutory appeal before High Court",
  "forum_intent": "High Court",
  "issues": [
    {
      "issue_id": "issue_1",
      "heading": "Limitation period",
      "controlling_provisions": ["FIO_2001_SEC_22",],
    },
  ],
}
```
"""
        mock_msg = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = malformed_llm_json
        mock_msg.content = [mock_block]

        async def _mock_ai_call(**kwargs):
            return mock_msg

        plan = await analyze_legal_query("What is the appeal limitation from Banking Court?", ai_client_fn=_mock_ai_call)
        assert plan is not None
        assert plan.primary_domain in ("banking_and_finance", "banking")
        assert any("FIO_2001" in str(p) for p in plan.statutory_provisions)

    asyncio.run(_run())
