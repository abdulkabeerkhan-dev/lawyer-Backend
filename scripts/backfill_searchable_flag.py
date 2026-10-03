"""
scripts/backfill_searchable_flag.py

Safe, non-blocking backfill script for Supabase / PostgreSQL.
Batches updates in chunks of 500 to avoid long transaction locks, statement timeouts,
and transaction control errors (such as COMMIT inside DO blocks).
"""

import os
import sys
import time

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None

BATCH_SIZE = 500
MIN_SEARCHABLE_LENGTH = 200

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: DATABASE_URL or SUPABASE_DB_URL environment variable is required.", file=sys.stderr)
        return None
    return psycopg2.connect(db_url)

def run_backfill(batch_size: int = BATCH_SIZE):
    if not psycopg2:
        print("psycopg2 is not installed. Install psycopg2-binary to run backfill on Supabase.", file=sys.stderr)
        return False

    conn = get_db_connection()
    if not conn:
        return False

    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Step 1: Ensure DDL column exists safely
        cursor.execute("ALTER TABLE full_judgments ADD COLUMN IF NOT EXISTS is_searchable BOOLEAN DEFAULT NULL;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_full_judgments_is_searchable ON full_judgments(is_searchable);")
        conn.commit()
        print("DDL migration verified: column is_searchable and index exist.")

        # Step 2: Iterate over unpopulated records in batches
        total_processed = 0
        total_stubs = 0
        total_searchable = 0

        while True:
            cursor.execute(
                """
                SELECT id, length(coalesce(full_text, raw_text, '')) as doc_len
                FROM full_judgments
                WHERE is_searchable IS NULL
                ORDER BY id
                LIMIT %s;
                """,
                (batch_size,)
            )
            rows = cursor.fetchall()
            if not rows:
                print("All records have been classified. Backfill complete.")
                break

            update_data = [
                (doc_len >= MIN_SEARCHABLE_LENGTH, row_id)
                for row_id, doc_len in rows
            ]

            cursor.executemany(
                """
                UPDATE full_judgments
                SET is_searchable = %s
                WHERE id = %s;
                """,
                update_data
            )
            conn.commit()

            stubs_in_batch = sum(1 for is_s, _ in update_data if not is_s)
            searchable_in_batch = len(update_data) - stubs_in_batch

            total_processed += len(rows)
            total_stubs += stubs_in_batch
            total_searchable += searchable_in_batch

            print(f"Batch processed: {len(rows)} rows | Cumulative: {total_processed} (Searchable: {total_searchable}, Stubs: {total_stubs})")
            time.sleep(0.05)  # cooperative yield for connection pool health

        print(f"\nFinal Summary: {total_processed} rows backfilled. {total_searchable} substantive, {total_stubs} stubs.")
        return True

    except Exception as e:
        conn.rollback()
        print(f"ERROR during backfill: {e}", file=sys.stderr)
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_backfill()
