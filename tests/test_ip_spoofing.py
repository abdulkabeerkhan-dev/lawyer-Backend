"""
tests/test_ip_spoofing.py

Unit tests for proxy-aware client IP extraction and anti-spoofing defense.
Validates:
1. CF-Connecting-IP is strictly ignored unless TRUST_CLOUDFLARE_PROXY=true.
2. X-Forwarded-For takes the rightmost untrusted value, rejecting attacker-controlled leftmost headers.
3. Railway's X-Envoy-External-Address is respected.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import get_real_client_ip, get_client_ip


class MockRequest:
    def __init__(self, headers=None, client_host="192.168.1.100"):
        self.headers = headers or {}
        if client_host:
            self.client = MagicMock()
            self.client.host = client_host
        else:
            self.client = None


class TestIPSpoofingDefense(unittest.TestCase):

    def setUp(self):
        self._orig_trust_cf = os.environ.get("TRUST_CLOUDFLARE_PROXY")
        if "TRUST_CLOUDFLARE_PROXY" in os.environ:
            del os.environ["TRUST_CLOUDFLARE_PROXY"]

    def tearDown(self):
        if self._orig_trust_cf is not None:
            os.environ["TRUST_CLOUDFLARE_PROXY"] = self._orig_trust_cf
        elif "TRUST_CLOUDFLARE_PROXY" in os.environ:
            del os.environ["TRUST_CLOUDFLARE_PROXY"]

    def test_cf_connecting_ip_ignored_by_default(self):
        """Attacker sends spoofed CF-Connecting-IP; ignored because Railway is not behind Cloudflare."""
        req = MockRequest(
            headers={"cf-connecting-ip": "1.1.1.1"},
            client_host="192.168.1.100"
        )
        resolved_ip = get_real_client_ip(req)
        self.assertEqual(resolved_ip, "192.168.1.100", "Spoofed CF-Connecting-IP was accepted!")

    def test_cf_connecting_ip_trusted_when_configured(self):
        """When TRUST_CLOUDFLARE_PROXY=true, CF-Connecting-IP is trusted."""
        os.environ["TRUST_CLOUDFLARE_PROXY"] = "true"
        req = MockRequest(
            headers={"cf-connecting-ip": "203.0.113.50"},
            client_host="192.168.1.100"
        )
        resolved_ip = get_real_client_ip(req)
        self.assertEqual(resolved_ip, "203.0.113.50")

    def test_x_forwarded_for_uses_rightmost_untrusted_ip(self):
        """
        Attacker prepends spoofed IP '10.0.0.1' to X-Forwarded-For.
        Nearest edge proxy appends client's genuine IP '198.51.100.77'.
        Backend must extract the rightmost IP '198.51.100.77', NOT '10.0.0.1'.
        """
        req = MockRequest(
            headers={"x-forwarded-for": "10.0.0.1, 172.16.0.5, 198.51.100.77"},
            client_host="192.168.1.100"
        )
        resolved_ip = get_real_client_ip(req)
        self.assertEqual(resolved_ip, "198.51.100.77", "Failed to extract rightmost untrusted XFF value!")

    def test_envoy_external_address_takes_precedence_over_xff(self):
        """Railway edge Envoy proxy header takes precedence over spoofable raw XFF."""
        req = MockRequest(
            headers={
                "x-envoy-external-address": "172.56.21.90",
                "x-forwarded-for": "1.2.3.4"
            },
            client_host="192.168.1.100"
        )
        resolved_ip = get_real_client_ip(req)
        self.assertEqual(resolved_ip, "172.56.21.90")

    def test_get_client_ip_alias(self):
        """Verify get_client_ip alias functions identically."""
        req = MockRequest(
            headers={"x-forwarded-for": "8.8.8.8, 9.9.9.9"},
            client_host="127.0.0.1"
        )
        self.assertEqual(get_client_ip(req), "9.9.9.9")


if __name__ == "__main__":
    unittest.main()
