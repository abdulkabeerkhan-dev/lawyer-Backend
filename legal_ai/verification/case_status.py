"""Supabase retrieval_status for retrieved cases.

Zilliz chunks carry no retrieval_status, so a case that full_judgments marks rejected,
quarantined or restricted (headnote fragments, rows holding another case's text) would
otherwise reach the answer. This looks the status up by real citation, with a cache and a
hard time budget: a slow or failed lookup never blocks a query, it just admits the case.
"""
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
from typing import Dict, Iterable, Optional

BLOCKED = frozenset({"rejected", "quarantined", "restricted"})

_cache: "OrderedDict[str, str]" = OrderedDict()   # key -> status ("" = fine, or not in Supabase)
_lock = threading.Lock()
_MAX = 20000
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="case-status")


def _lookup(keys):
    from core.case_store import retrieval_statuses
    return retrieval_statuses(keys)


def statuses(keys: Iterable[str], timeout_s: float = 2.5) -> Dict[str, Optional[str]]:
    """key -> status ('' when fine or unknown to Supabase); None when the lookup failed."""
    keys = [k for k in dict.fromkeys(str(k or "").strip().upper() for k in keys) if k]
    out: Dict[str, Optional[str]] = {}
    todo = []
    with _lock:
        for k in keys:
            if k in _cache:
                _cache.move_to_end(k)
                out[k] = _cache[k]
            else:
                todo.append(k)
    if todo:
        try:
            got = _pool.submit(_lookup, todo).result(timeout=timeout_s)
        except (_Timeout, Exception):
            got = None
        with _lock:
            for k in todo:
                if got is None:
                    out[k] = None
                    continue
                st = got.get(k) or ""
                out[k] = st
                _cache[k] = st
                if len(_cache) > _MAX:
                    _cache.popitem(last=False)
    return out


def blocked(keys: Iterable[str], timeout_s: float = 2.5) -> set:
    return {k for k, st in statuses(keys, timeout_s).items() if st in BLOCKED}
