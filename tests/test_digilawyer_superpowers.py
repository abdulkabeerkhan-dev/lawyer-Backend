"""
tests/test_digilawyer_superpowers.py

Unit and integration tests for Section AI + DigiLawyer Hybrid Architecture:
1. TemplateOrchestrator (Pre-built Pakistani templates, slot filling, docx export)
2. Shepardizing Citator (Good Law vs Overruled detection under Art 189)
3. Bilingual Roman Urdu Lexicon (FIR / trial court vernacular translation)
4. Chronological List of Dates and Events Generator (High Court Rules compliance)
5. Bench Quorum & Strength Weighting (Relevance-gated Art 189 hierarchy)
"""

import unittest
import io
from fastapi.testclient import TestClient
from docx import Document

from legal_ai.drafting.template_orchestrator import TemplateOrchestrator, TEMPLATES_REGISTRY
from legal_ai.drafting.chronology_generator import extract_dates_and_events_from_text, format_chronology_markdown
from core.precedent_treatment import check_precedent_treatment, PrecedentStatus, filter_and_flag_precedent_cards
from legal_ai.search.urdu_lexicon import expand_urdu_legal_query
from core.bench_quorum import calculate_quorum_multiplier, apply_bench_quorum_reranking
from main import app

client = TestClient(app)

class TestDigiLawyerSuperpowers(unittest.TestCase):

    def test_1_template_registry_coverage(self):
        """Verifies that all 6 standard Pakistani court templates exist."""
        templates = TemplateOrchestrator.list_templates()
        template_ids = [t["id"] for t in templates]
        self.assertIn("bail_pre_arrest_498", template_ids)
        self.assertIn("bail_post_arrest_497", template_ids)
        self.assertIn("writ_petition_199", template_ids)
        self.assertIn("application_12_2_cpc", template_ids)
        self.assertIn("stay_application_o39", template_ids)
        self.assertIn("legal_notice", template_ids)

    def test_2_shepardizing_negative_treatment(self):
        """Verifies that landmark overruled cases are flagged and Good Law passes."""
        # Overruled case: Zafar Ali Shah (PLD 2000 SC 869)
        res_overruled = check_precedent_treatment("PLD 2000 SC 869")
        self.assertEqual(res_overruled["status"], PrecedentStatus.OVERRULED.value)
        self.assertTrue(res_overruled["fatal_in_court"])
        self.assertIn("PLD 2009 SC 879", res_overruled["overruled_by"])

        # Good Law case: 2024 SCMR 101
        res_good = check_precedent_treatment("2024 SCMR 101")
        self.assertEqual(res_good["status"], PrecedentStatus.GOOD_LAW.value)
        self.assertFalse(res_good["fatal_in_court"])

        # Filter cards
        cards = [
            {"neutral_citation": "PLD 2000 SC 869", "title": "Zafar Ali Shah"},
            {"neutral_citation": "2024 SCMR 101", "title": "Ayaz v. Mustafa"}
        ]
        safe, blocked = filter_and_flag_precedent_cards(cards)
        self.assertEqual(len(safe), 1)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(safe[0]["neutral_citation"], "2024 SCMR 101")
        self.assertEqual(blocked[0]["neutral_citation"], "PLD 2000 SC 869")

    def test_3_bilingual_urdu_transliteration(self):
        """Verifies that Roman Urdu vernacular is expanded with statutory provisions."""
        # Pre-arrest bail vernacular
        res1 = expand_urdu_legal_query("mujhe zamanat qabal az giraftari chahiye")
        self.assertTrue(res1["has_urdu_terms"])
        self.assertIn("Section 498 CrPC", res1["statutory_anchors"])
        self.assertIn("CrPC 498", res1["expanded_query"])

        # Cheque dishonour
        res2 = expand_urdu_legal_query("cheque bounce 489-f case")
        self.assertTrue(res2["has_urdu_terms"])
        self.assertIn("Section 489-F PPC", res2["statutory_anchors"])

        # Stay order
        res3 = expand_urdu_legal_query("hukm-e-imtanai application for property")
        self.assertTrue(res3["has_urdu_terms"])
        self.assertIn("Order XXXIX Rules 1 and 2 CPC", res3["statutory_anchors"])

    def test_4_chronology_generator(self):
        """Verifies date extraction and formatted Markdown synopsis table."""
        sample_narrative = (
            "On 12.04.2023, the complainant registered false FIR No. 12/2023.\n"
            "On 25.07.2023, the Additional Sessions Judge dismissed bail application.\n"
            "On August 10, 2023, petitioner filed departmental representation."
        )
        events = extract_dates_and_events_from_text(sample_narrative)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["date"], "12.04.2023")
        self.assertEqual(events[0]["annexure"], "Annexure 'A'")

        table_md = format_chronology_markdown(events)
        self.assertIn("SYNOPSIS & CHRONOLOGICAL LIST OF DATES AND EVENTS", table_md)
        self.assertIn("| 1. | 12.04.2023 |", table_md)

    def test_5_bench_quorum_weighting(self):
        """Verifies quorum weighting and relevance gating."""
        full_bench_case = {
            "case_title": "Federation of Pakistan v. Shaukat Aziz Siddiqui",
            "bench_type": "5-member Full Bench",
            "journal": "SCMR",
            "score": 0.85
        }
        single_bench_case = {
            "case_title": "Tariq v. State",
            "bench_type": "Single Bench",
            "journal": "YLR",
            "score": 0.85
        }

        # Multiplier when relevant (score >= 0.70)
        mult_fb = calculate_quorum_multiplier(full_bench_case, semantic_relevance=0.85)
        mult_sb = calculate_quorum_multiplier(single_bench_case, semantic_relevance=0.85)
        self.assertEqual(mult_fb, 1.50)
        self.assertEqual(mult_sb, 1.05)

        # Relevance gating: if irrelevant (< 0.70), multiplier is neutral 1.0
        mult_gated = calculate_quorum_multiplier(full_bench_case, semantic_relevance=0.50)
        self.assertEqual(mult_gated, 1.0)

    def test_6_drafting_endpoints_api(self):
        """Tests FastAPI /api/v1/drafting endpoints."""
        # 1. List templates
        r1 = client.get("/api/v1/drafting/templates")
        self.assertEqual(r1.status_code, 200)
        data1 = r1.json()
        self.assertGreaterEqual(len(data1["templates"]), 6)

        # 2. Check authority endpoint
        r2 = client.get("/api/v1/drafting/check-authority?citation=PLD%202000%20SC%20869")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["result"]["status"], "OVERRULED")

        # 3. Generate pleading markdown
        payload = {
            "template_id": "bail_pre_arrest_498",
            "slots": {
                "court_name": "Lahore High Court, Rawalpindi Bench",
                "petitioner": "Muhammad Asif",
                "respondent": "The State & Another",
                "facts": "On 15.05.2024, FIR was lodged due to business rivalry without evidence."
            },
            "export_format": "markdown"
        }
        r3 = client.post("/api/v1/drafting/generate", json=payload)
        self.assertEqual(r3.status_code, 200)
        self.assertIn("Muhammad Asif", r3.json()["markdown"])
        self.assertIn("SECTION 498", r3.json()["markdown"].upper())

        # 4. Generate pleading docx
        payload["export_format"] = "docx"
        r4 = client.post("/api/v1/drafting/generate", json=payload)
        self.assertEqual(r4.status_code, 200)
        self.assertEqual(r4.headers["content-type"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        docx_bytes = r4.content
        self.assertGreater(len(docx_bytes), 1000)
        doc = Document(io.BytesIO(docx_bytes))
        self.assertAlmostEqual(doc.sections[0].left_margin.inches, 1.5, places=2)

if __name__ == "__main__":
    unittest.main()
