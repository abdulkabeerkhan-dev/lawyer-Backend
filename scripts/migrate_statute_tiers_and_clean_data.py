import os
import sys
import json
import re

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from core.statute_tiers import normalize_statute_tier, StatuteTier
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def migrate_tiers():
    total_files = 0
    total_provisions = 0
    for fname in os.listdir(UNIFIED_DIR):
        if not fname.endswith(".json"): continue
        fpath = os.path.join(UNIFIED_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as fp:
            records = json.load(fp)
        
        if isinstance(records, dict):
            for k in ["sections", "provisions", "data"]:
                if k in records and isinstance(records[k], list):
                    records = records[k]
                    break
        if not isinstance(records, list):
            continue

        modified = False
        for r in records:
            if not isinstance(r, dict):
                continue
            old_tier = r.get("tier")
            new_tier = normalize_statute_tier(old_tier)
            if old_tier != new_tier:
                r["tier"] = new_tier
                r["verification_status"] = new_tier
                modified = True
            total_provisions += 1
            
        if fname == "LIMITATION_1908.json":
            for r in records:
                cid = str(r.get("canonical_id", ""))
                txt = str(r.get("text", "")).strip()
                title = str(r.get("title", "")).strip()
                # 1. Sections 1-29 placeholder cleanup
                if "_SEC_" in cid:
                    if "Statutory provision under Limitation Act" in txt or txt == f"{title}. Statutory provision under Limitation Act, 1908.":
                        r["text"] = ""
                        r["tier"] = StatuteTier.TITLE_ONLY.value
                        r["verification_status"] = StatuteTier.TITLE_ONLY.value
                        r["missing_reason"] = "Official bare-act text not yet ingested into verified store"
                        modified = True
                # 2. Schedule articles re-tag
                elif "_ART_" in cid:
                    num = str(r.get("primary_num", ""))
                    if num == "64A":
                        r["tier"] = StatuteTier.DISPUTED.value
                        r["verification_status"] = StatuteTier.DISPUTED.value
                        r["missing_reason"] = "Article 64A disputed pending official gazette page proof"
                        modified = True
                    elif txt and not txt.startswith("Statutory provision"):
                        # Genuine schedule row
                        r["tier"] = StatuteTier.INGESTED_UNREVIEWED.value
                        r["verification_status"] = StatuteTier.INGESTED_UNREVIEWED.value
                        r["missing_reason"] = None
                        modified = True

        elif fname == "PPC_1860.json":
            for r in records:
                txt = str(r.get("text", "")).strip()
                # Identify synthetic boilerplate
                if "This statutory provision stands enacted as Section" in txt:
                    r["text"] = ""
                    r["tier"] = StatuteTier.TITLE_ONLY.value
                    r["verification_status"] = StatuteTier.TITLE_ONLY.value
                    r["missing_reason"] = "Official bare-act text not yet ingested into verified store"
                    modified = True

        if modified:
            with open(fpath, "w", encoding="utf-8") as fp:
                json.dump(records, fp, indent=2, ensure_ascii=False)
            total_files += 1

    print(f"Migration complete: {total_files} files updated across {total_provisions} provisions.")

if __name__ == "__main__":
    migrate_tiers()
