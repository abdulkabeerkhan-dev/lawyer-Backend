r"""
scripts/zilliz/ingest_from_supabase.py

Backfills judgments that exist in Supabase `full_judgments` but not in Zilliz
`judgments_v1`, using the same cleaning (build_registry.classify_case_content),
segmentation (segment.segment_case) and enrichment (enrich.MetadataEnricher)
as the main ingestion, so new chunks match the existing ones.

Talks to every service over HTTPS REST (no gRPC), so it runs anywhere:
  - Supabase Management API  (SUPABASE_ACCESS_TOKEN, project ref)  -> read rows
  - Voyage AI embeddings     (VOYAGE_API_KEY)                      -> voyage-4-large
  - Zilliz REST v2 upsert    (ZILLIZ_URI, ZILLIZ_TOKEN)

Idempotent and resumable: chunk_id is deterministic and writes use upsert;
finished case_keys are recorded in a local SQLite manifest.

Usage:
  python scripts/zilliz/ingest_from_supabase.py --missing missing.json --dry-run
  python scripts/zilliz/ingest_from_supabase.py --missing missing.json --spend-cap 15
"""
import argparse
import http.client
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.zilliz.build_registry import classify_case_content, normalize_journal  # noqa: E402
from scripts.zilliz.enrich import MetadataEnricher  # noqa: E402
from scripts.zilliz.segment import segment_case  # noqa: E402
from core.hierarchical_legal_chunker import count_tokens  # noqa: E402

EMBED_MODEL = "voyage-4-large"
PRICE_PER_M_TOKENS = 0.12
COLLECTION = "judgments_v1"

# Supabase court_name (free text) -> (court_code, court_level), matching build_registry.map_court codes.
_COURT_RULES: List[Tuple[str, str, int]] = [
    (r"federal\s+shariat", "FSC", 2),
    (r"supreme\s+appell", "GBSAC", 3),
    (r"supreme\s+court", "SC", 1),
    (r"lahore", "LHC", 3),
    (r"sindh|karachi", "SHC", 3),
    (r"peshawar", "PHC", 3),
    (r"balochistan|quetta", "BHC", 3),
    (r"islamabad", "IHC", 3),
    (r"azad|ajk", "AJKHC", 3),
]
_CIT_COURT_HINT = {"SC": ("SC", 1), "LAH": ("LHC", 3), "KAR": ("SHC", 3), "PESH": ("PHC", 3),
                   "QUETTA": ("BHC", 3), "ISL": ("IHC", 3), "FSC": ("FSC", 2)}
_CIT_RE = re.compile(r"\b(19\d\d|20\d\d)\b")


def map_court_name(court_name: str, citation: str, journal: str) -> Tuple[str, int]:
    s = (court_name or "").lower()
    for pat, code, level in _COURT_RULES:
        if re.search(pat, s):
            return code, level
    for tok in re.split(r"[\s.]+", (citation or "").upper()):
        if tok in _CIT_COURT_HINT:
            return _CIT_COURT_HINT[tok]
    if journal == "SCMR":
        return "SC", 1
    return "OTHER", 4


def parse_citation(raw: str) -> Optional[Dict[str, Any]]:
    """'PLD 1989 Pesh 64' / '2018 PLC(CS) 237' / '2024_SCMR_1567' -> year, journal, page."""
    if not raw or len(raw) > 60:
        return None
    s = raw.replace("_", " ").replace("PLC (CS)", "PLC(CS)")
    m_year = _CIT_RE.search(s)
    if not m_year:
        return None
    year = int(m_year.group(1))
    rest = (s[:m_year.start()] + " " + s[m_year.end():]).strip()
    m_page = re.search(r"(\d{1,5}[A-Za-z]?)\s*$", rest)
    if not m_page:
        return None
    page = m_page.group(1).upper()
    head = rest[:m_page.start()].strip()
    journal = ""
    for tok in [head] + head.split():
        j = normalize_journal(tok)
        if j and j.upper() == j and re.fullmatch(r"[A-Z()]+", j) and len(j) >= 3:
            journal = j
            break
    if not journal:
        return None
    if journal != "PLC(CS)":
        page = str(int(re.match(r"\d+", page).group(0))) + page.lstrip("0123456789")
    return {"year": year, "journal": journal, "page": page, "citation": f"{year} {journal} {page}"}


# ---------------------------------------------------------------- HTTP helpers
def _post(url: str, payload: Dict[str, Any], token: str, timeout: int = 120, retries: int = 5) -> Any:
    body = json.dumps(payload).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f"HTTP {e.code} from {url}: {e.read()[:300]!r}")
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            # URLError, TimeoutError, ConnectionResetError and IncompleteRead all retry.
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f"network error calling {url}: {e}")


class Supabase:
    def __init__(self, project_ref: str, token: str):
        self.url = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
        self.token = token

    def fetch_rows(self, ids: List[str]) -> List[Dict[str, Any]]:
        safe = [i for i in ids if re.fullmatch(r"[0-9a-f-]{36}", i)]
        in_list = ",".join(f"'{i}'" for i in safe)
        sql = ("select id::text id, case_id, neutral_citation, case_title, court_name, bench, "
               "full_text, headnote from full_judgments where id in (" + in_list + ")")
        rows = _post(self.url, {"query": sql, "read_only": True}, self.token, timeout=300)
        if not isinstance(rows, list):
            raise RuntimeError(f"Supabase query failed: {rows}")
        return rows


def voyage_embed(texts: List[str], token: str) -> Tuple[List[List[float]], int]:
    d = _post("https://api.voyageai.com/v1/embeddings",
              {"input": texts, "model": EMBED_MODEL, "input_type": "document"}, token)
    vecs = [x["embedding"] for x in sorted(d["data"], key=lambda x: x["index"])]
    return vecs, int(d.get("usage", {}).get("total_tokens", 0))


def zilliz_upsert(uri: str, token: str, records: List[Dict[str, Any]]) -> int:
    d = _post(uri.rstrip("/") + "/v2/vectordb/entities/upsert",
              {"collectionName": COLLECTION, "data": records}, token)
    if d.get("code") != 0:
        raise RuntimeError(f"Zilliz upsert failed: {d}")
    return int(d.get("data", {}).get("upsertCount", len(records)))


# ---------------------------------------------------------------- core
def build_case(row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    parsed = parse_citation(row.get("neutral_citation") or "") or parse_citation(row.get("case_id") or "")
    if not parsed:
        return None, "unparseable_citation"
    hn, jd, level, junk = classify_case_content(row.get("full_text") or "", row.get("headnote") or "")
    if junk:
        return None, "junk_text"
    code, court_level = map_court_name(row.get("court_name") or "", row.get("neutral_citation") or "", parsed["journal"])
    return {
        "case_key": f"{parsed['year']}_{parsed['journal']}_{code}_{parsed['page']}",
        "citation": parsed["citation"],
        "legacy_case_id": row.get("case_id") or f"{parsed['year']}_{parsed['journal']}_{parsed['page']}",
        "journal": parsed["journal"],
        "year": parsed["year"],
        "page": parsed["page"],
        "court_code": code,
        "court_level": court_level,
        "parties": (row.get("case_title") or "").strip(),
        "judge": (row.get("bench") or "").strip(),
        "content_level": level,
        "headnote_text": hn,
        "judgment_text": jd,
        "parallel_citations": [],
    }, "ok"


def to_record(c: Dict[str, Any], case: Dict[str, Any], vec: List[float], now_iso: str) -> Dict[str, Any]:
    return {
        "chunk_id": str(c["chunk_id"])[:128],
        "case_key": str(c["case_key"])[:64],
        "text": str(c["text"])[:65535],
        "dense": vec,
        "citation": str(c.get("citation") or case["citation"])[:128],
        "journal": str(c.get("journal") or case["journal"])[:32],
        "court_code": str(c.get("court_code") or case["court_code"])[:32],
        "year": int(c.get("year") or case["year"]),
        "court_level": int(c.get("court_level") or case["court_level"]),
        "cited_by_count": int(c.get("cited_by_count", 0)),
        "section": str(c.get("section", "headnote"))[:32],
        "content_level": str(c.get("content_level") or case["content_level"])[:32],
        "domain": str(c.get("domain", "civil"))[:32],
        "statutes": [str(s)[:64] for s in (c.get("statutes") or [])[:64] if s and isinstance(s, str)],
        "chunk_hash": str(c.get("chunk_hash") or hashlib.sha256(c["text"].encode()).hexdigest())[:64],
        "embed_model": EMBED_MODEL,
        "schema_version": "v1",
        "ingested_at": now_iso[:32],
    }


class Manifest:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("create table if not exists done (supabase_id text primary key, case_key text, "
                        "status text, chunks int, at text)")

    def is_done(self, sid: str) -> bool:
        return self.db.execute("select 1 from done where supabase_id=?", (sid,)).fetchone() is not None

    def mark(self, sid: str, case_key: str, status: str, chunks: int) -> None:
        self.db.execute("insert or replace into done values (?,?,?,?,?)",
                        (sid, case_key, status, chunks, datetime.utcnow().isoformat()))
        self.db.commit()


def process_batch(args, sb, batch_ids, manifest, enricher, stats, voyage_key, z_uri, z_tok) -> None:
    rows = sb.fetch_rows(batch_ids)
    pending: List[Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]] = []
    for row in rows:
        stats["rows"] += 1
        case, why = build_case(row)
        if not case:
            stats["skipped"][why] = stats["skipped"].get(why, 0) + 1
            if not args.dry_run:
                manifest.mark(row["id"], "", why, 0)
            continue
        chunks = segment_case(case, enricher)
        if not chunks:
            stats["skipped"]["no_chunks"] = stats["skipped"].get("no_chunks", 0) + 1
            continue
        stats["cases"] += 1
        stats["chunks"] += len(chunks)
        stats["tokens_est"] += sum(count_tokens(c["text"]) for c in chunks)
        stats["by_journal"][case["journal"]] = stats["by_journal"].get(case["journal"], 0) + 1
        stats["by_level"][case["content_level"]] = stats["by_level"].get(case["content_level"], 0) + 1
        pending.append((row, case, chunks))

    if not args.dry_run and pending:
        now_iso = datetime.utcnow().isoformat()
        flat = [(row, case, c) for row, case, chunks in pending for c in chunks]
        records = []
        for i in range(0, len(flat), 64):
            part = flat[i:i + 64]
            vecs, used = voyage_embed([c["text"] for _, _, c in part], voyage_key)
            stats["tokens_billed"] += used
            records += [to_record(c, case, v, now_iso) for (_, case, c), v in zip(part, vecs)]
        for i in range(0, len(records), 100):
            stats["upserted"] += zilliz_upsert(z_uri, z_tok, records[i:i + 100])
        for row, case, chunks in pending:
            manifest.mark(row["id"], case["case_key"], "done", len(chunks))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--missing", required=True, help="JSON list of {id,...} rows (Supabase full_judgments ids)")
    ap.add_argument("--work-dir", default=os.path.join(PROJECT_ROOT, "zilliz_backfill"))
    ap.add_argument("--project-ref", default=os.environ.get("SUPABASE_PROJECT_REF", "dexolywhperqvmnyqxpd"))
    ap.add_argument("--dry-run", action="store_true", help="Fetch + segment only; report tokens and cost")
    ap.add_argument("--spend-cap", type=float, default=15.0, help="Stop when embedding spend reaches this (USD)")
    ap.add_argument("--limit", type=int, default=None, help="Process at most N missing rows")
    ap.add_argument("--fetch-batch", type=int, default=100)
    args = ap.parse_args()

    sb = Supabase(args.project_ref, os.environ.get("SUPABASE_ACCESS_TOKEN", ""))
    voyage_key = os.environ.get("VOYAGE_API_KEY", "")
    z_uri, z_tok = os.environ.get("ZILLIZ_URI", ""), os.environ.get("ZILLIZ_TOKEN", "")
    if not args.dry_run and not (voyage_key and z_uri and z_tok):
        sys.exit("VOYAGE_API_KEY, ZILLIZ_URI and ZILLIZ_TOKEN are required unless --dry-run")

    missing = json.load(open(args.missing))
    ids = [m["id"] for m in missing if m.get("id")][: args.limit]
    manifest = Manifest(os.path.join(args.work_dir, "backfill_manifest.db"))
    enricher = MetadataEnricher()
    stats = {"rows": 0, "cases": 0, "chunks": 0, "tokens_est": 0, "tokens_billed": 0, "upserted": 0,
             "skipped": {}, "by_journal": {}, "by_level": {}}
    todo = ids if args.dry_run else [i for i in ids if not manifest.is_done(i)]
    print(f"{len(ids)} missing rows, {len(todo)} to process (dry_run={args.dry_run})", flush=True)

    failed_batches = 0
    for b in range(0, len(todo), args.fetch_batch):
        try:
            process_batch(args, sb, todo[b:b + args.fetch_batch], manifest, enricher, stats,
                          voyage_key, z_uri, z_tok)
        except RuntimeError as e:
            # Rows in this batch stay unmarked, so the next run retries them.
            failed_batches += 1
            print(f"[{b}] batch failed after retries, will retry on next run: {e}", flush=True)
        spend = stats["tokens_billed"] / 1e6 * PRICE_PER_M_TOKENS
        est = stats["tokens_est"] / 1e6 * PRICE_PER_M_TOKENS
        print(f"[{min(b + args.fetch_batch, len(todo))}/{len(todo)}] cases={stats['cases']} chunks={stats['chunks']} "
              f"est_cost=${est:.2f} spent=${spend:.2f} upserted={stats['upserted']} skipped={stats['skipped']} "
              f"failed_batches={failed_batches}", flush=True)
        if not args.dry_run and spend >= args.spend_cap:
            print(f"Spend cap ${args.spend_cap} reached; stopping. Re-run to resume.", flush=True)
            break
    stats["failed_batches"] = failed_batches

    stats["est_cost_usd"] = round(stats["tokens_est"] / 1e6 * PRICE_PER_M_TOKENS, 2)
    stats["spent_usd"] = round(stats["tokens_billed"] / 1e6 * PRICE_PER_M_TOKENS, 2)
    os.makedirs(args.work_dir, exist_ok=True)
    with open(os.path.join(args.work_dir, "backfill_report.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
