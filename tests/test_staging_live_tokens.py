import unittest
import os
import sys
import httpx

class TestStagingLiveTokens(unittest.TestCase):
    """
    Directive 5: Staging Integration Test Suite for Real Clerk Tokens
    Verifies behavior against live staging environment with actual Clerk session tokens:
    1. Valid whitelisted token -> Reaches user endpoints (200 OK).
    2. Valid non-listed token -> Rejected by prototype tester whitelist (403 Forbidden).
    3. Whitelisted non-admin token -> Rejected on all /admin/* endpoints (403 Forbidden).
    """

    @classmethod
    def setUpClass(cls):
        cls.staging_url = os.environ.get("STAGING_URL", "").rstrip("/")
        cls.whitelisted_token = os.environ.get("REAL_CLERK_TOKEN_WHITELISTED", "").strip()
        cls.non_listed_token = os.environ.get("REAL_CLERK_TOKEN_NON_LISTED", "").strip()
        cls.non_admin_token = os.environ.get("REAL_CLERK_TOKEN_NON_ADMIN", "").strip()

    def test_live_whitelisted_token_on_staging(self):
        """Test that a valid whitelisted token succeeds on staging protected route."""
        if not self.staging_url or not self.whitelisted_token:
            self.skipTest("STAGING_URL or REAL_CLERK_TOKEN_WHITELISTED not configured in environment.")

        headers = {"Authorization": f"Bearer {self.whitelisted_token}"}
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{self.staging_url}/users/quota", headers=headers)
            self.assertIn(
                res.status_code, [200],
                f"Expected 200 for valid whitelisted token on staging /users/quota, got {res.status_code}: {res.text}"
            )

    def test_live_non_listed_token_forbidden_on_staging(self):
        """Test that a genuine Clerk token for an unlisted user is rejected with 403 on staging."""
        if not self.staging_url or not self.non_listed_token:
            self.skipTest("STAGING_URL or REAL_CLERK_TOKEN_NON_LISTED not configured in environment.")

        headers = {"Authorization": f"Bearer {self.non_listed_token}"}
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{self.staging_url}/users/quota", headers=headers)
            self.assertEqual(
                res.status_code, 403,
                f"Expected 403 for non-whitelisted token on staging, got {res.status_code}: {res.text}"
            )

    def test_live_whitelisted_non_admin_forbidden_on_admin_routes(self):
        """Test that an authorized user without admin role receives 403 on /admin/* routes."""
        token = self.non_admin_token or self.whitelisted_token
        if not self.staging_url or not token:
            self.skipTest("STAGING_URL or test token not configured in environment.")

        headers = {"Authorization": f"Bearer {token}"}
        admin_endpoints = ["/admin/activity", "/admin/associates", "/admin/export-training-data"]
        with httpx.Client(timeout=10.0) as client:
            for ep in admin_endpoints:
                res = client.get(f"{self.staging_url}{ep}", headers=headers)
                self.assertEqual(
                    res.status_code, 403,
                    f"Expected 403 on admin route {ep} for non-admin token, got {res.status_code}: {res.text}"
                )

if __name__ == "__main__":
    unittest.main()
