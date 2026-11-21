import re
import os
import glob
import json
from pathlib import Path

staging_dir = Path("data/statutes_v3_staging")
raw_txt_dir = Path(r"D:\pakistan_code_text")

print("=" * 80)
print("PART B1: AUDITING FOOTNOTE-NUMBER REPAIRS (e.g. 1366 -> 366)")
print("=" * 80)

# Check all raw files for potential footnote-prefixed section numbers
# A footnote-prefixed section number has pattern: ^[1-9](\d{2,3}[A-Z]?)\.
# where the section number in sequence should be \1

rewritten_ids = []

for txt_file in sorted(raw_txt_dir.glob("*.txt")):
    if txt_file.stat().st_size == 0 or txt_file.stat().st_size < 600:
        continue
    with open(txt_file, "r", encoding="utf-8", errors="ignore") as fp:
        content = fp.read()
        
    # Find all matches of section numbers
    matches = list(re.finditer(r'(?:^|\n)\s*(?:[\*\#\{\[\d\s]*)\b([0-9]{1,4}[A-Za-z]{0,2})\s*(?:\.|\—|\:|\.\s*[\—\-])\s*([^\n\r]*)', content))
    
    # Check for cases where raw_num starts with a single digit followed by a valid 2-3 digit number
    for i, m in enumerate(matches):
        raw_num = m.group(1).upper()
        heading = m.group(2).strip()
        
        # Check if raw_num is 4 digits e.g. 1366, 2154, etc.
        if len(raw_num) >= 4 and raw_num[0] in '123456789' and raw_num.isdigit():
            val = int(raw_num)
            if val >= 1000 and val <= 9999:
                cand_sec = int(raw_num[1:])
                # Check preceding and succeeding sections
                prev_num = None
                next_num = None
                if i > 0:
                    m_prev = re.match(r'^(\d+)', matches[i-1].group(1))
                    if m_prev: prev_num = int(m_prev.group(1))
                if i + 1 < len(matches):
                    m_next = re.match(r'^(\d+)', matches[i+1].group(1))
                    if m_next: next_num = int(m_next.group(1))
                    
                # Sequence verification
                verified = False
                reason = "out of sequence"
                if prev_num is not None and next_num is not None:
                    if prev_num <= cand_sec <= next_num:
                        verified = True
                        reason = f"in sequence between {prev_num} and {next_num}"
                    elif abs(cand_sec - prev_num) <= 2 or abs(next_num - cand_sec) <= 2:
                        verified = True
                        reason = f"adjacent sequence (prev {prev_num}, next {next_num})"
                elif prev_num is not None and abs(cand_sec - prev_num) <= 2:
                    verified = True
                    reason = f"adjacent to prev {prev_num}"
                elif next_num is not None and abs(next_num - cand_sec) <= 2:
                    verified = True
                    reason = f"adjacent to next {next_num}"
                    
                rewritten_ids.append({
                    "file": txt_file.name,
                    "raw_num": raw_num,
                    "repaired_sec": cand_sec,
                    "prev_sec": prev_num,
                    "next_sec": next_num,
                    "verified": verified,
                    "reason": reason,
                    "heading": heading[:50]
                })

print(f"Total potential footnote-number repairs found: {len(rewritten_ids)}")
verified_repairs = [r for r in rewritten_ids if r['verified']]
unverified_repairs = [r for r in rewritten_ids if not r['verified']]
print(f"Verified against sequence: {len(verified_repairs)}")
print(f"Unverified (out of sequence): {len(unverified_repairs)}")

print("\n--- Verified Repairs Sample ---")
for r in verified_repairs[:15]:
    print(f"  {r['file'][:30]} | {r['raw_num']} -> {r['repaired_sec']} ({r['reason']}) | Hdg: {r['heading']}")

print("\n--- Unverified Repairs ---")
for r in unverified_repairs[:20]:
    print(f"  {r['file'][:30]} | {r['raw_num']} -> {r['repaired_sec']} ({r['reason']}) | Hdg: {r['heading']}")
