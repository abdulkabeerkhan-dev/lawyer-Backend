r"""
scripts/zilliz/ingest_from_r2_texts.py

Indexes judgment text that Zilliz `judgments_v1` does not have yet, reading the text from the
local copies of the R2 archives (full_judgments.full_text is empty since the text moved to R2):
  - texts/v1 copy       (one JSON per Supabase row id: full_text, headnote)
  - case_texts/v1 copy  (the old Turso case_texts table, keyed by case_id)

Two kinds of work, both from lists written by the audit:
  --missing  rows whose case is not in Zilliz at all        -> every chunk is indexed
  --hn-only  cases Zilliz holds only as headnote chunks      -> body chunks are added under the
                                                                 case's EXISTING case_key, so the
                                                                 case is not duplicated

Same cleaning, segmentation, enrichment, embedding model and record shape as
ingest_from_supabase.py. Idempotent (deterministic chunk ids + upsert) and resumable (SQLite
manifest). Rows whose stored text carries a different citation are never indexed.

Usage:
  python scripts/zilliz/ingest_from_r2_texts.py --texts DIR --case-texts DIR \
      --missing gap_missing.json --hn-only gap_hn_only.json --dry-run
"""
import argparse
import glob
import gzip
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.zilliz.enrich import MetadataEnricher  # noqa: E402
from scripts.zilliz.segment import segment_case  # noqa: E402
from scripts.zilliz.ingest_from_supabase import (  # noqa: E402
    PRICE_PER_M_TOKENS, Manifest, Supabase, build_case, to_record, voyage_embed, zilliz_upsert, _post)
from core.hierarchical_legal_chunker import count_tokens  # noqa: E402
from legal_ai.verification.citation_keys import citation_key  # noqa: E402

BLOCKED = {"rejected", "quarantined", "restricted"}


def load_texts(texts_dir: str, case_texts_dir: str, ids: set, case_ids: set) -> Tuple[Dict, Dict]:
    local, turso = {}, {}
    for f in glob.glob(os.path.join(texts_dir, "*.json.gz")):
        with gzip.open(f) as fh:
            for k, v in json.load(fh).items():
                if k in ids:
                    local[k] = v
    for f in glob.glob(os.path.join(case_texts_dir, "*.jsonl")):
        with open(f) as fh:
            for line in fh:
                x = json.loads(line)
                if x["k"] in case_ids:
                    turso[x["k"]] = x["r"]
    return local, turso


def fetch_meta(sb: Supabase, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for i in range(0, len(ids), 2000):
        part = ",".join(f"'{x}'" for x in ids[i:i + 2000])
        rows = _post(sb.url, {"query": "select id::text id, case_id, neutral_citation, case_title, court_name, bench, "
                                       f"retrieval_status from full_judgments where id in ({part})",
                              "read_only": True}, sb.token, timeout=300)
        out.update({r["id"]: r for r in rows})
    return out


def existing_keys(z_uri: str, z_tok: str, keys: List[str]) -> set:
    found = set()
    for i in range(0, len(keys), 200):
        part = keys[i:i + 200]
        d = _post(z_uri.rstrip("/") + "/v2/vectordb/entities/query",
                  {"collectionName": "judgments_v1", "filter": "case_key in " + json.dumps(part),
                   "outputFields": ["case_key"], "limit": 16000}, z_tok)
        found.update(x["case_key"] for x in d.get("data", []))
    return found


def plan_case(item: Dict[str, Any], meta: Dict, local: Dict, turso: Dict, zilliz_keys: set,
              enricher: MetadataEnricher) -> Tuple[Optional[Tuple[Dict, List[Dict]]], str]:
    m = meta.get(item["id"])
    if not m:
        return None, "row_gone"
    if (m.get("retrieval_status") or "") in BLOCKED:
        return None, "blocked_status"
    lt, tt = local.get(item["id"]) or {}, turso.get(m.get("case_id")) or {}
    body = max([lt.get("full_text") or "", tt.get("full_text") or ""], key=len)
    row = dict(m, full_text=body, headnote=lt.get("headnote") or "")
    # never index text that carries another case's citation
    own = citation_key(m.get("neutral_citation") or "") or citation_key(m.get("case_id") or "")
    head = citation_key(body[:160]) if body else None
    if head and own and head != own:
        return None, "text_citation_mismatch"
    case, why = build_case(row)
    if not case:
        return None, why
    hn_only = item.get("kind") == "hn_only"
    if hn_only:
        keys = item.get("zkeys") or []
        if len(keys) != 1:
            return None, "ambiguous_existing_key"
        if case["content_level"] != "full_judgment":
            return None, "no_judgment_body"
        case["case_key"] = keys[0]
        case["court_code"] = keys[0].split("_")[2] if keys[0].count("_") >= 3 else case["court_code"]
    elif case["case_key"] in zilliz_keys:
        return None, "key_already_in_zilliz"
    chunks = segment_case(case, enricher)
    if hn_only:
        chunks = [c for c in chunks if c.get("section") != "headnote"]
    if not chunks:
        return None, "no_chunks"
    return (case, chunks), "ok"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--case-texts", required=True)
    ap.add_argument("--missing")
    ap.add_argument("--hn-only")
    ap.add_argument("--work-dir", default=os.path.join(PROJECT_ROOT, "zilliz_backfill_r2"))
    ap.add_argument("--project-ref", default=os.environ.get("SUPABASE_PROJECT_REF", "zrfemmnklhrzvfsqrhqs"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--spend-cap", type=float, default=20.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    items: List[Dict[str, Any]] = []
    if args.missing:
        items += [dict(x, kind="missing") for x in json.load(open(args.missing))]
    if args.hn_only:
        items += [dict(x, kind="hn_only") for x in json.load(open(args.hn_only))]
    items = items[: args.limit]
    manifest = Manifest(os.path.join(args.work_dir, "manifest.db"))
    todo = items if args.dry_run else [x for x in items if not manifest.is_done(x["id"])]
    print(f"{len(items)} items, {len(todo)} to process (dry_run={args.dry_run})", flush=True)

    sb = Supabase(args.project_ref, os.environ.get("SUPABASE_ACCESS_TOKEN", "proxy-injected"))
    voyage_key = os.environ.get("VOYAGE_API_KEY", "proxy-injected")
    z_uri = os.environ.get("ZILLIZ_URI", "https://in03-c674ca53157f642.serverless.gcp-us-west1.cloud.zilliz.com")
    z_tok = os.environ.get("ZILLIZ_TOKEN", "proxy-injected")

    meta = fetch_meta(sb, [x["id"] for x in todo])
    local, turso = load_texts(args.texts, args.case_texts, {x["id"] for x in todo},
                              {m.get("case_id") for m in meta.values()})
    enricher = MetadataEnricher()
    stats = {"items": 0, "cases": 0, "chunks": 0, "tokens_est": 0, "tokens_billed": 0, "upserted": 0,
             "skipped": {}, "by_kind": {}}
    planned = []
    for x in todo:
        stats["items"] += 1
        res, why = plan_case(x, meta, local, turso, set(), enricher)
        if not res:
            stats["skipped"][why] = stats["skipped"].get(why, 0) + 1
            if not args.dry_run and why not in ("row_gone",):
                manifest.mark(x["id"], "", why, 0)
            continue
        case, chunks = res
        planned.append((x, case, chunks))
    # a "missing" case whose key Zilliz already has is a court/key clash, not a gap: leave it
    clash = existing_keys(z_uri, z_tok, [c["case_key"] for x, c, _ in planned if x["kind"] == "missing"])
    kept = []
    for x, case, chunks in planned:
        if x["kind"] == "missing" and case["case_key"] in clash:
            stats["skipped"]["key_already_in_zilliz"] = stats["skipped"].get("key_already_in_zilliz", 0) + 1
            continue
        kept.append((x, case, chunks))
        stats["cases"] += 1
        stats["chunks"] += len(chunks)
        stats["tokens_est"] += sum(count_tokens(c["text"]) for c in chunks)
        stats["by_kind"][x["kind"]] = stats["by_kind"].get(x["kind"], 0) + 1
    est = stats["tokens_est"] / 1e6 * PRICE_PER_M_TOKENS
    print(f"planned cases={stats['cases']} chunks={stats['chunks']} est_cost=${est:.2f} skipped={stats['skipped']}",
          flush=True)
    if args.dry_run:
        print(json.dumps(stats, indent=1))
        return

    lock = threading.Lock()
    stop = threading.Event()

    def work(group):
        if stop.is_set():
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        flat = [(x, case, c) for x, case, chunks in group for c in chunks]
        records = []
        for i in range(0, len(flat), 64):
            part = flat[i:i + 64]
            vecs, used = voyage_embed([c["text"] for _, _, c in part], voyage_key)
            with lock:
                stats["tokens_billed"] += used
            records += [to_record(c, case, v, now_iso) for (_, case, c), v in zip(part, vecs)]
        n = 0
        for i in range(0, len(records), 100):
            n += zilliz_upsert(z_uri, z_tok, records[i:i + 100])
        with lock:
            stats["upserted"] += n
            for x, case, chunks in group:
                manifest.mark(x["id"], case["case_key"], "done", len(chunks))
            if stats["tokens_billed"] / 1e6 * PRICE_PER_M_TOKENS >= args.spend_cap:
                stop.set()

    groups = [kept[i:i + 20] for i in range(0, len(kept), 20)]
    failed = 0
    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(work, g) for g in groups]
        for i, f in enumerate(futs, 1):
            try:
                f.result()
            except Exception as e:  # rows stay unmarked and are retried next run
                failed += 1
                print(f"group {i} failed: {str(e)[:200]}", flush=True)
            if i % 50 == 0:
                print(f"[{i}/{len(groups)}] upserted={stats['upserted']} "
                      f"spent=${stats['tokens_billed'] / 1e6 * PRICE_PER_M_TOKENS:.2f} failed={failed}", flush=True)
    stats["failed_groups"] = failed
    stats["spent_usd"] = round(stats["tokens_billed"] / 1e6 * PRICE_PER_M_TOKENS, 2)
    if stop.is_set():
        print(f"Spend cap ${args.spend_cap} reached; re-run to resume.", flush=True)
    os.makedirs(args.work_dir, exist_ok=True)
    json.dump(stats, open(os.path.join(args.work_dir, "report.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
