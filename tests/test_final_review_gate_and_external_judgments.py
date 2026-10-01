import unittest
import asyncio
from core.final_review_gate import run_final_review_gate
from core.recent_judgments_search import (
    search_recent_external_judgments,
    format_external_authorities_section,
    is_whitelisted_court_url,
    derive_court_from_url
)

class TestFinalReviewGate(unittest.TestCase):
    def test_gate_passes_when_claims_supported(self):
        async def mock_reviewer_supported(prompt):
            return {
                "passed": True,
                "propositions": [
                    {
                        "claim": "Section 489-F PPC requires dishonest issuance of a cheque.",
                        "cited_authority": "2013 SCMR 51",
                        "classification": "supported",
                        "reason": "Directly stated in the judgment text."
                    }
                ],
                "issues": []
            }

        memo = "In 2013 SCMR 51, the Supreme Court held that dishonest issuance is required under Section 489-F PPC."
        chunks = [{"citation": "2013 SCMR 51", "full_text": "Dishonest issuance of cheque is an essential ingredient."}]

        res = asyncio.run(run_final_review_gate(memo, chunks, reviewer_fn=mock_reviewer_supported))
        self.assertTrue(res["passed"])
        self.assertEqual(len(res["issues"]), 0)

    def test_gate_fails_when_claim_overstated(self):
        async def mock_reviewer_overstated(prompt):
            return {
                "passed": False,
                "propositions": [
                    {
                        "claim": "The Supreme Court abolished all civil cheque remedies.",
                        "cited_authority": "2013 SCMR 51",
                        "classification": "overstated",
                        "reason": "Judgment only dealt with criminal liability under 489-F, not civil remedies."
                    }
                ],
                "issues": ["2013 SCMR 51: Claim that civil remedies were abolished is overstated."]
            }

        memo = "Under 2013 SCMR 51, the Supreme Court abolished all civil cheque recovery suits."
        chunks = [{"citation": "2013 SCMR 51", "full_text": "Criminal proceedings under Section 489-F PPC."}]

        res = asyncio.run(run_final_review_gate(memo, chunks, reviewer_fn=mock_reviewer_overstated))
        self.assertFalse(res["passed"])
        self.assertIn("overstated", res["issues"][0].lower())

    def test_gate_fails_when_claim_unsupported(self):
        async def mock_reviewer_unsupported(prompt):
            return {
                "passed": False,
                "propositions": [
                    {
                        "claim": "Order XXI Rule 90 requires 50% deposit.",
                        "cited_authority": "PLD 2020 SC 500",
                        "classification": "unsupported",
                        "reason": "The cited case does not mention Order XXI Rule 90 or 50% deposit."
                    }
                ],
                "issues": ["PLD 2020 SC 500: The cited case does not support 50% deposit."]
            }

        memo = "In PLD 2020 SC 500, a 50% deposit is mandatory under Order XXI Rule 90."
        chunks = [{"citation": "PLD 2020 SC 500", "full_text": "Judgment on service tribunal jurisdiction."}]

        res = asyncio.run(run_final_review_gate(memo, chunks, reviewer_fn=mock_reviewer_unsupported))
        self.assertFalse(res["passed"])
        self.assertIn("does not support", res["issues"][0])


class TestRecentJudgmentsSearch(unittest.TestCase):
    def test_whitelisted_court_domains(self):
        self.assertTrue(is_whitelisted_court_url("https://www.supremecourt.gov.pk/judgments/sc_order_123.pdf"))
        self.assertTrue(is_whitelisted_court_url("https://lhc.gov.pk/system/files/case_456.pdf"))
        self.assertTrue(is_whitelisted_court_url("https://shc.gov.pk/judgments/789"))
        self.assertTrue(is_whitelisted_court_url("https://fsc.gov.pk/decisions/2020"))

        # Non-whitelisted must fail
        self.assertFalse(is_whitelisted_court_url("https://randomblog.com/case-law"))
        self.assertFalse(is_whitelisted_court_url("https://news.pk/sc-ruling"))
        self.assertFalse(is_whitelisted_court_url(""))

    def test_derive_court_from_url(self):
        self.assertEqual(derive_court_from_url("https://supremecourt.gov.pk/order.pdf"), "Supreme Court of Pakistan")
        self.assertEqual(derive_court_from_url("https://lhc.gov.pk/order.pdf"), "Lahore High Court")
        self.assertEqual(derive_court_from_url("https://shc.gov.pk/judgment"), "High Court of Sindh")
        self.assertEqual(derive_court_from_url("https://fsc.gov.pk/judgment"), "Federal Shariat Court")

    def test_format_external_authorities_section(self):
        records = [
            {
                "title": "M/s ABC v. Federation of Pakistan",
                "court": "Supreme Court of Pakistan",
                "date": "2025-11-20",
                "content_type": "judgment",
                "url": "https://supremecourt.gov.pk/judgments/abc.pdf",
                "snippet": "Holding that statutory deposit requirements apply prospectively."
            }
        ]
        rendered = format_external_authorities_section(records)
        self.assertIn("### External Authorities (Not Yet in Database)", rendered)
        self.assertIn("M/s ABC v. Federation of Pakistan", rendered)
        self.assertIn("Supreme Court of Pakistan", rendered)
        self.assertIn("2025-11-20", rendered)
        self.assertIn("https://supremecourt.gov.pk/judgments/abc.pdf", rendered)
        self.assertIn("Holding that statutory deposit requirements apply prospectively.", rendered)

    def test_empty_records_returns_empty_section(self):
        rendered = format_external_authorities_section([])
        self.assertEqual(rendered, "")

    def test_search_recent_external_judgments_with_mock(self):
        async def mock_fetcher(query):
            return [
                {
                    "title": "State v. Tariq",
                    "court": "Lahore High Court",
                    "date": "2026-02-15",
                    "content_type": "order",
                    "url": "https://lhc.gov.pk/cases/tariq.pdf",
                    "snippet": "Order granting post-arrest bail."
                }
            ]

        results = asyncio.run(search_recent_external_judgments("bail in narcotics case", mock_fetcher=mock_fetcher))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["court"], "Lahore High Court")
        self.assertEqual(results[0]["content_type"], "order")

if __name__ == "__main__":
    unittest.main()
