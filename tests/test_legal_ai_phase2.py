"""
tests/test_legal_ai_phase2.py

Unit tests for legal_ai Phase 2 modules:
- legal_ai.ranking.court_weighting
- legal_ai.ranking.relevance_filter
- legal_ai.ranking.authority_ranker
- legal_ai.retrieval.unified_orchestrator
"""

import unittest
from legal_ai.ranking.court_weighting import (
    get_court_hierarchy_weight,
    get_recency_weight,
    normalize_court_name
)
from legal_ai.ranking.relevance_filter import filter_candidate_quality_before_ranking
from legal_ai.ranking.authority_ranker import (
    calculate_authority_score,
    rank_and_filter_authorities
)
from legal_ai.retrieval.unified_orchestrator import merge_candidates_with_rrf


class TestLegalAIPhase2(unittest.TestCase):

    def setUp(self):
        self.mock_plan = {
            "legal_domain": ["criminal law", "corporate crime", "pre-arrest bail"],
            "provisions": ["Section 409 PPC", "Section 420 PPC", "Section 498 CrPC"],
            "legal_questions": [
                "civil dispute vs criminal breach of trust",
                "dishonest intention at inception",
                "grounds for pre-arrest bail under Section 498 CrPC"
            ],
            "factual_matrix": ["Rs. 45M loan diversion", "director liability"]
        }

    def test_court_weighting(self):
        # Supreme Court Tier 1
        sc_weight = get_court_hierarchy_weight("Supreme Court of Pakistan")
        self.assertEqual(sc_weight, 1.00)

        # High Court Tier 2
        lhc_weight = get_court_hierarchy_weight("Lahore High Court")
        self.assertEqual(lhc_weight, 0.85)

        # Recency
        self.assertEqual(get_recency_weight(2025), 1.00)
        self.assertLess(get_recency_weight(1990), 0.90)

        # Normalization
        self.assertEqual(normalize_court_name("sc"), "Supreme Court of Pakistan")
        self.assertEqual(normalize_court_name("lhc"), "Lahore High Court")
        self.assertEqual(normalize_court_name("shc"), "High Court of Sindh")

    def test_relevance_filter(self):
        raw_candidates = [
            # Valid 409 PPC candidate
            {
                "case_id": "2024_SCMR_500",
                "title": "Tariq Mahmood v. State",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Section 409 PPC. Pre-arrest bail confirmed where commercial dispute lacks dishonest intention at inception.",
                "year": 2024
            },
            # Caption only
            {
                "case_id": "2010_SCMR_10",
                "title": "State v. Ahmad",
                "court": "Supreme Court of Pakistan",
                "content_type": "caption_only",
                "preview": "State v. Ahmad, Criminal Appeal No. 12 of 2010.",
                "year": 2010
            },
            # Short stub
            {
                "case_id": "2015_PCrLJ_20",
                "title": "Short Order",
                "court": "Lahore High Court",
                "content_type": "order_text",
                "preview": "Adjourned.",
                "year": 2015
            },
            # Foreign court
            {
                "case_id": "AIR_1990_SC_1",
                "title": "Indian Case",
                "court": "Supreme Court of India",
                "content_type": "full_text",
                "preview": "Indian Supreme Court ruling on Section 409 IPC with detailed judicial paragraphs and analysis.",
                "year": 1990
            },
            # Defamation off-topic
            {
                "case_id": "PLD_1958_Lah_747",
                "title": "Mushtaq Ahmad Gurmani v. Z. A. Suleri",
                "court": "Lahore High Court",
                "content_type": "full_text",
                "preview": "Section 500 PPC. Libel and defamation suit concerning journalistic privilege and publication of defamatory newspaper articles.",
                "year": 1958
            }
        ]

        clean, rejections = filter_candidate_quality_before_ranking(raw_candidates, self.mock_plan)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["case_id"], "2024_SCMR_500")
        self.assertGreater(rejections["caption_only"], 0)
        self.assertGreater(rejections["insufficient_text"], 0)
        self.assertGreater(rejections["foreign_jurisdiction"], 0)
        self.assertGreater(rejections["unrelated_subject"], 0)

    def test_authority_ranking(self):
        candidates = [
            {
                "case_id": "1995_PCrLJ_100",
                "title": "Old High Court Case",
                "citation": "1995 PCrLJ 100",
                "court": "Lahore High Court",
                "content_type": "full_text",
                "preview": "Section 409 PPC. Pre-arrest bail discussed briefly." + (" word" * 80),
                "year": 1995
            },
            {
                "case_id": "2025_SCMR_999",
                "title": "Supreme Court Ruling on Director Loan & Section 409",
                "citation": "2025 SCMR 999",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Section 409 PPC and Section 420 PPC. In a commercial dispute involving loan repayment, "
                           "dishonest intention at inception must be proved. Pre-arrest bail confirmed." + (" analysis" * 250),
                "year": 2025
            }
        ]

        ranked = rank_and_filter_authorities(candidates, self.mock_plan, top_k=5)
        self.assertEqual(len(ranked), 2)
        # 2025 Supreme Court case must be ranked #1
        self.assertEqual(ranked[0]["case_id"], "2025_SCMR_999")
        self.assertGreater(ranked[0]["authority_score"], ranked[1]["authority_score"])

    def test_rrf_merging(self):
        engine_results = {
            "Supabase": [
                {"id": "2025_SCMR_999", "is_supabase_fts": True, "metadata": {"full_text": "FTS text"}},
                {"id": "1996_SCMR_186", "is_supabase_fts": True, "metadata": {}}
            ],
            "Pinecone": [
                {"id": "2025_SCMR_999", "dense_score": 0.88, "metadata": {}},
                {"id": "2024_SCMR_500", "dense_score": 0.82, "metadata": {}}
            ],
            "BM25": [
                {"id": "2024_SCMR_500", "sparse_score": 25.0, "metadata": {}},
                {"id": "1996_SCMR_186", "sparse_score": 20.0, "metadata": {}}
            ]
        }

        merged = merge_candidates_with_rrf(engine_results)
        self.assertEqual(len(merged), 3)
        # Check that 2025_SCMR_999 has both Supabase tag and dense_score preserved
        cand_999 = next(c for c in merged if c["id"] == "2025_SCMR_999")
        self.assertTrue(cand_999["is_supabase_fts"])
        self.assertEqual(cand_999["dense_score"], 0.88)
        self.assertGreater(cand_999["rrf_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
