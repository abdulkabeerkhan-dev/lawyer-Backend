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
