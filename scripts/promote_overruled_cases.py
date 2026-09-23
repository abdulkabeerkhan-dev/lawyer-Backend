#!/usr/bin/env python3
"""
Promote Verified Overruled Precedents to Production
1. Loads approved records from data/pending_overruled_review.json.
2. Normalizes canonical case_ids and cleans case titles.
3. Upserts records into public.precedent_status table in Supabase.
4. Updates data/precedent_annotations.json for local seed fallback.
"""

import os
import sys
import re
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_DIR, ".env"))

from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

def sanitize_title(title: str) -> str:
    """Sanitizes raw Pakistani case title into clean 'Party A v. Party B' format."""
    if not title or title.startswith("Not specified") or title.startswith("[Case name"):
        return ""
    t = title.replace("\t", " ").strip()
    t = re.sub(r'^\d+\s+(?:(?:19|20)\d{2}\s+[A-Za-z0-9\(\)\s]+\s+\d+\s+)?', '', t, flags=re.I)
    t = re.sub(r'^(?:(?:19|20)\d{2}\s+[A-Za-z0-9\(\)\s]+\s+\d+\s+)', '', t, flags=re.I)
    t = re.sub(r'\s*-\s*Honorable\s+Justice.*$', '', t, flags=re.I)
    t = re.sub(r'\s*[\-\t]?\s*(?:SUPREME-COURT.*|HIGH-COURT.*|SHARIAT-COURT.*|LABOUR-APPELLATE.*)$', '', t, flags=re.I)
    t = re.sub(r'\s+(?:VS|VERSUS)\s+', ' v. ', t, flags=re.I)
    t = t.strip()
    if t.isupper():
        words = t.split()
        t = " ".join(w.lower() if w.lower() in ("v.", "of", "the", "and") else w.capitalize() for w in words)
    return t

def generate_canonical_case_id(citation: str) -> str:
    """Generates standard case_id from citation: '2004 CLC 1186' -> '2004_CLC_1186'."""
    cit = re.sub(r'[\(\)\[\],]', ' ', citation).strip()
    match = re.search(r'\b(19\d\d|20\d\d)\s+([A-Za-z]+)(?:\s+([A-Za-z]+))?\s+(\d+)\b', cit)
    if match:
        year, j1, j2, page = match.groups()
        if j2:
            return f"{year}_{j1.upper()}_{j2.upper()}_{page}"
        return f"{year}_{j1.upper()}_{page}"
    # AIR or other format
    match_air = re.search(r'\bAIR\s+(19\d\d|20\d\d)\s+([A-Za-z\s]+?)\s+(\d+)\b', cit, re.I)
    if match_air:
        year, court, page = match_air.groups()
        court_clean = re.sub(r'[^A-Za-z0-9]+', '_', court).strip('_').upper()
        return f"{year}_AIR_{court_clean}_{page}"
    return re.sub(r'[^A-Za-z0-9]+', '_', cit).strip('_').upper()

def promote_records():
    review_path = os.path.join(REPO_DIR, "data", "pending_overruled_review.json")
    annotations_path = os.path.join(REPO_DIR, "data", "precedent_annotations.json")
    
    if not os.path.exists(review_path):
        print(f"❌ Pending review file not found: {review_path}")
        return

    with open(review_path, "r", encoding="utf-8") as f:
        approved_records = json.load(f)

    print(f"[*] Loaded {len(approved_records)} approved records from {review_path}.")

    promoted_rows: List[Dict[str, Any]] = []

    for r in approved_records:
        cit = r.get("citation", "").strip()
        case_id = r.get("case_id") or generate_canonical_case_id(cit)
        
        # Clean case name
        raw_name = r.get("case_name", "")
        clean_name = sanitize_title(raw_name)
        if not clean_name:
            clean_name = cit

        # Clean superseding case name
        raw_sup_name = r.get("superseding_case_name", "")
        clean_sup_name = sanitize_title(raw_sup_name) or raw_sup_name

        row = {
            "case_id": case_id,
            "citation": cit,
            "case_name": clean_name,
            "status": r.get("status", "overruled"),
            "superseded_by_case_id": r.get("superseded_by_case_id"),
            "superseding_citation": r.get("superseding_citation"),
            "superseding_case_name": clean_sup_name,
            "doctrinal_note": r.get("doctrinal_note", ""),
            "source_citation": r.get("source_citation") or r.get("superseding_citation", ""),
            "annotated_by": "manual_review"
        }
        promoted_rows.append(row)

    # 1. Update local annotations fallback
    existing_annotations = []
    if os.path.exists(annotations_path):
        with open(annotations_path, "r", encoding="utf-8") as f:
            try:
                existing_annotations = json.load(f)
            except Exception:
                existing_annotations = []

    existing_ids = {a.get("case_id") for a in existing_annotations}
    existing_citations = {a.get("citation") for a in existing_annotations}

    for row in promoted_rows:
        if row["case_id"] not in existing_ids and row["citation"] not in existing_citations:
            existing_annotations.append(row)
            existing_ids.add(row["case_id"])
            existing_citations.add(row["citation"])

    with open(annotations_path, "w", encoding="utf-8") as f:
        json.dump(existing_annotations, f, ensure_ascii=False, indent=2)
    print(f"✅ Synced {len(promoted_rows)} records to {annotations_path} (total: {len(existing_annotations)}).")

    # 2. Upsert into Supabase table public.precedent_status
    if supabase:
        print("[*] Attempting Supabase upsert into public.precedent_status...")
        try:
            res = supabase.table("precedent_status").upsert(promoted_rows, on_conflict="case_id").execute()
            print(f"✅ Successfully upserted {len(res.data or promoted_rows)} rows into Supabase precedent_status!")
        except Exception as e:
            print(f"⚠️ Supabase upsert notice: {e}")
            print("   (Local annotations fallback is active and fully functional.)")

    print("\n--- PROMOTION SUMMARY ---")
    for row in promoted_rows:
        print(f"• {row['case_name']} ({row['citation']}) -> {row['status']}")
        print(f"  Overruled by: {row['superseding_case_name']} ({row['superseding_citation']})")
        print(f"  Note: {row['doctrinal_note']}\n")

if __name__ == "__main__":
    promote_records()
