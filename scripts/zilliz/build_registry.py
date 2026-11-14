r"""
scripts/zilliz/build_registry.py

Builds the canonical case registry from the 10 raw Pakistani law CSV files on I:\.
Adheres strictly to docs/antigravity/RULES.md and docs/ZILLIZ_MIGRATION_PLAN.md §1-3.

Features:
- Deterministic case_key: f"{year}_{journal}_{court_code}_{page}"
- Robust parsing of 'Citation / Title' with court code mapping to hierarchy levels 1-4
- Content-based classification: junk, full_judgment (>=6k chars, bench marker, case no), headnote
- Deduplication layer 1: collapses identical case_key rows by preference order
- Deduplication layer 2: groups parallel reports by text_hash (sha1 of normalized first 3,000 chars)
- Handles PLD empty rows and malformed rows (flags preceding case text_possibly_truncated=True)
- CLI support: --dry-run, --limit-cases N, --case-keys K1,K2
- Logging to I:\zilliz_work\logs\registry.log
"""

import os
import sys
import csv
import json
import re
import hashlib
import logging
import argparse
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple, Set

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.hierarchical_legal_chunker import HierarchicalLegalChunker
from core.court_derivation import clean_judgment_title

# Increase CSV field size limit for large judgment texts
csv.field_size_limit(2147483647)

# Allowed source CSVs in the root of I:\ (Rule 2)
ALLOWED_SOURCE_FILES = [
    "SCMR_cases.csv",
    "PLD_cases.csv",
    "MLD_cases.csv",
    "YLR_cases.csv",
    "PCRLJ_cases.csv",
    "CLC_cases.csv",
    "PLC_cases.csv",
    "CLD_cases.csv",
    "PTD_cases.csv",
    "GBLR_cases.csv",
]

# Canonical legal journals recognized in Pakistani legal reporting
CANONICAL_JOURNALS = {
    "SCMR", "PLD", "MLD", "YLR", "PCRLJ", "CLC", "PLC", "PLC(CS)", "CLD", "PTD", "GBLR"
}

# Journal authority ranking for parallel reports resolution (SCMR/PLD over others)
JOURNAL_AUTHORITY_PRIORITY = {
    "SCMR": 1,
    "PLD": 2,
    "PCRLJ": 3,
    "CLC": 4,
    "MLD": 5,
    "YLR": 6,
    "CLD": 7,
    "PTD": 8,
    "PLC": 9,
    "PLC(CS)": 10,
    "GBLR": 11,
}

# Bench markers and Case Number regex for full judgment classification
RE_BENCH = re.compile(
    r'\b(?:Present:\s*|Before\s+[A-Za-z\s\.\,\(\)]+(?:,\s*|\s+)(?:J|JJ|CJ|C\.J\.|Judge|Judges))\b',
    re.IGNORECASE
)
RE_CASE_NO = re.compile(
    r'(?i)\b(?:No\.?|Number)\s*[\w\d\-\/\.\s]{1,30}?\s+of\s+(?:19\d\d|20\d\d)\b'
)


def normalize_journal(raw: str) -> str:
    """Normalizes raw journal string to canonical name."""
    if not raw:
        return ""
    cleaned = re.sub(r'[\s\.\-]+', '', raw.upper())
    if cleaned in ("PCRLJ", "PCRLJ"):
        return "PCRLJ"
    if "PLC" in cleaned and ("CS" in cleaned or "C.S" in cleaned):
        return "PLC(CS)"
    if cleaned == "PLC":
        return "PLC"
    if cleaned in CANONICAL_JOURNALS:
        return cleaned
    # Check if raw uppercase matches
    raw_upper = raw.strip().upper()
    if raw_upper in CANONICAL_JOURNALS:
        return raw_upper
    return raw.strip()


def map_court(header_court_str: str, journal: str = "") -> Tuple[str, int]:
    """
    Maps header court string to canonical (court_code, court_level).
    According to spec §2 table:
    - SUPREME-COURT -> SC (1)
    - FEDERAL-SHARIAT-COURT -> FSC (2)
    - LAHORE-HIGH-COURT-LAHORE (and benches) -> LHC (3)
    - KARACHI-HIGH-COURT-SINDH -> SHC (3)
    - PESHAWAR-HIGH-COURT -> PHC (3)
    - QUETTA-HIGH-COURT-BALOCHISTAN -> BHC (3)
    - ISLAMABAD -> IHC (3)
    - HIGH-COURT-AZAD-KASHMIR -> AJKHC (3)
    - SUPREME-APPELLATE-COURT (GB) -> GBSAC (3)
    - anything else -> log it, OTHER (4)
    """
    s = header_court_str.strip() if header_court_str else ""
    if not s:
        # If empty but journal is SCMR, it is Supreme Court
        if journal == "SCMR":
            return ("SC", 1)
        if journal == "GBLR":
            return ("GBSAC", 3)
        return ("OTHER", 4)

    s_upper = s.upper()

    # Level 1: Apex Supreme Court of Pakistan
    if s_upper == "SUPREME-COURT":
        return ("SC", 1)

    # Level 2: Federal Shariat Court
    if s_upper == "FEDERAL-SHARIAT-COURT":
        return ("FSC", 2)

    # Level 3: High Courts & GB Supreme Appellate Court
    if "LAHORE-HIGH-COURT" in s_upper or s_upper == "BAGHDAD-UL-JADID":
        return ("LHC", 3)
    if s_upper == "KARACHI-HIGH-COURT-SINDH":
        return ("SHC", 3)
    if s_upper == "PESHAWAR-HIGH-COURT":
        return ("PHC", 3)
    if s_upper == "QUETTA-HIGH-COURT-BALOCHISTAN":
        return ("BHC", 3)
    if s_upper in ("ISLAMABAD", "ISLAMABAD-HIGH-COURT"):
        return ("IHC", 3)
    if s_upper == "HIGH-COURT-AZAD-KASHMIR":
        return ("AJKHC", 3)
    if any(k in s_upper for k in [
        "SUPREME-APPELLATE-COURT", "SUPREME-APPELATE-COURT",
        "SUPREME-APPELLANT-COURT", "NORTHERN AREAS SUPREME APPELLATE COURT"
    ]):
        return ("GBSAC", 3)

    # All others map to OTHER at Level 4
    return ("OTHER", 4)


def parse_citation_and_title(raw_field: str) -> Optional[Dict[str, Any]]:
    """
    Parses 'Citation / Title' string:
    Format: {index}\t{YYYY JOURNAL PAGE}\t{Parties} - {Judge} - {Counsel}\t{COURT-CODE-STRING}
    """
    if not raw_field:
        return None

    parts = raw_field.strip().split('\t')
    if len(parts) < 2:
        return None

    index_str = parts[0].strip()
    cit_candidate = parts[1].strip()
    title_counsel_str = parts[2].strip() if len(parts) >= 3 else ""
    court_raw = parts[-1].strip() if len(parts) >= 4 else ""

    # Parse citation: YYYY JOURNAL PAGE
    m = re.match(r'^(\d{4})\s+([A-Za-z\(\)\.\s]+?)\s+(\d+[A-Za-z]?)$', cit_candidate)
    if not m:
        # Fallback search if there are stray leading/trailing characters
        m = re.search(r'\b(19\d\d|20\d\d)\s+([A-Za-z\(\)\.\s]+?)\s+(\d+[A-Za-z]?)\b', cit_candidate)

    if not m:
        return None

    year_str, journal_raw, page_str = m.groups()
    journal = normalize_journal(journal_raw)
    if journal not in CANONICAL_JOURNALS:
        return None

    year = int(year_str)
    page = page_str.strip().upper()
    canonical_citation = f"{year} {journal} {page}"

    # Parse Parties, Judge, Counsel from title_counsel_str
    parties = ""
    judge = ""
    counsel = ""
    if title_counsel_str:
        subparts = [p.strip() for p in title_counsel_str.split(' - ') if p.strip()]
        if len(subparts) == 1:
            parties = subparts[0]
        elif len(subparts) == 2:
            parties = subparts[0]
            if any(k in subparts[1].lower() for k in ["justice", "honorable", "j.", "cj"]):
                judge = subparts[1]
            else:
                counsel = subparts[1]
        elif len(subparts) >= 3:
            parties = subparts[0]
            judge = subparts[1]
            counsel = " - ".join(subparts[2:])

    return {
        "year": year,
        "journal": journal,
        "page": page,
        "citation": canonical_citation,
        "parties": clean_judgment_title(parties) if parties else "",
        "judge": judge,
        "counsel": counsel,
        "court_raw": court_raw,
    }


def clean_portal_debris_extended(text: str) -> str:
    """
    Extends HierarchicalLegalChunker.clean_portal_debris to strip portal navigation chrome.
    """
    if not text:
        return ""
    # Strip Layout B site navigation chrome
    t = re.sub(
        r'(?is)^(?:My Account|Register)\s+Feedback\s+Customer Care Office.*?Case Law Search.*?Search\s*',
        '', text
    )
    t = re.sub(
        r'(?is)^(?:My Account|Register)\s+Feedback\s+Customer Care Office[^\n]+\n(?:[^\n]+\n){1,30}?(?:Case Law Search|Latest Caselaws)',
        '', t
    )
    # Apply baseline cleaner
    t = HierarchicalLegalChunker.clean_portal_debris(t)
    return t.strip()


def is_junk_text(text: str) -> bool:
    """Classifies if a cleaned text is junk per spec §3."""
    if not text or len(text) < 200:
        return True
    lower = text.lower()
    if (
        "server error in" in lower
        or "error code:700" in lower
        or "something went wrong" in lower
        or "ensembles the idea of lawonline" in lower
        or "#\tcitation\ttitle" in lower
    ):
        return True
    return False


def is_full_judgment(text: str) -> bool:
    """Checks if text meets full judgment requirements per spec §3."""
    if len(text) < 6000:
        return False
    if not RE_BENCH.search(text):
        return False
    if not RE_CASE_NO.search(text):
        return False
    return True


def classify_case_content(
    col4_raw: str,
    col5_raw: Optional[str] = None
) -> Tuple[str, str, str, bool]:
    """
    Cleans and classifies columns into:
    (headnote_text, judgment_text, content_level, is_junk)
    """
    c4 = clean_portal_debris_extended(col4_raw)
    c5 = clean_portal_debris_extended(col5_raw) if col5_raw is not None else ""

    j4 = is_junk_text(c4)
    j5 = is_junk_text(c5) if col5_raw is not None else True

    f4 = not j4 and is_full_judgment(c4)
    f5 = not j5 and is_full_judgment(c5) if col5_raw is not None else False

    # Layout B or single column
    if col5_raw is None:
        if f4:
            return ("", c4, "full_judgment", False)
        elif not j4:
            return (c4, "", "headnote_only", False)
        else:
            return ("", "", "headnote_only", True)

    # Layout A (two text columns)
    if f4 and not f5:
        hn = c5 if not j5 else ""
        return (hn, c4, "full_judgment", False)
    elif f5 and not f4:
        hn = c4 if not j4 else ""
        return (hn, c5, "full_judgment", False)
    elif f4 and f5:
        # Both meet full_judgment threshold: longer is judgment, shorter is headnote
        if len(c4) >= len(c5):
            return (c5, c4, "full_judgment", False)
        else:
            return (c4, c5, "full_judgment", False)
    else:
        # Neither is full judgment
        if j4 and j5:
            return ("", "", "headnote_only", True)
        elif not j4 and j5:
            return (c4, "", "headnote_only", False)
        elif j4 and not j5:
            return (c5, "", "headnote_only", False)
        else:
            # Both are valid headnotes: pick the longer/more informative one
            hn = c5 if len(c5) >= len(c4) else c4
            return (hn, "", "headnote_only", False)


def compute_text_hash(text: str) -> str:
    """Computes sha1 of normalized first 3,000 chars for parallel reports deduplication."""
    norm = re.sub(r'[^a-z0-9]+', ' ', text[:3000].lower()).strip()
    return hashlib.sha1(norm.encode('utf-8')).hexdigest()


def candidate_preference_score(case: Dict[str, Any]) -> Tuple[int, int, int, str]:
    """
    Deduplication preference score per spec §2:
    Order: (1) not junk, (2) full judgment, (3) longest cleaned text, (4) latest Scraped At
    """
    is_not_junk = 1 if not case.get("is_junk", False) else 0
    is_full = 1 if case.get("content_level") == "full_judgment" else 0
    total_len = len(case.get("judgment_text", "")) + len(case.get("headnote_text", ""))
    scraped_at = str(case.get("scraped_at", ""))
    return (is_not_junk, is_full, total_len, scraped_at)


def build_registry(
    source_dir: str = "I:\\",
    work_dir: str = "I:\\zilliz_work",
    limit_cases: Optional[int] = None,
    case_keys_filter: Optional[Set[str]] = None,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """
    Main registry builder. Reads the 10 CSVs, parses and classifies rows,
    collapses duplicates, resolves parallel reports, and writes registry.jsonl.
    """
    if logger is None:
        logger = logging.getLogger("build_registry")

    logger.info("Starting build_registry pipeline...")
    logger.info(f"Source directory: {source_dir}")
    logger.info(f"Work directory: {work_dir}")
    logger.info(f"Dry run: {dry_run}")
    if limit_cases:
        logger.info(f"Limit cases: {limit_cases}")
    if case_keys_filter:
        logger.info(f"Filtering to {len(case_keys_filter)} case keys")

    rows_read_per_file: Dict[str, int] = {}
    empty_rows_per_file: Dict[str, List[int]] = defaultdict(list)
    malformed_rows_per_file: Dict[str, List[int]] = defaultdict(list)
    unparsable_citations_per_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unknown_court_strings: Counter = Counter()

    # Intermediate storage grouped by case_key
    # case_key -> list of raw parsed candidate dicts
    grouped_by_case_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    flagged_case_keys: Set[str] = set()

    for fname in ALLOWED_SOURCE_FILES:
        filepath = os.path.join(source_dir, fname)
        if not os.path.exists(filepath):
            logger.error(f"Source file not found: {filepath}")
            raise FileNotFoundError(f"Missing required source file: {filepath}")

        logger.info(f"Processing {fname}...")
        file_row_count = 0
        last_valid_case_key: Optional[str] = None

        with open(filepath, "r", encoding="utf-8-sig", newline="", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                logger.warning(f"File {fname} is completely empty!")
                continue

            expected_cols = len(header)
            is_layout_b = (expected_cols == 6)

            cit_idx = header.index("Citation / Title")
            scraped_idx = header.index("Scraped At") if "Scraped At" in header else -1

            for line_no, row in enumerate(reader, start=2):
                file_row_count += 1

                # 1. Check for empty rows
                if not row or all(c.strip() == "" for c in row):
                    empty_rows_per_file[fname].append(line_no)
                    logger.debug(f"{fname}:{line_no}: Empty row skipped")
                    continue

                # 2. Check for malformed rows (broken quoted fields)
                if len(row) != expected_cols:
                    malformed_rows_per_file[fname].append(line_no)
                    logger.warning(f"{fname}:{line_no}: Malformed row with {len(row)} cols skipped (fragment: '{row[0][:60]}')")
                    if last_valid_case_key:
                        flagged_case_keys.add(last_valid_case_key)
                    continue

                # 3. Parse Citation / Title
                cit_field = row[cit_idx].strip()
                parsed_cit = parse_citation_and_title(cit_field)
                if not parsed_cit:
                    unparsable_citations_per_file[fname].append({
                        "line": line_no,
                        "citation_raw": cit_field[:100]
                    })
                    logger.warning(f"{fname}:{line_no}: Unparsable citation '{cit_field[:60]}'")
                    continue

                # 4. Map court string to code and level
                court_raw = parsed_cit["court_raw"]
                court_code, court_level = map_court(court_raw, parsed_cit["journal"])
                if court_code == "OTHER":
                    unknown_court_strings[court_raw] += 1

                # 5. Build case_key
                year = parsed_cit["year"]
                journal = parsed_cit["journal"]
                page = parsed_cit["page"]
                case_key = f"{year}_{journal}_{court_code}_{page}"
                legacy_case_id = f"{year}_{journal}_{page}"

                # Update last valid case key for malformed row tracking
                last_valid_case_key = case_key

                # Apply case keys filter if specified
                if case_keys_filter and case_key not in case_keys_filter:
                    continue

                # 6. Clean and classify content
                if is_layout_b:
                    col4 = row[4]
                    hn_text, jd_text, content_lvl, is_junk = classify_case_content(col4, None)
                else:
                    col4 = row[4]
                    col5 = row[5]
                    hn_text, jd_text, content_lvl, is_junk = classify_case_content(col4, col5)

                scraped_at = row[scraped_idx].strip() if scraped_idx >= 0 and len(row) > scraped_idx else ""

                candidate = {
                    "case_key": case_key,
                    "citation": parsed_cit["citation"],
                    "legacy_case_id": legacy_case_id,
                    "journal": journal,
                    "year": year,
                    "page": page,
                    "court_code": court_code,
                    "court_level": court_level,
                    "court_raw": court_raw,
                    "parties": parsed_cit["parties"],
                    "judge": parsed_cit["judge"],
                    "counsel": parsed_cit["counsel"],
                    "content_level": content_lvl,
                    "headnote_text": hn_text,
                    "judgment_text": jd_text,
                    "is_junk": is_junk,
                    "scraped_at": scraped_at,
                    "source_file": fname,
                    "source_line": line_no,
                    "text_possibly_truncated": False,
                }
                grouped_by_case_key[case_key].append(candidate)

        rows_read_per_file[fname] = file_row_count
        logger.info(
            f"Finished {fname}: {file_row_count} data rows, "
            f"{len(empty_rows_per_file[fname])} empty, {len(malformed_rows_per_file[fname])} malformed, "
            f"{len(unparsable_citations_per_file[fname])} unparsable citations."
        )

    # Propagate text_possibly_truncated flag to matching case_keys
    for ck in flagged_case_keys:
        if ck in grouped_by_case_key:
            for cand in grouped_by_case_key[ck]:
                cand["text_possibly_truncated"] = True

    logger.info(f"Total distinct case_keys before deduplication: {len(grouped_by_case_key)}")

    # Deduplication Layer 1: Collapse identical case_key rows
    unique_cases: Dict[str, Dict[str, Any]] = {}
    duplicate_rows_collapsed = 0
    all_junk_cases_count = 0
    all_junk_cases: List[Dict[str, Any]] = []

    for case_key, candidates in grouped_by_case_key.items():
        if len(candidates) > 1:
            duplicate_rows_collapsed += (len(candidates) - 1)
            # Sort candidates by preference score descending
            best_cand = max(candidates, key=candidate_preference_score)
            # If any candidate was flagged as text_possibly_truncated, preserve it
            if any(c.get("text_possibly_truncated") for c in candidates):
                best_cand["text_possibly_truncated"] = True
        else:
            best_cand = candidates[0]

        # Check if best candidate is all-junk
        if best_cand["is_junk"]:
            all_junk_cases_count += 1
            all_junk_cases.append(best_cand)
            continue

        # Compute text_hash
        target_text = best_cand["judgment_text"] if best_cand["judgment_text"] else best_cand["headnote_text"]
        best_cand["text_hash"] = compute_text_hash(target_text)
        best_cand["parallel_citations"] = []
        unique_cases[case_key] = best_cand

    logger.info(f"Duplicate rows collapsed: {duplicate_rows_collapsed}")
    logger.info(f"All-junk cases excluded: {all_junk_cases_count}")
    logger.info(f"Valid unique cases before parallel report resolution: {len(unique_cases)}")

    # Deduplication Layer 2: Resolve parallel reports by text_hash
    # Group cases by text_hash
    hash_to_cases: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for case in unique_cases.values():
        hash_to_cases[case["text_hash"]].append(case)

    final_registry: Dict[str, Dict[str, Any]] = {}
    parallel_report_pairs: List[Tuple[str, str]] = []

    for text_hash, cases_in_group in hash_to_cases.items():
        if len(cases_in_group) == 1:
            final_registry[cases_in_group[0]["case_key"]] = cases_in_group[0]
            continue

        # Group has multiple cases sharing the same text_hash!
        # Pick primary case based on journal authority priority
        def authority_key(c: Dict[str, Any]) -> Tuple[int, int, str]:
            prio = JOURNAL_AUTHORITY_PRIORITY.get(c["journal"], 99)
            # Earlier year or lower case_key as deterministic tie-breakers
            return (prio, -c["year"], c["case_key"])

        cases_sorted = sorted(cases_in_group, key=authority_key)
        primary_case = cases_sorted[0]

        for secondary_case in cases_sorted[1:]:
            primary_case["parallel_citations"].append(secondary_case["citation"])
            parallel_report_pairs.append((primary_case["case_key"], secondary_case["case_key"]))
            logger.info(
                f"Parallel report collapsed: {secondary_case['case_key']} "
                f"into primary {primary_case['case_key']} (citation: {secondary_case['citation']})"
            )

        final_registry[primary_case["case_key"]] = primary_case

    logger.info(f"Parallel report pairs collapsed: {len(parallel_report_pairs)}")
    logger.info(f"Final active cases in registry: {len(final_registry)}")

    # Calculate cross-court citations count (citations shared by different court codes)
    legacy_to_courts = defaultdict(set)
    for case in final_registry.values():
        legacy_to_courts[case["legacy_case_id"]].add(case["court_code"])
    cross_court_citations = {k: v for k, v in legacy_to_courts.items() if len(v) > 1}
    cross_court_citations_count = len(cross_court_citations)

    # Calculate content level counts per journal
    content_level_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"full_judgment": 0, "headnote_only": 0})
    total_full_judgments = 0
    total_headnote_only = 0

    for case in final_registry.values():
        j = case["journal"]
        cl = case["content_level"]
        content_level_counts[j][cl] += 1
        if cl == "full_judgment":
            total_full_judgments += 1
        else:
            total_headnote_only += 1

    # Apply limit_cases if specified for pilot/dry run
    ordered_case_keys = sorted(final_registry.keys())
    if limit_cases is not None:
        ordered_case_keys = ordered_case_keys[:limit_cases]

    # Write output registry.jsonl
    os.makedirs(work_dir, exist_ok=True)
    registry_path = os.path.join(work_dir, "registry.jsonl")
    report_path = os.path.join(work_dir, "registry_report.json")

    if not dry_run:
        logger.info(f"Writing {len(ordered_case_keys)} entries to {registry_path}...")
        with open(registry_path, "w", encoding="utf-8") as out_f:
            for ck in ordered_case_keys:
                case = final_registry[ck]
                out_f.write(json.dumps(case, ensure_ascii=False) + "\n")
        logger.info(f"Registry written successfully to {registry_path}")

    # Prepare report summary dict
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "rows_read_per_file": rows_read_per_file,
        "total_rows_read": sum(rows_read_per_file.values()),
        "empty_rows_per_file": {k: len(v) for k, v in empty_rows_per_file.items()},
        "total_empty_rows": sum(len(v) for v in empty_rows_per_file.values()),
        "malformed_rows_per_file": {k: len(v) for k, v in malformed_rows_per_file.items()},
        "total_malformed_rows": sum(len(v) for v in malformed_rows_per_file.values()),
        "unparsable_citations_per_file": {k: len(v) for k, v in unparsable_citations_per_file.items()},
        "total_unparsable_citations": sum(len(v) for v in unparsable_citations_per_file.values()),
        "flagged_cases_count": len(flagged_case_keys),
        "flagged_case_keys": sorted(list(flagged_case_keys)),
        "duplicate_rows_collapsed": duplicate_rows_collapsed,
        "junk_cases_excluded": all_junk_cases_count,
        "parallel_report_pairs_count": len(parallel_report_pairs),
        "cross_court_citations_kept_distinct": cross_court_citations_count,
        "final_unique_cases_count": len(final_registry),
        "written_cases_count": len(ordered_case_keys),
        "total_full_judgments": total_full_judgments,
        "total_headnote_only": total_headnote_only,
        "content_level_counts_per_journal": {k: dict(v) for k, v in content_level_counts.items()},
        "unknown_court_strings_counts": dict(unknown_court_strings),
        "malformed_row_line_numbers": dict(malformed_rows_per_file),
        "unparsable_citations_details": dict(unparsable_citations_per_file),
        "parallel_report_pairs": parallel_report_pairs[:100],  # sample
    }

    if not dry_run:
        with open(report_path, "w", encoding="utf-8") as rf:
            json.dump(report, rf, indent=2, ensure_ascii=False)
        logger.info(f"Report written successfully to {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Build canonical case law registry for Zilliz ingestion")
    parser.add_argument("--source-dir", default="I:\\", help="Directory containing the 10 CSV files")
    parser.add_argument("--work-dir", default="I:\\zilliz_work", help="Working directory for outputs")
    parser.add_argument("--limit-cases", type=int, default=None, help="Limit number of output cases")
    parser.add_argument("--case-keys", type=str, default=None, help="Comma-separated case keys to process")
    parser.add_argument("--dry-run", action="store_true", help="Perform processing without writing files")
    args = parser.parse_args()

    # Configure logging
    log_dir = os.path.join(args.work_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "registry.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("build_registry")

    case_keys_filter = None
    if args.case_keys:
        case_keys_filter = set(k.strip() for k in args.case_keys.split(",") if k.strip())

    report = build_registry(
        source_dir=args.source_dir,
        work_dir=args.work_dir,
        limit_cases=args.limit_cases,
        case_keys_filter=case_keys_filter,
        dry_run=args.dry_run,
        logger=logger,
    )

    print("\n--- REGISTRY BUILD COMPLETE ---")
    print(f"Total Rows Read: {report['total_rows_read']}")
    print(f"Empty Rows: {report['total_empty_rows']}")
    print(f"Malformed Rows: {report['total_malformed_rows']}")
    print(f"Flagged Cases (possibly truncated): {report['flagged_cases_count']}")
    print(f"Unparsable Citations: {report['total_unparsable_citations']}")
    print(f"Duplicate Rows Collapsed: {report['duplicate_rows_collapsed']}")
    print(f"Junk Cases Excluded: {report['junk_cases_excluded']}")
    print(f"Cross-Court Citations Kept Distinct: {report['cross_court_citations_kept_distinct']}")
    print(f"Parallel Report Pairs Collapsed: {report['parallel_report_pairs_count']}")
    print(f"Total Unique Cases in Registry: {report['final_unique_cases_count']}")
    print(f"Full Judgments: {report['total_full_judgments']}")
    print(f"Headnote Only: {report['total_headnote_only']}")


if __name__ == "__main__":
    main()
