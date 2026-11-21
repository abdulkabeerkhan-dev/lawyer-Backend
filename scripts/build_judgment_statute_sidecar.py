"""
scripts/build_judgment_statute_sidecar.py

Evaluates stored statute tags on 300 sampled chunks from Zilliz judgments_v1 (READ-ONLY).
Extracts clean canonical statute IDs from chunk text via resolve_statute_id.
Calculates Precision and Recall of stored tags.
Lists 20 concrete wrong/noisy stored tags.
Stores the clean sidecar mapping in data/judgment_statute_sidecar.db.
"""

import os
import re
import sys
import json
import sqlite3
import random
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
from dotenv import load_dotenv

load_dotenv('D:/lawyer-Backend/.env')
sys.path.insert(0, 'D:/lawyer-Backend')

from legal_ai.config import get_zilliz_client
from legal_ai.retrieval.statute_resolver import resolve_statute_id
from legal_ai.retrieval.query_planner import parse_explicit_references

BASE_DIR = Path('D:/lawyer-Backend')
DB_PATH = BASE_DIR / 'data' / 'judgment_statute_sidecar.db'
REPORT_PATH = BASE_DIR / 'reports' / 'judgment_statute_sidecar_300_eval.json'

def init_sidecar_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS judgment_statute_sidecar (
            chunk_id TEXT PRIMARY KEY,
            case_key TEXT NOT NULL,
            clean_statute_ids TEXT NOT NULL,
            stored_statute_ids TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sidecar_case_key ON judgment_statute_sidecar(case_key);")
    conn.commit()
    conn.close()

def extract_statutes_from_chunk_text(text: str) -> List[str]:
    """
    Extracts all statute provision IDs from text using regex and resolve_statute_id.
    """
    if not text:
        return []
    
    extracted_cids = set()
    
    # 1. Use explicit reference parser
    refs = parse_explicit_references(text)
    for r in refs:
        cid = r.get("canonical_id")
        if cid:
            extracted_cids.add(cid)
            
    # 2. Additional robust patterns for judgments:
    # "Section 302 of Pakistan Penal Code", "Section 497, Cr.P.C.", "Article 199 of Constitution"
    patterns = [
        r'(?:section|s\.)\s*(\d+[a-z]?(?:\(\d+\))?(?:\([a-z]\))?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\.\s]+)',
        r'(?:article|art\.)\s*(\d+[a-z]?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\.\s]+)',
        r'(?:order|ord\.)\s*([0-9ivxlcdm]+)\s*(?:rule|r\.)\s*(\d+[a-z]?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\.\s]+)?',
    ]
    
    # Common shorthand
    act_map = {
        'P.P.C': 'PPC_1860', 'PPC': 'PPC_1860', 'PAKISTAN PENAL CODE': 'PPC_1860',
        'CR.P.C': 'CRPC_1898', 'CRPC': 'CRPC_1898', 'CODE OF CRIMINAL PROCEDURE': 'CRPC_1898',
        'C.P.C': 'CPC_1908', 'CPC': 'CPC_1908', 'CODE OF CIVIL PROCEDURE': 'CPC_1908',
        'CONSTITUTION': 'CONST_1973', 'QANUN-E-SHAHADAT': 'QSO_1984', 'QSO': 'QSO_1984',
        'FINANCIAL INSTITUTIONS': 'FIO_2001', 'FIO': 'FIO_2001',
        'NATIONAL ACCOUNTABILITY': 'NAO_1999', 'NAO': 'NAO_1999',
        'INCOME TAX': 'ITO_2001', 'SALES TAX': 'SALES_TAX_1990',
        'CONTROL OF NARCOTIC': 'CNSA_1997', 'CNSA': 'CNSA_1997',
        'ANTI-TERRORISM': 'ATA_1997', 'ATA': 'ATA_1997',
    }

    # Search for "Section <num> <Act>"
    for match in re.finditer(r'\b(?:Section|Sec\.?|S\.)\s*(\d+[A-Za-z]?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\.\s]{3,35})\b', text, re.IGNORECASE):
        sec = match.group(1).upper()
        act_raw = match.group(2).upper().strip()
        matched_act = None
        for k, v in act_map.items():
            if k in act_raw:
                matched_act = v
                break
        if matched_act:
            cand = f"{matched_act}_SEC_{sec}"
            resolved = resolve_statute_id(cand)
            if resolved:
                extracted_cids.add(resolved)

    # Search for "Article <num> <Act>"
    for match in re.finditer(r'\b(?:Article|Art\.?)\s*(\d+[A-Za-z]?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\.\s]{3,35})\b', text, re.IGNORECASE):
        art = match.group(1).upper()
        act_raw = match.group(2).upper().strip()
        matched_act = "CONST_1973" if "CONST" in act_raw else ("QSO_1984" if "QANUN" in act_raw or "QSO" in act_raw else None)
        if matched_act:
            cand = f"{matched_act}_ART_{art}"
            resolved = resolve_statute_id(cand)
            if resolved:
                extracted_cids.add(resolved)

    return sorted(list(extracted_cids))

def evaluate_300_samples():
    print("Connecting to Zilliz Cloud (READ-ONLY on judgments_v1)...")
    client = get_zilliz_client()
    if not client:
        print("ERROR: Zilliz client could not be initialized.")
        return

    # Sample 300 chunks
    print("Querying 300 sample chunks from judgments_v1...")
    sample_res = client.query(
        collection_name="judgments_v1",
        filter='chunk_id != ""',
        output_fields=["chunk_id", "case_key", "text", "statutes"],
        limit=300
    )
    print(f"Retrieved {len(sample_res)} sample chunks.")

    init_sidecar_db()
    sidecar_entries = []

    total_stored_tags = 0
    valid_stored_tags = 0
    total_clean_extracted = 0
    stored_matching_clean = 0

    wrong_stored_examples = []

    for idx, row in enumerate(sample_res):
        chunk_id = str(row.get("chunk_id", ""))
        case_key = str(row.get("case_key", ""))
        text = row.get("text", "") or ""
        raw_stored = row.get("statutes", [])
        if isinstance(raw_stored, str):
            try:
                raw_stored = json.loads(raw_stored)
            except Exception:
                raw_stored = [raw_stored]
        elif not isinstance(raw_stored, list):
            raw_stored = []

        # Extract ground truth clean statutes from text
        clean_extracted = extract_statutes_from_chunk_text(text)
        total_clean_extracted += len(clean_extracted)

        # Evaluate stored tags
        clean_stored = []
        for tag in raw_stored:
            total_stored_tags += 1
            resolved = resolve_statute_id(str(tag))
            if resolved:
                valid_stored_tags += 1
                clean_stored.append(resolved)
                if resolved in clean_extracted:
                    stored_matching_clean += 1
            else:
                if len(wrong_stored_examples) < 30:
                    wrong_stored_examples.append({
                        "chunk_id": chunk_id,
                        "case_key": case_key,
                        "invalid_stored_tag": str(tag),
                        "reason": "Unresolvable / malformed syntax / nonexistent section",
                        "text_snippet": text[:150]
                    })

        # Check for false positives: resolved tags not actually in text
        for st in set(clean_stored):
            if st not in clean_extracted and len(wrong_stored_examples) < 30:
                wrong_stored_examples.append({
                    "chunk_id": chunk_id,
                    "case_key": case_key,
                    "invalid_stored_tag": st,
                    "reason": "Hallucinated / not mentioned in chunk text",
                    "text_snippet": text[:150]
                })

        sidecar_entries.append((
            chunk_id,
            case_key,
            json.dumps(clean_extracted),
            json.dumps(raw_stored)
        ))

    # Save to SQLite sidecar DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany("""
        INSERT OR REPLACE INTO judgment_statute_sidecar (chunk_id, case_key, clean_statute_ids, stored_statute_ids)
        VALUES (?, ?, ?, ?)
    """, sidecar_entries)
    conn.commit()
    conn.close()

    # Calculate metrics
    precision = (stored_matching_clean / total_stored_tags) if total_stored_tags > 0 else 1.0
    recall = (stored_matching_clean / total_clean_extracted) if total_clean_extracted > 0 else 1.0

    eval_report = {
        "sampled_chunks": len(sample_res),
        "total_stored_tags_in_sample": total_stored_tags,
        "valid_resolvable_stored_tags": valid_stored_tags,
        "clean_extracted_from_text": total_clean_extracted,
        "stored_matching_clean_extracted": stored_matching_clean,
        "precision_of_stored_tags": round(precision, 4),
        "recall_of_stored_tags": round(recall, 4),
        "sidecar_table_db": str(DB_PATH),
        "wrong_stored_examples_top20": wrong_stored_examples[:20]
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)

    print("\n--- JUDGMENT STATUTE EVALUATION (300 SAMPLES) ---")
    print(f"Sampled Chunks: {len(sample_res)}")
    print(f"Total Stored Tags: {total_stored_tags}")
    print(f"Resolvable Stored Tags: {valid_stored_tags}")
    print(f"Clean Extracted From Text: {total_clean_extracted}")
    print(f"Stored Tags Matching Text Ground Truth: {stored_matching_clean}")
    print(f"Precision of Stored Tags: {precision * 100:.2f}%")
    print(f"Recall of Stored Tags: {recall * 100:.2f}%")
    print(f"Saved sidecar to: {DB_PATH}")
    print(f"Saved detailed report to: {REPORT_PATH}")

if __name__ == "__main__":
    evaluate_300_samples()
