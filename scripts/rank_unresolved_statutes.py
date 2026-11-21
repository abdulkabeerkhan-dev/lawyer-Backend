import json
import os
import glob
import re
from collections import defaultdict

# 1. Load all canonical IDs currently in staging
staging_dir = 'data/statutes_v3_staging'
ALL_CANONICAL_IDS = set()

for f in glob.glob(os.path.join(staging_dir, '*.json')):
    with open(f, 'r', encoding='utf-8') as fp:
        try:
            recs = json.load(fp)
            for r in recs:
                cid = r.get('canonical_id', '')
                if cid:
                    ALL_CANONICAL_IDS.add(cid.upper())
        except Exception:
            pass

print(f"Total v3 Canonical IDs in Staging: {len(ALL_CANONICAL_IDS):,}")

# 2. Build robust resolve_statute_id function
INT_TO_ROMAN = {
    1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X',
    11: 'XI', 12: 'XII', 13: 'XIII', 14: 'XIV', 15: 'XV', 16: 'XVI', 17: 'XVII', 18: 'XVIII', 19: 'XIX', 20: 'XX',
    21: 'XXI', 22: 'XXII', 23: 'XXIII', 24: 'XXIV', 25: 'XXV', 26: 'XXVI', 27: 'XXVII', 28: 'XXVIII', 29: 'XXIX', 30: 'XXX',
    31: 'XXXI', 32: 'XXXII', 33: 'XXXIII', 34: 'XXXIV', 35: 'XXXV', 36: 'XXXVI', 37: 'XXXVII', 38: 'XXXVIII', 39: 'XXXIX', 40: 'XL',
    41: 'XLI', 42: 'XLII', 43: 'XLIII', 44: 'XLIV', 45: 'XLV', 46: 'XLVI', 47: 'XLVII', 48: 'XLVIII', 49: 'XLIX', 50: 'L'
}
ARTICLE_ACTS = {'CONST_1973', 'QSO_1984', 'LIMITATION_1908'}

def resolve_statute_id(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return None

    cid = raw.strip().upper()
    if cid in ALL_CANONICAL_IDS:
        return cid

    # 1. Strip trailing noise words
    clean_noise = re.sub(r'(CONSTITUTIONAL|PENAL|CIVIL|CRIMINAL|GENERAL|SPECIAL|ACT|ORD|ORDER)$', '', cid).rstrip('_')
    if clean_noise in ALL_CANONICAL_IDS:
        return clean_noise

    # 2. CPC Orders & Rules
    m_cpc = re.match(r'^CPC_1908_(?:O|ORD|ORDER)_([0-9IVXLCDM]+)_(?:R|RULE)_([0-9]+)$', clean_noise)
    if m_cpc:
        ord_val = m_cpc.group(1)
        r_val = m_cpc.group(2)
        ord_roman = INT_TO_ROMAN.get(int(ord_val), ord_val) if ord_val.isdigit() else ord_val
        cand = f"CPC_1908_ORD_{ord_roman}_R_{r_val}"
        if cand in ALL_CANONICAL_IDS:
            return cand

    # 3. SEC vs ART swaps
    for art_act in ARTICLE_ACTS:
        if clean_noise.startswith(f"{art_act}_SEC_"):
            swapped = clean_noise.replace(f"{art_act}_SEC_", f"{art_act}_ART_")
            if swapped in ALL_CANONICAL_IDS:
                return swapped

    # 4. Normalize lettered sections: 382-B, 382_B, 382(B) -> 382B
    m_sec = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)[\-_]?([A-Z])$', clean_noise)
    if m_sec:
        cand = f"{m_sec.group(1)}_{m_sec.group(2)}_{m_sec.group(3)}{m_sec.group(4)}"
        if cand in ALL_CANONICAL_IDS:
            return cand
        if m_sec.group(1) in ARTICLE_ACTS:
            cand_art = f"{m_sec.group(1)}_ART_{m_sec.group(3)}{m_sec.group(4)}"
            if cand_art in ALL_CANONICAL_IDS:
                return cand_art

    # 5. Definition sub-clauses: FIO_2001_SEC_2_G -> FIO_2001_SEC_2_g
    m_sub = re.match(r'^([A-Z0-9_]+)_(SEC|ART)_(\d+)_([A-Z])$', clean_noise)
    if m_sub:
        cand_lower = f"{m_sub.group(1)}_{m_sub.group(2)}_{m_sub.group(3)}_{m_sub.group(4).lower()}"
        if cand_lower in ALL_CANONICAL_IDS:
            return cand_lower
        cand_joined = f"{m_sub.group(1)}_{m_sub.group(2)}_{m_sub.group(3)}{m_sub.group(4)}"
        if cand_joined in ALL_CANONICAL_IDS:
            return cand_joined

    # 6. Famous cross-statute reconciliations in Pakistani case law
    if clean_noise in ("CRPC_1898_SEC_302", "ATA_1997_SEC_302", "CONST_1973_SEC_302", "ARMS_1965_SEC_302"):
        return "PPC_1860_SEC_302"
    if clean_noise in ("CRPC_1898_SEC_302B", "PPC_1860_SEC_302B"):
        return "PPC_1860_SEC_302"
    if clean_noise in ("CRPC_1898_SEC_382B", "PPC_1860_SEC_382B", "PPC_1860_SEC_382_B"):
        return "CRPC_1898_SEC_382B"
    if clean_noise in ("CRPC_1898_SEC_497", "PPC_1860_SEC_497"):
        return "CRPC_1898_SEC_497"
    if clean_noise in ("CRPC_1898_SEC_498", "PPC_1860_SEC_498"):
        return "CRPC_1898_SEC_498"
    if clean_noise in ("CRPC_1898_SEC_342", "ATA_1997_SEC_342"):
        return "CRPC_1898_SEC_342"
    if clean_noise in ("CRPC_1898_SEC_161", "ATA_1997_SEC_161"):
        return "CRPC_1898_SEC_161"
    if clean_noise in ("CRPC_1898_SEC_164", "ATA_1997_SEC_164"):
        return "CRPC_1898_SEC_164"

    return None

# 3. Load distinct statutes from judgments_v1
with open('reports/judgments_v1_distinct_statutes.json', 'r', encoding='utf-8') as fp:
    data = json.load(fp)

items = data.get('statutes', {}).items()

total_ids = len(items)
total_occurrences = sum(v for k, v in items if isinstance(v, int))

resolved_count = 0
resolved_occurrences = 0

unresolved = []

for stat, count in items:
    if not stat or not isinstance(count, int):
        continue
    resolved = resolve_statute_id(stat)
    if resolved:
        resolved_count += 1
        resolved_occurrences += count
    else:
        unresolved.append((stat.upper(), count))

unresolved.sort(key=lambda x: x[1], reverse=True)

print("=" * 90)
print("RECONCILIATION SUMMARY WITH resolve_statute_id APPLIED")
print("=" * 90)
print(f"Total Distinct Statute IDs in judgments_v1 : {total_ids:,}")
print(f"Total Citation Occurrences in judgments_v1 : {total_occurrences:,}")
print(f"Resolved IDs                                : {resolved_count:,} ({resolved_count/total_ids*100:.1f}%)")
print(f"Resolved Citation Occurrences               : {resolved_occurrences:,} ({resolved_occurrences/total_occurrences*100:.1f}%)")
print(f"STILL Unresolved IDs                        : {len(unresolved):,}")
print(f"STILL Unresolved Occurrences                : {total_occurrences - resolved_occurrences:,}")

print("\n" + "=" * 90)
print("TOP 40 STILL UNRESOLVED STATUTE CITATIONS (BY OCCURRENCE)")
print("=" * 90)
for rank, (stat, cnt) in enumerate(unresolved[:40], start=1):
    print(f"[{rank:02d}] {stat:<50} : {cnt:>9,} occurrences")

# Group by act
unresolved_by_act = defaultdict(int)
for stat, count in unresolved:
    parts = stat.split('_SEC_')[0].split('_ART_')[0].split('_ORD_')[0].split('_SCH_')[0]
    unresolved_by_act[parts] += count

sorted_unresolved_acts = sorted(unresolved_by_act.items(), key=lambda x: x[1], reverse=True)
print("\n" + "=" * 90)
print("TOP 40 STILL UNRESOLVED ACT PREFIXES (GROUPED BY ACT)")
print("=" * 90)
for rank, (act, cnt) in enumerate(sorted_unresolved_acts[:40], start=1):
    print(f"[{rank:02d}] {act:<50} : {cnt:>9,} occurrences")

# Save report
out_data = {
    "total_ids": total_ids,
    "total_occurrences": total_occurrences,
    "resolved_count": resolved_count,
    "resolved_occurrences": resolved_occurrences,
    "unresolved_count": len(unresolved),
    "top_40_unresolved_ids": [{"id": s, "occurrences": c} for s, c in unresolved[:40]],
    "top_40_unresolved_acts": [{"act": a, "occurrences": c} for a, c in sorted_unresolved_acts[:40]]
}
with open("reports/unresolved_statutes_ranking_report.json", "w", encoding="utf-8") as fp:
    json.dump(out_data, fp, indent=2)
print("\nSaved report to reports/unresolved_statutes_ranking_report.json")
