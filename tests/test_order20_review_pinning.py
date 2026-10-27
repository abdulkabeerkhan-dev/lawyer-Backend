"""
tests/test_order20_review_pinning.py

ORDER 2.0 — STEP 8: Review Key Pinning Tests
Tests cryptographic public-key signature verification with ADVOCATE_PUBKEY_SHA256 pinning.
Uses strictly in-memory throwaway RSA key; zero persistent key generation.
"""

import unittest
import os
import tempfile
import json
import hashlib
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

import core.unified_statute_store as uss

class TestOrder20ReviewPinning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate throwaway RSA key in memory only
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()
        cls.pubkey_bytes = cls.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        cls.pubkey_sha256 = hashlib.sha256(cls.pubkey_bytes).hexdigest()

        cls.cid = "TEST_2026_SEC_1"
        cls.content_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

        # Sign payload in memory
        payload = f"{cls.cid}:{cls.content_hash}".encode("utf-8")
        signature = cls.private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
        cls.sig_hex = signature.hex()

    def test_key_pinning_unset_env_fails_closed(self):
        """When ADVOCATE_PUBKEY_SHA256 is unset, verify_reviewed_tier returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pub_path = os.path.join(tmpdir, "advocate_public_key.pem")
            with open(pub_path, "wb") as f:
                f.write(self.pubkey_bytes)

            rev_path = os.path.join(tmpdir, f"{self.cid}.review.json")
            with open(rev_path, "w", encoding="utf-8") as f:
                json.dump({
                    "canonical_id": self.cid,
                    "record_content_hash": self.content_hash,
                    "status": "approved",
                    "cryptographic_signature": self.sig_hex
                }, f)

            with patch.object(uss, "REVIEWS_DIR", tmpdir):
                with patch.dict(os.environ, {}, clear=True):
                    # Unset env var
                    self.assertFalse(uss.verify_reviewed_tier(self.cid, self.content_hash))

    def test_key_pinning_mismatch_fails_closed(self):
        """When ADVOCATE_PUBKEY_SHA256 does not match public key hash, returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pub_path = os.path.join(tmpdir, "advocate_public_key.pem")
            with open(pub_path, "wb") as f:
                f.write(self.pubkey_bytes)

            rev_path = os.path.join(tmpdir, f"{self.cid}.review.json")
            with open(rev_path, "w", encoding="utf-8") as f:
                json.dump({
                    "canonical_id": self.cid,
                    "record_content_hash": self.content_hash,
                    "status": "approved",
                    "cryptographic_signature": self.sig_hex
                }, f)

            with patch.object(uss, "REVIEWS_DIR", tmpdir):
                with patch.dict(os.environ, {"ADVOCATE_PUBKEY_SHA256": "0" * 64}):
                    self.assertFalse(uss.verify_reviewed_tier(self.cid, self.content_hash))

    def test_key_pinning_matching_hash_passes(self):
        """When ADVOCATE_PUBKEY_SHA256 matches public key hash, verification succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pub_path = os.path.join(tmpdir, "advocate_public_key.pem")
            with open(pub_path, "wb") as f:
                f.write(self.pubkey_bytes)

            rev_path = os.path.join(tmpdir, f"{self.cid}.review.json")
            with open(rev_path, "w", encoding="utf-8") as f:
                json.dump({
                    "canonical_id": self.cid,
                    "record_content_hash": self.content_hash,
                    "status": "approved",
                    "cryptographic_signature": self.sig_hex
                }, f)

            with patch.object(uss, "REVIEWS_DIR", tmpdir):
                with patch.dict(os.environ, {"ADVOCATE_PUBKEY_SHA256": self.pubkey_sha256}):
                    self.assertTrue(uss.verify_reviewed_tier(self.cid, self.content_hash))

if __name__ == "__main__":
    unittest.main()
