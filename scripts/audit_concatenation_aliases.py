import json

with open('reports/citation_reconciliation_report.json', 'r', encoding='utf-8') as f:
    rep = json.load(f)

aliases = rep.get('proposed_aliases', {})

# Find concatenation aliases: keys where removing the last 1 or 2 digits matches an existing section prefix
# e.g. CRPC_1898_SEC_4972 -> CRPC_1898_SEC_497
# e.g. CRPC_1898_SEC_302 -> CRPC_1898_SEC_30

# Load all valid canonical IDs in staging
import glob
staging_ids = set()
for f in glob.glob('data/statutes_v3_staging/*.json'):
    with open(f, 'r', encoding='utf-8') as fp:
        try:
            recs = json.load(fp)
            for r in recs:
                staging_ids.add(r.get('canonical_id'))
        except Exception:
            pass

print(f"Total valid staging IDs: {len(staging_ids):,}")

concat_cases = []
for orig_id, mapped_id in aliases.items():
    # check if orig_id ends with numbers that were truncated
    if orig_id != mapped_id:
        # e.g. ACT_SEC_4972 vs ACT_SEC_497
        parts_orig = orig_id.rsplit('_', 1)
        parts_map = mapped_id.rsplit('_', 1)
        if len(parts_orig) == 2 and len(parts_map) == 2:
            act_orig, sec_orig = parts_orig
            act_map, sec_map = parts_map
            if act_orig == act_map and sec_orig.startswith(sec_map) and sec_orig != sec_map:
                diff = sec_orig[len(sec_map):]
                if diff.isdigit():
                    # This is a concatenation alias candidate e.g. 4972 -> 497, 302 -> 30
                    full_exists = orig_id in staging_ids
                    prefix_exists = mapped_id in staging_ids
                    concat_cases.append({
                        "orig_id": orig_id,
                        "mapped_id": mapped_id,
                        "sec_orig": sec_orig,
                        "sec_prefix": sec_map,
                        "trailing": diff,
                        "full_exists": full_exists,
                        "prefix_exists": prefix_exists,
                        "is_ambiguous": full_exists or int(diff) > 9 or len(sec_orig) <= 3
                    })

print(f"Total concatenation aliases detected: {len(concat_cases)}")
ambiguous = [c for c in concat_cases if c['is_ambiguous']]
valid_concats = [c for c in concat_cases if not c['full_exists'] and c['prefix_exists'] and not c['is_ambiguous']]

print(f"Ambiguous cases: {len(ambiguous)}")
print(f"Clean valid cases: {len(valid_concats)}")

print("\n--- TOP 30 AMBIGUOUS CASES FOR REVIEW ---")
for i, c in enumerate(ambiguous[:30]):
    status = "CONFLICT (full ID exists!)" if c['full_exists'] else "QUESTIONABLE (short sec/large digit)"
    print(f"[{i+1:02d}] {c['orig_id']} -> {c['mapped_id']} | Sec: {c['sec_orig']} -> {c['sec_prefix']}({c['trailing']}) | {status}")
