#!/usr/bin/env python3
"""
scripts/build_master_statutes_db.py

Constructs the definitive, deduplicated master SQLite database with FTS5 full-text search
and exports the lightweight statute catalog from PakistanLawSite scraped CSV files.
"""

import os
import sys
import csv
import re
import json
import sqlite3
import time
import hashlib
from datetime import datetime

csv.field_size_limit(2147483647)

INPUT_FILES = [
    ("Federal", r"I:\Statutes\Federal_Statutes.csv"),
    ("Punjab/Sindh", r"I:\Statutes\Provincial_Statutes.csv"),
    ("Sindh/KPK/Balochistan", r"I:\Statutes\Provincial_Statutes_Remaining.csv")
]

DB_PATH = r"I:\Statutes\pakistan_statutes_master.db"
CATALOG_PATH = r"I:\Statutes\statute_catalog.json"
REPO_CATALOG_PATH = r"D:\lawyer-Backend\data\statute_catalog.json"

JUR_CODES = {
    "FEDERAL": "FED",
    "PUNJAB": "PB",
    "SINDH": "SD",
    "KHYBER PAKHTUNKHWA": "KPK",
    "KPK": "KPK",
    "BALOCHISTAN": "BL"
}

def slugify(text: str) -> str:
    s = re.sub(r'[^a-zA-Z0-9]+', '-', text).strip('-')
    return s.upper() or "GENERAL"

def normalize_title(title: str) -> str:
    t = title.strip()
    t = re.sub(r'\s+', ' ', t)
    return t

def normalize_sec(sec: str) -> str:
    s = sec.strip()
    s = re.sub(r'\s+', ' ', s)
    return s

def extract_year(title: str) -> str:
    m = re.search(r'\b(1[89]\d{2}|20[0-2]\d)\b', title)
    return m.group(1) if m else ""

def generate_canonical_id(jur: str, title: str, sec: str) -> str:
    jur_code = JUR_CODES.get(jur.upper(), "PK")
    slug_title = slugify(title)[:35].strip('-')
    slug_sec = slugify(sec)[:20].strip('-')
    hash_suffix = hashlib.sha256(f"{jur.upper()}|{title.upper()}|{sec.upper()}".encode("utf-8")).hexdigest()[:8].upper()
    return f"PK-{jur_code}-{slug_title}-{slug_sec}-{hash_suffix}"

def main():
    start_time = time.time()
    print("=" * 70, flush=True)
    print("STEP 1: Scanning and Deduplicating 620,892 Raw Sections...", flush=True)
    print("=" * 70, flush=True)

    # Dictionary: key -> record dict
    # key: (jur_norm, title_norm, sec_norm)
    dedup_store = {}
    total_raw_rows = 0
    duplicate_count = 0

    for label, fpath in INPUT_FILES:
        print(f"Reading {label} from {fpath}...", flush=True)
        if not os.path.exists(fpath):
            print(f"ERROR: File not found: {fpath}", flush=True)
            sys.exit(1)

        file_rows = 0
        file_dups = 0
        with open(fpath, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_raw_rows += 1
                file_rows += 1

                raw_jur = row.get("Jurisdiction", "").strip()
                jur_norm = raw_jur.upper()
                raw_title = row.get("Statute_Title", "").strip()
                title_norm = normalize_title(raw_title).upper()
                raw_sec = row.get("Section_Number", "").strip()
                sec_norm = normalize_sec(raw_sec).upper()

                if not raw_jur or not raw_title or not raw_sec:
                    continue

                key = (jur_norm, title_norm, sec_norm)
                full_text = (row.get("Full_Text") or "").strip()
                scraped_at = (row.get("Scraped_At") or "").strip()
                sec_title = (row.get("Section_Title") or "").strip()
                letter = (row.get("Letter") or "").strip().upper()
                statute_index = row.get("Statute_Index", "").strip()

                if key in dedup_store:
                    duplicate_count += 1
                    file_dups += 1
                    # Keep the record with longer text or more complete data
                    existing = dedup_store[key]
                    if len(full_text) > len(existing["full_text"]):
                        dedup_store[key] = {
                            "jurisdiction": raw_jur,
                            "statute_title": normalize_title(raw_title),
                            "section_number": normalize_sec(raw_sec),
                            "section_title": sec_title,
                            "full_text": full_text,
                            "letter": letter,
                            "statute_index": statute_index,
                            "scraped_at": scraped_at
                        }
                else:
                    dedup_store[key] = {
                        "jurisdiction": raw_jur,
                        "statute_title": normalize_title(raw_title),
                        "section_number": normalize_sec(raw_sec),
                        "section_title": sec_title,
                        "full_text": full_text,
                        "letter": letter,
                        "statute_index": statute_index,
                        "scraped_at": scraped_at
                    }

        print(f"  Processed {file_rows:,} rows (duplicates resolved: {file_dups:,})", flush=True)

    unique_count = len(dedup_store)
    print("-" * 70, flush=True)
    print(f"Raw rows read:       {total_raw_rows:,}", flush=True)
    print(f"Duplicates resolved: {duplicate_count:,}", flush=True)
    print(f"Clean Unique Units:  {unique_count:,}", flush=True)
    print("-" * 70, flush=True)

    # STEP 2: Building Master SQLite Database
    print("\nSTEP 2: Initializing SQLite Database with FTS5 Indexing...", flush=True)
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"Removed previous database at {DB_PATH}", flush=True)
        except Exception as e:
            print(f"Notice: Could not remove old DB: {e}", flush=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA synchronous = OFF;")
    cur.execute("PRAGMA journal_mode = MEMORY;")
    cur.execute("PRAGMA cache_size = 100000;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS statutes (
        canonical_id TEXT PRIMARY KEY,
        jurisdiction TEXT NOT NULL,
        statute_title TEXT NOT NULL,
        section_number TEXT NOT NULL,
        section_title TEXT,
        full_text TEXT NOT NULL,
        letter TEXT,
        statute_index INTEGER,
        scraped_at TEXT,
        word_count INTEGER
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_statutes_lookup ON statutes(jurisdiction, statute_title, section_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_statutes_jur_title ON statutes(jurisdiction, statute_title);")

    # Step 3: Batch Insert
    print("Inserting 620k unique provisions into SQLite...", flush=True)
    insert_sql = """
    INSERT OR REPLACE INTO statutes (
        canonical_id, jurisdiction, statute_title, section_number, section_title, full_text, letter, statute_index, scraped_at, word_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch = []
    catalog = {}  # (jurisdiction, statute_title) -> metadata

    for idx, (key, rec) in enumerate(dedup_store.items()):
        jur = rec["jurisdiction"]
        jur_code = JUR_CODES.get(jur.upper(), "PK")
        title = rec["statute_title"]
        sec = rec["section_number"]
        txt = rec["full_text"]
        words = len(txt.split())

        cid = generate_canonical_id(jur, title, sec)

        # Index catalog
        cat_key = (jur.upper(), title.upper())
        if cat_key not in catalog:
            catalog[cat_key] = {
                "jurisdiction": jur,
                "statute_title": title,
                "year": extract_year(title),
                "sections_count": 0,
                "canonical_prefix": f"PK-{jur_code}-{slugify(title)[:35].strip('-')}"
            }
        catalog[cat_key]["sections_count"] += 1

        statute_idx = int(rec["statute_index"]) if rec["statute_index"].isdigit() else None

        batch.append((
            cid,
            jur,
            title,
            sec,
            rec["section_title"],
            txt,
            rec["letter"],
            statute_idx,
            rec["scraped_at"],
            words
        ))

        if len(batch) >= 10000:
            cur.executemany(insert_sql, batch)
            conn.commit()
            batch = []
            if (idx + 1) % 50000 == 0:
                print(f"  Inserted {idx + 1:,} / {unique_count:,} records...", flush=True)

    if batch:
        cur.executemany(insert_sql, batch)
        conn.commit()
    print(f"All {unique_count:,} provisions inserted into base table.", flush=True)

    # STEP 4: Creating FTS5 Index
    print("\nSTEP 4: Building FTS5 Full-Text Search Virtual Table...", flush=True)
    fts_start = time.time()
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS statutes_fts USING fts5(
        canonical_id UNINDEXED,
        jurisdiction,
        statute_title,
        section_number,
        section_title,
        full_text,
        content='statutes',
        content_rowid='rowid'
    );
    """)
    cur.execute("""
    INSERT INTO statutes_fts(statutes_fts) VALUES('rebuild');
    """)
    conn.commit()
    print(f"FTS5 rebuild completed in {time.time() - fts_start:.1f}s.", flush=True)

    # Check database size
    conn.close()
    db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"Database built successfully at: {DB_PATH} ({db_size_mb:.2f} MB)", flush=True)

    # STEP 5: Generating Statute Catalog JSON
    print("\nSTEP 5: Generating Statute Catalog JSON...", flush=True)
    catalog_list = sorted(list(catalog.values()), key=lambda x: (x["jurisdiction"], x["statute_title"]))
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog_list, f, indent=2, ensure_ascii=False)
    print(f"Catalog saved to {CATALOG_PATH} ({len(catalog_list):,} unique statutes)", flush=True)

    # Copy to repo data folder if exists
    os.makedirs(os.path.dirname(REPO_CATALOG_PATH), exist_ok=True)
    with open(REPO_CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog_list, f, indent=2, ensure_ascii=False)
    print(f"Catalog copied to {REPO_CATALOG_PATH}", flush=True)

    total_time = time.time() - start_time
    print("=" * 70, flush=True)
    print(f"ALL COMPLETE IN {total_time:.1f} SECONDS!", flush=True)
    print(f"Total Unique Statutes:   {len(catalog_list):,}")
    print(f"Total Unique Provisions: {unique_count:,}")
    print(f"Zero Duplication:        100% Guaranteed")
    print("=" * 70, flush=True)

if __name__ == "__main__":
    main()
