"""
scripts/explain_fio_s10_and_q5.py

ITEM 4: FIO SECTION 10 BEFORE/AFTER ORDER 1.3 & Q5 LOOKUP FAILURE EXPLANATION
Prints:
1. Diff of stored FIO s.10 text between commit f8013c5 (Order 1.2) and commit 8b0b7d7 (Order 1.3).
2. Exact explanation of why Q5 had 3 empty spans in Order 1.3:
   - Line break between 'date' and 'of first service' prevented substring match.
   - Hand-typed keyword 'summary of the defence' vs statutory text 'summary of the substantial questions of law'.
   - Hand-typed keyword 'shall forthwith pass a decree' vs statutory text 'proceed to pass judgment and decree'.
"""

import os
import sys
import json
import subprocess
import difflib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("=" * 110)
    print("ITEM 4: FIO SECTION 10 BEFORE/AFTER ORDER 1.3 & Q5 EMPTY SPAN AUDIT")
    print("=" * 110)

    # 1. Fetch text from commit f8013c5 (before Order 1.3)
    cmd1 = ["git", "show", "f8013c5:data/unified_statutes/FIO_2001.json"]
    raw_old = subprocess.run(cmd1, capture_output=True, text=True, encoding="utf-8").stdout
    old_data = json.loads(raw_old)
    old_s10 = [r for r in old_data if r.get("canonical_id") == "FIO_2001_SEC_10"][0]["text"]

    # 2. Fetch text from commit 8b0b7d7 (after Order 1.3)
    cmd2 = ["git", "show", "8b0b7d7:data/unified_statutes/FIO_2001.json"]
    raw_new = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8").stdout
    new_data = json.loads(raw_new)
    new_s10 = [r for r in new_data if r.get("canonical_id") == "FIO_2001_SEC_10"][0]["text"]

    print(f"Old Stored Length (commit f8013c5): {len(old_s10)} chars")
    print(f"New Stored Length (commit 8b0b7d7): {len(new_s10)} chars")
    print(f"Characters Removed: {len(old_s10) - len(new_s10)} chars")

    print("\n" + "-" * 110)
    print("UNIFIED DIFF OF FIO SECTION 10 (Commit f8013c5 -> Commit 8b0b7d7):")
    print("-" * 110)
    diff = list(difflib.unified_diff(
        old_s10.splitlines(keepends=True),
        new_s10.splitlines(keepends=True),
        fromfile="commit_f8013c5:FIO_s10",
        tofile="commit_8b0b7d7:FIO_s10",
        n=2
    ))
    sys.stdout.write("".join(diff))

    print("\n" + "-" * 110)
    print("ANALYSIS OF THE THREE EMPTY SPANS IN Q5 EVALUATION:")
    print("-" * 110)

    # Check Check #1
    kw1 = "thirty days of the date of first service"
    print("Check #1: '30 days mandatory timeline from service'")
    print(f"  Attempted Keyword: {repr(kw1)}")
    print(f"  Match in raw multiline text: {kw1 in new_s10}")
    norm_s10 = " ".join(new_s10.split())
    print(f"  Match in whitespace-normalized text: {kw1 in norm_s10}")
    print("  Actual Statutory Line in s.10(2):")
    for l in new_s10.splitlines():
        if "thirty days" in l or "first service" in l:
            print(f"    {repr(l)}")
    print("  Root Cause: A newline character between 'date' and 'of first service' caused the raw .find() check to fail!\n")

    # Check Check #2
    kw2 = "summary of the defence"
    print("Check #2: 'Summary of defence and accounts disclosure'")
    print(f"  Attempted Keyword: {repr(kw2)}")
    print(f"  Match in s.10: {kw2 in new_s10 or kw2 in norm_s10}")
    print("  Actual Statutory Text in s.10(3):")
    for l in new_s10.splitlines():
        if "summary" in l or "substantial" in l:
            print(f"    {repr(l)}")
    print("  Root Cause: Hand-typed keyword 'summary of the defence' was imported from CPC Order XXXVII, whereas FIO s.10(3) explicitly reads 'summary of the substantial questions of law as well as fact'!\n")

    # Check Check #3
    kw3 = "shall forthwith pass a decree"
    print("Check #3: 'Failure to apply / rejection leads to decree forthwith'")
    print(f"  Attempted Keyword: {repr(kw3)}")
    print(f"  Match in s.10: {kw3 in new_s10 or kw3 in norm_s10}")
    print("  Actual Statutory Text in s.10(11):")
    for l in new_s10.splitlines():
        if "pass judgment" in l or "decree" in l:
            print(f"    {repr(l)}")
    print("  Root Cause: Hand-typed keyword 'shall forthwith pass a decree' did not exist in FIO s.10(11); the authentic statute reads 'proceed to pass judgment and decree in favour of the plaintiff'!")

    print("=" * 110)

if __name__ == "__main__":
    main()
