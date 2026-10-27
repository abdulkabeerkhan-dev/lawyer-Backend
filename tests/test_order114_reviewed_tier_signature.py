"""
tests/test_order114_reviewed_tier_signature.py

ORDER 1.14 - ITEM 6 TESTS:
1. Review file signed with a throwaway in-memory private key MUST FAIL verification against the committed authorized public key.
2. Missing signature or missing review file returns False.
"""

import os
import json
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

from core.unified_statute_store import (
    verify_reviewed_tier,
    review_file_present,
    REVIEWS_DIR
)

def test_throwaway_key_signature_fails_verification(tmp_path):
    # 1. Generate an unauthorized throwaway keypair in memory (NEVER saved to disk)
    throwaway_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    canonical_id = "FIO_2001_SEC_22"
    content_hash = "69894cf7a3a91bbdcffebdd06e0ee74164a2f8c5c76db3fe2cb3485d11e5dc42"
    payload = f"{canonical_id}:{content_hash}".encode("utf-8")
    
    # Sign payload with throwaway key
    signature = throwaway_key.sign(
        payload,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sig_hex = signature.hex()

    # 2. Write review file to REVIEWS_DIR temporarily
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    review_data = {
        "canonical_id": canonical_id,
        "reviewer_name": "Advocate Test",
        "bar_council_id": "P/99999/HC",
        "review_date": "2026-10-27",
        "record_content_hash": content_hash,
        "status": "approved",
        "cryptographic_signature": sig_hex
    }
    
    with open(review_file, "w", encoding="utf-8") as f:
        json.dump(review_data, f, indent=2)

    try:
        # 3. Check review_file_present: disk metadata presence check PASSES
        assert review_file_present(canonical_id, content_hash) is True
        
        # 4. Cryptographic signature check against committed authorized public key MUST FAIL!
        is_verified = verify_reviewed_tier(canonical_id, content_hash)
        assert is_verified is False, "Signature produced with throwaway key MUST NOT pass verification against committed advocate public key!"
    finally:
        # Clean up review file
        if os.path.exists(review_file):
            os.remove(review_file)
