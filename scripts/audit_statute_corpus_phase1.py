"""
scripts/audit_statute_corpus_phase1.py

Phase 1 Corpus Audit Across All Statutes in data/statutes_v2/*.json.
Checks for:
1. Page markers in text
2. Fused footnote numbers & footnote text leakage
3. Merged records (multiple provisions in one record)
4. Empty text fields
5. Missing sub-sections / truncated text
6. Mismatched canonical IDs
"""

import os
import re
import json
from collections import defaultdict
from typing import Dict, List, Any

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")

PAGE_MARKER_REGEX = re.compile(r'\bPage\s+\d+\s+of\s+\d+\b|\bPage\s+\d+\b', re.IGNORECASE)
FOOTNOTE_LEAK_REGEX = re.compile(r'\b(?:The original words|Subs\. by|Ins\. by|Added by|Omitted by|Rep\. by)\b', re.IGNORECASE)
FUSED_FOOTNOTE_REGEX = re.compile(r'\b\d+\*|\b\d+\[\([0-9a-zA-Z]+\)', re.IGNORECASE)
MERGED_RECORD_REGEX = re.compile(r'\n\s*(?:(?:Section|Article|Order|Rule|Sec\.?|Art\.?)\s+\d+[A-Za-z]?\b|\b\d+\.\s+[A-Z][a-z]+)', re.MULTILINE)

def audit_record(rec: Dict[str, Any], act_code: str) -> List[Dict[str, str]]:
    issues = []
    cid = rec.get("canonical_id") or ""
    text = (rec.get("text") or rec.get("text_raw") or "").strip()
    sec_num = str(rec.get("primary_num") or rec.get("section") or "").strip()

    # 1. Canonical ID validation
    if not cid:
        issues.append({"type": "mismatched_canonical_id", "severity": "text_corrupting", "detail": "Missing canonical_id"})
    elif not cid.startswith(act_code) and act_code not in cid:
        issues.append({"type": "mismatched_canonical_id", "severity": "text_corrupting", "detail": f"CID {cid} does not match act {act_code}"})

    # 2. Empty text
    if not text:
        issues.append({"type": "empty_text", "severity": "text_corrupting", "detail": "Text is empty or null"})
        return issues  # Cannot check remaining text rules

    # 3. Page markers
    if PAGE_MARKER_REGEX.search(text):
        issues.append({"type": "page_marker", "severity": "cosmetic", "detail": "Page marker (e.g. 'Page X of Y') in text"})

    # 4. Footnote leakage
    if FOOTNOTE_LEAK_REGEX.search(text):
        issues.append({"type": "footnote_leakage", "severity": "moderate", "detail": "Editorial footnote text (e.g. 'Subs. by') leaked into body"})

    if FUSED_FOOTNOTE_REGEX.search(text):
        issues.append({"type": "fused_footnote_digits", "severity": "moderate", "detail": "Fused footnote digit artifact (e.g. '2*', '3[(2)')"})

    # 5. Merged records: text contains another subsequent section header
    # Exclude Limitation schedule multi-column articles or rules
    if "_ART_" not in cid and "_ORD_" not in cid:
        m_merged = MERGED_RECORD_REGEX.findall(text)
        if len(m_merged) > 1:
            issues.append({"type": "merged_records", "severity": "text_corrupting", "detail": f"Contains multiple provision headers: {m_merged[:3]}"})

    # 6. Truncated text / cut off
    if len(text) < 40 and not any(k in text.lower() for k in ["omitted", "repealed", "deleted"]):
        issues.append({"type": "truncated_text", "severity": "text_corrupting", "detail": f"Extremely short text ({len(text)} chars) without omit flag"})
    elif text[-1] not in ('.', ':', ';', '"', "'", ')', ']', '}', '?', '—', '-'):
        if len(text.splitlines()) > 2:
            issues.append({"type": "truncated_text", "severity": "moderate", "detail": f"Dangling sentence end: '{text[-30:]}'"})

    return issues

def run_corpus_audit():
    files = sorted([f for f in os.listdir(STATUTES_DIR) if f.endswith(".json")])
    print(f"Auditing {len(files)} statute files in {STATUTES_DIR}...\n")

    statute_reports = []
    total_provisions = 0
    total_corrupted = 0
    total_text_corrupting = 0
    total_moderate = 0
    total_cosmetic = 0

    issue_type_counts = defaultdict(int)

    for fname in files:
        act_code = fname.replace(".json", "")
        fpath = os.path.join(STATUTES_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                provisions = json.load(f)
        except Exception as e:
            statute_reports.append({
                "act_code": act_code,
                "error": f"Failed to parse JSON: {e}",
                "provision_count": 0,
                "corrupted_count": 0,
                "corruption_rate": 1.0
            })
            continue

        prov_count = len(provisions)
        total_provisions += prov_count
        corrupted_in_act = []

        for p in provisions:
            if not isinstance(p, dict):
                continue
            issues = audit_record(p, act_code)
            if issues:
                cid = p.get("canonical_id") or f"{act_code}_UNKNOWN"
                corrupted_in_act.append({
                    "canonical_id": cid,
                    "section": p.get("primary_num") or p.get("section"),
                    "issues": issues
                })
                for iss in issues:
                    issue_type_counts[iss["type"]] += 1
                    if iss["severity"] == "text_corrupting":
                        total_text_corrupting += 1
                    elif iss["severity"] == "moderate":
                        total_moderate += 1
                    else:
                        total_cosmetic += 1

        c_count = len(corrupted_in_act)
        total_corrupted += c_count
        rate = round(c_count / prov_count, 4) if prov_count > 0 else 0.0

        statute_reports.append({
            "act_code": act_code,
            "provision_count": prov_count,
            "corrupted_count": c_count,
            "corruption_rate": rate,
            "sample_corrupted": corrupted_in_act[:3]
        })

    statute_reports.sort(key=lambda x: x["corruption_rate"], reverse=True)

    summary = {
        "total_statute_files": len(files),
        "total_provisions": total_provisions,
        "total_corrupted_records": total_corrupted,
        "overall_corruption_rate": round(total_corrupted / total_provisions, 4) if total_provisions > 0 else 0.0,
        "severity_breakdown": {
            "text_corrupting": total_text_corrupting,
            "moderate_editorial_leakage": total_moderate,
            "cosmetic_page_markers": total_cosmetic
        },
        "issue_type_counts": dict(issue_type_counts),
        "statute_reports": statute_reports
    }

    report_path = os.path.join(REPO_DIR, "corpus_audit_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=" * 70)
    print("PHASE 1 STATUTE CORPUS AUDIT SUMMARY")
    print("=" * 70)
    print(f"Total Statutes Audited:      {len(files)}")
    print(f"Total Provisions Audited:    {total_provisions}")
    print(f"Total Corrupted Records:     {total_corrupted}")
    print(f"Overall Corpus Error Rate:   {summary['overall_corruption_rate'] * 100:.2f}%\n")
    print("Severity Breakdown:")
    print(f"  - Text-Corrupting (Empty/Merged/Truncated): {total_text_corrupting}")
    print(f"  - Moderate (Footnote Leaks/Fused Digits):   {total_moderate}")
    print(f"  - Cosmetic (Page markers / Headers):       {total_cosmetic}\n")

    print("Top 15 Statutes with Highest Corruption Rate:")
    print(f"{'Act Code':<35} {'Provisions':<12} {'Corrupted':<12} {'Rate':<8}")
    print("-" * 70)
    for rep in statute_reports[:15]:
        print(f"{rep['act_code']:<35} {rep['provision_count']:<12} {rep['corrupted_count']:<12} {rep['corruption_rate']*100:.1f}%")

    print("\nReport saved to:", report_path)
    return summary

if __name__ == "__main__":
    run_corpus_audit()
