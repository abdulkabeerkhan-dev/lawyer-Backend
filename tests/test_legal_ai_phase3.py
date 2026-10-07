"""
tests/test_legal_ai_phase3.py

Unit tests for legal_ai Phase 3 modules:
- legal_ai.synthesis.memorandum_generator
- legal_ai.verification.citation_validator
- legal_ai.verification.quote_verifier
"""

import unittest
from legal_ai.synthesis.memorandum_generator import (
    purge_debug_warnings,
    sanitize_precedent_card,
    REQUIRED_12_FIELDS
)
from legal_ai.verification.citation_validator import (
    parse_pakistan_citation,
    repair_ocr_citation
)
from legal_ai.verification.quote_verifier import verify_quotations_in_text


class TestLegalAIPhase3(unittest.TestCase):

    def test_purge_debug_warnings(self):
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
        for field in REQUIRED_12_FIELDS:
            self.assertIn(field, sanitized, f"Field '{field}' missing from precedent card")
            self.assertTrue(sanitized[field], f"Field '{field}' has empty value")

        self.assertEqual(sanitized["source_type"], "Pinecone")
        self.assertEqual(sanitized["verification_status"], "Verified Full Judgment")
        self.assertTrue(sanitized["pdf_url"].startswith("http"))

    def test_citation_validator(self):
        # 1. OCR repair
        repaired = repair_ocr_citation("2O24 S.C.M.R. 5OO")
        self.assertIn("2024", repaired)
        self.assertIn("SCMR", repaired)

        # 2. Parsing
        res = parse_pakistan_citation("2024 SCMR 500")
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["journal"], "SCMR")
        self.assertEqual(res["year"], 2024)
        self.assertEqual(res["page"], 500)
        self.assertEqual(res["court_inference"], "Supreme Court of Pakistan")

        res_hc = parse_pakistan_citation("2021 PCrLJ 120")
        self.assertTrue(res_hc["is_valid"])
        self.assertEqual(res_hc["journal"], "PCRLJ")
        self.assertEqual(res_hc["court_inference"], "High Court")

    def test_quote_verifier(self):
        context = [
            {
                "case_id": "2024_SCMR_500",
                "preview": "Held that mere non-payment of commercial loan without dishonest intention at inception is not criminal breach of trust."
            }
        ]
        # Text with genuine quote
        genuine_text = 'The Supreme Court confirmed that "mere non-payment of commercial loan without dishonest intention at inception" does not constitute an offence.'
        passed, details = verify_quotations_in_text(genuine_text, context)
        self.assertTrue(passed)
        self.assertEqual(len(details), 1)
        self.assertTrue(details[0]["is_grounded"])

        # Text with fake quote
        fake_text = 'The Court ruled that "every loan default is strictly punishable with life imprisonment and immediate asset seizure".'
        passed_fake, details_fake = verify_quotations_in_text(fake_text, context)
        self.assertFalse(passed_fake)
        self.assertFalse(details_fake[0]["is_grounded"])


if __name__ == "__main__":
    unittest.main()
