import unittest
import os
import sys
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main
from core.quarantine_manager import approve_and_promote_record


class TestQuarantineDashboard(unittest.TestCase):

    def test_direct_script_promotion_blocked(self):
        """Verify direct Python/CLI invocation is blocked by safety token gate."""
        with self.assertRaises(PermissionError) as ctx:
            approve_and_promote_record(
                record_composite_key_or_url="any_key",
                reviewer="kabeer_admin"
            )
        self.assertIn("SAFETY VIOLATION", str(ctx.exception))

    def test_direct_script_promotion_blocked_on_generic_reviewer_even_with_token(self):
        """Verify passing a generic/system reviewer is blocked even if token prefix matches."""
        with self.assertRaises(ValueError) as ctx:
            approve_and_promote_record(
                record_composite_key_or_url="any_key",
                reviewer="kabeer_admin",
                dashboard_session_token="HUMAN_DASHBOARD_VERIFIED_TEST123"
            )
        self.assertIn("verified human reviewer identifier must be provided", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx2:
            approve_and_promote_record(
                record_composite_key_or_url="any_key",
                reviewer="system",
                dashboard_session_token="HUMAN_DASHBOARD_VERIFIED_TEST123"
            )
        self.assertIn("verified human reviewer identifier must be provided", str(ctx2.exception))


    def test_submit_review_rejects_generic_reviewer(self):
        """Verify API blocks generic or missing human reviewer names."""
        payload = {
            "record_id": "test_id",
            "action": "approve",
            "reviewer_name": "system"
        }
        with self.assertRaises(main.HTTPException) as ctx:
            asyncio.run(main.submit_quarantine_review(payload))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("human reviewer name", ctx.exception.detail)

    def test_submit_review_reject_requires_reason(self):
        """Verify API blocks rejection without a reason."""
        payload = {
            "record_id": "test_id",
            "action": "reject",
            "reviewer_name": "kabeer_curator",
            "rejection_reason": ""
        }
        with self.assertRaises(main.HTTPException) as ctx:
            asyncio.run(main.submit_quarantine_review(payload))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("rejection reason must be provided", ctx.exception.detail)

    def test_dynamic_badges_in_sanitize_precedent_card(self):
        """Verify dynamic badges for standard fresh fetch and partial fetch."""
        # 1. Standard fresh fetch
        fresh_card = {
            "case_name": "Test Fresh Case",
            "citation": "2026 SCMR 100",
            "source_url": "https://www.supremecourt.gov.pk/downloads_judgements/test.pdf",
            "is_partial": False,
            "text_health_score": 0.95
        }
        sanitized_fresh = main.sanitize_precedent_card(fresh_card)
        self.assertEqual(sanitized_fresh.get("source_badge_type"), "fresh_fetch")
        self.assertIn("Retrieved directly from supremecourt.gov.pk — not yet in our full verified index. [View original source →]", sanitized_fresh.get("source_badge_text"))

        # 2. Truncated / Partial fetch
        partial_card = {
            "case_name": "Test Partial Case",
            "citation": "2026 LHC 200",
            "source_url": "https://sys.lhc.gov.pk/appjudgments/partial.pdf",
            "is_partial": True,
            "text_health_score": 0.65
        }
        sanitized_partial = main.sanitize_precedent_card(partial_card)
        self.assertEqual(sanitized_partial.get("source_badge_type"), "partial_fetch")
        self.assertIn("⚠️ Partial document — full text extraction incomplete. [Read the complete judgment at the original source →]", sanitized_partial.get("source_badge_text"))

    def test_normalize_quarantine_record_bottom_anchors_date(self):
        """Verify normalization anchors date at footer/signatures rather than grabbing header lower court date."""
        mock_raw_text = (
            "IN THE SUPREME COURT OF PAKISTAN\n"
            "C.P.L.A. No. 88-P of 2022\n"
            "(Against judgment dated 03.11.2021 passed by the Peshawar High Court in FAB No.37-P of 2011)\n"
            "Abdul Salam Khan\n"
            "Petitioner\n"
            "Versus\n"
            "M/s Bank Al-Habib Ltd, etc.\n"
            "Respondent(s)\n"
            "Some legal judgment text on merits...\n"
            "JUDGE\n"
            "Islamabad.\n"
            "18 July, 2025.\n"
            "Approved for Reporting.\n"
            "JUDGE"
        )
        rec = {
            "raw_text": mock_raw_text,
            "source_url": "https://www.supremecourt.gov.pk/downloads_judgements/c.p._88_p_2022.pdf",
            "docket_number": "88-P/2022"
        }
        normalized = main.normalize_quarantine_record_for_dashboard(rec)
        self.assertEqual(normalized["decision_date"], "18 July, 2025")
        self.assertNotEqual(normalized["decision_date"], "03.11.2021")
        self.assertEqual(normalized["case_title"], "Abdul Salam Khan v. M/s Bank Al-Habib Ltd, etc")
        self.assertEqual(normalized["court_name"], "Supreme Court of Pakistan")


    def test_serve_dashboard_html(self):
        """Verify GET /admin/quarantine/dashboard returns HTML with interactive controls."""
        resp = asyncio.run(main.serve_quarantine_dashboard())
        self.assertEqual(resp.status_code, 200)
        html = resp.body.decode('utf-8')
        self.assertIn("Quarantine Review & Promotion Dashboard", html)
        self.assertIn("Human-in-the-Loop Gatekeeper", html)
        self.assertIn("/admin/quarantine/review", html)
        self.assertIn("Physical Sign-Off & Promote", html)


if __name__ == '__main__':
    unittest.main()
