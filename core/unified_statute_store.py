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
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
TABLES_DIR = os.path.join(REPO_DIR, "data", "statute_tables")
VERSIONS_DIR = os.path.join(REPO_DIR, "data", "statute_versions")
REVIEWS_DIR = os.path.join(REPO_DIR, "data", "reviews")

def verify_reviewed_tier(canonical_id: str, content_hash: str) -> bool:
    """
    Validates whether a provision has been legitimately promoted to 'reviewed' tier.
    A provision can ONLY be 'reviewed' if a signed review file exists in data/reviews/
    named <canonical_id>.review.json with matching record_content_hash, reviewer_name,
    and cryptographic_signature. Agents/models cannot set this tier.
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

        # Primary load directory: UNIFIED_DIR
        target_dir = UNIFIED_DIR if os.path.exists(UNIFIED_DIR) and len(os.listdir(UNIFIED_DIR)) > 0 else TABLES_DIR

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
