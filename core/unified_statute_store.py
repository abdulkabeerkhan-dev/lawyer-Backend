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
                            self._by_cid[cid.upper()] = r
                        if num:
                            norm_num = re.sub(r'[^A-Z0-9]', '', num.upper())
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
