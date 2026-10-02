#!/usr/bin/env python3
"""
scripts/check_data_provenance.py

Pre-Commit Data Change Control Gate:
Blocks any git commit that adds or modifies data records under data/ without
verified provenance metadata:
1. source_url or file_path
2. fetch_date
3. content_hash (SHA-256 matching text)
4. source_type in {'official', 'licensed', 'user upload'}
5. Rejects any record beginning with unreviewed editorial or AI-authored markers.

Usage in git pre-commit hook or CI:
    python scripts/check_data_provenance.py [--all]
"""

import os
import sys
import json
import hashlib
import subprocess
from typing import List, Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALID_SOURCE_TYPES = {"official", "licensed", "user upload"}

def get_staged_data_files() -> List[str]:
    """Get list of staged files under data/ from git status."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "data/"],
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        files = [f.strip() for f in res.stdout.splitlines() if f.strip().endswith(".json")]
        return files
    except Exception:
        return []

def verify_record_provenance(record: Dict[str, Any], file_name: str) -> List[str]:
    errors = []
    
    # Check if text is present and text_available is true
    has_text = bool(record.get("text") or record.get("full_text"))
    text_avail = record.get("text_available", True)
    
    # If text is not present, ensure it is marked text_available=False or has source citation
    if not has_text:
        source = record.get("source_url") or record.get("source_citation") or record.get("source")
        if not source and text_avail is not False and record.get("status") != "Unreviewed":
            errors.append(f"Missing source or source_citation in {file_name} record ID: {record.get('id') or record.get('case_id') or record.get('canonical_id')}")
        return errors
        
    source = record.get("source_url") or record.get("file_path") or record.get("provenance_source")
    if not source:
        errors.append(f"Missing source_url or file_path in {file_name} record ID: {record.get('id') or record.get('case_id') or record.get('canonical_id')}")
        
    date_val = record.get("fetch_date") or record.get("fetched_at")
    if not date_val:
        errors.append(f"Missing fetch_date in {file_name} record ID: {record.get('id') or record.get('case_id') or record.get('canonical_id')}")
        
    stype = (record.get("source_type") or "").strip().lower()
    if stype not in VALID_SOURCE_TYPES:
        errors.append(f"Invalid or missing source_type '{stype}' in {file_name}. Must be in {VALID_SOURCE_TYPES}")
        
    txt = record.get("text") or record.get("full_text") or ""
    if txt:
        chash = record.get("content_hash")
        if not chash:
            errors.append(f"Missing content_hash for text in {file_name} record ID: {record.get('id') or record.get('case_id') or record.get('canonical_id')}")
        else:
            computed = hashlib.sha256(txt.encode("utf-8")).hexdigest()
            if chash != computed:
                errors.append(f"Content hash mismatch in {file_name} record ID: {record.get('id') or record.get('case_id') or record.get('canonical_id')}")
                
        if txt.strip().lower().startswith(("[editorial", "[ai-authored", "[synthetic", "[unreviewed", "[placeholder")):
            errors.append(f"Unreviewed editorial/synthetic marker detected in {file_name} record ID: {record.get('id') or record.get('case_id') or record.get('canonical_id')}")
            
    return errors

def check_file(fpath: str) -> List[str]:
    errors = []
    fname = os.path.basename(fpath)
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        records = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            if "procedures" in data:
                records = data["procedures"]
            elif "acts" in data:
                records = data["acts"]
            elif "records" in data:
                records = data["records"]
                
        for r in records:
            if isinstance(r, dict):
                errors.extend(verify_record_provenance(r, fname))
    except Exception as e:
        errors.append(f"Failed to read/parse {fname}: {e}")
    return errors

def main():
    check_all = "--all" in sys.argv
    if check_all:
        files = []
        for root, _, fnames in os.walk(os.path.join(WORKSPACE_DIR, "data")):
            for fn in fnames:
                if fn.endswith(".json") and not fn.startswith("audit_"):
                    files.append(os.path.join(root, fn))
    else:
        files = [os.path.join(WORKSPACE_DIR, f) for f in get_staged_data_files()]

    if not files:
        print("[DATA CHANGE CONTROL] No staged data files to check.")
        sys.exit(0)

    print(f"[DATA CHANGE CONTROL] Verifying provenance across {len(files)} data file(s)...")
    all_errors = []
    for f in files:
        errs = check_file(f)
        if errs:
            all_errors.extend(errs)

    if all_errors:
        print("\n❌ DATA CHANGE CONTROL REJECTED THE COMMIT:")
        for err in all_errors:
            print(f"  - {err}")
        print("\nAll data records added or modified under data/ must include verified provenance metadata.")
        print("Please obtain official source text with provenance before committing.")
        sys.exit(1)

    print("✅ [DATA CHANGE CONTROL] All data files verified for provenance.")
    sys.exit(0)

if __name__ == "__main__":
    main()
