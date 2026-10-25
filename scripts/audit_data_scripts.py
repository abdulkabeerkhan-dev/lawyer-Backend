"""
scripts/audit_data_scripts.py

ORDER 1.1 ITEM 10: DATA SCRIPTS AUDIT
Audits data modification scripts executed in Order 1.1.
Compares git HEAD (baseline before Order 1.1 corrections) with current working tree:
  - Record counts per enactment (before vs after)
  - Total word counts per enactment (before vs after)
  - Whole-file SHA-256 hashes (before vs after)
  - Record-level text hash changes for modified/added/downgraded provisions
"""

import os
import sys
import json
import hashlib
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

def sha256_text(t):
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()

def get_git_head_content(rel_path):
    cmd = ["git", "show", f"HEAD:{rel_path.replace(os.sep, '/')}"]
    res = subprocess.run(cmd, cwd=REPO_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode == 0:
        return res.stdout
    return None

def main():
    print("=" * 110)
    print("ORDER 1.1 ITEM 10: AUDIT OF DATA MODIFICATION SCRIPTS")
    print("=" * 110)
    print("Baseline Git Commit: HEAD")
    git_head_cmd = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_DIR, stdout=subprocess.PIPE, text=True)
    baseline_commit = git_head_cmd.stdout.strip()
    print(f"Commit Hash: {baseline_commit}")
    
    # 1. Summary of Data Modification Scripts Executed in Order 1.1
    print("\n" + "-" * 110)
    print("1. SUMMARY OF DATA MODIFICATION SCRIPTS RUN IN ORDER 1.1")
    print("-" * 110)
    scripts_info = [
        {
            "name": "scripts/order1_1_page_verified_audit.py",
            "purpose": "Audited 23 provisions tagged 'page_verified' across 7 enactments. Found 0 stored dual-layer OCR text or similarity metrics. Downgraded all 23 unearned records to 'ingested_unreviewed'. Set page_verified count strictly to 0.",
            "impact": "Tier downgrades: PPC (3), CPC (13), FIO (1), MFLO (1), ITO (3), Land Revenue (1), Arbitration (1)."
        },
        {
            "name": "scripts/ingest_verified_missing_provisions.py",
            "purpose": "Ingested missing provisions with authentic PDF page references, word counts, and SHA-256 hashes from data/official_pdfs/.",
            "impact": "Added/Replaced: PPC ss.415, 417; CPC s.96, O.XXI R.1, 2, 10, 11, 22, 30; TPA ss.58, 67, 69; Contract ss.126, 127, 129, 130, 133, 134, 135; BCO ss.27, 83 (verified heading 'Penalties'), 83A; Stamp s.35; Reg s.17; Limitation Art. 73, 80, 115, 116, 132, 181, 182."
        },
        {
            "name": "scripts/fix_r24_and_reg49.py",
            "purpose": "Ingested CPC Order XXI Rule 24 and Registration Act Section 49 from authentic PDF text layers.",
            "impact": "Added: CPC O.XXI R.24 (Page 107, 108 words); Registration Act Section 49 (Page 21, 75 words)."
        },
        {
            "name": "scripts/fix_contract_128.py",
            "purpose": "Corrected page offset for Contract Act Section 128 (extracted from authentic Page 43).",
            "impact": "Updated: Contract Act Section 128 (Page 43, 71 words, SHA-256 f9cd5312c4fd...)."
        }
    ]
    
    for s in scripts_info:
        print(f"Script:  {s['name']}")
        print(f"Purpose: {s['purpose']}")
        print(f"Impact:  {s['impact']}\n")

    # 2. Per-Act Statistics: Before (HEAD) vs After (Working Tree)
    print("-" * 110)
    print("2. PER-ACT METRICS: BASELINE (HEAD) VS CURRENT WORKING TREE")
    print("-" * 110)
    print(f"{'Enactment File':<28} | {'Records Before':<14} | {'Records After':<14} | {'Words Before':<12} | {'Words After':<12} | {'File SHA256 (After)'[:25]}")
    print("-" * 110)

    # Collect all json files in unified_statutes
    all_files = sorted(os.listdir(STATUTES_DIR))
    
    records_audit = []
    
    for fname in all_files:
        if not fname.endswith(".json"):
            continue
        curr_path = os.path.join(STATUTES_DIR, fname)
        rel_path = os.path.relpath(curr_path, REPO_DIR)
        
        # Read current
        with open(curr_path, "rb") as f:
            curr_bytes = f.read()
        curr_sha = sha256_bytes(curr_bytes)
        try:
            curr_data = json.loads(curr_bytes.decode("utf-8"))
        except Exception:
            curr_data = []
        def parse_items(data):
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                return [r for r in data.values() if isinstance(r, dict)]
            return []

        curr_items = parse_items(curr_data)
        curr_recs = len(curr_items)
        curr_words = sum(len((r.get("text") or "").split()) for r in curr_items)
        
        # Read HEAD
        head_bytes = get_git_head_content(rel_path)
        if head_bytes is not None:
            head_sha = sha256_bytes(head_bytes)
            try:
                head_data = json.loads(head_bytes.decode("utf-8"))
            except Exception:
                head_data = []
            head_items = parse_items(head_data)
            head_recs = len(head_items)
            head_words = sum(len((r.get("text") or "").split()) for r in head_items)
        else:
            head_sha = "NEW FILE (UNTRACKED)"
            head_items = []
            head_recs = 0
            head_words = 0
            
        print(f"{fname:<28} | {head_recs:<14} | {curr_recs:<14} | {head_words:<12} | {curr_words:<12} | {curr_sha[:20]}...")
        
        records_audit.append({
            "file": fname,
            "head_recs": head_recs,
            "curr_recs": curr_recs,
            "head_words": head_words,
            "curr_words": curr_words,
            "head_data": {r.get("canonical_id"): r for r in head_items if r.get("canonical_id")},
            "curr_data": {r.get("canonical_id"): r for r in curr_items if r.get("canonical_id")}
        })

    # 3. Provision-Level Hash and Content Mutation Audit
    print("\n" + "-" * 110)
    print("3. PROVISION-LEVEL MUTATION & TEXT HASH AUDIT FOR TARGET RECOVERY / ORDER 1.1 PROVISIONS")
    print("-" * 110)
    print(f"{'Canonical ID':<30} | {'Action':<10} | {'Tier (Before -> After)':<30} | {'Words':<10} | {'Text SHA256 (After)'}")
    print("-" * 110)

    target_cids = [
        "PPC_1860_SEC_409", "PPC_1860_SEC_420", "PPC_1860_SEC_489F", "PPC_1860_SEC_415", "PPC_1860_SEC_417",
        "CPC_1908_SEC_96", "CPC_1908_ORD_XXI_R_1", "CPC_1908_ORD_XXI_R_2", "CPC_1908_ORD_XXI_R_10",
        "CPC_1908_ORD_XXI_R_11", "CPC_1908_ORD_XXI_R_22", "CPC_1908_ORD_XXI_R_24", "CPC_1908_ORD_XXI_R_30",
        "CPC_1908_ORD_XXXIX_R_1", "CPC_1908_ORD_XXXIX_R_2", "CPC_1908_ORD_XXXIX_R_2A",
        "FIO_2001_SEC_10", "FIO_2001_SEC_22",
        "LIMITATION_1908_ART_73", "LIMITATION_1908_ART_80", "LIMITATION_1908_ART_115",
        "LIMITATION_1908_ART_116", "LIMITATION_1908_ART_132", "LIMITATION_1908_ART_181", "LIMITATION_1908_ART_182",
        "TPA_1882_SEC_58", "TPA_1882_SEC_67", "TPA_1882_SEC_69",
        "CONTRACT_1872_SEC_126", "CONTRACT_1872_SEC_127", "CONTRACT_1872_SEC_128", "CONTRACT_1872_SEC_129",
        "CONTRACT_1872_SEC_130", "CONTRACT_1872_SEC_133", "CONTRACT_1872_SEC_134", "CONTRACT_1872_SEC_135",
        "BCO_1962_SEC_27", "BCO_1962_SEC_83", "BCO_1962_SEC_83A",
        "STAMP_1899_SEC_35", "REGISTRATION_1908_SEC_17", "REGISTRATION_1908_SEC_49"
    ]

    all_curr_map = {}
    all_head_map = {}
    for ra in records_audit:
        all_curr_map.update(ra["curr_data"])
        all_head_map.update(ra["head_data"])

    for cid in target_cids:
        head_rec = all_head_map.get(cid)
        curr_rec = all_curr_map.get(cid)
        
        if not head_rec and curr_rec:
            action = "ADDED"
            tier_str = f"N/A -> {curr_rec.get('tier')}"
            words = len((curr_rec.get("text") or "").split())
            t_hash = sha256_text(curr_rec.get("text"))[:16]
        elif head_rec and curr_rec:
            h_tier = head_rec.get("tier")
            c_tier = curr_rec.get("tier")
            h_text = head_rec.get("text") or ""
            c_text = curr_rec.get("text") or ""
            words = len(c_text.split())
            t_hash = sha256_text(c_text)[:16]
            if h_text != c_text and h_tier != c_tier:
                action = "MOD+DOWN"
                tier_str = f"{h_tier} -> {c_tier}"
            elif h_text != c_text:
                action = "TEXT_MOD"
                tier_str = f"{h_tier} -> {c_tier}"
            elif h_tier != c_tier:
                action = "DOWNGRADE"
                tier_str = f"{h_tier} -> {c_tier}"
            else:
                action = "UNCHANGED"
                tier_str = f"{c_tier}"
        elif head_rec and not curr_rec:
            action = "DELETED"
            tier_str = f"{head_rec.get('tier')} -> DELETED"
            words = 0
            t_hash = "N/A"
        else:
            action = "NOT_FOUND"
            tier_str = "N/A"
            words = 0
            t_hash = "N/A"

        print(f"{cid:<30} | {action:<10} | {tier_str:<30} | {words:<10} | {t_hash}")
    print("=" * 110)

if __name__ == "__main__":
    main()
