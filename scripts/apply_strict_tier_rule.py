"""
scripts/apply_strict_tier_rule.py

ITEM 6: STRICT TIER & STATUS ALIGNMENT
Exact Rule:
  - Title Only means NO operative statutory text:
    * text is empty
    * text contains only heading/title
    * text is synthetic boilerplate (e.g. 'Statutory provision under...', 'This statutory provision stands enacted as...')
    * placeholder records (e.g. Schedule II with 0 provisions)
  - Substantive (ingested_unreviewed) means authentic operative statutory text is present.
  - Disputed provisions remain Disputed.
Applies this rule across all unified statute JSON files and prints every record that changes.
"""

import os
import sys
import json
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def has_real_operative_text(record):
    text = (record.get("text") or record.get("statutory_text") or "").strip()
    if not text:
        return False

    # Check for boilerplate patterns used in earlier ingestion passes
    boilerplate_patterns = [
        r'statutory\s+provision\s+under\b',
        r'this\s+statutory\s+provision\s+stands\s+enacted\s+as\b',
        r'schedule\s+ii\s+8-column\s+tabular\s+entries\b',
        r'\[statutory\s+text\s+not\s+found\b',
        r'\[?omitted\s+by\b',
        r'\[?repealed\s+by\b'
    ]
    for bp in boilerplate_patterns:
        if re.search(bp, text, re.I):
            # Check if there is actual operative text besides the boilerplate
            cleaned_of_bp = re.sub(bp, "", text, flags=re.I).strip()
            title = (record.get("title") or record.get("display_name") or "").strip()
            sec_num = str(record.get("primary_num") or "").strip()
            if title:
                cleaned_of_bp = re.sub(re.escape(title), "", cleaned_of_bp, flags=re.I).strip()
            if sec_num:
                cleaned_of_bp = re.sub(rf'\b{re.escape(sec_num)}\b[\.\s\-:]*', "", cleaned_of_bp).strip()
            # Count remaining substantive words
            words = re.findall(r'\b[a-zA-Z]{3,}\b', cleaned_of_bp)
            if len(words) < 10:
                return False

    title = (record.get("title") or record.get("display_name") or "").strip()
    sec_num = str(record.get("primary_num") or "").strip()

    # Strip heading/title from text
    cleaned = text
    if title:
        cleaned = re.sub(re.escape(title), "", cleaned, flags=re.I)
    if sec_num:
        cleaned = re.sub(rf'\b{re.escape(sec_num)}\b[\.\s\-:]*', "", cleaned)
    cleaned = cleaned.strip()

    # Count operative words
    words = re.findall(r'\b[a-zA-Z]{2,}\b', cleaned)
    return len(words) >= 8

def main():
    print("=" * 110)
    print("ITEM 6: STRICT TIER & STATUS ALIGNMENT (TITLE ONLY = NO OPERATIVE TEXT)")
    print("=" * 110)

    changes = []
    file_summary = {}

    for fname in sorted(os.listdir(STATUTES_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(STATUTES_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                continue

        records = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        file_changed = False
        counts = {"substantive": 0, "title_only": 0, "disputed": 0}

        for r in records:
            if not isinstance(r, dict):
                continue

            cid = r.get("canonical_id", "UNKNOWN")
            old_tier = r.get("tier")
            old_status = r.get("status")
            if isinstance(old_status, dict):
                old_status_str = old_status.get("federal") or old_status.get("punjab") or "unknown"
            else:
                old_status_str = str(old_status)

            is_disputed = old_tier == "disputed" or old_status_str.lower() == "disputed"

            if is_disputed:
                new_tier = "disputed"
                counts["disputed"] += 1
            else:
                operative = has_real_operative_text(r)
                if operative:
                    new_tier = "ingested_unreviewed"
                    counts["substantive"] += 1
                else:
                    new_tier = "title_only"
                    counts["title_only"] += 1

            if old_tier != new_tier:
                changes.append({
                    "file": fname,
                    "canonical_id": cid,
                    "old_tier": old_tier,
                    "new_tier": new_tier,
                    "words": len((r.get("text") or "").split())
                })
                r["tier"] = new_tier
                file_changed = True

        file_summary[fname] = counts

        if file_changed:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Total tier changes made across corpus: {len(changes)}\n")
    print(f"{'Enactment File':<28} | {'Canonical ID':<26} | {'Old Tier':<22} | {'New Tier':<22} | {'Words'}")
    print("-" * 110)
    for c in changes[:35]:
        print(f"{c['file']:<28} | {c['canonical_id']:<26} | {str(c['old_tier']):<22} | {str(c['new_tier']):<22} | {c['words']}")
    if len(changes) > 35:
        print(f"... and {len(changes) - 35} more records updated.")

    print("\n" + "-" * 110)
    print("CORPUS SUMMARY AFTER STRICT TIER ALIGNMENT")
    print("-" * 110)
    print(f"{'Enactment File':<30} | {'Substantive':<14} | {'Title Only':<14} | {'Disputed':<10} | {'Total'}")
    print("-" * 110)
    for fn, cnts in file_summary.items():
        tot = cnts['substantive'] + cnts['title_only'] + cnts['disputed']
        print(f"{fn:<30} | {cnts['substantive']:<14} | {cnts['title_only']:<14} | {cnts['disputed']:<10} | {tot}")
    print("=" * 110)

if __name__ == "__main__":
    main()
