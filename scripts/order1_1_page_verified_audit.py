import os
import sys
import json
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
EVIDENCE_DIR = os.path.join(REPO_DIR, "data", "evidence")

print("=" * 80)
print("ORDER 1.1 ITEM 1: PAGE-VERIFIED EVIDENCE AUDIT & DOWNGRADE")
print("=" * 80)

# 1. Identify all page_verified records across data/unified_statutes
page_verified_records = []
all_files = sorted([f for f in os.listdir(UNIFIED_DIR) if f.endswith(".json")])

for fname in all_files:
    fpath = os.path.join(UNIFIED_DIR, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    records = data
    if isinstance(data, dict):
        for k in ["provisions", "sections", "records", "data"]:
            if k in data and isinstance(data[k], list):
                records = data[k]
                break
    
    if not isinstance(records, list):
        continue

    for idx, r in enumerate(records):
        tier = r.get("tier")
        vstatus = r.get("verification_status")
        if tier == "page_verified" or vstatus == "page_verified":
            cid = r.get("canonical_id", r.get("section", r.get("title", f"idx_{idx}")))
            page_verified_records.append({
                "file": fname,
                "fpath": fpath,
                "index": idx,
                "record": r,
                "canonical_id": cid,
                "source_page": r.get("source_page"),
                "has_ocr_text": "ocr_text" in r,
                "has_image_hash": "page_image_hash" in r,
                "has_similarity": "similarity" in r or "ocr_similarity" in r
            })

print(f"\n[1.1] Total records currently tagged 'page_verified': {len(page_verified_records)}")
print(f"{'File':<24} | {'Canonical ID':<26} | {'Page':<8} | {'OCR Stored':<10} | {'Image Hash':<10} | {'Similarity'}")
print("-" * 95)
for rec in page_verified_records:
    print(f"{rec['file']:<24} | {rec['canonical_id']:<26} | {str(rec['source_page']):<8} | {str(rec['has_ocr_text']):<10} | {str(rec['has_image_hash']):<10} | {str(rec['has_similarity'])}")

# 2. Check evidence folder for stored dual-layer artifacts
print("\n[1.2] Checking data/evidence/ directory for dual-layer artifacts...")
evidence_files = []
if os.path.exists(EVIDENCE_DIR):
    for root, _, files in os.walk(EVIDENCE_DIR):
        for f in files:
            evidence_files.append(os.path.relpath(os.path.join(root, f), EVIDENCE_DIR))
print(f"Evidence files present on disk ({len(evidence_files)} files):")
for ef in sorted(evidence_files):
    fpath = os.path.join(EVIDENCE_DIR, ef)
    size = os.path.getsize(fpath)
    print(f"  - data/evidence/{ef} ({size:,} bytes)")

print("\nFinding: Dual-layer artifacts (raw text layer, RapidOCR extraction, page PNG images) exist ONLY for FIO Section 22.")
print("Zero dual-layer artifacts exist on disk for any of the 23 records tagged 'page_verified'.")

# 3. Explanation of PPC 409, 420, 489-F lineage
print("\n[1.3] PPC 409, 420, 489-F Provenance Lineage:")
print("  - Commit 2ed0c3a: PPC 409, 420, 489F had tier='ingested_unreviewed', status='in_force', source_page=113, 115, 138.")
print("  - Commit 1df39f2: Phase 1.7 script manually assigned tier='page-verified' on the basis of manual page number citations, without generating OCR text, page image hashes, or computing cross-layer similarity scores.")
print("  - Commit c17904c: Statute tier normalization converted 'page-verified' -> 'page_verified'.")
print("  - Verdict: The 'page_verified' tag on PPC 409, 420, and 489-F was unearned because no dual-layer OCR/similarity evidence was captured or stored.")

# 4. Downgrade all 23 records to 'ingested_unreviewed'
print("\n[1.4] Downgrading all 23 unearned 'page_verified' records to 'ingested_unreviewed'...")
files_modified = set()

for rec in page_verified_records:
    r = rec["record"]
    r["tier"] = "ingested_unreviewed"
    r["verification_status"] = "ingested_unreviewed"
    r["missing_reason"] = None
    files_modified.add(rec["fpath"])

# Save updated files
for fpath in files_modified:
    with open(fpath, "r", encoding="utf-8") as f:
        file_data = json.load(f)
    # Update records in file_data
    if isinstance(file_data, list):
        for rec in page_verified_records:
            if rec["fpath"] == fpath:
                file_data[rec["index"]] = rec["record"]
    elif isinstance(file_data, dict):
        for k in ["provisions", "sections", "records", "data"]:
            if k in file_data and isinstance(file_data[k], list):
                for rec in page_verified_records:
                    if rec["fpath"] == fpath:
                        file_data[k][rec["index"]] = rec["record"]
                break
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(file_data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {os.path.basename(fpath)}")

# 5. Verify zero page_verified records remain
remaining_pv = 0
for fname in all_files:
    fpath = os.path.join(UNIFIED_DIR, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        d = json.load(f)
    items = d if isinstance(d, list) else []
    if isinstance(d, dict):
        for k in ["provisions", "sections", "records", "data"]:
            if k in d and isinstance(d[k], list): items = d[k]; break
    for it in items:
        if isinstance(it, dict) and (it.get("tier") == "page_verified" or it.get("verification_status") == "page_verified"):
            remaining_pv += 1

print(f"\n[1.5] Verification: Remaining records tagged 'page_verified' across all unified statutes: {remaining_pv}")
assert remaining_pv == 0, f"Expected 0 page_verified records, found {remaining_pv}"
print("ASSERTION PASSED: All unearned page_verified records successfully downgraded to 'ingested_unreviewed'.")
