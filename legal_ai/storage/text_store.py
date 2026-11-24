"""
legal_ai/storage/text_store.py

TextStore Interface and SQLite Implementation per Remediation Spec Phase 3.
Provides high-capacity, un-truncated judgment full-text storage to eliminate the 1,200 character cap.
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, asdict
from typing import Optional, Protocol, Dict, Any, List

logger = logging.getLogger(__name__)

@dataclass
class CaseText:
    case_id: str
    citation: str
    title_clean: str
    court: str            # 'UNKNOWN' allowed
    court_source: str     # 'citation_prefix' | 'bench_in_title' | 'metadata' | 'unknown'
    year: Optional[int]
    content_level: str    # 'full_judgment' | 'headnote_only' | 'short_order'
    text: str
    truncated: bool
    source_pdf_key: Optional[str] = None

class TextStore(Protocol):
    def get_case_text(self, case_id: str) -> Optional[CaseText]:
        ...
    def put_case_text(self, rec: CaseText) -> None:
        ...

class SQLiteTextStore:
    """
    Hermetic SQLite / local text store with FTS5 search and robust fallback.
    """
    def __init__(self, db_path: str = "data/case_texts.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS case_texts (
                    case_id TEXT PRIMARY KEY,
                    citation TEXT,
                    title_clean TEXT,
                    court TEXT,
                    court_source TEXT,
                    year INTEGER,
                    content_level TEXT,
                    text TEXT,
                    truncated INTEGER,
                    source_pdf_key TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_case_texts_citation ON case_texts(citation)")
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS case_texts_fts USING fts5(
                        case_id UNINDEXED,
                        citation,
                        title_clean,
                        text
                    )
                """)
            except Exception as e:
                logger.debug(f"FTS5 initialization notice: {e}")
            conn.commit()

    def get_case_text(self, case_id: str) -> Optional[CaseText]:
        clean_id = str(case_id or "").strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM case_texts WHERE case_id = ? OR citation = ? LIMIT 1",
                (clean_id, clean_id)
            ).fetchone()
            if not row:
                return None
            return CaseText(
                case_id=row["case_id"],
                citation=row["citation"] or "",
                title_clean=row["title_clean"] or "",
                court=row["court"] or "UNKNOWN",
                court_source=row["court_source"] or "unknown",
                year=row["year"],
                content_level=row["content_level"] or "headnote_only",
                text=row["text"] or "",
                truncated=bool(row["truncated"]),
                source_pdf_key=row["source_pdf_key"],
            )

    def put_case_text(self, rec: CaseText) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO case_texts (
                    case_id, citation, title_clean, court, court_source, year,
                    content_level, text, truncated, source_pdf_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec.case_id,
                rec.citation,
                rec.title_clean,
                rec.court,
                rec.court_source,
                rec.year,
                rec.content_level,
                rec.text,
                1 if rec.truncated else 0,
                rec.source_pdf_key,
            ))
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO case_texts_fts (case_id, citation, title_clean, text)
                    VALUES (?, ?, ?, ?)
                """, (rec.case_id, rec.citation, rec.title_clean, rec.text[:10000]))
            except Exception:
                pass
            conn.commit()


_GLOBAL_TEXT_STORE: Optional[TextStore] = None

def get_text_store() -> TextStore:
    global _GLOBAL_TEXT_STORE
    if _GLOBAL_TEXT_STORE is None:
        _GLOBAL_TEXT_STORE = SQLiteTextStore()
    return _GLOBAL_TEXT_STORE
