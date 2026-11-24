#!/usr/bin/env python3
"""
Copy full_judgments text (full_text, headnote, ratio_decidendi) verbatim from Supabase
into Cloudflare R2 shards, then verify every row against Supabase independently.

Read-only on Supabase. Writes only to the R2 bucket. Resumable (SQLite manifest).

    SUPABASE_ACCESS_TOKEN=... CLOUDFLARE_API_TOKEN=... \\
    python3 scripts/r2/export_texts_to_r2.py --bucket section-judgment-texts --work-dir /tmp/r2 upload
    ... verify

Uploads go through the Cloudflare API (bearer token); the app reads through the
S3 API (legal_ai.storage.r2_text_store) with R2 access keys.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from legal_ai.storage.r2_text_store import SHARD_CHARS, shard_key, text_sha256  # noqa: E402

SB_PROJECT = os.environ.get("SUPABASE_PROJECT_REF", "dexolywhperqvmnyqxpd")
SB_URL = f"https://api.supabase.com/v1/projects/{SB_PROJECT}/database/query"
CF = "https://api.cloudflare.com/client/v4"
FIELDS = ("full_text", "headnote", "ratio_decidendi")
SHARDS = [format(i, f"0{SHARD_CHARS}x") for i in range(16 ** SHARD_CHARS)]


def _req(url, method="GET", body=None, token="", ctype="application/json", timeout=300, raw=False):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    for attempt in range(7):
        try:
            r = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {token}", "Content-Type": ctype, "User-Agent": "section-r2-export/1"})
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                out = resp.read()
                return out if raw else json.loads(out or b"null")
        except urllib.error.HTTPError as e:
            if e.code == 404 and raw:
                return None
            if e.code in (429, 500, 502, 503, 504) and attempt < 6:
                time.sleep(min(60, 3 * 2 ** attempt))
                continue
            raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read()[:300]!r}")
        except (urllib.error.URLError, OSError) as e:
            if attempt < 6:
                time.sleep(min(60, 3 * 2 ** attempt))
                continue
            raise RuntimeError(f"{method} {url} -> {e}")


def sb_query(sql: str):
    rows = _req(SB_URL, "POST", {"query": sql, "read_only": True}, os.environ["SUPABASE_ACCESS_TOKEN"])
    if not isinstance(rows, list):
        raise RuntimeError(f"Supabase error: {str(rows)[:300]}")
    return rows


def shard_where(shard: str) -> str:
    lo = f"{shard}{'0' * (8 - SHARD_CHARS)}-0000-0000-0000-000000000000"
    nxt = int(shard, 16) + 1
    if nxt >= 16 ** SHARD_CHARS:
        return f"id >= '{lo}'::uuid"
    hi = f"{format(nxt, f'0{SHARD_CHARS}x')}{'0' * (8 - SHARD_CHARS)}-0000-0000-0000-000000000000"
    return f"id >= '{lo}'::uuid and id < '{hi}'::uuid"


class Manifest:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("create table if not exists shards (shard text primary key, rows int, bytes int, "
                        "uploaded_at text, verified_at text, verify_note text)")
        self.db.commit()

    def get(self, shard):
        return self.db.execute("select rows, bytes, uploaded_at, verified_at from shards where shard=?", (shard,)).fetchone()

    def uploaded(self, shard, rows, nbytes):
        with self.lock:
            self.db.execute("insert or replace into shards (shard, rows, bytes, uploaded_at) values (?,?,?,datetime('now'))",
                            (shard, rows, nbytes))
            self.db.commit()

    def verified(self, shard, note):
        with self.lock:
            self.db.execute("update shards set verified_at=datetime('now'), verify_note=? where shard=?", (note, shard))
            self.db.commit()

    def totals(self):
        return self.db.execute("select count(*), sum(rows), sum(bytes), count(verified_at) from shards").fetchone()


def object_url(args, key):
    return f"{CF}/accounts/{args.account}/r2/buckets/{args.bucket}/objects/{key}"


def ensure_bucket(args):
    tok = os.environ["CLOUDFLARE_API_TOKEN"]
    if not args.account:
        accts = _req(f"{CF}/accounts", token=tok)["result"]
        if len(accts) != 1:
            raise SystemExit(f"pass --account; token sees {[(a['id'], a['name']) for a in accts]}")
        args.account = accts[0]["id"]
    try:
        _req(f"{CF}/accounts/{args.account}/r2/buckets/{args.bucket}", token=tok)
        print(f"bucket {args.bucket} exists", flush=True)
    except RuntimeError as e:
        if "HTTP 404" not in str(e):
            raise
        _req(f"{CF}/accounts/{args.account}/r2/buckets", "POST", {"name": args.bucket}, tok)
        print(f"created private bucket {args.bucket}", flush=True)


def upload_shard(args, man, shard):
    rows = sb_query("select id::text id, case_id, full_text, headnote, ratio_decidendi from full_judgments where "
                    + shard_where(shard))
    recs = {}
    for r in rows:
        recs[r["id"]] = {"case_id": r["case_id"], **{f: r[f] for f in FIELDS},
                         "sha256": text_sha256(r["full_text"], r["headnote"], r["ratio_decidendi"])}
    blob = gzip.compress(json.dumps(recs, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    _req(object_url(args, shard_key(shard, args.prefix)), "PUT", blob, os.environ["CLOUDFLARE_API_TOKEN"],
         ctype="application/gzip")
    man.uploaded(shard, len(recs), len(blob))
    return len(recs), len(blob)


def verify_shard(args, man, shard):
    """Re-download from R2 and compare md5 of each field with md5 computed inside Postgres."""
    raw = _req(object_url(args, shard_key(shard, args.prefix)), token=os.environ["CLOUDFLARE_API_TOKEN"], raw=True)
    if raw is None:
        raise RuntimeError(f"shard {shard} missing in R2")
    r2 = json.loads(gzip.decompress(raw).decode("utf-8"))
    sb = sb_query("select id::text id, md5(coalesce(full_text,'')) a, md5(coalesce(headnote,'')) b, "
                  "md5(coalesce(ratio_decidendi,'')) c from full_judgments where " + shard_where(shard))
    md5 = lambda s: hashlib.md5((s or "").encode("utf-8")).hexdigest()
    bad = []
    for r in sb:
        rec = r2.get(r["id"])
        if not rec or (md5(rec["full_text"]), md5(rec["headnote"]), md5(rec["ratio_decidendi"])) != (r["a"], r["b"], r["c"]):
            bad.append(r["id"])
    extra = set(r2) - {r["id"] for r in sb}
    note = f"ok {len(sb)}" if not bad and not extra else f"MISMATCH {len(bad)} missing/different, {len(extra)} extra"
    man.verified(shard, note)
    return len(sb), bad, extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["upload", "verify"])
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--account", default=os.environ.get("R2_ACCOUNT_ID", ""))
    ap.add_argument("--prefix", default="texts/v1")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="only the first N shards (testing)")
    args = ap.parse_args()
    os.makedirs(args.work_dir, exist_ok=True)
    man = Manifest(os.path.join(args.work_dir, "r2_manifest.db"))
    ensure_bucket(args)
    shards = SHARDS[: args.limit] if args.limit else SHARDS

    if args.mode == "upload":
        todo = [s for s in shards if not man.get(s)]
        print(f"{len(shards)} shards, {len(todo)} to upload", flush=True)
        fn = lambda s: upload_shard(args, man, s)
    else:
        todo = [s for s in shards if man.get(s) and not man.get(s)[3]]
        print(f"{len(todo)} shards to verify", flush=True)
        fn = lambda s: verify_shard(args, man, s)

    done, failed, problems = 0, [], []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(fn, s): s for s in todo}
        for f in cf.as_completed(futs):
            s = futs[f]
            try:
                res = f.result()
                if args.mode == "verify" and (res[1] or res[2]):
                    problems.append((s, len(res[1]), len(res[2])))
            except Exception as e:
                failed.append(s)
                print(f"shard {s} failed: {e}", flush=True)
            done += 1
            if done % 100 == 0 or done == len(todo):
                n, rows, nbytes, ver = man.totals()
                print(f"[{done}/{len(todo)}] shards={n} rows={rows} gz_mb={(nbytes or 0) / 1e6:.1f} verified={ver} "
                      f"failed={len(failed)} mismatched={len(problems)}", flush=True)
    n, rows, nbytes, ver = man.totals()
    report = {"mode": args.mode, "shards": n, "rows": rows, "gz_bytes": nbytes, "verified_shards": ver,
              "failed": failed, "mismatched": problems, "account": args.account, "bucket": args.bucket}
    json.dump(report, open(os.path.join(args.work_dir, f"r2_{args.mode}_report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "account"}, indent=1))
    sys.exit(1 if failed or problems else 0)


if __name__ == "__main__":
    main()
