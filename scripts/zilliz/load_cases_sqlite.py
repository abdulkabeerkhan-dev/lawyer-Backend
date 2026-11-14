r"""
scripts/zilliz/load_cases_sqlite.py

High-performance local SQLite loader for Pakistani case law registry.
Creates `cases_v2` table, B-tree indexes, and FTS5 full-text index `cases_v2_fts`.
Zero remote database dependencies; manages local disk space efficiently.
"""

import os
import sys
import time
import json
import sqlite3
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

LOG_DIR = r"I:\zilliz_work\logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "load_cases_sqlite.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("load_cases_sqlite")


def init_sqlite_schema(conn: sqlite3.Connection):
    """Initialize cases_v2 table, indexes, and FTS5 search index."""
    logger.info("Initializing SQLite cases_v2 and FTS5 schema...")
    with conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -64000;")  # 64MB cache

        conn.execute("""
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
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_v2_citation ON cases_v2(citation);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_v2_year_court ON cases_v2(year, court_code);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_v2_journal ON cases_v2(journal);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_v2_domain ON cases_v2(domain);")

        conn.execute("""
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
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cases_v2_ai AFTER INSERT ON cases_v2 BEGIN
              INSERT INTO cases_v2_fts(rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES (new.rowid, new.case_key, new.citation, new.parties, new.judge, new.court_name, new.statutes, new.headnote_text, new.judgment_text);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cases_v2_ad AFTER DELETE ON cases_v2 BEGIN
              INSERT INTO cases_v2_fts(cases_v2_fts, rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES('delete', old.rowid, old.case_key, old.citation, old.parties, old.judge, old.court_name, old.statutes, old.headnote_text, old.judgment_text);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cases_v2_au AFTER UPDATE ON cases_v2 BEGIN
              INSERT INTO cases_v2_fts(cases_v2_fts, rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES('delete', old.rowid, old.case_key, old.citation, old.parties, old.judge, old.court_name, old.statutes, old.headnote_text, old.judgment_text);
              INSERT INTO cases_v2_fts(rowid, case_key, citation, parties, judge, court_name, statutes, headnote_text, judgment_text)
              VALUES (new.rowid, new.case_key, new.citation, new.parties, new.judge, new.court_name, new.statutes, new.headnote_text, new.judgment_text);
            END;
        """)


def load_registry_to_sqlite(
    registry_file: str = r"I:\zilliz_work\registry.jsonl",
    db_path: str = r"d:\lawyer-Backend\data\cases_v2.db",
    batch_size: int = 5000,
    limit_cases: Optional[int] = None,
):
    """Load registry into local SQLite database."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    logger.info(f"Target SQLite database: {db_path}")

    conn = sqlite3.connect(db_path)
    init_sqlite_schema(conn)

    sql_insert = """
    INSERT OR REPLACE INTO cases_v2 (
        case_key, citation, journal, year, court_code, court_name, court_level, page,
        parties, judge, content_level, headnote_text, judgment_text,
        parallel_citations, statutes, domain, cited_by_count, legacy_case_id,
        text_possibly_truncated, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    now_iso = datetime.utcnow().isoformat()
    batch = []
    total_processed = 0
    t0 = time.time()

    logger.info(f"Streaming cases from {registry_file}...")

    with open(registry_file, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ck = rec["case_key"]

            row = (
                ck,
                rec.get("citation", ""),
                rec.get("journal", ""),
                rec.get("year"),
                rec.get("court_code", ""),
                rec.get("court_name", ""),
                rec.get("court_level", 3),
                rec.get("page"),
                rec.get("parties", ""),
                rec.get("judge", ""),
                rec.get("content_level", ""),
                rec.get("headnote_text", ""),
                rec.get("judgment_text", ""),
                json.dumps(rec.get("parallel_citations", [])),
                json.dumps(rec.get("statutes", [])),
                rec.get("domain", ""),
                rec.get("cited_by_count", 0),
                rec.get("legacy_case_id", ""),
                1 if rec.get("text_possibly_truncated") else 0,
                now_iso,
            )
            batch.append(row)
            total_processed += 1

            if len(batch) >= batch_size:
                with conn:
                    conn.executemany(sql_insert, batch)
                elapsed = time.time() - t0
                logger.info(f"Inserted {total_processed:,} cases ({elapsed:.1f}s)")
                batch = []

            if limit_cases and total_processed >= limit_cases:
                break

        if batch:
            with conn:
                conn.executemany(sql_insert, batch)
            elapsed = time.time() - t0
            logger.info(f"Inserted final {len(batch)} cases. Total: {total_processed:,} cases in {elapsed:.1f}s")

    # Verify counts
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM cases_v2;")
    case_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM cases_v2_fts;")
    fts_count = cur.fetchone()[0]

    db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    logger.info(f"\nSQLite load complete!")
    logger.info(f"  cases_v2 rows: {case_count:,}")
    logger.info(f"  cases_v2_fts rows: {fts_count:,}")
    logger.info(f"  Database file size: {db_size_mb:.2f} MB ({db_size_mb/1024:.2f} GB)")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load cases into local SQLite database")
    parser.add_argument("--registry", default=r"I:\zilliz_work\registry.jsonl", help="Registry JSONL path")
    parser.add_argument("--db-path", default=r"d:\lawyer-Backend\data\cases_v2.db", help="Target SQLite DB path")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size per transaction")
    parser.add_argument("--limit-cases", type=int, default=None, help="Limit cases")

    args = parser.parse_args()
    load_registry_to_sqlite(
        registry_file=args.registry,
        db_path=args.db_path,
        batch_size=args.batch_size,
        limit_cases=args.limit_cases,
    )


if __name__ == "__main__":
    main()
