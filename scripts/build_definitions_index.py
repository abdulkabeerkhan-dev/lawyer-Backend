"""
scripts/build_definitions_index.py

Extracts all statutory definitions across Pakistan Code and legacy staging.
Produces:
1. data/definitions_index.json: defined_term -> [ { act_code, section, canonical_id, definition_snippet } ]
2. reports/ambiguous_terms.json: terms defined in 2+ acts.
Confirms mappings for key terms like "willful default" -> FIO 2(g) and NAO 5(u).
"""

import json
import re
from pathlib import Path
from collections import defaultdict

STAGING_DIR = Path("D:/lawyer-Backend/data/statutes_v3_staging")
REPORTS_DIR = Path("D:/lawyer-Backend/reports")
DATA_DIR = Path("D:/lawyer-Backend/data")

def extract_definitions():
    # Regex patterns for statutory definitions in Pakistani legislation
    # e.g.:
    # (a) "court" means ...
    # (b) “willful default” means ...
    # "goods" includes ...
    # 'banking company' means ...
    def_term_pat = re.compile(
        r'(?:^|[\(\s\n])[\“\"\'\`\‘]([a-zA-Z0-9\s\-\/\(\)]+?)[\”\"\'\`\’]\s*(?:means|includes|shall\s+include|has\s+the\s+same\s+meaning|shall\s+have\s+the\s+meaning|shall\s+mean|a\s+person\s+or\s+a\s+holder|is\s+said\s+to\s+commit)\b',
        re.IGNORECASE
    )

    definitions_index = defaultdict(list)

    # Scan definition provisions across staging
    for fpath in STAGING_DIR.glob("*.json"):
        if fpath.name == "statutes_v2_legacy.json":
            with open(fpath, "r", encoding="utf-8") as fp:
                records = json.load(fp)
        else:
            with open(fpath, "r", encoding="utf-8") as fp:
                records = json.load(fp)

        if not isinstance(records, list):
            continue

        for r in records:
            sec = str(r.get("section", ""))
            heading = str(r.get("heading", ""))
            cid = r.get("canonical_id", "")
            act_code = r.get("act_code", "")
            raw = r.get("raw_text", "")
            clean = r.get("text", "")

            # If the record is a definition subclause itself (e.g. FIO 2(g), NAO 5(u))
            # Check if heading is the defined term
            if ("SEC_2_" in cid or "SEC_3_" in cid or "SEC_4_" in cid or "SEC_5_" in cid or "ART_2_" in cid):
                clean_hdg = heading.strip().lower()
                clean_hdg = re.sub(r'[\“\"\'\`\‘\”]', '', clean_hdg).strip()
                if clean_hdg and len(clean_hdg) > 2 and len(clean_hdg.split()) <= 6:
                    snippet = (clean if len(clean) > 0 else raw)[:200].replace('\n', ' ')
                    definitions_index[clean_hdg].append({
                        "act_code": act_code,
                        "act_name": r.get("act_name", ""),
                        "section": sec,
                        "canonical_id": cid,
                        "heading": heading,
                        "snippet": snippet
                    })

            text_to_scan = clean if len(clean) > 0 else raw

            for m in def_term_pat.finditer(text_to_scan):
                term_raw = m.group(1).strip()
                # Normalize term
                term_clean = re.sub(r'\s+', ' ', term_raw).lower()
                # Exclude long phrases that aren't real terms
                if len(term_clean) > 4 and len(term_clean.split()) <= 6:
                    snippet = text_to_scan[max(0, m.start()-10):min(len(text_to_scan), m.end()+120)].strip().replace('\n', ' ')
                    definitions_index[term_clean].append({
                        "act_code": act_code,
                        "act_name": r.get("act_name", ""),
                        "section": sec,
                        "canonical_id": cid,
                        "heading": heading,
                        "snippet": snippet
                    })

    # Deduplicate entries per term + canonical_id
    deduped_index = {}
    for term, entries in definitions_index.items():
        seen = set()
        unique_entries = []
        for e in entries:
            key = (e["act_code"], e["canonical_id"])
            if key not in seen:
                seen.add(key)
                unique_entries.append(e)
        deduped_index[term] = unique_entries

    # Cross-link spelling variants (willful <-> wilful)
    if "willful default" in deduped_index or "wilful default" in deduped_index:
        combined_wd = deduped_index.get("willful default", []) + deduped_index.get("wilful default", [])
        # unique by canonical_id
        seen_wd = set()
        uniq_wd = []
        for item in combined_wd:
            if item["canonical_id"] not in seen_wd:
                seen_wd.add(item["canonical_id"])
                uniq_wd.append(item)
        deduped_index["willful default"] = uniq_wd
        deduped_index["wilful default"] = uniq_wd

    # Identify ambiguous terms (defined in 2+ acts)
    ambiguous_terms = {}
    for term, entries in deduped_index.items():
        acts = set(e["act_code"] for e in entries)
        if len(acts) >= 2:
            ambiguous_terms[term] = {
                "distinct_acts_count": len(acts),
                "acts": list(acts),
                "definitions": entries
            }

    # Save outputs
    with open(DATA_DIR / "definitions_index.json", "w", encoding="utf-8") as fp:
        json.dump(deduped_index, fp, indent=2, ensure_ascii=False)

    with open(REPORTS_DIR / "ambiguous_terms.json", "w", encoding="utf-8") as fp:
        json.dump(ambiguous_terms, fp, indent=2, ensure_ascii=False)

    print(f"Definitions Index Built:")
    print(f"Total defined terms: {len(deduped_index):,}")
    print(f"Ambiguous terms (defined in 2+ acts): {len(ambiguous_terms):,}")

    # Explicit check for "willful default" / "wilful default"
    print("\n--- CONFIRMATION: 'willful default' / 'wilful default' ---")
    for variant in ["willful default", "wilful default"]:
        matches = deduped_index.get(variant, [])
        print(f"Term '{variant}': {len(matches)} matches:")
        for m in matches:
            print(f"  -> {m['act_code']} {m['section']} ({m['canonical_id']})")

if __name__ == "__main__":
    extract_definitions()
