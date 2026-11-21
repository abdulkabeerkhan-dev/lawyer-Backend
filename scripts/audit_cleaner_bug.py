import json
import re
from pathlib import Path

staging_dir = Path("data/statutes_v3_staging")

# Patterns indicating deleted numbers in legal text
disappeared_pats = [
    re.compile(r'\b(sections?|articles?|sub-sections?|rules?|orders?|clauses?)\s*,\s*', re.I),
    re.compile(r'\b(sections?|articles?|sub-sections?|rules?|orders?|clauses?)\s+or\b', re.I),
    re.compile(r'\b(sections?|articles?|sub-sections?|rules?|orders?|clauses?)\s+and\b', re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s*,\s*', re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s+or\b', re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s*\(', re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s*$', re.M | re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s+the\b', re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s+to\b', re.I),
    re.compile(r'\bunder\s+(?:sections?|articles?)\s+by\b', re.I),
    re.compile(r'\b(sections?|articles?)\s+to\b', re.I),
    re.compile(r'\b(sections?|articles?)\s+\.', re.I),
]

def find_disappeared_in_record(raw, clean):
    for pat in disappeared_pats:
        m = pat.search(clean)
        if m:
            # Check if raw text had a number adjacent to that match
            matched_phrase = m.group(0)
            keyword = m.group(1) if m.lastindex else "section"
            # look for keyword in raw
            m_raw = re.search(rf'\b{re.escape(keyword)}\s+(\d+)', raw, re.I)
            if m_raw:
                num = m_raw.group(1)
                # If num is not in clean near this position
                if num not in clean[max(0, m.start()-30):min(len(clean), m.end()+30)]:
                    snippet = clean[max(0, m.start()-25):min(len(clean), m.end()+25)].replace('\n', ' ')
                    raw_snippet = raw[max(0, m_raw.start()-15):min(len(raw), m_raw.end()+25)].replace('\n', ' ')
                    return matched_phrase, snippet, raw_snippet, num
    return None

findings_by_act = {}
examples = []

total_provisions = 0
for p in sorted(staging_dir.glob("*.json")):
    if p.name == "statutes_v2_legacy.json":
        continue
    with open(p, "r", encoding="utf-8") as f:
        recs = json.load(f)
    if not isinstance(recs, list):
        continue
        
    for r in recs:
        total_provisions += 1
        raw = r.get("raw_text", "")
        clean = r.get("text", "")
        cid = r.get("canonical_id", "")
        act = r.get("act_code", "")
        
        res = find_disappeared_in_record(raw, clean)
        if res:
            matched_phrase, clean_snip, raw_snip, num = res
            findings_by_act[act] = findings_by_act.get(act, 0) + 1
            examples.append({
                "canonical_id": cid,
                "act": act,
                "missing_number": num,
                "clean_pattern": matched_phrase.strip(),
                "clean_snippet": clean_snip.strip(),
                "raw_snippet": raw_snip.strip()
            })

print("=" * 80)
print("AUDIT: DISAPPEARED DIGITS IN CLEANED TEXT (CURRENT STAGING)")
print("=" * 80)
print(f"Total provisions scanned: {total_provisions:,}")
total_affected = sum(findings_by_act.values())
print(f"Total acts affected: {len(findings_by_act)}")
print(f"Total provisions with disappeared numbers: {total_affected}")

print("\n--- AFFECTED ACTS COUNT ---")
for act, count in sorted(findings_by_act.items(), key=lambda x: x[1], reverse=True):
    print(f"  {act}: {count}")

print(f"\n--- 20 CONCRETE EXAMPLES (STARTING WITH ITO 122) ---")
# Prioritize ITO 122 first
ito_122 = [ex for ex in examples if "ITO_2001_SEC_122" in ex["canonical_id"]]
other_ex = [ex for ex in examples if "ITO_2001_SEC_122" not in ex["canonical_id"]]
sorted_examples = ito_122 + other_ex

for i, ex in enumerate(sorted_examples[:20], 1):
    print(f"\n[{i:02d}] {ex['canonical_id']} (Lost number: {ex['missing_number']})")
    print(f"     RAW  : {repr(ex['raw_snippet'])}")
    print(f"     CLEAN: {repr(ex['clean_snippet'])}")

# Save report
report_data = {
    "total_provisions_scanned": total_provisions,
    "total_affected": total_affected,
    "acts_count": len(findings_by_act),
    "by_act": findings_by_act,
    "examples": sorted_examples[:25]
}
with open("reports/cleaner_disappeared_digits_report.json", "w", encoding="utf-8") as f:
    json.dump(report_data, f, indent=2)
print("\nSaved full audit to reports/cleaner_disappeared_digits_report.json")
