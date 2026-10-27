"""
core/unified_statute_store.py

Single authoritative source-of-truth lookup API for Pakistani statutes.
Merges statute tables and versions into a unified in-memory and disk registry.
Every provision returns:
- act_code, act_name
- primary_num, canonical_id, title
- verbatim text (or explicit missing_reason)
- source_file, source_page, content_hash
- tier ('ingested_unreviewed' / 'reviewed' / 'disputed')
- status ('in_force' / 'repealed' / 'omitted')
- jurisdiction ('federal' / province)
- effective_from, effective_to
"""

import os
import json
import re
from typing import Dict, List, Any, Optional

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")
TABLES_DIR = os.path.join(REPO_DIR, "data", "statute_tables")
VERSIONS_DIR = os.path.join(REPO_DIR, "data", "statute_versions")
REVIEWS_DIR = os.path.join(REPO_DIR, "data", "reviews")

def review_file_present(canonical_id: str, content_hash: str) -> bool:
    """
    Order 1.14 - Item 6: Checks presence of review metadata file on disk.
    This was previously called verify_reviewed_tier but only checked disk presence.
    """
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    if not os.path.exists(review_file):
        return False
    try:
        import json
        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return (
            str(data.get("canonical_id")).upper() == str(canonical_id).upper() and
            bool(data.get("reviewer_name")) and
            bool(data.get("review_date")) and
            str(data.get("record_content_hash")) == str(content_hash) and
            data.get("status") == "approved" and
            bool(data.get("cryptographic_signature"))
        )
    except Exception:
        return False

def verify_reviewed_tier(canonical_id: str, content_hash: str) -> bool:
    """
    Order 2.0 - Step 8: Cryptographic public-key signature verification for 'reviewed' tier with key pinning.
    The expected SHA-256 of the advocate public key must be supplied via ADVOCATE_PUBKEY_SHA256 env var.
    If unset or mismatched against data/reviews/advocate_public_key.pem, fails closed (returns False).
    """
    expected_pubkey_hash = os.environ.get("ADVOCATE_PUBKEY_SHA256")
    if not expected_pubkey_hash:
        return False

    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    pub_key_file = os.path.join(REVIEWS_DIR, "advocate_public_key.pem")
    
    if not os.path.exists(review_file) or not os.path.exists(pub_key_file):
        return False
    try:
        with open(pub_key_file, "rb") as pf:
            pubkey_bytes = pf.read()

        import hashlib
        actual_pubkey_hash = hashlib.sha256(pubkey_bytes).hexdigest()
        if actual_pubkey_hash.lower() != expected_pubkey_hash.strip().lower():
            return False

        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        if str(data.get("canonical_id")).upper() != str(canonical_id).upper():
            return False
        if str(data.get("record_content_hash")) != str(content_hash):
            return False
        if data.get("status") != "approved":
            return False
        
        sig_hex = data.get("cryptographic_signature", "")
        if not sig_hex:
            return False
        sig_bytes = bytes.fromhex(sig_hex)

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        
        public_key = serialization.load_pem_public_key(pubkey_bytes)
        
        # Payload verified is canonical_id + content_hash
        payload = f"{canonical_id}:{content_hash}".encode("utf-8")
        
        public_key.verify(
            sig_bytes,
            payload,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False

class UnifiedStatuteStore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(UnifiedStatuteStore, cls).__new__(cls)
            cls._instance._loaded = False
            cls._instance._by_cid = {}
            cls._instance._by_act_num = {}
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self.load()

    def load(self):
        """Loads all unified statutes into fast in-memory hash maps."""
        self._by_cid.clear()
        self._by_act_num.clear()

        # Order 2.0 Step 1: App must load ONLY data/statutes_v2 from now on.
        target_dir = UNIFIED_DIR
        if not os.path.exists(target_dir):
            self._loaded = True
            return

        for fname in os.listdir(target_dir):
            if not fname.endswith(".json"):
                continue
            act_code = fname.replace(".json", "")
            fpath = os.path.join(target_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    provisions = json.load(f)
                    if isinstance(provisions, dict):
                        for k in ["sections", "provisions", "data"]:
                            if k in provisions and isinstance(provisions[k], list):
                                provisions = provisions[k]
                                break
                    if not isinstance(provisions, list):
                        continue
                    
                    for r in provisions:
                        if not isinstance(r, dict):
                            continue
                        cid = r.get("canonical_id")
                        num = str(r.get("primary_num") or "").strip()
                        act = str(r.get("act_code") or act_code).upper()

                        if not cid and num:
                            cid = f"{act}_SEC_{num}"

                        # Backward compatibility alias for text_layer_matched <-> page_verified
                        if "text_layer_matched" in r:
                            r["page_verified"] = r.get("text_layer_matched")
                        elif "page_verified" in r:
                            r["text_layer_matched"] = r.get("page_verified")

                        if cid:
                            if r.get("tier") == "reviewed":
                                if not verify_reviewed_tier(cid.upper(), r.get("content_hash", "")):
                                    r["tier"] = "disputed" if r.get("is_disputed") else "ingested_unreviewed"
                                    r["quoting_allowed"] = False
                            self._by_cid[cid.upper()] = r
                        if num:
                            norm_num = re.sub(r'[^A-Z0-9]', '', num.upper())
                            expected_root_cid = f"{act}_SEC_{norm_num}"
                            if (act, norm_num) not in self._by_act_num or cid == expected_root_cid:
                                self._by_act_num[(act, norm_num)] = r
                                self._by_act_num[(act, num.upper())] = r
            except Exception as e:
                pass

        self._loaded = True

    def get_by_canonical_id(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        if not self._loaded:
            self.load()
        if not canonical_id:
            return None
        return self._by_cid.get(canonical_id.strip().upper())

    def get_provision(self, act_code: str, provision_num: str) -> Optional[Dict[str, Any]]:
        if not self._loaded:
            self.load()
        if not act_code or not provision_num:
            return None

        act_upper = act_code.strip().upper()
        alias_map = {
            "STAMP_ACT_1899": "STAMP_1899",
            "CONTRACT_ACT_1872": "CONTRACT_1872",
            "REGISTRATION_ACT_1908": "REGISTRATION_1908",
            "LIMITATION_ACT_1908": "LIMITATION_1908",
        }
        act_upper = alias_map.get(act_upper, act_upper)
        clean_num = str(provision_num).strip().upper()
        norm_num = re.sub(r'[^A-Z0-9]', '', clean_num)

        # 1. Direct lookup by (act, num)
        rec = self._by_act_num.get((act_upper, clean_num)) or self._by_act_num.get((act_upper, norm_num))
        if rec:
            return rec

        # 2. Canonical ID variants
        cids_to_try = [
            f"{act_upper}_SEC_{clean_num}",
            f"{act_upper}_SEC_{norm_num}",
            f"{act_upper}_ART_{clean_num}",
            f"{act_upper}_ART_{norm_num}",
            f"{act_upper}_{clean_num}"
        ]
        for cid in cids_to_try:
            r = self._by_cid.get(cid)
            if r:
                return r

        return None

# Singleton accessor
def get_unified_statute_store() -> UnifiedStatuteStore:
    return UnifiedStatuteStore()
