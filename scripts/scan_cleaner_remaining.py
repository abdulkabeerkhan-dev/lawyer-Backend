import json
import re
from pathlib import Path

staging_dir = Path("D:/lawyer-Backend/data/statutes_v3_staging")

# True bugs: where raw text had e.g. 'section 1215[' or 'section 121' followed by [ or footnote,
# but clean text has 'section ,' or 'sections ,' or 'under section ,' etc.
true_bugs = []
total_records = 0

for p in staging_dir.glob("*.json"):
    with open(p, "r", encoding="utf-8") as f:
        records = json.load(f)
    for r in records:
        total_records += 1
        clean = r.get("text", "")
        raw = r.get("raw_text", "")
        
        # Check if clean text has 'section ,' or 'rule ,' or 'article ,' where raw had a number
        for m in re.finditer(r'\b(section|article|sub-section|rule|order|clause)\s*,', clean, re.I):
            kw = m.group(1)
            # Find in raw text if there was a number glued to [
            raw_match = re.search(rf'\b{kw}\s*(\d{{1,4}})\d\[', raw, re.I)
            if raw_match:
                true_bugs.append({
                    "id": r["canonical_id"],
                    "raw": raw_match.group(0),
                    "clean_snippet": clean[max(0, m.start()-20):min(len(clean), m.end()+40)]
                })

print(f"Scanned {total_records} records.")
print(f"Remaining true bugs with missing section number before [: {len(true_bugs)}")
for b in true_bugs:
    print(b)
