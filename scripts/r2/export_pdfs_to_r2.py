#!/usr/bin/env python3
"""
Copy the original judgment PDFs (Turso case_pdfs, 137k files) into Cloudflare R2 as
bundles, so the copy needs ~2,800 uploads instead of 137k (the Cloudflare REST API
allows ~4 requests/s):

    {prefix}/{JOURNAL}/{YEAR}/{PAGE // 250}.zip     (default prefix "pdfs/v1")
      -> uncompressed ZIP; member "{PAGE}.pdf" is the original PDF, byte for byte.

upload  reads each bundle's PDFs from Turso, writes the ZIP, uploads it, and checks the
        ETag R2 returns equals the MD5 of the ZIP. Per-PDF MD5s go to the manifest.
verify  downloads every bundle back over the S3 API (R2_* keys, read-only is enough),
        opens it, and checks every PDF's MD5 against the manifest and the per-bundle
        row count against Turso.

Read-only on Turso. Resumable (SQLite manifest in --work-dir).

    TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... CLOUDFLARE_API_TOKEN=... \\
    python3 scripts/r2/export_pdfs_to_r2.py --bucket section-judgment-texts --account <id> --work-dir /tmp/r2pdf upload
    R2_ACCOUNT_ID=... R2_BUCKET=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... ... verify
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import hashlib
import io
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..")))

from core.case_store import PDF_BUNDLE_PAGES, pdf_bundle_key  # noqa: E402

CF = "https://api.cloudflare.com/client/v4"


def _http(url, method="GET", body=None, headers=None, timeout=180):
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


def turso_query(sql, args=()):
    url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
    typed = [{"type": "integer", "value": str(a)} if isinstance(a, int) else {"type": "text", "value": str(a)}
             for a in args]
    body = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql, "args": typed}}, {"type": "close"}]}).encode()
    out = _http(url, "POST", body, {"Authorization": f"Bearer {os.environ['TURSO_AUTH_TOKEN']}",
                                    "Content-Type": "application/json"}, timeout=240)
    res = out["results"][0]
    if res["type"] != "ok":
        raise RuntimeError(f"Turso error: {str(res)[:300]}")
    cols = [c["name"] for c in res["response"]["result"]["cols"]]
    return [{c: v.get("value") for c, v in zip(cols, row)} for row in res["response"]["result"]["rows"]]


class Manifest:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""
            create table if not exists bundles (key text primary key, journal text, year int, bucket int,
                n int, bytes int, md5 text, etag_ok int, uploaded_at text, verified_at text, verify_note text);
            create table if not exists bundle_pdfs (pdf_id text primary key, key text, page int, bytes int,
                md5 text, note text);
        """)
        self.db.commit()

    def uploaded(self, b, pdfs):
        with self.lock:
            self.db.executemany("insert or replace into bundle_pdfs values (?,?,?,?,?,?)", pdfs)
            self.db.execute("insert or replace into bundles values (?,?,?,?,?,?,?,?,datetime('now'),null,null)", b)
            self.db.commit()

    def verified(self, key, note):
        with self.lock:
            self.db.execute("update bundles set verified_at=datetime('now'), verify_note=? where key=?", (note, key))
            self.db.commit()

    def done_keys(self):
        return {r[0] for r in self.db.execute("select key from bundles where etag_ok=1")}

    def totals(self):
        return self.db.execute("select count(*), sum(n), sum(bytes), sum(etag_ok), "
                               "sum(case when verify_note like 'ok%' then 1 else 0 end), "
                               "sum(case when verify_note is not null and verify_note not like 'ok%' then 1 else 0 end) "
                               "from bundles").fetchone()


def build_bundle(rows):
    buf = io.BytesIO()
    pdfs = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for r in sorted(rows, key=lambda r: int(r["page"])):
            raw = base64.b64decode(r["pdf_base64"])
            note = "" if raw.startswith(b"%PDF") else "not_pdf_header"
            zf.writestr(f"{int(r['page'])}.pdf", raw)
            pdfs.append((r["pdf_id"], int(r["page"]), len(raw), hashlib.md5(raw).hexdigest(), note))
    return buf.getvalue(), pdfs


def upload_bundle(args, man, journal, year, bucket):
    lo, hi = bucket * PDF_BUNDLE_PAGES, (bucket + 1) * PDF_BUNDLE_PAGES
    rows = turso_query("select pdf_id, page, pdf_base64 from case_pdfs where journal = ? and year = ? "
                       "and page >= ? and page < ?", (journal, int(year), lo, hi))
    blob, pdfs = build_bundle(rows)
    md5 = hashlib.md5(blob).hexdigest()
    key = pdf_bundle_key(journal, year, lo, args.prefix)
    url = f"{CF}/accounts/{args.account}/r2/buckets/{args.bucket}/objects/{urllib.parse.quote(key)}"
    res = _http(url, "PUT", blob, {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}",
                                   "Content-Type": "application/zip"})
    etag = ((res or {}).get("result") or {}).get("etag", "").strip('"')
    ok = int(etag == md5)
    man.uploaded((key, journal, int(year), bucket, len(rows), len(blob), md5, ok),
                 [(p[0], key, p[1], p[2], p[3], p[4]) for p in pdfs])
    if not ok:
        raise RuntimeError(f"{key}: etag {etag} != md5 {md5}")
    return len(rows)


def verify_bundle(args, man, key, expected_n):
    from legal_ai.storage.r2_text_store import _signed_get
    raw = None
    for attempt in range(5):
        try:
            raw = _signed_get(key, timeout_s=60)
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(3 * 2 ** attempt)
    if raw is None:
        man.verified(key, "MISSING in R2")
        return False
    want = {page: md5 for page, md5 in man.db.execute("select page, md5 from bundle_pdfs where key=?", (key,))}
    bad, seen = [], 0
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            page = int(name.split(".")[0])
            seen += 1
            if hashlib.md5(zf.read(name)).hexdigest() != want.get(page):
                bad.append(page)
    ok = not bad and seen == len(want) == expected_n
    man.verified(key, f"ok {seen}" if ok else f"MISMATCH bad={bad[:10]} seen={seen} manifest={len(want)} turso={expected_n}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["upload", "verify"])
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--account", required=True)
    ap.add_argument("--prefix", default="pdfs/v1")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(args.work_dir, exist_ok=True)
    man = Manifest(os.path.join(args.work_dir, "r2_pdf_bundles.db"))

    groups = turso_query(f"select journal, year, page / {PDF_BUNDLE_PAGES} as b, count(*) as n "
                         f"from case_pdfs group by 1, 2, 3 order by 1, 2, 3")
    total_pdfs = sum(int(g["n"]) for g in groups)
    expected = {pdf_bundle_key(g["journal"], g["year"], int(g["b"]) * PDF_BUNDLE_PAGES, args.prefix): int(g["n"])
                for g in groups}

    if args.mode == "upload":
        done = man.done_keys()
        todo = [g for g in groups
                if pdf_bundle_key(g["journal"], g["year"], int(g["b"]) * PDF_BUNDLE_PAGES, args.prefix) not in done]
        fn = lambda g: upload_bundle(args, man, g["journal"], g["year"], int(g["b"]))
        label = lambda g: f"{g['journal']}/{g['year']}/{g['b']}"
    else:
        todo = [k for k, in man.db.execute("select key from bundles where etag_ok=1 and "
                                           "(verify_note is null or verify_note not like 'ok%')")]
        fn = lambda k: verify_bundle(args, man, k, expected.get(k, -1))
        label = lambda k: k
    if args.limit:
        todo = todo[: args.limit]
    print(f"{total_pdfs} PDFs in {len(groups)} bundles; {len(todo)} to {args.mode}", flush=True)

    failed = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(fn, t): t for t in todo}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                f.result()
            except Exception as e:
                failed.append(label(futs[f]))
                print(f"{label(futs[f])} failed: {e}", flush=True)
            if i % 100 == 0 or i == len(todo):
                n, pdfs, nbytes, eok, vok, vbad = man.totals()
                print(f"[{i}/{len(todo)}] bundles={n}/{len(groups)} pdfs={pdfs}/{total_pdfs} "
                      f"mb={(nbytes or 0) / 1e6:.0f} etag_ok={eok} verified_ok={vok} verify_bad={vbad} "
                      f"failed={len(failed)}", flush=True)

    n, pdfs, nbytes, eok, vok, vbad = man.totals()
    missing = sorted(set(expected) - man.done_keys())
    report = {"mode": args.mode, "turso_pdfs": total_pdfs, "bundles_expected": len(groups), "bundles_uploaded": n,
              "pdfs_uploaded": pdfs, "bytes": nbytes, "etag_ok": eok, "verified_ok": vok, "verify_bad": vbad,
              "failed": failed, "missing_bundles": missing[:50], "bucket": args.bucket, "prefix": args.prefix}
    json.dump(report, open(os.path.join(args.work_dir, f"r2_pdf_{args.mode}_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))
    complete = (eok == len(groups) and pdfs == total_pdfs and not failed
                and (args.mode == "upload" or vok == len(groups)))
    sys.exit(0 if complete else 1)


if __name__ == "__main__":
    main()
