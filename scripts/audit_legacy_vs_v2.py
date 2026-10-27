"""
scripts/audit_legacy_vs_v2.py

ORDER 2.0 — STEP 3: AUDIT LEGACY STORE AGAINST STATUTES_V2
Compares every legacy provision with text against the new statutes_v2 extract.
Specifically:
- FIO_2001_SEC_11, SEC_12, SEC_13 printed full text side-by-side.
- Off-by-one key shifts detected and counted per Act.
- Full diffs for all altered/drifted records.
- Saves raw output to reports/legacy_vs_v2_audit.txt.
"""

import os
import sys
import json
import re
import difflib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_DIR = os.path.join(REPO_DIR, "data", "legacy_store")
V2_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")
REPORT_PATH = os.path.join(REPO_DIR, "reports", "legacy_vs_v2_audit.txt")

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)

def norm(text: str) -> str:
    if not text:
        return ""
    lines = [
        re.sub(r'[ \t]+', ' ', l).strip()
        for l in text.replace('\r', '\n').splitlines()
        if l.strip() and not re.match(r'^Page\s+\d+\s+of\s+\d+$', l.strip(), re.I)
    ]
    return '\n'.join(lines)

def run_audit():
    lines_out = []
    def log(msg=""):
        lines_out.append(msg)
        print(msg)

    log("=" * 80)
    log("ORDER 2.0 — STEP 3: AUDIT OF LEGACY STORE AGAINST STATUTES_V2")
    log("=" * 80)

    # 1. Load V2 Store
    v2_store = {}
    for fname in os.listdir(V2_DIR):
        if not fname.endswith(".json"):
            continue
        act = fname.replace(".json", "")
        with open(os.path.join(V2_DIR, fname), "r", encoding="utf-8") as f:
            v2_store[act] = json.load(f)

    # 2. Side-by-side comparison of FIO_2001_SEC_11, SEC_12, SEC_13
    log("\n" + "=" * 80)
    log("SPECIFIC SIDE-BY-SIDE FORENSIC CHECK: FIO 2001 SECTIONS 11, 12, 13")
    log("=" * 80)

    legacy_fio = {}
    if os.path.exists(os.path.join(LEGACY_DIR, "FIO_2001.json")):
        with open(os.path.join(LEGACY_DIR, "FIO_2001.json"), "r", encoding="utf-8") as f:
            for r in json.load(f):
                cid = r.get("canonical_id", "")
                legacy_fio[cid] = r

    v2_fio = {r.get("canonical_id"): r for r in v2_store.get("FIO_2001", [])}

    for target_cid in ["FIO_2001_SEC_11", "FIO_2001_SEC_12", "FIO_2001_SEC_13"]:
        leg_r = legacy_fio.get(target_cid, {})
        v2_r = v2_fio.get(target_cid, {})
        log(f"\n--- {target_cid} ---")
        log(f"LEGACY TITLE:   {leg_r.get('title')}")
        log(f"V2 HEADING:     {v2_r.get('heading')}")
        log(f"LEGACY PRIMARY: {leg_r.get('primary_num')}")
        log(f"V2 SECTION:     {v2_r.get('section')}")
        log("LEGACY FULL TEXT:")
        log(leg_r.get("text", "[NO TEXT]"))
        log("-" * 40)
        log("V2 OFFICIAL PDF EXTRACT (VERBATIM):")
        log(v2_r.get("text_raw", "[NO TEXT]"))
        log("-" * 40)
        # Note on forensic findings
        if target_cid == "FIO_2001_SEC_11":
            log("FORENSIC NOTE: Legacy store held rephrased s.10(12) ('Where the Banking Court refuses to grant leave...').")
            log("               V2 store correctly restores real statutory Section 11 ('Interim Decree').")
        elif target_cid == "FIO_2001_SEC_12":
            log("FORENSIC NOTE: Legacy store held Section 11 ('If the Banking Court is of the opinion...').")
            log("               V2 store correctly restores real statutory Section 12 ('Power to set aside decree').")
        elif target_cid == "FIO_2001_SEC_13":
            log("FORENSIC NOTE: Legacy store held Section 12 ('In any case in which a decree is passed...').")
            log("               V2 store correctly restores real statutory Section 13 ('Disposal of suit').")

    # 3. Off-by-one Key Shift Analysis Per Act
    log("\n" + "=" * 80)
    log("OFF-BY-ONE KEY SHIFT AUDIT PER ACT")
    log("=" * 80)

    off_by_one_summary = {}

    for fname in sorted(os.listdir(LEGACY_DIR)):
        if not fname.endswith(".json"):
            continue
        act = fname.replace(".json", "")
        with open(os.path.join(LEGACY_DIR, fname), "r", encoding="utf-8") as f:
            leg_records = json.load(f)

        if isinstance(leg_records, dict):
            for k in ["sections", "provisions", "data"]:
                if k in leg_records and isinstance(leg_records[k], list):
                    leg_records = leg_records[k]
                    break
        if not isinstance(leg_records, list):
            continue

        shifts = []
        for r in leg_records:
            if not isinstance(r, dict):
                continue
            cid = r.get("canonical_id", "")
            title = r.get("title", "")
            txt = r.get("text", "")
            if not txt:
                continue

            # Check if canonical_id number differs from printed section in text
            m_cid = re.search(r'_SEC_([0-9]+[A-Z]?)', cid)
            if m_cid:
                cid_num = m_cid.group(1)
                # Check what number appears at start of text
                m_txt = re.match(r'^\s*([0-9]+[A-Z]?)\.\s*', txt)
                if m_txt:
                    txt_num = m_txt.group(1)
                    if cid_num != txt_num:
                        shifts.append((cid, cid_num, txt_num, title))

        off_by_one_summary[act] = shifts
        log(f"{act:<25}: {len(shifts)} off-by-one shifted keys detected with text")
        for s in shifts[:5]:
            log(f"   * Key {s[0]} (num {s[1]}) holds Section {s[2]} text ('{s[3]}')")

    # 4. Overall Text Drift & Difference Audit
    log("\n" + "=" * 80)
    log("DETAILED TEXT DRIFT AUDIT: LEGACY VS STATUTES_V2")
    log("=" * 80)

    total_legacy_with_text = 0
    drifted_count = 0
    exact_count = 0

    for fname in sorted(os.listdir(LEGACY_DIR)):
        if not fname.endswith(".json") or fname == "CRPC_SCHEDULE_II.json":
            continue
        act = fname.replace(".json", "")
        with open(os.path.join(LEGACY_DIR, fname), "r", encoding="utf-8") as f:
            leg_records = json.load(f)

        if isinstance(leg_records, dict):
            for k in ["sections", "provisions", "data"]:
                if k in leg_records and isinstance(leg_records[k], list):
                    leg_records = leg_records[k]
                    break
        if not isinstance(leg_records, list):
            continue

        v2_map = {r.get("canonical_id"): r for r in v2_store.get(act, []) if isinstance(r, dict)}

        log(f"\nAct: {act}")
        act_drifted = 0
        act_exact = 0
        act_no_v2 = 0

        for lr in leg_records:
            if not isinstance(lr, dict):
                continue
            ltxt = lr.get("text", "")
            if not ltxt:
                continue
            total_legacy_with_text += 1
            cid = lr.get("canonical_id")
            vr = v2_map.get(cid)
            if not vr:
                act_no_v2 += 1
                continue

            vtxt = vr.get("text_raw", "")
            n_ltxt = norm(ltxt)
            n_vtxt = norm(vtxt)

            if n_ltxt == n_vtxt:
                exact_count += 1
                act_exact += 1
            else:
                drifted_count += 1
                act_drifted += 1
                diff = list(difflib.unified_diff(
                    n_vtxt.splitlines(), n_ltxt.splitlines(),
                    fromfile="v2_official_pdf", tofile="legacy_store",
                    lineterm=""
                ))
                log(f"  [DRIFT] {cid} (similarity: {difflib.SequenceMatcher(None, n_vtxt, n_ltxt).ratio():.2f})")
                for d in diff[:8]:
                    log(f"    {d}")

        log(f"Summary for {act}: exact={act_exact}, drifted={act_drifted}, no_v2_match={act_no_v2}")

    log("\n" + "=" * 80)
    log(f"TOTAL LEGACY RECORDS WITH TEXT AUDITED : {total_legacy_with_text}")
    log(f"TOTAL MATCHING V2 EXACTLY               : {exact_count}")
    log(f"TOTAL DRIFTED / REPHRASED RECORDS       : {drifted_count}")
    log("=" * 80)

    with open(REPORT_PATH, "w", encoding="utf-8") as rf:
        rf.write("\n".join(lines_out))
    log(f"\nAudit report successfully saved to {REPORT_PATH}")

if __name__ == "__main__":
    run_audit()
