import json
import re
from collections import defaultdict

with open('reports/judgments_v1_distinct_statutes.json', 'r', encoding='utf-8') as fp:
    data = json.load(fp)

# We want historical enactments that are absent from v3
# Filter out CPC Orders (since CPC is an existing code with orders in legacy)
historical_candidates = defaultdict(int)
historical_samples = defaultdict(list)

for s, count in data.get('statutes', {}).items():
    if s.startswith('CPC_1908_O_') or s.startswith('CPC_1908_ORD_'):
        continue
    
    # Check if s matches an act pattern
    m = re.match(r'^([A-Z0-9_]+?)(?:_SEC_|_ART_|_SCH_|_ORDER_|_RULE_|_ORD_|\Z)', s)
    if m:
        act = m.group(1)
        # Check if year is present and historical
        m_yr = re.search(r'_(18\d\d|19\d\d|20\d\d)\b', act)
        if m_yr:
            historical_candidates[act] += count
            if len(historical_samples[act]) < 3:
                historical_samples[act].append(s)

# Filter out acts that exist in v3 staging
import glob, os
v3_acts = set(os.path.basename(f).replace('.json', '').upper() for f in glob.glob('data/statutes_v3_staging/*.json'))

filtered_historical = []
for act, cnt in historical_candidates.items():
    if act not in v3_acts and act not in ['COMPANIES_1984', 'CPC_1908', 'CRPC_1898', 'PPC_1860', 'CONST_1973', 'ITO_2001', 'FIO_2001', 'NAO_1999', 'SALES_TAX_1990']:
        filtered_historical.append((act, cnt, historical_samples[act]))

filtered_historical.sort(key=lambda x: x[1], reverse=True)

print("=" * 100)
print("TOP 40 HISTORICAL LAWS CITED IN JUDGMENTS_V1 ABSENT FROM V3 (EXCLUDING IN-FORCE / V3 ACTS)")
print("=" * 100)
for rank, (act, cnt, samples) in enumerate(filtered_historical[:40], start=1):
    ex = ", ".join(samples[:2])
    print(f"[{rank:02d}] {act:<38} : {cnt:>9,} citations | Examples: {ex}")
