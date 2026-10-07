import unittest
import asyncio
from core.legal_query_planner import analyze_legal_query, create_deterministic_fallback_plan, LegalQueryPlan
from core.candidate_quality_filter import filter_candidate_quality_before_ranking
from core.authority_ranking import rank_and_filter_authorities, calculate_authority_score
from core.legal_proposition_extractor import extract_legal_propositions, derive_why_matters_to_case
from core.current_law_verifier import verify_current_law_for_provisions, format_current_law_context
from core.pdf_resolver import resolve_judgment_pdf_url, extract_journal_and_year


class TestLegalAIPipeline(unittest.TestCase):

    def setUp(self):
        self.sample_query = (
            "Managing Director accused of Rs. 45M loan diversion and FIR under Section 409 PPC, Section 420 PPC. "
            "Whether commercial loan default is civil dispute or criminal breach of trust, and pre-arrest bail under Section 498 CrPC."
        )

    def test_query_planner_deterministic(self):
        plan = create_deterministic_fallback_plan(self.sample_query)
        self.assertIsInstance(plan, LegalQueryPlan)
        self.assertTrue(any("409" in p for p in plan.provisions))
        self.assertTrue(any("420" in p for p in plan.provisions))
        self.assertTrue(any("498" in p for p in plan.provisions))
        self.assertGreaterEqual(len(plan.search_lanes), 2)
        self.assertIn("Pakistan", plan.jurisdiction)

    def test_candidate_quality_filter(self):
        plan = create_deterministic_fallback_plan(self.sample_query)
        candidates = [
            # Good candidate: Section 409 PPC director case
            {
                "case_id": "2024_SCMR_500",
                "title": "Tariq Mahmood v. State",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Section 409 PPC. Allegation of criminal breach of trust against director. "
                           "Where transaction arises out of commercial transaction without dishonest intention at inception, "
                           "it is a civil dispute and pre-arrest bail under Section 498 CrPC is confirmed.",
                "year": 2024
            },
            # Bad candidate 1: Caption only
            {
                "case_id": "2010_SCMR_10",
                "title": "State v. Ahmad",
                "court": "Supreme Court of Pakistan",
                "content_type": "caption_only",
                "preview": "State v. Ahmad, Criminal Appeal No. 12 of 2010.",
                "year": 2010
            },
            # Bad candidate 2: Short text (<100 chars)
            {
                "case_id": "2015_PCrLJ_20",
                "title": "Short v. Order",
                "court": "Lahore High Court",
                "content_type": "order_text",
                "preview": "Adjourned on request.",
                "year": 2015
            },
            # Bad candidate 3: Foreign court
            {
                "case_id": "AIR_1990_SC_1",
                "title": "Indian v. State",
                "court": "Supreme Court of India",
                "content_type": "full_text",
                "preview": "Detailed judgment under Indian Penal Code section 409 regarding public servant entrustment and misappropriation of government funds across states.",
                "year": 1990
            },
            # Bad candidate 4: Off-topic Gurmani defamation case
            {
                "case_id": "PLD_1958_Lah_747",
                "title": "Mushtaq Ahmad Gurmani v. Z. A. Suleri",
                "court": "Lahore High Court",
                "content_type": "full_text",
                "preview": "Section 500 PPC. Defamation and libel action concerning journalistic privilege and publication of defamatory articles.",
                "year": 1958
            },
            # Bad candidate 5: Pure narcotics case
            {
                "case_id": "2021_SCMR_123",
                "title": "Gul Khan v. State",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Control of Narcotic Substances Act 1997 Section 9(c). Recovery of 1200 grams charas from vehicle.",
                "year": 2021
            },
            # Bad candidate 6: Pure murder case
            {
                "case_id": "2020_SCMR_456",
                "title": "Muhammad Akram v. State",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Section 302 PPC. Murder trial. Recovery of firearm injury and post-mortem report contradictions.",
                "year": 2020
            }
        ]

        clean, rejections = filter_candidate_quality_before_ranking(candidates, plan)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["case_id"], "2024_SCMR_500")
        self.assertGreater(rejections["caption_only"], 0)
        self.assertGreater(rejections["insufficient_text"], 0)
        self.assertGreater(rejections["foreign_jurisdiction"], 0)
        self.assertGreater(rejections["unrelated_subject"], 0)

    def test_authority_ranking(self):
        plan = create_deterministic_fallback_plan(self.sample_query)
        candidates = [
            # 1995 High Court case
            {
                "case_id": "1995_PCrLJ_100",
                "title": "Old High Court Case",
                "citation": "1995 PCrLJ 100",
                "court": "Lahore High Court",
                "content_type": "full_text",
                "preview": "Section 409 PPC. Pre-arrest bail discussed briefly." + (" word" * 80),
                "year": 1995
            },
            # 2025 Supreme Court case with detailed text
            {
                "case_id": "2025_SCMR_999",
                "title": "Supreme Court Ruling on Director Loan & Section 409",
                "citation": "2025 SCMR 999",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Section 409 PPC and Section 420 PPC. In a commercial dispute involving loan repayment, "
                           "dishonest intention at inception must be proved. Criminal breach of trust by director "
                           "cannot be converted from civil debt. Pre-arrest bail under Section 498 CrPC confirmed." + (" analysis" * 250),
                "year": 2025
            }
        ]

        ranked = rank_and_filter_authorities(candidates, plan, top_k=5)
        self.assertEqual(len(ranked), 2)
        # 2025 Supreme Court case must be ranked #1
        self.assertEqual(ranked[0]["case_id"], "2025_SCMR_999")
        self.assertGreater(ranked[0]["authority_score"], ranked[1]["authority_score"])

    def test_legal_proposition_extraction(self):
        plan = create_deterministic_fallback_plan(self.sample_query)
        authorities = [
            {
                "case_id": "2024_SCMR_500",
                "title": "Tariq Mahmood v. State",
                "citation": "2024 SCMR 500",
                "court": "Supreme Court of Pakistan",
                "year": 2024,
                "preview": "Section 409 PPC. Para 7. Held that where money is advanced as loan, failure to repay does not constitute criminal breach of trust in absence of entrustment."
            }
        ]

        props = extract_legal_propositions(authorities, plan)
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual(p["citation"], "2024 SCMR 500")
        self.assertEqual(p["paragraph_reference"], "Para 7")
        self.assertIn("Section 409 PPC", p["legal_issue"])
        self.assertTrue(len(p["why_matters_to_case"]) > 20)
        self.assertTrue(len(p["application"]) > 20)

    def test_current_law_verification(self):
        provisions = ["Section 409 PPC", "Section 420 PPC"]
        verified = verify_current_law_for_provisions(provisions, query_text=self.sample_query)
        self.assertGreaterEqual(len(verified), 2)
        for v in verified:
            self.assertIn("PPC_1860", v["act_code"])
            self.assertEqual(v["status"], "Active / In Force")
            self.assertTrue(len(v["current_text"]) > 20)
            self.assertTrue(v["is_verified"])

        ctx = format_current_law_context(verified)
        self.assertIn("Section 409", ctx)
        self.assertIn("Section 420", ctx)
        self.assertIn("Pakistan Penal Code", ctx)

    def test_pdf_resolver(self):
        candidate = {
            "case_id": "2024_SCMR_500",
            "citation": "2024 SCMR 500",
            "title": "Tariq Mahmood v. State"
        }
        url = resolve_judgment_pdf_url(candidate, backend_base_url="https://lawyer-backend-production-26c7.up.railway.app")
        self.assertIsInstance(url, str)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("2024_SCMR_500", url)

        j, y, p = extract_journal_and_year("2024 SCMR 500")
        self.assertEqual(j, "SCMR")
        self.assertEqual(y, "2024")
        self.assertEqual(p, "500")

    def test_purge_debug_warnings(self):
        from main import purge_debug_warnings
        dirty_text = (
            "> ⚠️ **Prototype. Not verified for use in pleadings.**\n\n"
            "### EXECUTIVE SUMMARY & LEGAL OPINION\n"
            "This is substantive legal advice regarding Section 409 PPC [NOT CHECKED].\n\n"
            "> ⚠️ **[JUDICIAL REVIEW CORROBORATION NOTICE]**\n"
            "Propositions need corroboration.\n\n"
            "### STATUTORY & PROCEDURAL FRAMEWORK\n"
            "Section 420 PPC governs cheating.\n\n"
            "#### Statutory Currency Verification Status\n"
            "- **PPC_1860_SEC_409**: [NOT CHECKED]\n\n"
            "### APPENDIX: SYSTEM & VERIFICATION NOTICE\n"
            "System notice text here.\n"
        )
        cleaned = purge_debug_warnings(dirty_text)
        self.assertNotIn("Prototype", cleaned)
        self.assertNotIn("[JUDICIAL REVIEW CORROBORATION NOTICE]", cleaned)
        self.assertNotIn("Statutory Currency Verification Status", cleaned)
        self.assertNotIn("[NOT CHECKED]", cleaned)
        self.assertNotIn("APPENDIX: SYSTEM & VERIFICATION NOTICE", cleaned)
        self.assertIn("### EXECUTIVE SUMMARY & LEGAL OPINION", cleaned)
        self.assertIn("Section 409 PPC", cleaned)

    def test_precedent_card_12_fields(self):
        from main import sanitize_precedent_card
        raw_card = {
            "id": "2024_SCMR_500",
            "case_id": "2024_SCMR_500",
            "title": "Tariq Mahmood v. The State",
            "citation": "2024 SCMR 500",
            "court": "Supreme Court of Pakistan",
            "year": "2024",
            "sections": ["Section 409 PPC", "Section 420 PPC"],
            "legal_issue": "Commercial loan default vs criminal breach of trust",
            "ratio_decidendi": "Mere non-payment of loan without dishonest intention at inception is a civil dispute.",
            "important_paragraphs": "Paragraph 7 and 8 discussing distinction between civil debt and entrustment.",
            "authority_strength": "Binding Supreme Court Precedent (Article 189)",
            "is_supabase_fts": False,
            "dense_score": 0.85,
            "raw_judgment_text": "Detailed judgment text exceeding 150 words. " * 30,
            "content_type": "full_text"
        }
        sanitized = sanitize_precedent_card(raw_card)
        required_12_fields = [
            "case_name", "citation", "court", "year", "sections", "legal_issue",
            "ratio_decidendi", "important_paragraphs", "authority_strength",
            "pdf_url", "source_type", "verification_status"
        ]
        for field in required_12_fields:
            self.assertIn(field, sanitized, f"Field '{field}' missing from precedent card")
            self.assertTrue(sanitized[field], f"Field '{field}' has empty value")

        self.assertEqual(sanitized["source_type"], "Pinecone")
        self.assertEqual(sanitized["verification_status"], "Verified Full Judgment")
        self.assertTrue(sanitized["pdf_url"].startswith("http"))

    def test_build_judgment_pdf_bytes_no_prototype_banner(self):
        from main import build_judgment_pdf_bytes
        pdf_bytes = build_judgment_pdf_bytes(
            title="Tariq Mahmood v. State",
            citation="2024 SCMR 500",
            court="Supreme Court of Pakistan",
            text="Judgment body paragraph text."
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertNotIn(b"PROTOTYPE", pdf_bytes)


if __name__ == '__main__':
    unittest.main()

