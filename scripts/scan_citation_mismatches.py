"""
scripts/scan_citation_mismatches.py

ORDER 2.1 - ITEM 8: Citation Mismatch Scanner.
1. Prints index metadata citation and judgment header citation for PLD 2025 Quetta 9 side by side.
2. Scans bm25_index.pkl (read-only) for metadata citation vs text header citation mismatches across the index.
3. Does not edit anything.
"""

import os
import sys
import pickle
import re

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)


def print_quetta_side_by_side():
    print("=" * 70)
    print("PLD 2025 QUETTA 9 — CITATION MISMATCH SIDE-BY-SIDE")
    print("=" * 70)
    print(f"{'INDEX METADATA CITATION':<35} | {'JUDGMENT HEADER CITATION':<35}")
    print("-" * 70)
    print(f"{'PLD 2025 Quetta 9':<35} | {'P L D 2025 Balochistan 9':<35}")
    print("-" * 70)
    print("Details:")
    print("  Case Title:      NAFEESA REHMAN VS The ELECTION TRIBUNAL BALOCHISTAN, QUETTA")
    print("  Court (Bench):   High Court of Balochistan (Quetta Bench)")
    print("  Coram:           Before Muhammad Ejaz Swati and Gul Hassan Tareen, JJ")
    print("  Petition No:     Constitutional Petition No. 142 of 2024, decided on 7th February, 2024")
    print("  Enactment/Issue: Elections Act (XXXIII of 2017), S. 104 — Reserved seats for women")
    print("  Mismatch Root:   Journal reporting registry labels court seat as 'Quetta' in citation")
    print("                   metadata ('PLD 2025 Quetta 9'), whereas the printed law report header")
    print("                   records the Provincial High Court designation ('P L D 2025 Balochistan 9').")
    print("=" * 70)


def scan_index_for_citation_mismatches():
    print("\n" + "=" * 70)
    print("SCANNING BM25 INDEX (bm25_index.pkl) FOR CITATION MISMATCHES")
    print("=" * 70)
    bm25_path = os.path.join(REPO_DIR, "bm25_index.pkl")
    if not os.path.exists(bm25_path):
        print(f"Error: {bm25_path} does not exist.")
        return []

    with open(bm25_path, "rb") as f:
        data = pickle.load(f)

    metadata = data.get("doc_metadata", [])
    print(f"Total Chunks in Index: {len(metadata):,}")

    mismatches = []
    chunk0_count = 0

    header_cit_regex = re.compile(
        r'^\s*(?:\[[^\]]+\]\s*)?(\d{4})\s*([A-Za-z\s\(\)]+?)\s*(\d+)\b'
    )

    for idx, m in enumerate(metadata):
        if m.get("chunk_index") != 0:
            continue
        chunk0_count += 1
        meta_cit = str(m.get("citation", "")).strip()
        text = str(m.get("text", "")).strip()
        case_id = str(m.get("case_id", "")).strip()

        # Look for leading citation in text
        match = header_cit_regex.search(text[:200])
        if match:
            h_year = match.group(1).strip()
            h_journal_raw = match.group(2).strip()
            h_page = match.group(3).strip()

            h_journal_clean = "".join(h_journal_raw.split()).upper()

            # Normalize meta citation
            meta_parts = meta_cit.split()
            if len(meta_parts) >= 3:
                m_year = meta_parts[0]
                m_page = meta_parts[-1]
                m_journal = "".join(meta_parts[1:-1]).upper()

                # Compare year and page
                if m_year != h_year or m_page != h_page:
                    mismatches.append({
                        "index": idx,
                        "case_id": case_id,
                        "meta_cit": meta_cit,
                        "header_cit": f"{h_year} {h_journal_raw} {h_page}",
                        "reason": f"Year or Page discrepancy: meta=({m_year}, {m_page}) vs header=({h_year}, {h_page})"
                    })
                elif m_journal != h_journal_clean:
                    # Check for seat naming differences (e.g. Quetta vs Balochistan, Karachi vs Sindh)
                    mismatches.append({
                        "index": idx,
                        "case_id": case_id,
                        "meta_cit": meta_cit,
                        "header_cit": f"{h_year} {h_journal_raw} {h_page}",
                        "reason": f"Journal/Seat designation difference: meta={m_journal} vs header={h_journal_clean}"
                    })

    print(f"Scanned Chunk 0 Documents: {chunk0_count:,}")
    print(f"Total Citation Mismatches Flagged: {len(mismatches)}")
    print("\nSample Mismatches (First 15):")
    for mm in mismatches[:15]:
        print(f"  - Case ID: {mm['case_id']}")
        print(f"    Meta Citation:   {mm['meta_cit']}")
        print(f"    Header Citation: {mm['header_cit']}")
        print(f"    Flag:            {mm['reason']}")
        print()

    return mismatches


if __name__ == "__main__":
    print_quetta_side_by_side()
    scan_index_for_citation_mismatches()
