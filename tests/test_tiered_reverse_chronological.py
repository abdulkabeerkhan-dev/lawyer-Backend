import unittest
from main import (
    get_court_hierarchy_tier,
    extract_year_int,
    rerank_by_judicial_hierarchy_and_recency,
)

class TestTieredReverseChronologicalSearch(unittest.TestCase):
    def test_court_hierarchy_tiers(self):
        self.assertEqual(get_court_hierarchy_tier("2026 SCMR 1076", "Supreme Court of Pakistan"), 1)
        self.assertEqual(get_court_hierarchy_tier("PLD 2025 SC 53", "Supreme Court"), 1)
        self.assertEqual(get_court_hierarchy_tier("2024 SCMR 28", ""), 1)
        self.assertEqual(get_court_hierarchy_tier("2025 CLC 500", "Lahore High Court"), 2)
        self.assertEqual(get_court_hierarchy_tier("2026 YLR 20", "High Court of Sindh"), 2)
        self.assertEqual(get_court_hierarchy_tier("2026 FTO 1", "Federal Tax Ombudsman"), 3)

    def test_extract_year_int(self):
        self.assertEqual(extract_year_int(2026), 2026)
        self.assertEqual(extract_year_int("2025-01-01"), 2025)
        self.assertEqual(extract_year_int(None, citation="2024 SCMR 900"), 2024)

    def test_supreme_court_precedes_high_court(self):
        candidates = [
            {"metadata": {"court": "Lahore High Court", "year": 2025, "citation": "2025 CLC 500"}, "score": 0.95},
            {"metadata": {"court": "Supreme Court of Pakistan", "year": 2024, "citation": "2024 SCMR 100"}, "score": 0.40},
        ]
        reranked = rerank_by_judicial_hierarchy_and_recency(candidates)
        self.assertEqual(reranked[0]["metadata"]["citation"], "2024 SCMR 100")
        self.assertEqual(reranked[1]["metadata"]["citation"], "2025 CLC 500")

    def test_reverse_chronological_stepping_within_tier(self):
        candidates = [
            {"metadata": {"court": "Supreme Court of Pakistan", "year": 2006, "citation": "2006 SCMR 10"}, "score": 0.80},
            {"metadata": {"court": "Supreme Court of Pakistan", "year": 2026, "citation": "2026 SCMR 1076"}, "score": 0.50},
            {"metadata": {"court": "Supreme Court of Pakistan", "year": 2025, "citation": "2025 SCMR 200"}, "score": 0.60},
            {"metadata": {"court": "Supreme Court of Pakistan", "year": 2024, "citation": "2024 SCMR 300"}, "score": 0.70},
        ]
        reranked = rerank_by_judicial_hierarchy_and_recency(candidates)
        cits = [c["metadata"]["citation"] for c in reranked]
        self.assertEqual(cits, ["2026 SCMR 1076", "2025 SCMR 200", "2024 SCMR 300", "2006 SCMR 10"])

    def test_boosted_citation_remains_absolute_first(self):
        candidates = [
            {"metadata": {"court": "Supreme Court of Pakistan", "year": 2026, "citation": "2026 SCMR 1076"}, "score": 0.85},
            {"metadata": {"court": "Lahore High Court", "year": 2006, "citation": "2006 YLR 1206", "is_boosted": True}, "is_boosted": True, "score": 9999.0},
        ]
        reranked = rerank_by_judicial_hierarchy_and_recency(candidates)
        self.assertEqual(reranked[0]["metadata"]["citation"], "2006 YLR 1206")
        self.assertEqual(reranked[1]["metadata"]["citation"], "2026 SCMR 1076")

if __name__ == '__main__':
    unittest.main()
