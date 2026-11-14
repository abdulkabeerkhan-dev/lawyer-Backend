r"""
scripts/zilliz/load_cases_v2.py

Loads canonical case registry from I:\zilliz_work\registry.jsonl into Turso table `cases_v2`
and creates an FTS5 full-text index `cases_v2_fts`.
Adheres strictly to docs/antigravity/RULES.md (Rules 4, 19, 22) and docs/ZILLIZ_MIGRATION_PLAN.md §11.

Guarantees:
1. Does NOT touch old Turso tables: case_texts, case_texts_fts, case_pdfs, statute_provisions.
2. Creates table cases_v2 with primary key case_key.
3. Checkpointed and resumable (I:\zilliz_work\turso_cases_v2_checkpoint.json).
4. Supports --dry-run, --limit-cases, and --case-keys.
"""

import os
import sys
import time
import json
import logging
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

# Ensure project root in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

LOG_DIR = r"I:\zilliz_work\logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "load_cases_v2.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("load_cases_v2")

CHECKPOINT_PATH = r"I:\zilliz_work\turso_cases_v2_checkpoint.json"


def get_turso_config():
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    raw_url = os.environ.get("TURSO_DATABASE_URL_PIPELINE") or os.environ.get("TURSO_DATABASE_URL", "")
    if raw_url.startswith("libsql://"):
        raw_url = raw_url.replace("libsql://", "https://")
    if raw_url and not raw_url.endswith("/v2/pipeline"):
        raw_url = raw_url.rstrip("/") + "/v2/pipeline"

    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not raw_url or not token:
        raise ValueError("TURSO_DATABASE_URL or TURSO_AUTH_TOKEN missing in .env")
    return raw_url, token


def execute_pipeline(stmts: List[Dict[str, Any]], timeout: int = 15, max_retries: int = 5) -> bool:
    """Execute raw pipeline statements against Turso HTTP API."""
    url, token = get_turso_config()
    requests = []
    for s in stmts:
        stmt_obj = {"sql": s["sql"]}
        if "args" in s and s["args"]:
            clean_args = []
            for a in s["args"]:
                arg_copy = dict(a)
                if arg_copy.get("type") == "integer" and not isinstance(arg_copy.get("value"), str) and arg_copy.get("value") is not None:
                    arg_copy["value"] = str(arg_copy["value"])
                clean_args.append(arg_copy)
            stmt_obj["args"] = clean_args
        requests.append({"type": "execute", "stmt": stmt_obj})

    payload = json.dumps({"requests": requests}).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("results", []):
                    if item.get("type") == "error":
                        raise RuntimeError(f"Turso SQL error: {item.get('error', {}).get('message')}")
                return True
        except Exception as e:
            logger.warning(f"Turso pipeline attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            time.sleep(2 ** attempt)
    return False


def setup_cases_v2_schema(dry_run: bool = False):
    """Create cases_v2 table, indexes, and FTS5 virtual table."""
    logger.info("Setting up cases_v2 table schema in Turso...")
    stmts = [
        {
            "sql": """
            CREATE TABLE IF NOT EXISTS cases_v2 (
                case_key TEXT PRIMARY KEY,
                citation TEXT NOT NULL,
                journal TEXT,
                year INTEGER,
                court_code TEXT,
                court_name TEXT,
                court_level INTEGER,
                page INTEGER,
                parties TEXT,
                judge TEXT,
                content_level TEXT,
                headnote_text TEXT,
                judgment_text TEXT,
                parallel_citations TEXT,
                statutes TEXT,
                domain TEXT,
                cited_by_count INTEGER DEFAULT 0,
                legacy_case_id TEXT,
                text_possibly_truncated INTEGER DEFAULT 0,
                created_at TEXT
            );
            """
        },
        {"sql": "CREATE INDEX IF NOT EXISTS idx_cases_v2_citation ON cases_v2(citation);"},
        {"sql": "CREATE INDEX IF NOT EXISTS idx_cases_v2_year_court ON cases_v2(year, court_code);"},
        {"sql": "CREATE INDEX IF NOT EXISTS idx_cases_v2_journal ON cases_v2(journal);"},
        {"sql": "CREATE INDEX IF NOT EXISTS idx_cases_v2_domain ON cases_v2(domain);"},
        {
            "sql": """
            CREATE VIRTUAL TABLE IF NOT EXISTS cases_v2_fts USING fts5(
                case_key UNINDEXED,
                citation,
                parties,
                judge,
                court_name,
                statutes,
                headnote_text,
                judgment_text,
                content='cases_v2',
                content_rowid='rowid'
            );
            """
        },
        {
            "sql": """
            CREATE TRIGGER IF NOT EXISTS cases_v2_ai AFTER INSERT ON cases_v2 BEGIN
              INSERT INTO cases_v2_fts(rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES (new.rowid, new.case_key, new.citation, new.parties, new.judge, new.court_name, new.statutes, new.headnote_text, new.judgment_text);
            END;
            """
        },
        {
            "sql": """
            CREATE TRIGGER IF NOT EXISTS cases_v2_ad AFTER DELETE ON cases_v2 BEGIN
              INSERT INTO cases_v2_fts(cases_v2_fts, rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES('delete', old.rowid, old.case_key, old.citation, old.parties, old.judge, old.court_name, old.statutes, old.headnote_text, old.judgment_text);
            END;
            """
        },
        {
            "sql": """
            CREATE TRIGGER IF NOT EXISTS cases_v2_au AFTER UPDATE ON cases_v2 BEGIN
              INSERT INTO cases_v2_fts(cases_v2_fts, rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES('delete', old.rowid, old.case_key, old.citation, old.parties, old.judge, old.court_name, old.statutes, old.headnote_text, old.judgment_text);
              INSERT INTO cases_v2_fts(rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES (new.rowid, new.case_key, new.citation, new.parties, new.judge, new.court_name, new.statutes, new.headnote_text, new.judgment_text);
            END;
            """
        },
    ]

    if dry_run:
        logger.info("[DRY-RUN] Would create cases_v2 table, indexes, and FTS5 triggers.")
        return

    execute_pipeline(stmts)
    logger.info("cases_v2 table and FTS5 index setup completed successfully!")


def load_checkpoint() -> Dict[str, Any]:
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read checkpoint: {e}")
    return {"loaded_count": 0, "last_case_key": None}


def save_checkpoint(data: Dict[str, Any]):
    try:
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save checkpoint: {e}")


def load_registry_into_cases_v2(
    registry_file: str = r"I:\zilliz_work\registry.jsonl",
    batch_size: int = 50,
    limit_cases: Optional[int] = None,
    case_keys_filter: Optional[Set[str]] = None,
    dry_run: bool = False,
):
    """Stream registry cases and batch insert into Turso cases_v2."""
    setup_cases_v2_schema(dry_run=dry_run)

    cp = load_checkpoint()
    loaded_count = cp.get("loaded_count", 0)
    last_case_key = cp.get("last_case_key")

    logger.info(f"Starting registry load from {registry_file}")
    logger.info(f"Resuming from checkpoint: {loaded_count} cases previously loaded (last key: {last_case_key})")

    sql_insert = """
    INSERT OR REPLACE INTO cases_v2 (
        case_key, citation, journal, year, court_code, court_name, court_level, page,
        parties, judge, content_level, headnote_text, judgment_text,
        parallel_citations, statutes, domain, cited_by_count, legacy_case_id,
        text_possibly_truncated, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    stmts_batch = []
    cases_batch_keys = []
    total_processed = 0
    now_iso = datetime.utcnow().isoformat()

    with open(registry_file, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ck = rec["case_key"]

            if case_keys_filter and ck not in case_keys_filter:
                continue

            # Checkpoint resumption
            if last_case_key is not None:
                if ck == last_case_key:
                    last_case_key = None  # reached resume point
                continue

            year_val = rec.get("year")
            page_val = rec.get("page")
            year_arg = {"type": "integer", "value": str(year_val)} if year_val is not None else {"type": "null"}
            page_arg = {"type": "integer", "value": str(page_val)} if page_val is not None else {"type": "null"}
            court_level_arg = {"type": "integer", "value": str(rec.get("court_level", 3))}
            cited_by_arg = {"type": "integer", "value": str(rec.get("cited_by_count", 0))}
            trunc_arg = {"type": "integer", "value": "1" if rec.get("text_possibly_truncated") else "0"}

            args = [
                {"type": "text", "value": str(ck)},
                {"type": "text", "value": str(rec.get("citation", ""))},
                {"type": "text", "value": str(rec.get("journal", ""))},
                year_arg,
                {"type": "text", "value": str(rec.get("court_code", ""))},
                {"type": "text", "value": str(rec.get("court_name", ""))},
                court_level_arg,
                page_arg,
                {"type": "text", "value": str(rec.get("parties", ""))},
                {"type": "text", "value": str(rec.get("judge", ""))},
                {"type": "text", "value": str(rec.get("content_level", ""))},
                {"type": "text", "value": str(rec.get("headnote_text", ""))},
                {"type": "text", "value": str(rec.get("judgment_text", ""))},
                {"type": "text", "value": json.dumps(rec.get("parallel_citations", []))},
                {"type": "text", "value": json.dumps(rec.get("statutes", []))},
                {"type": "text", "value": str(rec.get("domain", ""))},
                cited_by_arg,
                {"type": "text", "value": str(rec.get("legacy_case_id", ""))},
                trunc_arg,
                {"type": "text", "value": now_iso},
            ]

            stmts_batch.append({"sql": sql_insert, "args": args})
            cases_batch_keys.append(ck)
            total_processed += 1

            if limit_cases and total_processed >= limit_cases:
                break

            if len(stmts_batch) >= batch_size:
                if not dry_run:
                    execute_pipeline(stmts_batch)
                    loaded_count += len(stmts_batch)
                    save_checkpoint({"loaded_count": loaded_count, "last_case_key": cases_batch_keys[-1]})
                logger.info(f"Loaded {total_processed} cases into cases_v2 (last: {cases_batch_keys[-1]})")
                stmts_batch = []
                cases_batch_keys = []

        if stmts_batch:
            if not dry_run:
                execute_pipeline(stmts_batch)
                loaded_count += len(stmts_batch)
                save_checkpoint({"loaded_count": loaded_count, "last_case_key": cases_batch_keys[-1]})
            logger.info(f"Loaded final {len(stmts_batch)} cases. Total cases processed: {total_processed}")

    logger.info("Turso cases_v2 load complete!")


def main():
    parser = argparse.ArgumentParser(description="Load cases into Turso cases_v2")
    parser.add_argument("--registry", default=r"I:\zilliz_work\registry.jsonl", help="Registry JSONL")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size per pipeline call")
    parser.add_argument("--limit-cases", type=int, default=None, help="Limit cases")
    parser.add_argument("--case-keys", type=str, default=None, help="Comma-separated case keys")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without DB writes")

    args = parser.parse_args()
    filter_keys = set(args.case_keys.split(",")) if args.case_keys else None

    load_registry_into_cases_v2(
        registry_file=args.registry,
        batch_size=args.batch_size,
        limit_cases=args.limit_cases,
        case_keys_filter=filter_keys,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
