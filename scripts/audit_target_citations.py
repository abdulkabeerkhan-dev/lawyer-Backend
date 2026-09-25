"""
Audit and Gap Analysis Script for Tier 1 Precedents (PLD & SCMR)
Cross-references pakistan_law_site_citations.csv against Supabase full_judgments
and Pinecone judgments namespace.
"""
import os
import sys
import csv
import json
import re
import time
import sqlite3
from typing import Dict, List, Set, Tuple, Any

WORKSPACE_DIR = r"C:\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
SCRATCH_DIR = r"C:\Users\kabeer\.gemini\antigravity\brain\5ce49601-04d3-4264-9d73-e9af4be35593\scratch"
CSV_PATH = r"C:\Users\kabeer\Pictures\pakistan_law_site_citations.csv"
DB_PATH = os.path.join(SCRATCH_DIR, "supabase_catalog.db")
PINECONE_VECTORS_PATH = os.path.join(SCRATCH_DIR, "pinecone_vector_ids.json")

REINDEX_QUEUE_PATH = os.path.join(WORKSPACE_DIR, "reindex_queue.json")
TARGET_FETCH_QUEUE_PATH = os.path.join(WORKSPACE_DIR, "target_fetch_queue.json")
SUMMARY_REPORT_PATH = os.path.join(SCRATCH_DIR, "audit_summary_report.json")

DOMAIN_WHITELIST = [
    "supremecourt.gov.pk",
    "lhc.gov.pk",
    "shc.gov.pk",
    "phc.gov.pk",
    "ihc.gov.pk",
    "balochistanhighcourt.gov.pk",
    "federalshariatcourt.gov.pk"
]

COURT_ALIASES = {
    "SUPREME-COURT": ["SC", "SUPREME COURT", "SUPREME-COURT", "S.C."],
    "LAHORE-HIGH-COURT-LAHORE": ["LAH", "LHC", "LAHORE", "LAHORE-HIGH-COURT-LAHORE"],
    "KARACHI-HIGH-COURT-SINDH": ["KAR", "SHC", "SINDH", "KARACHI", "KARACHI-HIGH-COURT-SINDH"],
    "PESHAWAR-HIGH-COURT": ["PESH", "PHC", "PESHAWAR", "PESHAWAR-HIGH-COURT"],
    "QUETTA-HIGH-COURT-BALOCHISTAN": ["QTA", "BHC", "QUETTA", "BALOCHISTAN", "QUETTA-HIGH-COURT-BALOCHISTAN"],
    "ISLAMABAD": ["ISL", "IHC", "ISLAMABAD"],
    "FEDERAL-SHARIAT-COURT": ["FSC", "FEDERAL SHARIAT COURT", "FEDERAL-SHARIAT-COURT"],
    "HIGH-COURT-AZAD-KASHMIR": ["AJK", "AZAD KASHMIR", "HIGH-COURT-AZAD-KASHMIR"],
    "SUPREME-COURT-AZAD-KASHMIR": ["SC (AJ&K)", "SC AJK", "SCAJK", "SUPREME-COURT-AZAD-KASHMIR"],
    "DHAKA-HIGH-COURT": ["DACCA", "DHAKA", "EAST PAKISTAN", "DHAKA-HIGH-COURT"],
    "FEDERAL-CONSTITUTIONAL-COURT": ["FCC", "FEDERAL-CONSTITUTIONAL-COURT"],
    "PRIVY-COUNCIL": ["PC", "PRIVY COUNCIL"],
    "FEDERAL-COURT-OF-PAKISTAN": ["FC", "FEDERAL COURT"]
}


def normalize_cit_key(s: str) -> str:
    """Normalize citation by stripping non-alphanumerics."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def main():
    print("=" * 70)
    print("STARTING STRICT NON-DESTRUCTIVE AUDIT & GAP ANALYSIS")
    print("=" * 70)
    
    # 1. Load Pinecone base case IDs
    print(f"\n[Step 1] Loading Pinecone indexed vectors from {PINECONE_VECTORS_PATH}...")
    with open(PINECONE_VECTORS_PATH, "r", encoding="utf-8") as f:
        pc_data = json.load(f)
    
    pc_base_cases: Set[str] = set(x.upper() for x in pc_data.get("base_case_ids", []))
    pc_normalized: Set[str] = set(normalize_cit_key(x) for x in pc_base_cases)
    print(f"Loaded {pc_data.get('total_vectors', 0)} vectors across {len(pc_base_cases)} unique base case IDs in Pinecone 'judgments' namespace.")

    # 2. Load Supabase Catalog from local SQLite DB
    print(f"\n[Step 2] Loading Supabase full_judgments catalog from {DB_PATH}...")
    t0 = time.time()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT case_id, neutral_citation, court_name, case_title, decision_date FROM full_judgments_catalog")
    supabase_rows = c.fetchall()
    conn.close()
    print(f"Loaded {len(supabase_rows)} Supabase records in {time.time()-t0:.2f}s.")

    # Build multi-tier in-memory index for Supabase
    print("Indexing Supabase records into multi-tier lookup structures...")
    case_id_map: Dict[str, Tuple] = {}
    neutral_cit_map: Dict[str, Tuple] = {}
    normalized_map: Dict[str, Tuple] = {}
    j_y_p_map: Dict[Tuple[str, str, str], List[Tuple]] = {}

    for r in supabase_rows:
        cid, nc, court, title, d_date = r
        cid_u = (cid or "").strip().upper()
        nc_u = (nc or "").strip().upper()

        if cid_u:
            case_id_map[cid_u] = r
            normalized_map[normalize_cit_key(cid_u)] = r
        if nc_u:
            neutral_cit_map[nc_u] = r
            normalized_map[normalize_cit_key(nc_u)] = r

        # Parse journal, year, page
        m = re.search(r"\b(19\d\d|20\d\d)[_\s]+([A-Z]+)[_\s]+(?:([A-Za-z]+)[_\s]+)?(\d+)\b", f"{cid_u} {nc_u}")
        if m:
            yr, jr, crt_abbr, pg = m.group(1), m.group(2), (m.group(3) or "").upper(), m.group(4)
            j_y_p_map.setdefault((jr, yr, pg), []).append((r, crt_abbr))

    print(f"Multi-tier indexing complete: {len(case_id_map)} case_ids, {len(neutral_cit_map)} neutral citations, {len(j_y_p_map)} (journal, year, page) buckets.")

    # 3. Read and Cross-Reference Target CSV (PLD & SCMR)
    print(f"\n[Step 3] Cross-referencing target dataset: {CSV_PATH}...")
    t_audit_start = time.time()

    list_a_found: List[Dict[str, Any]] = []
    list_b_missing: List[Dict[str, Any]] = []

    set_verified_active: List[Dict[str, Any]] = []
    set_needs_embedding: List[Dict[str, Any]] = []
    reindex_case_ids: Set[str] = set()

    pld_audited = 0
    scmr_audited = 0

    with open(CSV_PATH, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            journal = (row.get("journal") or "").strip().upper()
            if journal not in ("PLD", "SCMR"):
                continue

            if journal == "PLD":
                pld_audited += 1
            else:
                scmr_audited += 1

            raw_cit = (row.get("citation") or row.get("\ufeffcitation") or "").strip()
            cit_upper = raw_cit.upper()
            court_raw = (row.get("court") or "").strip().upper()
            year = (row.get("year") or "").strip()
            title = (row.get("title") or "").strip()
            details = (row.get("details") or "").strip()

            matched_supa_row = None

            # Attempt 1: Direct exact match on neutral_citation
            if cit_upper in neutral_cit_map:
                matched_supa_row = neutral_cit_map[cit_upper]

            # Attempt 2: Direct match on case_id with underscore
            if not matched_supa_row:
                under_cit = cit_upper.replace(" ", "_")
                if under_cit in case_id_map:
                    matched_supa_row = case_id_map[under_cit]

            # Attempt 3: Normalized alphanumeric match
            if not matched_supa_row:
                norm_key = normalize_cit_key(cit_upper)
                if norm_key in normalized_map:
                    matched_supa_row = normalized_map[norm_key]

            # Attempt 4: Multi-court bucket matching on (journal, year, page)
            if not matched_supa_row:
                parts = cit_upper.split()
                if len(parts) >= 3:
                    yr, jr, pg = parts[0], parts[1], parts[2]
                    bucket = j_y_p_map.get((jr, yr, pg), [])
                    if len(bucket) == 1:
                        matched_supa_row = bucket[0][0]
                    elif len(bucket) > 1:
                        # Find best match by court alias
                        target_aliases = COURT_ALIASES.get(court_raw, [court_raw])
                        for cand_r, crt_abbr in bucket:
                            cand_title = (cand_r[3] or "").upper()
                            cand_court = (cand_r[2] or "").upper()
                            cand_cid = (cand_r[0] or "").upper()
                            if any(a in cand_title or a in cand_court or a in cand_cid for a in target_aliases):
                                matched_supa_row = cand_r
                                break
                            if crt_abbr and any(crt_abbr == a for a in target_aliases):
                                matched_supa_row = cand_r
                                break
                        if not matched_supa_row:
                            matched_supa_row = bucket[0][0]

            # Segment into LIST_A vs LIST_B
            if matched_supa_row:
                supa_case_id = matched_supa_row[0]
                supa_neutral_cit = matched_supa_row[1]
                supa_court = matched_supa_row[2]
                supa_title = matched_supa_row[3]

                item_a = {
                    "target_citation": raw_cit,
                    "journal": journal,
                    "year": year,
                    "court": court_raw,
                    "target_title": title,
                    "supabase_case_id": supa_case_id,
                    "supabase_neutral_citation": supa_neutral_cit,
                    "supabase_court": supa_court,
                    "supabase_title": supa_title
                }
                list_a_found.append(item_a)

                # Pinecone Verification
                cid_u = supa_case_id.upper()
                norm_cid = normalize_cit_key(supa_case_id)
                norm_t_cit = normalize_cit_key(raw_cit)

                is_in_pinecone = (
                    cid_u in pc_base_cases or
                    norm_cid in pc_normalized or
                    norm_t_cit in pc_normalized
                )

                if is_in_pinecone:
                    set_verified_active.append(item_a)
                else:
                    set_needs_embedding.append(item_a)
                    reindex_case_ids.add(supa_case_id)
            else:
                list_b_missing.append({
                    "citation": raw_cit,
                    "journal": journal,
                    "year": year,
                    "court": court_raw,
                    "title": title,
                    "details": details,
                    "target_domain_whitelist": DOMAIN_WHITELIST
                })

    elapsed_audit = time.time() - t_audit_start
    total_audited = pld_audited + scmr_audited

    print(f"\nAudit completed in {elapsed_audit:.2f}s:")
    print(f"  * Total PLD Citations Audited: {pld_audited:,}")
    print(f"  * Total SCMR Citations Audited: {scmr_audited:,}")
    print(f"  * Total Target Audited: {total_audited:,}")
    print(f"  * Found in Supabase (LIST_A): {len(list_a_found):,}")
    print(f"  * Missing from Supabase (LIST_B): {len(list_b_missing):,}")
    print(f"  * Verified Active in Pinecone (SET_VERIFIED_ACTIVE): {len(set_verified_active):,}")
    print(f"  * Stored in Supabase Needing Embedding (SET_NEEDS_EMBEDDING): {len(set_needs_embedding):,}")
    print(f"  * Unique Supabase case_ids in Reindex Queue: {len(reindex_case_ids):,}")

    # 4. Generate Output Deliverables
    print("\n[Step 4] Generating output deliverables...")

    # A. reindex_queue.json
    sorted_reindex_ids = sorted(list(reindex_case_ids))
    with open(REINDEX_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted_reindex_ids, f, indent=2)
    print(f"  [OK] Exported reindex queue to: {REINDEX_QUEUE_PATH} ({len(sorted_reindex_ids):,} case_ids)")

    # B. target_fetch_queue.json
    # Format per specification: {"citation": "...", "journal": "...", "year": "...", "target_domain_whitelist": [...]}
    formatted_fetch_queue = []
    for item in list_b_missing:
        formatted_fetch_queue.append({
            "citation": item["citation"],
            "journal": item["journal"],
            "year": item["year"],
            "court": item["court"],
            "title": item["title"],
            "target_domain_whitelist": item["target_domain_whitelist"]
        })

    with open(TARGET_FETCH_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(formatted_fetch_queue, f, indent=2)
    print(f"  [OK] Exported target fetch queue to: {TARGET_FETCH_QUEUE_PATH} ({len(formatted_fetch_queue):,} missing citations)")

    # C. audit_summary_report.json
    summary_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scope": "Tier 1 (PLD & SCMR)",
        "total_audited": total_audited,
        "pld_audited": pld_audited,
        "scmr_audited": scmr_audited,
        "list_a_found_in_supabase": len(list_a_found),
        "list_b_missing_from_supabase": len(list_b_missing),
        "set_verified_active": len(set_verified_active),
        "set_needs_embedding": len(set_needs_embedding),
        "unique_case_ids_needs_embedding": len(sorted_reindex_ids),
        "files_generated": {
            "reindex_queue": REINDEX_QUEUE_PATH,
            "target_fetch_queue": TARGET_FETCH_QUEUE_PATH
        }
    }
    with open(SUMMARY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)
    print(f"  [OK] Exported audit summary report to: {SUMMARY_REPORT_PATH}")

    print("\n" + "=" * 70)
    print("AUDIT COMPLETE — AWAITING EXPLICIT USER CONFIRMATION")
    print("No insert, update, or scrape commands were executed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
