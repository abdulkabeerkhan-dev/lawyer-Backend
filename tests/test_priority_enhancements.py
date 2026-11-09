"""
tests/test_priority_enhancements.py

Unit and regression tests verifying the three priority items:
1. Verification status is strictly 'HEADNOTE_ONLY - not verified' when full text is absent.
   Verified badges ('verified_source', 'is_verified', 'verified', 'has_identifiable_holding')
   are blocked (False) on those records.
2. Mandatory executive answer paragraph at the top of every memo summarising the overall
   position in exactly two to four sentences.
3. 'Time as essence' standing open question under Section 55 Contract Act, 1872 whenever
   a fixed completion date is present in a specific performance query.
"""

import re
import unittest
from typing import Dict, Any

from legal_ai.synthesis.memorandum_generator import (
    sanitize_precedent_card,
    build_honest_partial_response,
    is_headnote_only_card
)
from legal_ai.synthesis.structured_memo_engine import (
    render_layer8_markdown,
    ensure_executive_answer_paragraph,
    build_structured_memo_prompts
)
from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack, EvidenceItem
from legal_ai.verification.statute_evidence_verifier import MemoVerificationReport
from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern


class TestPriorityEnhancements(unittest.TestCase):

    # -------------------------------------------------------------------------
    # Priority 1: Verification Status & Badge Integrity
    # -------------------------------------------------------------------------
    def test_headnote_only_when_full_text_absent(self):
        """Precedent card without genuine full text must strictly be HEADNOTE_ONLY - not verified."""
        raw_card = {
            "citation": "2024 SCMR 999",
            "case_name": "Test Precedent v. State",
            "content_type": "headnote_only",
            "preview": "This is an editorial headnote summarizing the decision.",
            "holding": "Editorial summary only.",
            "raw_judgment_text": "",  # No full text
            "full_text": None,
        }
        sanitized = sanitize_precedent_card(raw_card)

        self.assertEqual(sanitized["verification_status"], "HEADNOTE_ONLY - not verified")
        self.assertFalse(sanitized["verified_source"], "verified_source must be False when full text is absent")
        self.assertFalse(sanitized["is_verified"], "is_verified must be False when full text is absent")
        self.assertFalse(sanitized["verified"], "verified must be False when full text is absent")
        self.assertFalse(sanitized["has_identifiable_holding"], "has_identifiable_holding must be False")
        self.assertTrue(sanitized["is_headnote_only"], "is_headnote_only must be True")
        self.assertEqual(sanitized["source_badge"], "Headnote Only - Not Verified")
        self.assertTrue(is_headnote_only_card(sanitized))

    def test_short_preview_not_mistaken_for_full_text(self):
        """A preview snippet with >= 150 words must not trick the card into FULL_TEXT_CHECKED."""
        fake_snippet = "This is a repeated paragraph in a long preview text " * 30  # > 150 words
        raw_card = {
            "citation": "2024 CLC 1234",
            "case_name": "Vendor v. Vendee",
            "content_type": "editorial_summary",
            "preview": fake_snippet,
            "raw_judgment_text": fake_snippet,  # Merely identical to preview
            "full_text": None,
        }
        sanitized = sanitize_precedent_card(raw_card)

        self.assertEqual(sanitized["verification_status"], "HEADNOTE_ONLY - not verified")
        self.assertFalse(sanitized["verified_source"])
        self.assertFalse(sanitized["is_verified"])

    def test_full_text_checked_with_genuine_full_text_and_overlap(self):
        """When genuine full text >= 150 words exists and has >= 0.35 overlap, it receives FULL_TEXT_CHECKED."""
        holding_text = "The court held that earnest money cannot be forfeited without proving actual damage under section 73."
        genuine_full = (
            "IN THE HIGH COURT OF SINDH AT KARACHI. Before Justice A. The plaintiff filed a suit for specific performance. "
            "The court held that earnest money cannot be forfeited without proving actual damage under section 73 of the Contract Act. "
            "Having heard both sides and reviewed the certified records, we conclude that in the absence of evidence demonstrating "
            "actual pecuniary loss suffered by the defendant, forfeiture of earnest money is contrary to law and restitution must be decreed."
        ) * 4  # Well over 150 words

        raw_card = {
            "citation": "2023 SCMR 100",
            "case_name": "Karachi Builders v. Province of Sindh",
            "content_type": "full_text",
            "ratio_decidendi": holding_text,
            "holding": holding_text,
            "full_text": genuine_full,
            "raw_judgment_text": genuine_full,
        }
        sanitized = sanitize_precedent_card(raw_card)

        self.assertEqual(sanitized["verification_status"], "FULL_TEXT_CHECKED")
        self.assertTrue(sanitized["verified_source"])
        self.assertTrue(sanitized["is_verified"])
        self.assertEqual(sanitized["source_badge"], "Verified Judicial Text")

    # -------------------------------------------------------------------------
    # Priority 2: Mandatory 2-to-4 Sentence Answer Paragraph
    # -------------------------------------------------------------------------
    def test_executive_answer_paragraph_enforced_in_layer8_markdown(self):
        """Layer 8 markdown starts with Direct Legal Opinion and contains a 2-4 sentence executive summary."""
        pack = BoundedEvidencePack()
        pack.query_text = "Specific performance suit with completion date 15 September 2021."
        memo_payload = {
            "raw_query": "Specific performance suit with completion date 15 September 2021.",
            "answer": "The suit is barred by limitation.",  # Only 1 short sentence
            "claims": [],
            "caveats": [],
            "not_found": [],
            "open_questions": []
        }
        report = MemoVerificationReport(
            is_memo_verified=True,
            total_claims=0,
            verified_claims_count=0,
            unverified_claims_count=0
        )

        md = render_layer8_markdown(memo_payload, pack, report)

        # Must start with Direct Legal Opinion
        self.assertTrue(md.startswith("### Direct Legal Opinion"))

        # Extract answer paragraph under ### Direct Legal Opinion
        first_section = md.split("### Direct Legal Opinion")[1].split("\n\n")[0].strip()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', first_section) if len(s.strip()) > 15]

        self.assertGreaterEqual(len(sentences), 2, f"Expected at least 2 sentences, got {len(sentences)}: {first_section}")
        self.assertLessEqual(len(sentences), 4, f"Expected at most 4 sentences, got {len(sentences)}: {first_section}")
        self.assertIn("Article 113", first_section)

    def test_ensure_executive_answer_paragraph_preserves_valid_2_to_4_sentences(self):
        """Valid 2 to 4 sentence executive answers from LLM are preserved intact."""
        valid_ans = (
            "The suit for specific performance is statutorily time-barred under Article 113 of the Limitation Act, 1908. "
            "Under Section 3 of the Limitation Act, the court is legally mandated to dismiss the suit even if limitation is not pleaded. "
            "However, the plaintiff may maintain an alternative civil remedy for restitution of earnest money under Section 65 of the Contract Act."
        )
        pack = BoundedEvidencePack()
        pack.query_text = "Sale of plot agreement to sell 2021"
        memo_payload = {"answer": valid_ans}

        res = ensure_executive_answer_paragraph(valid_ans, memo_payload, pack)
        self.assertEqual(res, valid_ans)

    # -------------------------------------------------------------------------
    # Priority 3: 'Time as Essence' Standing Open Question
    # -------------------------------------------------------------------------
    def test_time_as_essence_in_fact_pattern_decomposition(self):
        """Fact pattern with specific performance and fixed completion date must include time as essence inquiry."""
        query = (
            "My client entered into a registered agreement to sell for a commercial plot in Lahore on 15 March 2021. "
            "The target completion date fixed in the agreement was 15 September 2021. The seller refused to execute the sale deed."
        )
        decomp = extract_legal_issues_from_fact_pattern(query)

        # Check issue IDs
        issue_ids = [iss.issue_id for iss in decomp.issues]
        self.assertIn("issue_time_as_essence_contract", issue_ids)

        # Check open questions
        self.assertTrue(len(decomp.open_questions) > 0)
        has_time_essence = any("time was made of the essence" in q.lower() or "section 55" in q.lower() for q in decomp.open_questions)
        self.assertTrue(has_time_essence, f"Expected Section 55 time as essence in open_questions: {decomp.open_questions}")

    def test_time_as_essence_rendered_in_layer8_open_questions(self):
        """Layer 8 markdown includes 'time as essence' under Evidentiary Questions for Counsel."""
        pack = BoundedEvidencePack()
        pack.query_text = "Agreement to sell plot completion date 15 September 2021 seller refused"
        memo_payload = {
            "raw_query": "Agreement to sell plot completion date 15 September 2021 seller refused",
            "answer": "The suit for specific performance is barred by limitation under Article 113. Under Section 3 the suit must be dismissed.",
            "claims": [],
            "open_questions": ["Whether defendant received earnest money payment."]
        }
        report = MemoVerificationReport(is_memo_verified=True, total_claims=0, verified_claims_count=0, unverified_claims_count=0)

        md = render_layer8_markdown(memo_payload, pack, report)

        self.assertIn("### Evidentiary Questions for Counsel", md)
        self.assertIn("Section 55 of the Contract Act, 1872", md)
        self.assertIn("PLD 2002 SC 229", md)
        self.assertIn("time was made of the essence", md)


if __name__ == "__main__":
    unittest.main()
