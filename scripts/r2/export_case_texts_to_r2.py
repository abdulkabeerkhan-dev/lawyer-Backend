#!/usr/bin/env python3
"""
Copy Turso `case_texts` (141k cases, every column, verbatim) into Cloudflare R2:

    {prefix}/{sha1(CASE_ID)[:3]}.json.gz   -> {"<CASE_ID>": {<all columns>}, ...}   (default prefix "case_texts/v1")

For about a third of cases Turso's `headnote` column holds the full reported judgment
that Supabase does not have, so this copy must be complete before Turso is deleted.

stage   page through Turso by rowid, write one JSONL file per shard locally, and record
        each row's SHA-256 (canonical JSON) in the manifest.
upload  gzip each shard, upload through the Cloudflare API, require ETag == MD5.
verify  (1) read Turso again, independently, and compare every row's SHA-256 with the
        manifest; (2) download every shard over the S3 API and compare every record's
        SHA-256 with the manifest. Row counts must match Turso exactly.

Read-only on Turso. Resumable.
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
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..")))

from core.case_store import case_text_shard_key, case_text_key  # noqa: E402

CF = "https://api.cloudflare.com/client/v4"
COLUMNS = ["case_id", "neutral_citation", "case_title", "court_name", "court_source", "year", "journal", "page",
           "content_level", "full_text", "headnote", "procedural_history", "facts", "issues", "reasoning",
           "holding", "disposition", "statutory_provisions", "is_quarantined", "has_pdf", "pdf_r2_key",
           "created_at", "updated_at"]
INT_COLS = {"year", "page", "is_quarantined", "has_pdf"}


def _http(url, method="GET", body=None, headers=None, timeout=240):
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 7:
                time.sleep(min(90, 3 * 2 ** attempt))
                continue
            raise RuntimeError(f"{method} {url[:120]} -> HTTP {e.code}: {e.read()[:300]!r}")
        except (urllib.error.URLError, OSError) as e:
            if attempt < 7:
                time.sleep(min(90, 3 * 2 ** attempt))
                continue
            raise RuntimeError(f"{method} {url[:120]} -> {e}")


def turso_rows(sql):
    url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
    body = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    out = _http(url, "POST", body, {"Authorization": f"Bearer {os.environ['TURSO_AUTH_TOKEN']}",
                                    "Content-Type": "application/json"})
    res = out["results"][0]
    if res["type"] != "ok":
        raise RuntimeError(f"Turso error: {str(res)[:300]}")
    cols = [c["name"] for c in res["response"]["result"]["cols"]]
    rows = []
    for row in res["response"]["result"]["rows"]:
        rec = {}
        for c, v in zip(cols, row):
            val = v.get("value") if v.get("type") != "null" else None
            if c in INT_COLS and val is not None:
                val = int(val)
            rec[c] = val
        rows.append(rec)
    return rows


def rec_sha(rec):
    return hashlib.sha256(json.dumps(rec, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def fetch_range(a, b):
    return turso_rows(f"select rowid as _rowid, {', '.join(COLUMNS)} from case_texts where rowid >= {a} and rowid < {b}")


class Manifest:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""
            create table if not exists rows (key text primary key, rowid int, shard text, sha text, verified_turso int, verified_r2 int);
            create table if not exists pages (lo int primary key, n int);
            create table if not exists shards (shard text primary key, n int, bytes int, md5 text, etag_ok int, note text);
        """)
        self.db.commit()

    def q(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def x(self, sql, args=(), many=False):
        with self.lock:
            (self.db.executemany if many else self.db.execute)(sql, args)
            self.db.commit()


def stage(args, man):
    lo, hi = [int(x) for x in turso_rows("select min(rowid) a, max(rowid) b from case_texts")[0].values()]
    done = {r[0] for r in man.q("select lo from pages")}
    spans = [(s, s + args.page) for s in range(lo, hi + 1, args.page) if s not in done]
    stage_dir = os.path.join(args.work_dir, "stage")
    os.makedirs(stage_dir, exist_ok=True)
    flock = threading.Lock()
    print(f"stage: {len(spans)} pages to read", flush=True)

    def one(span):
        rows = fetch_range(*span)
        entries, by_shard = [], {}
        for r in rows:
            rid = r.pop("_rowid")
            key = case_text_key(r["case_id"])
            shard = case_text_shard_key(key, prefix="").split("/")[-1].split(".")[0]
            entries.append((key, int(rid), shard, rec_sha(r)))
            by_shard.setdefault(shard, []).append(json.dumps({"k": key, "r": r}, ensure_ascii=False))
        with flock:
            for shard, lines in by_shard.items():
                with open(os.path.join(stage_dir, f"{shard}.jsonl"), "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
        man.x("insert or replace into rows (key, rowid, shard, sha) values (?,?,?,?)", entries, many=True)
        man.x("insert or replace into pages values (?,?)", (span[0], len(rows)))
        return len(rows)

    with cf.ThreadPoolExecutor(args.workers) as ex:
        for i, n in enumerate(ex.map(one, spans), 1):
            if i % 25 == 0 or i == len(spans):
                print(f"[stage {i}/{len(spans)}] rows={man.q('select count(*) from rows')[0][0]}", flush=True)


def load_stage_shard(args, shard):
    recs = {}
    with open(os.path.join(args.work_dir, "stage", f"{shard}.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                o = json.loads(line)
                recs[o["k"]] = o["r"]
    return recs


def upload(args, man):
    shards = [s for (s,) in man.q("select distinct shard from rows")]
    done = {s for (s,) in man.q("select shard from shards where etag_ok=1")}
    todo = [s for s in shards if s not in done]
    print(f"upload: {len(shards)} shards, {len(todo)} to upload", flush=True)

    def one(shard):
        recs = load_stage_shard(args, shard)
        blob = gzip.compress(json.dumps(recs, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
        md5 = hashlib.md5(blob).hexdigest()
        key = f"{args.prefix.strip('/')}/{shard}.json.gz"
        url = f"{CF}/accounts/{args.account}/r2/buckets/{args.bucket}/objects/{urllib.parse.quote(key)}"
        res = _http(url, "PUT", blob, {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}",
                                       "Content-Type": "application/gzip"})
        ok = int(((res or {}).get("result") or {}).get("etag", "").strip('"') == md5)
        man.x("insert or replace into shards values (?,?,?,?,?,?)", (shard, len(recs), len(blob), md5, ok, None))
        if not ok:
            raise RuntimeError(f"{key}: etag mismatch")

    failed = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(one, s): s for s in todo}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                f.result()
            except Exception as e:
                failed.append(futs[f])
                print(f"shard {futs[f]} failed: {e}", flush=True)
            if i % 200 == 0 or i == len(todo):
                n, b, ok = man.q("select count(*), sum(bytes), sum(etag_ok) from shards")[0]
                print(f"[upload {i}/{len(todo)}] shards={n} gz_mb={(b or 0) / 1e6:.0f} etag_ok={ok} failed={len(failed)}", flush=True)
    return failed


def verify(args, man):
    from legal_ai.storage.r2_text_store import _signed_get
    turso_n = int(turso_rows("select count(*) n from case_texts")[0]["n"])
    lo, hi = [int(x) for x in turso_rows("select min(rowid) a, max(rowid) b from case_texts")[0].values()]
    spans = [(s, s + args.page) for s in range(lo, hi + 1, args.page)]
    want = {k: s for k, s in man.q("select key, sha from rows")}

    def turso_pass(span):
        bad = []
        for r in fetch_range(*span):
            r.pop("_rowid")
            key = case_text_key(r["case_id"])
            if want.get(key) != rec_sha(r):
                bad.append(key)
            else:
                man.x("update rows set verified_turso=1 where key=?", (key,))
        return bad

    def r2_pass(shard):
        raw = None
        for attempt in range(5):
            try:
                raw = _signed_get(f"{args.prefix.strip('/')}/{shard}.json.gz", timeout_s=60)
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(3 * 2 ** attempt)
        recs = json.loads(gzip.decompress(raw).decode("utf-8")) if raw else {}
        expected = {k for (k,) in man.q("select key from rows where shard=?", (shard,))}
        bad = [k for k in expected if k not in recs or rec_sha(recs[k]) != want[k]]
        extra = set(recs) - expected
        ok_keys = [(k,) for k in expected if k not in bad]
        man.x("update rows set verified_r2=1 where key=?", ok_keys, many=True)
        return bad + list(extra)

    problems = {"turso": [], "r2": []}
    with cf.ThreadPoolExecutor(args.workers) as ex:
        for bad in ex.map(turso_pass, spans):
            problems["turso"] += bad
        print(f"verify turso pass: mismatched={len(problems['turso'])}", flush=True)
        shards = [s for (s,) in man.q("select shard from shards where etag_ok=1")]
        for i, bad in enumerate(ex.map(r2_pass, shards), 1):
            problems["r2"] += bad
            if i % 500 == 0:
                print(f"[verify r2 {i}/{len(shards)}] bad={len(problems['r2'])}", flush=True)
    n, vt, vr = man.q("select count(*), sum(verified_turso), sum(verified_r2) from rows")[0]
    return {"turso_rows": turso_n, "manifest_rows": n, "verified_against_turso": vt, "verified_in_r2": vr,
            "turso_mismatch": problems["turso"][:20], "r2_bad": problems["r2"][:20],
            "ok": turso_n == n == vt == vr and not problems["turso"] and not problems["r2"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["stage", "upload", "verify"])
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--account", required=True)
    ap.add_argument("--prefix", default="case_texts/v1")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--page", type=int, default=400, help="rowid span per Turso read")
    args = ap.parse_args()
    os.makedirs(args.work_dir, exist_ok=True)
    man = Manifest(os.path.join(args.work_dir, "case_texts_manifest.db"))
    if args.mode == "stage":
        stage(args, man)
        n = man.q("select count(*) from rows")[0][0]
        turso_n = int(turso_rows("select count(*) n from case_texts")[0]["n"])
        print(json.dumps({"staged_rows": n, "turso_rows": turso_n}))
        sys.exit(0 if n == turso_n else 1)
    if args.mode == "upload":
        failed = upload(args, man)
        print(json.dumps({"failed": failed}))
        sys.exit(1 if failed else 0)
    report = verify(args, man)
    json.dump(report, open(os.path.join(args.work_dir, "case_texts_verify.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
