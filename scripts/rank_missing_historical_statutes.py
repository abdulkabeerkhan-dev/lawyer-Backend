import json
import os
import glob
from collections import defaultdict

# 1. Load all canonical IDs present in v3 staging
staging_dir = 'data/statutes_v3_staging'
v3_canonical_ids = set()

for f in glob.glob(os.path.join(staging_dir, '*.json')):
    with open(f, 'r', encoding='utf-8') as fp:
        try:
            recs = json.load(fp)
            for r in recs:
                cid = r.get('canonical_id', '')
                if cid: v3_canonical_ids.add(cid.upper())
        except Exception:
            pass

print(f"Total v3 Canonical IDs: {len(v3_canonical_ids):,}")

# 2. Load distinct statutes from judgments_v1
with open('reports/judgments_v1_distinct_statutes.json', 'r', encoding='utf-8') as fp:
    data = json.load(fp)

items = data.get('statutes', {}).items()

# Group absent statute citations
absent_statutes = []
for stat, count in items:
    if not stat or not isinstance(count, int): continue
    s_upper = stat.upper()
    if s_upper not in v3_canonical_ids:
        absent_statutes.append((s_upper, count))

absent_statutes.sort(key=lambda x: x[1], reverse=True)

print("\n" + "=" * 90)
print("TOP 40 DISTINCT STATUTE CITATIONS IN JUDGMENTS_V1 ABSENT FROM V3 (BY FREQUENCY)")
print("=" * 90)
for rank, (stat, cnt) in enumerate(absent_statutes[:40], start=1):
    print(f"[{rank:02d}] {stat:<50} : {cnt:>9,} occurrences")

# Also aggregate by Act prefix
act_counts = defaultdict(int)
for stat, count in absent_statutes:
    parts = stat.split('_SEC_')[0].split('_ART_')[0].split('_ORD_')[0].split('_SCH_')[0]
    act_counts[parts] += count

sorted_acts = sorted(act_counts.items(), key=lambda x: x[1], reverse=True)
print("\n" + "=" * 90)
print("TOP 40 ACT PREFIXES IN JUDGMENTS_V1 ABSENT FROM V3 (BY TOTAL CITATION FREQUENCY)")
print("=" * 90)
for rank, (act, cnt) in enumerate(sorted_acts[:40], start=1):
    print(f"[{rank:02d}] {act:<50} : {cnt:>9,} occurrences")
