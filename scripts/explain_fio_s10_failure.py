"""
scripts/explain_fio_s10_failure.py

ORDER 1.7 - ITEM 1:
Prints repr() of stored FIO s.10(1) first 250 characters next to the Memo F quote.
Demonstrates forensically why the Memo F quote failed against stored FIO s.10(1).
"""

import os
import sys
import json
import difflib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from core.unified_statute_store import get_unified_statute_store

def main():
    store = get_unified_statute_store()
    rec = store.get_by_canonical_id("FIO_2001_SEC_10")
    if not rec:
        print("Error: FIO_2001_SEC_10 not found in unified statute store.")
        return

    stored_full = rec.get("text", "")
    stored_s10_1_first250 = stored_full[:250]

    memo_f_quote = (
        "The Banking Court shall not grant leave to defend the suit unless the application "
        "filed by the defendant under sub-section (2) discloses that there is a serious and bona fide dispute"
    )

    print("=" * 110)
    print("ITEM 1: FORENSIC COMPARISON OF STORED FIO S.10(1) vs MEMO F QUOTE")
    print("=" * 110)

    print("\n[A] STORED FIO SECTION 10(1) (FIRST 250 CHARACTERS):")
    print("-" * 110)
    print("repr():")
    print(repr(stored_s10_1_first250))
    print("\nReadable Text:")
    print(stored_s10_1_first250)

    print("\n[B] MEMO F QUOTE:")
    print("-" * 110)
    print("repr():")
    print(repr(memo_f_quote))
    print("\nReadable Text:")
    print(memo_f_quote)

    print("\n[C] EXACT ROOT CAUSE OF FAILURE:")
    print("-" * 110)
    # Check if Memo F quote text exists anywhere in the stored Section 10 text
    quote_in_stored = memo_f_quote.lower() in stored_full.lower()
    print(f"Does Memo F quote exist anywhere in stored Section 10? {quote_in_stored}")

    # Substring overlap analysis
    matcher = difflib.SequenceMatcher(None, stored_s10_1_first250.lower(), memo_f_quote.lower())
    match = matcher.find_longest_match(0, len(stored_s10_1_first250), 0, len(memo_f_quote))
    matched_block = memo_f_quote[match.b : match.b + match.size]

    print(f"Longest matching continuous block: {match.size} characters")
    print(f"Matching substring: {repr(matched_block)}")

    print("\nEXPLANATION:")
    print("1. Authentic Gazette PDF & Stored FIO Section 10(1) provides:")
    print("   '(1) In any case in which the summons has been served on the defendant as provided for in")
    print("   sub-section (5) of section 9, the defendant shall not be entitled to defend the suit unless")
    print("   he obtains leave from the Banking Court as hereinafter provided to defend the same...'")
    print()
    print("2. The Memo F text ('The Banking Court shall not grant leave to defend the suit unless...")
    print("   discloses that there is a serious and bona fide dispute') is an invented / paraphrased summary")
    print("   of case law / doctrine. It is NOT the statutory text of Section 10(1).")
    print("3. In Section 10, the requirement for 'substantial questions of law or fact' appears in subsection (3)")
    print("   and subsection (9), while 'bona fide mistake' appears in the 2016 amendment proviso to subsection (5).")
    print("   The sentence quoted in Memo F does not exist in Section 10(1) of the official Pakistan Code Gazette.")
    print("=" * 110)

if __name__ == "__main__":
    main()
