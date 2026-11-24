"""
Verbatim judgment text kept in Cloudflare R2, so Supabase stays under its free 500 MB.

Layout (written by scripts/r2/export_texts_to_r2.py):
    {prefix}/{first 3 hex chars of full_judgments.id}.json.gz
    -> {"<id>": {"case_id", "full_text", "headnote", "ratio_decidendi", "sha256"}, ...}

4,096 shards of ~50 judgments each. A lookup fetches one shard (~100 KB gzipped)
over the S3 API and caches it, so neighbouring lookups are free.

Env: R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
     R2_TEXT_PREFIX (default "texts/v1").
"""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

SHARD_CHARS = 3
DEFAULT_PREFIX = "texts/v1"
_CACHE_SHARDS = 48

_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_lock = threading.Lock()


def shard_of(row_id: str) -> str:
    return str(row_id).lower().replace("-", "")[:SHARD_CHARS]


def shard_key(shard: str, prefix: Optional[str] = None) -> str:
    return f"{(prefix or os.environ.get('R2_TEXT_PREFIX') or DEFAULT_PREFIX).strip('/')}/{shard}.json.gz"


def text_sha256(full_text: Optional[str], headnote: Optional[str], ratio: Optional[str]) -> str:
    h = hashlib.sha256()
    for part in (full_text, headnote, ratio):
        h.update((part or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def r2_configured() -> bool:
    return all(os.environ.get(k) for k in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))


# ---------------------------------------------------------------- SigV4 GET
def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signed_get(object_key: str, timeout_s: float) -> Optional[bytes]:
    account = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET"]
    access = os.environ["R2_ACCESS_KEY_ID"]
    secret = os.environ["R2_SECRET_ACCESS_KEY"]
    host = f"{account}.r2.cloudflarestorage.com"
    path = "/" + "/".join(urllib.request.quote(p, safe="") for p in f"{bucket}/{object_key}".split("/"))
    now = _dt.datetime.now(_dt.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical = "\n".join(["GET", path, "", f"host:{host}", f"x-amz-content-sha256:{payload_hash}",
                           f"x-amz-date:{amz_date}", "", "host;x-amz-content-sha256;x-amz-date", payload_hash])
    scope = f"{day}/auto/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(_sign(_sign(_sign(("AWS4" + secret).encode(), day), "auto"), "s3"), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"https://{host}{path}", headers={
        "Authorization": f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
                         f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={sig}",
        "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _load_shard(shard: str, timeout_s: float) -> Dict[str, Any]:
    with _lock:
        if shard in _cache:
            _cache.move_to_end(shard)
            return _cache[shard]
    raw = _signed_get(shard_key(shard), timeout_s)
    data = json.loads(gzip.decompress(raw).decode("utf-8")) if raw else {}
    with _lock:
        _cache[shard] = data
        while len(_cache) > _CACHE_SHARDS:
            _cache.popitem(last=False)
    return data


def get_texts(row_ids: Iterable[str], timeout_s: float = 4.0) -> Dict[str, Dict[str, Any]]:
    """id -> {"full_text", "headnote", "ratio_decidendi", ...}. Never raises."""
    out: Dict[str, Dict[str, Any]] = {}
    if not r2_configured():
        return out
    by_shard: Dict[str, list] = {}
    for rid in row_ids:
        if rid:
            by_shard.setdefault(shard_of(rid), []).append(str(rid))
    for shard, ids in by_shard.items():
        try:
            data = _load_shard(shard, timeout_s)
        except Exception as e:
            logger.warning(f"[R2TextStore] shard {shard} fetch failed: {e}")
            continue
        for rid in ids:
            rec = data.get(rid)
            if rec:
                out[rid] = rec
    return out
