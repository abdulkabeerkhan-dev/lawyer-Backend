"""
tests/test_legal_ai_phase1.py

Unit tests for legal_ai Phase 1 foundation modules:
- legal_ai.config
- legal_ai.analytics.telemetry
- legal_ai.documents.pdf_service
- prompts/*.md
"""

import os
import unittest
from legal_ai.config import (
    get_backend_base_url,
    get_authorized_testers,
    CLAUDE_MODEL,
    safe_create_anthropic_message
)
from legal_ai.analytics.telemetry import (
    compute_source_distribution,
    format_retrieval_telemetry_block,
    log_retrieval_telemetry,
    PipelineMetricsTracker
)
from legal_ai.documents.pdf_service import (
    extract_journal_and_year,
    build_judgment_pdf_bytes,
    resolve_judgment_pdf_url,
    sanitize_black_box_characters,
    strip_copyright_and_branding
)


class TestLegalAIPhase1(unittest.TestCase):

    def test_config_exports(self):
        url = get_backend_base_url()
        self.assertIsInstance(url, str)
        self.assertTrue(url.startswith("http"))

        testers = get_authorized_testers()
        self.assertIsInstance(testers, set)

        self.assertIsInstance(CLAUDE_MODEL, str)
        self.assertTrue(callable(safe_create_anthropic_message))

    def test_telemetry_source_distribution(self):
        # Sample mixed authorities pool
        pool = [
            {"case_id": "case1", "source_type": "Pinecone"},
            {"case_id": "case2", "is_supabase_fts": True},
            {"case_id": "case3", "source_type": "BM25"},
            {"case_id": "case4", "source_type": "External"}
        ]
        dist = compute_source_distribution(pool)
        self.assertEqual(dist["Pinecone"], 25.0)
        self.assertEqual(dist["Supabase"], 25.0)
        self.assertEqual(dist["BM25"], 25.0)
        self.assertEqual(dist["External"], 25.0)

    def test_telemetry_formatting_block(self):
        sections = ["Section 420 PPC", "Section 409 PPC"]
        issues = ["Commercial loan default vs criminal breach of trust"]
        filtered = {
            "caption only": 2,
            "wrong jurisdiction": 1,
            "irrelevant topic": 3,
            "low quality": 4,
            "trust gate exclusion": 0
        }
        pool = [
            {"case_id": "2024_SCMR_500", "source_type": "Pinecone"},
            {"case_id": "2025_SCMR_999", "is_supabase_fts": True}
        ]

        block = format_retrieval_telemetry_block(
            sections=sections,
            issues=issues,
            count_supabase=10,
            count_pinecone=20,
            count_bm25=15,
            count_external=3,
            filtered_counts=filtered,
            final_pool=pool
        )

        self.assertIn("QUERY PLAN:", block)
        self.assertIn("Sections: Section 420 PPC, Section 409 PPC", block)
        self.assertIn("SUPABASE RESULTS:\ncount: 10", block)
        self.assertIn("PINECONE RESULTS:\ncount: 20", block)
        self.assertIn("BM25 RESULTS:\ncount: 15", block)
        self.assertIn("EXTERNAL RESULTS:\ncount: 3", block)
        self.assertIn("FILTERED:\n- caption only: 2", block)
        self.assertIn("- wrong jurisdiction: 1", block)
        self.assertIn("- irrelevant topic: 3", block)
        self.assertIn("- low quality: 4", block)
        self.assertIn("FINAL AUTHORITY POOL:\ncount: 2", block)
        self.assertIn("FINAL SOURCES:", block)
        self.assertIn("Pinecone: 50.0%", block)
        self.assertIn("Supabase: 50.0%", block)

    def test_pdf_service(self):
        # 1. Extraction
        j, y, p = extract_journal_and_year("2024 SCMR 500")
        self.assertEqual(j, "SCMR")
        self.assertEqual(y, "2024")
        self.assertEqual(p, "500")

        # 2. PDF building
        pdf_bytes = build_judgment_pdf_bytes(
            title="Tariq Mahmood v. State",
            citation="2024 SCMR 500",
            court="Supreme Court of Pakistan",
            text="Judgment text regarding Section 409 and Section 420 PPC."
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertNotIn(b"PROTOTYPE", pdf_bytes)

        # 3. URL resolution
        card = {"case_id": "2024_SCMR_500", "citation": "2024 SCMR 500"}
        pdf_url = resolve_judgment_pdf_url(card)
        self.assertIn("/judgment-pdf/2024_SCMR_500", pdf_url)

        # 4. Text cleaning
        cleaned = sanitize_black_box_characters("Tariq■■■Mahmood")
        self.assertEqual(cleaned, "Tariq -- Mahmood")
        no_brand = strip_copyright_and_branding("Copyright © by Oratier Technologies (Pvt.) Ltd. Judgment text here.")
        self.assertIn("Judgment text here", no_brand)
        self.assertNotIn("Oratier", no_brand)

    def test_prompts_exist(self):
        root = os.path.dirname(os.path.dirname(__file__))
        prompts_dir = os.path.join(root, "prompts")

        planner_md = os.path.join(prompts_dir, "query_planner.md")
        researcher_md = os.path.join(prompts_dir, "researcher.md")
        writer_md = os.path.join(prompts_dir, "memorandum_writer.md")
        reviewer_md = os.path.join(prompts_dir, "reviewer.md")

        for p in [planner_md, researcher_md, writer_md, reviewer_md]:
            self.assertTrue(os.path.isfile(p), f"Missing prompt file: {p}")
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertGreater(len(content), 100)

    def test_pdf_public_access_and_base_url(self):
        """Verifies that /judgment-pdf/ requires zero auth and base URL points to 26c7."""
        import main
        from legal_ai.config import get_backend_base_url
        from fastapi.testclient import TestClient

        self.assertEqual(get_backend_base_url(), "https://lawyer-backend-production-26c7.up.railway.app")
        self.assertEqual(main.get_backend_base_url(), "https://lawyer-backend-production-26c7.up.railway.app")

        client = TestClient(main.app)
        # Request with NO Authorization bearer token
        resp = client.get("/judgment-pdf/aa5ec63f-e7fd-4bb5-83f4-b2c23d1ba76a")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
