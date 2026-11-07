"""
legal_ai/statutes/legal_knowledge_store.py

Layer 1: High-Performance SQLite-backed Legal Knowledge Store.
Adheres to Section AI Design Principles:
1. Structure first, search second. Every provision is an atomic, immutable LegalUnitRecord.
2. The model never supplies law: it can only select, quote, and cite records from this store.
3. Every claim carries a citation ID verified against this database before display.
4. Clean text, footnotes, period, trigger, parent hierarchy, and provenance are strictly isolated.
"""

import os
import json
import sqlite3
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

from legal_ai.statutes.legal_unit_record import LegalUnitRecord


DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "legal_knowledge_store.db"
)


class LegalKnowledgeStore:
    """
    Authoritative local SQLite repository for all verified Pakistani statutes
    (Federal and Provincial).
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes tables and indexes with WAL mode for fast concurrent reads."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_units (
                    unit_id TEXT PRIMARY KEY,
                    statute_id TEXT NOT NULL,
                    statute_title TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    unit_type TEXT NOT NULL,
                    number TEXT NOT NULL,
                    parent TEXT,
                    heading_description TEXT NOT NULL,
                    period TEXT,
                    trigger TEXT,
                    text TEXT NOT NULL,
                    footnotes_json TEXT,
                    cross_references_json TEXT,
                    caveats_json TEXT,
                    amended_to TEXT,
                    source_url TEXT,
                    retrieved_at TEXT,
                    checksum TEXT NOT NULL,
                    raw_row_json TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_statute_num ON legal_units(statute_id, unit_type, number);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_statute_id ON legal_units(statute_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jurisdiction ON legal_units(jurisdiction, statute_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_unit_type ON legal_units(unit_type);")

    def insert_unit(self, record: LegalUnitRecord) -> None:
        """Inserts or replaces an authoritative legal unit record."""
        self.insert_batch([record])

    def insert_batch(self, records: List[LegalUnitRecord]) -> int:
        """Batch inserts legal unit records within a single transaction."""
        if not records:
            return 0
        
        query = """
            INSERT OR REPLACE INTO legal_units (
                unit_id, statute_id, statute_title, jurisdiction, unit_type,
                number, parent, heading_description, period, trigger,
                text, footnotes_json, cross_references_json, caveats_json,
                amended_to, source_url, retrieved_at, checksum, raw_row_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        rows = []
        for r in records:
            rows.append((
                r.unit_id,
                r.statute_id,
                r.statute_title,
                r.jurisdiction,
                r.unit_type,
                r.number,
                r.parent,
                r.heading_description,
                r.period,
                r.trigger,
                r.text,
                json.dumps(r.footnotes, ensure_ascii=False),
                json.dumps(r.cross_references, ensure_ascii=False),
                json.dumps(r.caveats, ensure_ascii=False),
                r.amended_to,
                r.source_url,
                r.retrieved_at,
                r.checksum,
                json.dumps(r.raw_row, ensure_ascii=False) if r.raw_row else None
            ))

        with self._get_connection() as conn:
            conn.executemany(query, rows)
            conn.commit()
        return len(records)

    def get_unit(self, statute_id: str, unit_type: str, number: str) -> Optional[LegalUnitRecord]:
        """Direct O(1) indexed lookup of an exact legal unit."""
        clean_num = str(number).strip()
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM legal_units WHERE statute_id = ? AND unit_type = ? AND (number = ? OR number = ?) LIMIT 1;",
                (statute_id.lower().strip(), unit_type.lower().strip(), clean_num, clean_num.upper())
            )
            row = cur.fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def get_by_id(self, unit_id: str) -> Optional[LegalUnitRecord]:
        """Retrieves an exact record by its canonical global unit ID."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM legal_units WHERE unit_id = ? LIMIT 1;", (unit_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def search_units(
        self,
        query: str,
        statute_id: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        limit: int = 10
    ) -> List[LegalUnitRecord]:
        """Searches legal units by keyword matching across headings and body text."""
        sql = "SELECT * FROM legal_units WHERE 1=1"
        params: List[Any] = []

        if statute_id:
            sql += " AND statute_id = ?"
            params.append(statute_id.lower().strip())

        if jurisdiction:
            sql += " AND jurisdiction = ?"
            params.append(jurisdiction.lower().strip())

        words = [w.strip() for w in query.split() if len(w.strip()) > 2]
        if words:
            like_clauses = []
            for w in words[:4]:
                like_clauses.append("(heading_description LIKE ? OR text LIKE ?)")
                params.extend([f"%{w}%", f"%{w}%"])
            sql += " AND " + " AND ".join(like_clauses)

        sql += " LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cur = conn.execute(sql, params)
            return [self._row_to_record(r) for r in cur.fetchall()]

    def count_units(self) -> Dict[str, Any]:
        """Returns statistics on loaded legal units by statute and jurisdiction."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM legal_units;").fetchone()[0]
            by_jur = {}
            for r in conn.execute("SELECT jurisdiction, COUNT(*) FROM legal_units GROUP BY jurisdiction;").fetchall():
                by_jur[r[0]] = r[1]
            by_type = {}
            for r in conn.execute("SELECT unit_type, COUNT(*) FROM legal_units GROUP BY unit_type;").fetchall():
                by_type[r[0]] = r[1]
        return {
            "total_units": total,
            "by_jurisdiction": by_jur,
            "by_unit_type": by_type
        }

    def _row_to_record(self, row: sqlite3.Row) -> LegalUnitRecord:
        return LegalUnitRecord(
            unit_id=row["unit_id"],
            statute_id=row["statute_id"],
            statute_title=row["statute_title"],
            jurisdiction=row["jurisdiction"],
            unit_type=row["unit_type"],
            number=row["number"],
            parent=row["parent"],
            heading_description=row["heading_description"],
            period=row["period"],
            trigger=row["trigger"],
            text=row["text"],
            footnotes=json.loads(row["footnotes_json"] or "[]"),
            cross_references=json.loads(row["cross_references_json"] or "[]"),
            caveats=json.loads(row["caveats_json"] or "[]"),
            amended_to=row["amended_to"],
            source_url=row["source_url"] or "",
            retrieved_at=row["retrieved_at"] or "",
            checksum=row["checksum"],
            raw_row=json.loads(row["raw_row_json"]) if row["raw_row_json"] else None
        )
