import time
import re
from typing import Dict, Any, Optional, Tuple

class PartyFallbackCache:
    """
    Hardened cache for Tier 2 party-name fallback results.
    Prevents stale entries via TTL and prevents cross-case pollution by keying on
    citation/case_id + party_name and strictly enforcing case isolation.
    """
    def __init__(self, default_ttl_seconds: float = 3600.0):
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _normalize_key(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return re.sub(r'[^a-z0-9]+', '', str(text).lower())

    def make_cache_key(self, party_name: str, citation: Optional[str] = None, case_id: Optional[str] = None) -> str:
        p_norm = self._normalize_key(party_name)
        cit_norm = self._normalize_key(citation) or self._normalize_key(case_id) or "none"
        return f"{cit_norm}:{p_norm}"

    def get(self, party_name: str, citation: Optional[str] = None, case_id: Optional[str] = None, current_time: Optional[float] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Retrieves a cached record.
        Returns (is_hit, result).
        Enforces:
        1. TTL expiration
        2. Cross-case isolation: if a specific citation/case_id is requested, the cached record
           must match or belong to that citation context.
        """
        now = current_time if current_time is not None else time.time()
        key = self.make_cache_key(party_name, citation=citation, case_id=case_id)
        entry = self._cache.get(key)
        if not entry:
            return False, None

        # 1. TTL Check
        if now - entry["timestamp"] > self.default_ttl:
            del self._cache[key]
            return False, None

        # 2. Case Isolation Check
        res = entry.get("result")
        if res and (citation or case_id):
            req_cit = self._normalize_key(citation)
            req_cid = self._normalize_key(case_id)
            res_cit = self._normalize_key(res.get("neutral_citation") or res.get("citation"))
            res_cid = self._normalize_key(res.get("case_id"))

            if req_cit and res_cit and (req_cit not in res_cit and res_cit not in req_cit):
                return False, None
            if req_cid and res_cid and (req_cid != res_cid):
                return False, None

        return True, res

    def set(self, party_name: str, result: Optional[Dict[str, Any]], citation: Optional[str] = None, case_id: Optional[str] = None, current_time: Optional[float] = None):
        """Stores a party fallback result with timestamp and citation context."""
        now = current_time if current_time is not None else time.time()
        key = self.make_cache_key(party_name, citation=citation, case_id=case_id)
        self._cache[key] = {
            "timestamp": now,
            "result": result,
            "citation": citation,
            "case_id": case_id,
            "party_name": party_name
        }

    def clear(self):
        self._cache.clear()

    def __len__(self):
        return len(self._cache)

GLOBAL_PARTY_CACHE = PartyFallbackCache(default_ttl_seconds=3600.0)
