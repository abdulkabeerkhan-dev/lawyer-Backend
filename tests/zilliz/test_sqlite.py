import os
import tempfile
import sqlite3
import pytest
from scripts.zilliz.load_cases_sqlite import init_sqlite_schema

def test_sqlite_schema_and_fts():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name

    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        init_sqlite_schema(conn)

        # Insert a sample case
        with conn:
            conn.execute("""
                INSERT INTO cases_v2 (
                    case_key, citation, journal, year, court_code, court_name,
                    court_level, page, parties, judge, content_level,
                    headnote_text, judgment_text, statutes, domain
                ) VALUES (
                    '2024_SCMR_SC_14', '2024 SCMR 14', 'SCMR', 2024, 'SC', 'Supreme Court of Pakistan',
                    1, 14, 'Muhammad Aslam v. The State', 'Justice Yahya Afridi', 'full_judgment',
                    'Criminal Procedure Code S. 497 post-arrest bail',
                    'The petitioner seeks post arrest bail in case FIR under section 302 PPC. Bail is granted.',
                    '["PPC_1860_SEC_302", "CRPC_1898_SEC_497"]', 'criminal'
                )
            """)

        # Test exact citation lookup
        cur = conn.cursor()
        cur.execute("SELECT case_key, citation, judge FROM cases_v2 WHERE citation = '2024 SCMR 14'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "2024_SCMR_SC_14"
        assert row[1] == "2024 SCMR 14"
        assert "Afridi" in row[2]

        # Test FTS5 search
        cur.execute("""
            SELECT case_key, citation, rank
            FROM cases_v2_fts
            WHERE cases_v2_fts MATCH '\"post-arrest\" bail 302'
            ORDER BY rank
            LIMIT 5
        """)
        fts_rows = cur.fetchall()
        assert len(fts_rows) == 1
        assert fts_rows[0][0] == "2024_SCMR_SC_14"
    finally:
        if conn:
            conn.close()
        if os.path.exists(temp_db):
            os.remove(temp_db)
