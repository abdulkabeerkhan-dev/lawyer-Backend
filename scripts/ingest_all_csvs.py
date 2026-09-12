#!/usr/bin/env python3
"""
AMICUS AI - Automated Discovery, Text Sanitization, Bulk SQL Import & Incremental Embedding Engine

Scans system & workspace for judgment CSV files (PLD, SCMR, MLD, YLR, PCRLJ, CLC, PLC, CLD, PTD, GBLR, etc.),
sanitizes judgment content to strip scraper debris, populates PostgreSQL Master Ledger (full_judgments),
and incrementally embeds clean vectors into Pinecone namespace 'clean-v1'.
"""

import os
import sys
import glob
import csv
import re
import time
import argparse
import logging
from typing import List, Dict, Any, Optional, Tuple

csv.field_size_limit(sys.maxsize)
from dotenv import load_dotenv
from supabase import create_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ingest_all_csvs")

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY missing from environment.")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

JOURNAL_REGEX = r'(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC\s*\(CS\)|PLC|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)'

def sanitize_judgment_content(raw_text: str) -> str:
    """
    Strict content sanitization for Pakistani judgments:
    1. Strips HTML tags, doctypes, scripts, style blocks.
    2. Strips portal navigation, headers, footers, and copyright statements.
    3. Strips scraper serial counts, repeated dashes, equals, underscores, asterisks.
    4. Collapses irregular whitespace while keeping clean paragraph breaks.
    """
    if not raw_text:
        return ""
    text = str(raw_text)

    # 1. Strip HTML tags, doctypes, scripts, style blocks
    text = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)

    # 2. Strip standard portal navigation, headers, and footers
    text = re.sub(r'(?i)(home|search|case search|law finder|back to results|print preview|download pdf|disclaimer).*?\n', '', text)
    text = re.sub(r'(?i)page \d+ of \d+', '', text)
    text = re.sub(r'(?i)pakistan law site|pls|all rights reserved|copyright ©.*?\n', '', text)

    # 3. Strip scraper serial counts, repeated dashes, and page breaks
    text = re.sub(r'-{3,}', ' ', text)
    text = re.sub(r'={3,}', ' ', text)
    text = re.sub(r'_{3,}', ' ', text)
    text = re.sub(r'\*{3,}', ' ', text)

    # 4. Collapse irregular whitespace while keeping clean paragraph breaks
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()

def sanitize_case_title(raw_title: str) -> str:
    """
    Sanitizes party titles:
    - Strips leading page numbers ('339 '), reporter citations ('2021 SCMR 2092 ')
    - Strips judge suffixes ('- Honorable Justice Sayyed Mazahar Ali Akbar Naqvi')
    - Strips advocate names and trailing court tags ('SUPREME-COURT')
    - Standardizes 'VS' / 'VERSUS' to 'v.'
    """
    if not raw_title:
        return "Untitled Case"

    t = str(raw_title).replace("\t", " ").strip()
    t = re.sub(r'^\d+\s+(?:(?:19|20)\d{2}\s+[A-Za-z0-9\(\)\s]+\s+\d+\s+)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:(?:19|20)\d{2}\s+(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s+\d+\s+)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*[\-\t]?\s*(?:SUPREME-COURT|HIGH-COURT|SINDH-HIGH-COURT|LAHORE-HIGH-COURT|PESHAWAR-HIGH-COURT|BALOCHISTAN-HIGH-COURT|ISLAMABAD-HIGH-COURT|GILGIT-BALTISTAN\s+CHIEF\s+COURT)\s*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*-\s*(?:Honorable\s+)?Justice.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*-\s*[A-Z][a-z]+\s+[A-Z][a-z]+.*$', '', t)
    t = re.sub(r'\s+(?:VS\.?|VERSUS|Vs\.?|vs\.?)\s+', ' v. ', t, flags=re.IGNORECASE)

    parts = t.split(' v. ')
    if len(parts) == 2:
        p1 = parts[0].strip().title()
        p2 = parts[1].strip().title()
        if p2.lower() in ("state", "the state"):
            p2 = "The State"
        elif p2.lower().startswith("state"):
            p2 = "The State"
        t = f"{p1} v. {p2}"
    else:
        t = t.strip().title()

    t = re.sub(r'\s*-\s*$', '', t).strip()
    return t or "Untitled Case"

def clean_court_name(court_raw: str, journal_raw: str = "") -> str:
    c = str(court_raw or "").strip().lower()
    j = str(journal_raw or "").strip().upper()

    if "supreme" in c or "scmr" in j or "pld sc" in j:
        return "Supreme Court of Pakistan"
    if "lahore" in c or "lhc" in c:
        return "Lahore High Court"
    if "sindh" in c or "shc" in c or "karachi" in c:
        return "High Court of Sindh"
    if "peshawar" in c or "phc" in c:
        return "Peshawar High Court"
    if "balochistan" in c or "bhc" in c or "quetta" in c:
        return "High Court of Balochistan"
    if "islamabad" in c or "ihc" in c:
        return "Islamabad High Court"
    if "shariat" in c or "fsc" in c:
        return "Federal Shariat Court"

    if j in ("SCMR", "GBLR"):
        return "Supreme Court of Pakistan"
    if j in ("PCRLJ", "CLC", "MLD", "YLR", "CLD", "PTD", "PLC", "PLC (CS)", "ALD", "SLR", "ILR", "SBLR"):
        return "High Court"

    return "Court of Record"

def extract_citation_and_title(cit_title_raw: str, default_journal: str = "", default_year: str = "") -> Tuple[str, str, str]:
    """
    Extracts (neutral_citation, case_title, case_id) from raw 'Citation / Title' string.
    Example input: '2021 SCMR 2092 MUHAMMAD NASIR SHAFIQUE VS State'
    Returns: ('2021 SCMR 2092', 'Muhammad Nasir Shafique v. The State', '2021_SCMR_2092')
    """
    raw = str(cit_title_raw or "").strip()
    match = re.search(r'\b((?:19|20)\d{2}\s+(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s+\d+)\b', raw, re.IGNORECASE)

    if match:
        extracted_cit = match.group(1).strip()
        parts = re.split(r'\b' + re.escape(extracted_cit) + r'\b', raw, maxsplit=1, flags=re.IGNORECASE)
        raw_title = parts[1].strip() if len(parts) > 1 and parts[1].strip() else parts[0].strip()
        
        # Clean citation string e.g. "2021 SCMR 2092"
        cit_clean = re.sub(r'\s+', ' ', extracted_cit).upper()
        case_id = re.sub(r'[\s_\-]+', '_', cit_clean)
        title_clean = sanitize_case_title(raw_title)
        return cit_clean, title_clean, case_id

    # Fallback if no explicit reporter citation regex matched
    title_clean = sanitize_case_title(raw)
    year_clean = str(default_year or "2026").strip()
    j_clean = str(default_journal or "PLD").strip().upper()
    cit_clean = f"{year_clean} {j_clean} 1"
    case_id = f"{year_clean}_{j_clean}_1"
    return cit_clean, title_clean, case_id

def discover_csv_files() -> List[str]:
    """Discovers all judgment CSV files on system D: drive and workspace."""
    found = []
    # D: drive root judgment CSVs
    d_root = glob.glob("D:/*.csv")
    for f in d_root:
        if any(j in os.path.basename(f).upper() for j in ["PLD", "SCMR", "MLD", "YLR", "PCRLJ", "CLC", "PLC", "CLD", "PTD", "GBLR", "PAKISTAN_LAW"]):
            found.append(f)

    # Downloads & Corpus
    extra_files = [
        "D:/Downloads/pakistanlawsite_legals.csv",
        "D:/202504__/PLD_cases.csv",
        "D:/202504__/SCMR_cases.csv",
        "D:/202504__/YLR_cases.csv"
    ]
    for f in extra_files:
        if os.path.exists(f):
            found.append(f)

    return sorted(list(set(found)))

def ingest_csv_file(file_path: str, batch_size: int = 500) -> Tuple[int, int]:
    """Ingests a single judgment CSV file into PostgreSQL master ledger (full_judgments)."""
    logger.info(f"📂 Processing CSV dataset: {file_path}")
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return 0, 0

    inserted_total = 0
    updated_total = 0
    batch = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as fp:
            reader = csv.DictReader(fp)
            headers = [h.strip().lstrip('\ufeff') for h in (reader.fieldnames or [])]
            logger.info(f"   Detected Headers: {headers}")

            for row_idx, row in enumerate(reader):
                # Clean keys
                r = {str(k).strip().lstrip('\ufeff'): str(v or '').strip() for kk, v in row.items() if kk for k in [kk]}
                
                journal = r.get("Journal") or r.get("alphabet") or ""
                year = r.get("Year") or r.get("year") or ""
                cit_title = r.get("Citation / Title") or r.get("case_title") or r.get("citation") or ""
                
                # Raw text field detection
                raw_judgment_text = r.get("Full Judgment Body") or r.get("Judgment Content") or r.get("case_description") or r.get("headnotes") or ""
                headnotes_text = r.get("Headnotes / Case Description") or r.get("headnotes") or ""

                full_text = sanitize_judgment_content(raw_judgment_text or headnotes_text)
                if not full_text or len(full_text) < 20:
                    continue

                neutral_cit, case_title, case_id = extract_citation_and_title(cit_title, default_journal=journal, default_year=year)
                court = clean_court_name(r.get("court") or "", journal_raw=journal)

                db_record = {
                    "case_id": case_id,
                    "case_title": case_title,
                    "neutral_citation": neutral_cit,
                    "court_name": court,
                    "decision_date": f"{year}-01-01" if (year and str(year).isdigit() and len(str(year)) == 4) else None,
                    "full_text": full_text
                }
                batch.append(db_record)

                if len(batch) >= batch_size:
                    try:
                        res = supabase.table("full_judgments").upsert(batch, on_conflict="case_id").execute()
                        inserted_total += len(batch)
                    except Exception as upsert_err:
                        logger.warning(f"Batch upsert notice: {upsert_err}")
                        for rec in batch:
                            try:
                                supabase.table("full_judgments").upsert(rec, on_conflict="case_id").execute()
                                inserted_total += 1
                            except Exception:
                                pass
                    batch = []

            if batch:
                try:
                    res = supabase.table("full_judgments").upsert(batch, on_conflict="case_id").execute()
                    inserted_total += len(batch)
                except Exception as upsert_err:
                    for rec in batch:
                        try:
                            supabase.table("full_judgments").upsert(rec, on_conflict="case_id").execute()
                            inserted_total += 1
                        except Exception:
                            pass

    except Exception as err:
        logger.error(f"Error processing CSV {file_path}: {err}")

    logger.info(f"✅ Finished {file_path}: {inserted_total} records upserted into Master Ledger.")
    return inserted_total, updated_total

def main():
    parser = argparse.ArgumentParser(description="Automated Judgment CSV Ingestion & Vector Pipeline Engine")
    parser.add_argument("--file", type=str, help="Ingest a specific CSV file")
    parser.add_argument("--reindex", action="store_true", help="Trigger vector re-index to Pinecone clean-v1 after ingestion")
    args = parser.parse_args()

    logger.info("==================================================================")
    logger.info("   AUTOMATED JUDGMENT CSV DISCOVERY & SQL MASTER LEDGER IMPORT  ")
    logger.info("==================================================================")

    if args.file:
        files = [args.file]
    else:
        files = discover_csv_files()

    logger.info(f"🔍 Discovered {len(files)} judgment CSV dataset(s) for ingestion:")
    for f in files:
        size_mb = os.path.getsize(f) / (1024 * 1024) if os.path.exists(f) else 0
        logger.info(f"   • {f} ({size_mb:.1f} MB)")

    total_records = 0
    for f in files:
        count, _ = ingest_csv_file(f)
        total_records += count

    logger.info(f"==================================================================")
    logger.info(f"🎉 MASTER LEDGER INGESTION COMPLETE: {total_records:,} records processed.")
    logger.info(f"==================================================================")

    if args.reindex:
        logger.info("🚀 Launching clean_reindex.py to re-index clean vectors into Pinecone 'clean-v1'...")
        from clean_reindex import run_reindex_pipeline
        run_reindex_pipeline(target_namespace="clean-v1")

if __name__ == "__main__":
    main()
