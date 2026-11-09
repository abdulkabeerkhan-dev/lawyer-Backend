"""
scripts/export_turso_to_json.py

Exports statutory provisions from Turso LibSQL database into data/statutes_v2/<ACT_CODE>.json.
Mandatory pre-deploy step to ensure in-memory statute catalog never diverges from Turso.
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TURSO_URL = os.environ.get(
    "TURSO_DATABASE_URL_PIPELINE",
    "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
)
TURSO_TOKEN = os.environ.get(
    "TURSO_AUTH_TOKEN",
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"
)

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def execute_query(sql: str, args: list = None, timeout: int = 15) -> list:
    stmt = {"sql": sql}
    if args:
        stmt["args"] = args
    payload = json.dumps({"requests": [{"type": "execute", "stmt": stmt}]}).encode("utf-8")
    req = urllib.request.Request(
        TURSO_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for r in data.get("results", []):
                    res = r.get("response", {}).get("result", {})
                    cols = [c["name"] for c in res.get("cols", [])]
                    rows = []
                    for row in res.get("rows", []):
                        row_dict = {}
                        for i, cell in enumerate(row):
                            val = cell.get("value")
                            if cell.get("type") == "integer" and val is not None:
                                val = int(val)
                            row_dict[cols[i]] = val
                        rows.append(row_dict)
                    return rows
        except Exception as e:
            if attempt == 2:
                print(f"Error querying Turso: {e}", file=sys.stderr)
                raise
            time.sleep(1.0)
    return []

def run_export():
    print("=== Starting Export from Turso statute_provisions to data/statutes_v2/ ===")
    
    # 1. Get all acts that exist in data/statutes_v2 currently
    existing_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")]
    target_acts = set(f.replace(".json", "") for f in existing_files)
    
    # Also fetch all distinct act_codes with canonical IDs from Turso
    distinct_acts_res = execute_query("SELECT DISTINCT act_code FROM statute_provisions WHERE act_code IS NOT NULL;")
    turso_acts = set(r["act_code"].strip() for r in distinct_acts_res if r.get("act_code"))
    
    # Combine: prioritizes existing acts + any clean uppercase acts
    all_acts_to_export = target_acts.union({a for a in turso_acts if re.match(r'^[A-Z0-9_]+$', a)})
    print(f"Total target acts to export: {len(all_acts_to_export)}")
    
    total_provisions_exported = 0
    updated_files = 0
    
    for act in sorted(all_acts_to_export):
        rows = execute_query(
            "SELECT canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force, jurisdiction FROM statute_provisions WHERE act_code = ? ORDER BY rowid ASC;",
            args=[{"type": "text", "value": act}],
            timeout=20
        )
        if not rows:
            continue
        
        # Format into unified statute JSON schema
        json_records = []
        for r in rows:
            cid = r.get("canonical_id") or ""
            sec_num = str(r.get("section_num") or "").strip()
            title = r.get("title") or (f"Section {sec_num}" if sec_num else cid)
            text = (r.get("verbatim_text") or "").strip()
            
            is_art = "_ART_" in cid or "article" in title.lower() or "CONST" in act
            is_ord = "_ORD_" in cid or "order" in title.lower()
            is_rule = "_RULE_" in cid or "rule" in title.lower()
            
            p_type = "article" if is_art else ("order" if is_ord else ("rule" if is_rule else "section"))
            
            clean_num = re.sub(r'^(?:article|section|sec\.?|art\.?|order|ord\.?|rule)\s*', '', sec_num, flags=re.I).strip() or sec_num
            period = None
            trigger = None
            if "period of limitation:" in text.lower():
                m_p = re.search(r'Period of limitation:\s*([^\n\r.]+)', text, re.I)
                if m_p:
                    period = m_p.group(1).strip()
            if "time from which period begins to run:" in text.lower():
                m_t = re.search(r'Time from which period begins to run:\s*([^\n\r.]+)', text, re.I)
                if m_t:
                    trigger = m_t.group(1).strip()

            json_records.append({
                "canonical_id": cid,
                "act": r.get("act_code") or act,
                "act_code": r.get("act_code") or act,
                "act_name": r.get("act_name") or act.replace("_", " "),
                "section": sec_num,
                "primary_num": clean_num,
                "heading": title,
                "title": title,
                "provision_type": p_type,
                "period": period,
                "trigger": trigger,
                "text": text,
                "text_raw": text,
                "tier": r.get("tier") or "verified_golden",
                "quoting_allowed": True,
                "in_force": bool(r.get("in_force", 1)),
                "jurisdiction": r.get("jurisdiction") or "federal",
                "page_verified": True
            })
        
        safe_fname = re.sub(r'[/\\:*?"<>|]', '_', act) + ".json"
        fpath = os.path.join(OUTPUT_DIR, safe_fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(json_records, f, indent=2, ensure_ascii=False)
        
        total_provisions_exported += len(json_records)
        updated_files += 1
        print(f"  [OK] Exported {len(json_records):>4} provisions -> {safe_fname}")
    
    print("=" * 60)
    print(f"Export Completed: {total_provisions_exported} provisions written across {updated_files} JSON files.")
    
    # Verify Article 150 in LIMITATION_1908.json
    limitation_path = os.path.join(OUTPUT_DIR, "LIMITATION_1908.json")
    if os.path.exists(limitation_path):
        with open(limitation_path, "r", encoding="utf-8") as f:
            lim_data = json.load(f)
        art_150 = next((p for p in lim_data if p.get("canonical_id") == "LIMITATION_1908_ART_150"), None)
        if art_150:
            print("\nVerification of LIMITATION_1908_ART_150 in regenerated file:")
            print("  Title:", art_150.get("title"))
            print("  Text:\n" + art_150.get("text"))
            assert "Thirty days" in art_150.get("text"), "FAIL: Article 150 must contain 'Thirty days'"
            assert "When the loan is made" not in art_150.get("text"), "FAIL: Corrupted money lending text still present!"
            print("\n>>> CONFIRMED: Article 150 text is clean and verified! <<<")

if __name__ == "__main__":
    run_export()
