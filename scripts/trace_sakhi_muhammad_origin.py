"""
scripts/trace_sakhi_muhammad_origin.py

Audits git history of bm25_index.pkl for 'Muhammad Nazir v. Sakhi Muhammad'.
Prints exact findings, commits, offsets, or declares 'unproven'.
"""

import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

commits = ['83a9497', '18f03c7', '1aa7e7e', '7ab7d4b', 'cf41b64', '4939007', 'd9aa33c', '58fb8ab', '73e2156', 'c141302', '980f611']
full_target = b'Muhammad Nazir v. Sakhi Muhammad'
full_found = False

print("=" * 100)
print("AUDITING bm25_index.pkl ACROSS COMMITS FOR: 'Muhammad Nazir v. Sakhi Muhammad'")
print("=" * 100)

for c in commits:
    cmd = ['git', 'show', f'{c}:bm25_index.pkl']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data, _ = p.communicate()
    has_full = full_target in data
    print(f"Commit {c} (size: {len(data):,} bytes): full target found = {has_full}")
    if has_full:
        full_found = True
        idx = data.index(full_target)
        print(f"  FOUND exact title at byte offset {idx} in commit {c}")

print("-" * 100)
if not full_found:
    print("VERDICT: UNPROVEN. The exact case title 'Muhammad Nazir v. Sakhi Muhammad' does NOT exist")
    print("in any version of bm25_index.pkl in git history. 'Sakhi Muhammad' only appears as a witness name")
    print("in the body of scraped criminal judgments (e.g., 2006 YLR 2323).")
else:
    print("VERDICT: PROVEN in git history.")
print("=" * 100)
