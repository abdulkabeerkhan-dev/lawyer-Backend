"""
tests/test_order113_reviewed_tier.py

ORDER 1.13 - ITEM 10 / ORDER 1.14 - ITEM 6:
Tests for review file presence and gating.
"""

import os
import json
import pytest
from core.unified_statute_store import review_file_present, verify_reviewed_tier, UnifiedStatuteStore

def test_reviewed_tier_rejected_without_file():
    assert not review_file_present("FAKE_CID_999", "abc123hash")

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
        assert review_file_present(test_cid, test_hash) is True
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
        "reviewer_name": "Senior Advocate High Court",
        "bar_council_id": "P/12345/HC",
        "review_date": "2026-10-27",
        "record_content_hash": altered_hash,
        "status": "approved",
        "cryptographic_signature": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(review_data, f)
    try:
        assert not review_file_present(test_cid, correct_hash)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

def test_store_demotes_unverified_reviewed_tier():
    store = UnifiedStatuteStore()
    rec = store.get_by_canonical_id("FIO_2001_SEC_22")
    assert rec is not None
    assert rec.get("tier") != "reviewed"
