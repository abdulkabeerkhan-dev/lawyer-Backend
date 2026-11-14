r"""
tests/zilliz/test_bakeoff.py

Unit tests for Phase 3 embedding bake-off scoring, aggregation, and metrics.
"""

import os
import sys
import unittest
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.zilliz.bakeoff import (
    compute_cosine_similarity,
    aggregate_chunk_scores_to_cases,
    calculate_retrieval_metrics,
)


class TestBakeoffMetrics(unittest.TestCase):
    def test_compute_cosine_similarity(self):
        # Two identical vectors -> similarity = 1.0
        q = np.array([1.0, 0.0, 0.0])
        chunks = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
        ])
        sims = compute_cosine_similarity(q, chunks)
        self.assertAlmostEqual(sims[0], 1.0, places=5)
        self.assertAlmostEqual(sims[1], 0.0, places=5)
        self.assertAlmostEqual(sims[2], -1.0, places=5)

    def test_aggregate_chunk_scores_to_cases(self):
        chunk_ids = ["case1:headnote:001", "case1:facts:001", "case2:holding:001", "case3:order:001"]
        case_keys = ["case1", "case1", "case2", "case3"]
        scores = np.array([0.75, 0.88, 0.92, 0.60])

        ranked_cases = aggregate_chunk_scores_to_cases(chunk_ids, case_keys, scores)
        # Should be sorted descending by max chunk score
        # case2: 0.92
        # case1: 0.88
        # case3: 0.60
        self.assertEqual(len(ranked_cases), 3)
        self.assertEqual(ranked_cases[0][0], "case2")
        self.assertAlmostEqual(ranked_cases[0][1], 0.92, places=4)
        self.assertEqual(ranked_cases[1][0], "case1")
        self.assertAlmostEqual(ranked_cases[1][1], 0.88, places=4)
        self.assertEqual(ranked_cases[2][0], "case3")
        self.assertAlmostEqual(ranked_cases[2][1], 0.60, places=4)

    def test_calculate_retrieval_metrics(self):
        ranked_cases = [("caseA", 0.95), ("caseB", 0.90), ("caseC", 0.85), ("caseD", 0.80)]
        target_keys = ["caseB"]

        metrics = calculate_retrieval_metrics(ranked_cases, target_keys)
        self.assertEqual(metrics["recall@10"], 1.0)
        self.assertEqual(metrics["recall@50"], 1.0)
        self.assertEqual(metrics["first_rank"], 2)
        self.assertAlmostEqual(metrics["mrr"], 0.5, places=4)

        # Target not in top results
        metrics_miss = calculate_retrieval_metrics(ranked_cases, ["caseZ"])
        self.assertEqual(metrics_miss["recall@10"], 0.0)
        self.assertEqual(metrics_miss["recall@50"], 0.0)
        self.assertIsNone(metrics_miss["first_rank"])
        self.assertEqual(metrics_miss["mrr"], 0.0)


if __name__ == "__main__":
    unittest.main()
