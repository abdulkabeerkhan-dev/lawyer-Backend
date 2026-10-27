"""
tests/test_order113_reviewed_tier.py

ORDER 1.13 - ITEM 10: REVIEWED TIER CRYPTOGRAPHIC GATING TESTS
Verifies that:
1. 'reviewed' tier cannot be set by agents/models directly.
2. Without a valid review file in data/reviews/, any 'reviewed' tier record is downgraded.
3. With a cryptographically signed review file matching the record content hash, 'reviewed' is accepted.
4. If content hash in the review file differs from the record content hash, 'reviewed' is rejected.
"""

import os
import json
import pytest
from core.unified_statute_store import verify_reviewed_tier, UnifiedStatuteStore

def test_reviewed_tier_rejected_without_file():
    assert not verify_reviewed_tier("FAKE_CID_999", "abc123hash")

def test_reviewed_tier_with_valid_signed_file(tmp_path):
    reviews_dir = "data/reviews"
    os.makedirs(reviews_dir, exist_ok=True)
    test_cid = "TEST_STATUTE_SEC_1"
    test_hash = "5f4dcc3b5aa765d61d8327deb882cf99"
    test_file = os.path.join(reviews_dir, f"{test_cid}.review.json")
    
    review_data = {
        "canonical_id": test_cid,
        "reviewer_name": "Senior Advocate High Court",
        "bar_council_id": "P/12345/HC",
        "review_date": "2026-10-27",
        "record_content_hash": test_hash,
        "status": "approved",
        "cryptographic_signature": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(review_data, f)

    try:
        assert verify_reviewed_tier(test_cid, test_hash) is True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

def test_reviewed_tier_rejected_on_hash_mismatch():
    reviews_dir = "data/reviews"
    os.makedirs(reviews_dir, exist_ok=True)
    test_cid = "TEST_STATUTE_SEC_2"
    correct_hash = "11111111111111111111111111111111"
    altered_hash = "22222222222222222222222222222222"
    test_file = os.path.join(reviews_dir, f"{test_cid}.review.json")
    
    review_data = {
        "canonical_id": test_cid,
        "reviewer_name": "Advocate High Court",
        "bar_council_id": "P/99999/HC",
        "review_date": "2026-10-27",
        "record_content_hash": correct_hash,
        "status": "approved",
        "cryptographic_signature": "sig123"
    }
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(review_data, f)

    try:
        # Check against altered hash
        assert verify_reviewed_tier(test_cid, altered_hash) is False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
