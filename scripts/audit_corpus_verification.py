# scripts/audit_corpus_verification.py
import os
import sys
import json
import time
from typing import Dict, Any, List
from collections import defaultdict
from dotenv import load_dotenv

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE_DIR)
load_dotenv(os.path.join(WORKSPACE_DIR, '.env'))

from core.ingestion_verification import verify_case_record, verify_provenance

def run_corpus_audit(limit: int = 8000, batch_size: int = 1000):
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
    if not supabase_url or not supabase_key:
        print('[ERROR] Supabase credentials not found in environment.')
        return

    from supabase import create_client
    sb = create_client(supabase_url, supabase_key)

    print(f'Starting corpus ingestion audit on {limit} records...')
    offset = 0
    total_audited = 0
    t0 = time.time()

    category_counts = defaultdict(int)
    headnote_count = 0
    valid_count = 0
    retrievable_count = 0
    provenance_missing_count = 0

    mismatches_by_cat = defaultdict(list)

    while total_audited < limit:
        batch_limit = min(batch_size, limit - total_audited)
        print(f'Fetching records {offset} to {offset + batch_limit - 1}...')
        res = sb.table('full_judgments')\
            .select('id, case_id, neutral_citation, case_title, court_name, decision_date, full_text')\
            .range(offset, offset + batch_limit - 1)\
            .execute()
        rows = res.data or []
        if not rows:
            break

        for r in rows:
            total_audited += 1
            cid = r.get('case_id') or r.get('id')
            v_res = verify_case_record(r, require_provenance=False)
            prov_ok, prov_msg = verify_provenance(r)
            if not prov_ok:
                provenance_missing_count += 1

            if v_res['valid']:
                valid_count += 1
            if v_res['retrievable']:
                retrievable_count += 1
            if v_res['is_headnote']:
                headnote_count += 1

            cats = v_res.get('categories', [])
            for c in cats:
                category_counts[c] += 1
                if len(mismatches_by_cat[c]) < 50:
                    mismatches_by_cat[c].append({
                        'case_id': cid,
                        'citation': r.get('neutral_citation'),
                        'case_title': r.get('case_title'),
                        'court_name': r.get('court_name'),
                        'decision_date': r.get('decision_date'),
                        'reasons': [m for m in v_res['mismatches']]
                    })

        offset += len(rows)
        if len(rows) < batch_limit:
            break

    elapsed = time.time() - t0
    print(f'\nAudit Completed in {elapsed:.2f}s!')
    print(f'Total Audited: {total_audited}')
    print(f'Valid Records: {valid_count} ({valid_count/total_audited*100:.1f}%)')
    print(f'Retrievable Records: {retrievable_count} ({retrievable_count/total_audited*100:.1f}%)')
    print(f'Headnote-only Records: {headnote_count} ({headnote_count/total_audited*100:.1f}%)')
    print(f'Missing Provenance: {provenance_missing_count} ({provenance_missing_count/total_audited*100:.1f}%)')
    print('\nMismatches by Category:')
    for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f'  - {cat}: {cnt} ({cnt/total_audited*100:.2f}%)')

    out_dir = os.path.join(WORKSPACE_DIR, 'eval', 'results')
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, 'corpus_verification_audit.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_audited': total_audited,
            'valid_count': valid_count,
            'retrievable_count': retrievable_count,
            'headnote_count': headnote_count,
            'provenance_missing_count': provenance_missing_count,
            'category_counts': dict(category_counts),
            'samples': {k: v[:20] for k, v in mismatches_by_cat.items()}
        }, f, indent=2)

    md_path = os.path.join(out_dir, 'corpus_verification_audit.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('# Pakistani Superior Court Corpus Ingestion Verification Audit\n\n')
        f.write(f'- **Audited Records**: {total_audited:,}\n')
        f.write(f'- **Elapsed Time**: {elapsed:.2f} seconds\n')
        f.write(f'- **Valid Records**: {valid_count:,} ({valid_count/total_audited*100:.1f}%)\n')
        f.write(f'- **Retrievable Records**: {retrievable_count:,} ({retrievable_count/total_audited*100:.1f}%)\n')
        f.write(f'- **Headnote-Only (Preserved & Flagged)**: {headnote_count:,} ({headnote_count/total_audited*100:.1f}%)\n')
        f.write(f'- **Records Lacking Provenance**: {provenance_missing_count:,} ({provenance_missing_count/total_audited*100:.1f}%)\n\n')
        f.write('## Mismatch Breakdown by Category\n\n')
        f.write('| Mismatch Category | Count | Percentage | Description |\n')
        f.write('| :--- | :--- | :--- | :--- |\n')
        f.write(f"| **Court Hierarchy / Name** | {category_counts.get('court', 0):,} | {category_counts.get('court', 0)/total_audited*100:.2f}% | Claimed court contradicts document header |\n")
        f.write(f"| **Case Title / Parties** | {category_counts.get('title', 0):,} | {category_counts.get('title', 0)/total_audited*100:.2f}% | Party tokens not found in document header |\n")
        f.write(f"| **Citation / Reporter** | {category_counts.get('citation', 0):,} | {category_counts.get('citation', 0)/total_audited*100:.2f}% | Journal code or page number not found in header |\n")
        f.write(f"| **Decision Year** | {category_counts.get('year', 0):,} | {category_counts.get('year', 0)/total_audited*100:.2f}% | 4-digit decision year not found in header |\n")
        f.write(f"| **Missing / Empty Text** | {category_counts.get('missing_text', 0):,} | {category_counts.get('missing_text', 0)/total_audited*100:.2f}% | Text is empty, null, or 'not available' |\n")
        f.write(f"| **Editorial / Synthetic Marker** | {category_counts.get('editorial_marker', 0):,} | {category_counts.get('editorial_marker', 0)/total_audited*100:.2f}% | Full text begins with unreviewed editorial summary |\n\n")
        f.write('## Sample Mismatches for Review (Do Not Auto-Fix)\n\n')
        for cat, samples in mismatches_by_cat.items():
            f.write(f'### Category: {cat.upper()} ({len(samples)} samples recorded)\n\n')
            for s in samples[:10]:
                f.write(f"- **Case ID**: `{s['case_id']}` | **Citation**: `{s['citation']}`\n")
                f.write(f"  - **Title**: {s['case_title']}\n")
                f.write(f"  - **Claimed Court**: {s['court_name']}\n")
                f.write(f"  - **Reasons**: {', '.join(s['reasons'])}\n\n")
    print(f'Saved audit report to {md_path}')

if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_corpus_audit(limit=limit)
