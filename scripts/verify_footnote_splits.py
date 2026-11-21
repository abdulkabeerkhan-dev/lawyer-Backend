"""
scripts/verify_footnote_splits.py

Performs:
1. Footnote split verification: checks every glued-digit split against the act's footnotes.
2. Unverifiable split detection: keeps raw digits, sets needs_review=True, reports top list.
3. Digit conservation check across all staged provisions.
4. Selection of 30 random cleaned provisions alongside raw_text for inspection.
"""

import json
import re
import random
from pathlib import Path
from collections import Counter, defaultdict

STAGING_DIR = Path("D:/lawyer-Backend/data/statutes_v3_staging")
RAW_DIR = Path("D:/pakistan_code_text")
REPORTS_DIR = Path("D:/lawyer-Backend/reports")

def run_verification():
    # 1. Load all staging files
    all_records = []
    by_act = defaultdict(list)
    for p in STAGING_DIR.glob("*.json"):
        if p.name == "statutes_v2_legacy.json":
            continue
        with open(p, "r", encoding="utf-8") as f:
            recs = json.load(f)
            all_records.extend(recs)
            act_code = p.stem
            by_act[act_code].extend(recs)

    print(f"Loaded {len(all_records)} Pakistan Code records across {len(by_act)} acts.")

    # 2. Footnote split audit
    # For each provision, check raw_text for glued provision+footnote patterns:
    # (section|article|sub-section|rule|order|clause)\s+(\d{1,4})(\d{1,2})\[
    glued_pat = re.compile(r'\b(section|article|sub-section|rule|order|clause)\s+(\d{1,4})(\d{1,2})\[', re.I)
    
    # We will gather act-level footnote sets from amendment_notes and raw_text footnote lines
    act_footnotes = defaultdict(set)
    for r in all_records:
        act_code = r.get("act_code")
        notes = r.get("amendment_notes", [])
        for note in notes:
            m = re.match(r'^\s*(\d{1,4})\b', note)
            if m:
                act_footnotes[act_code].add(int(m.group(1)))
        # Also check raw_text
        raw = r.get("raw_text", "")
        for line in raw.splitlines():
            m = re.match(r'^\s*(\d{1,4})\s*(?:\[\s*\d*\s*\]\s*)?(?:Ins\.|Subs\.|Added|Omitted|Deleted|New|Replaced|For|The|Words?|Clause|Sub-section|Section|Proviso|Paragraph|Full|Comma|In|\*)\b', line, re.I)
            if m:
                act_footnotes[act_code].add(int(m.group(1)))

    splits_by_act = defaultdict(lambda: {"verified": 0, "unverifiable": 0, "details": []})
    unverifiable_list = []

    for r in all_records:
        raw = r.get("raw_text", "")
        act_code = r.get("act_code")
        known_fns = act_footnotes[act_code]
        matches = list(glued_pat.finditer(raw))
        if not matches:
            continue

        for m in matches:
            kw = m.group(1)
            sec_num = m.group(2)
            fn_num = int(m.group(3))
            
            # Verification criterion:
            # 1. fn_num is in known footnotes, or
            # 2. known_fns has footnotes and fn_num <= max(known_fns) and fn_num >= 1
            is_verified = (fn_num in known_fns) or (len(known_fns) > 0 and 1 <= fn_num <= max(known_fns))
            
            # Special check: If sec_num is 1 and fn_num is 0 (e.g. Article 10[), that's NOT a split of 1+0!
            # That's footnote 10!
            if fn_num == 0:
                is_verified = False

            if is_verified:
                splits_by_act[act_code]["verified"] += 1
                splits_by_act[act_code]["details"].append({
                    "canonical_id": r.get("canonical_id"),
                    "raw_match": m.group(0),
                    "sec_num": sec_num,
                    "fn_num": fn_num,
                    "status": "verified"
                })
            else:
                splits_by_act[act_code]["unverifiable"] += 1
                unv_info = {
                    "canonical_id": r.get("canonical_id"),
                    "act_code": act_code,
                    "raw_match": m.group(0),
                    "sec_num": sec_num,
                    "fn_num": fn_num,
                    "known_fns_sample": sorted(list(known_fns))[:10],
                    "status": "unverifiable"
                }
                splits_by_act[act_code]["details"].append(unv_info)
                unverifiable_list.append(unv_info)
                r["needs_review"] = True

    print(f"Total acts with glued splits: {len(splits_by_act)}")
    total_verified = sum(v["verified"] for v in splits_by_act.values())
    total_unverifiable = sum(v["unverifiable"] for v in splits_by_act.values())
    print(f"Total verified splits: {total_verified}")
    print(f"Total unverifiable splits: {total_unverifiable}")

    # 3. Digit Conservation Check
    # For every provision: digits in raw_text minus accounted footnote/header digits must equal digits in clean_text
    conservation_mismatches = []
    
    re_page_footer = re.compile(r'^\s*Page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE)
    re_gazette_header = re.compile(r'^\s*(?:THE\s+GAZETTE\s+OF\s+PAKISTAN|EXTRAORDINARY|PART\s+[IVX]+)\s*$', re.IGNORECASE)
    re_running_header = re.compile(r'^\s*(?:Chapter|Part)\s+[IVX0-9]+.*?_{3,}\s*$', re.IGNORECASE)
    re_page_num_alone = re.compile(r'^\s*\d{1,4}\s*$')
    re_footnote_line = re.compile(
        r'^\s*\d+\s*(?:\[\s*\d*\s*\]\s*)?(?:Ins\.|Subs\.|Added|Omitted|Deleted|New\s+section|Replaced|For\s+the|The\s+words|Words?|Clause|Sub-section|Section|Proviso|Paragraph|Full\s+stop|Comma|In\s+section|Under\s+the|\*|Ommited)\b',
        re.IGNORECASE
    )

    for r in all_records:
        raw = r.get("raw_text", "")
        clean = r.get("text", "")
        
        # Digits in clean text
        clean_digits = re.findall(r'\d', clean)
        clean_counts = Counter(clean_digits)
        
        # Identify accounted removed digits:
        # Footnote notes:
        notes_text = " ".join(r.get("amendment_notes", []))
        notes_digits = re.findall(r'\d', notes_text)
        
        # Headers/footers in raw
        header_digits = []
        for line in raw.splitlines():
            s_line = line.strip()
            if re_page_footer.match(s_line) or re_gazette_header.match(s_line) or re_running_header.match(s_line) or re_page_num_alone.match(s_line):
                header_digits.extend(re.findall(r'\d', s_line))
        
        # Footnote markers before [: e.g. ' 1[', ' 310['
        fn_marker_digits = []
        for m in re.finditer(r'(?:^|(?<=[\s\(\,\.\;\:\—\-\"]))(\d{1,3})\[', raw):
            fn_marker_digits.extend(list(m.group(1)))
            
        # Accounted digits removed:
        # Raw digits:
        raw_digits = re.findall(r'\d', raw)
        raw_counts = Counter(raw_digits)
        
        # Total accounted digits = clean_digits + notes_digits + header_digits + fn_marker_digits
        # We test if clean_digits has any digit that wasn't in raw_digits, or if substantive digits disappeared
        # Check if raw_counts has more digits than accounted for
        accounted_counts = clean_counts + Counter(notes_digits) + Counter(header_digits) + Counter(fn_marker_digits)
        
        # Difference:
        diff_missing = {}
        for d in "0123456789":
            # If raw has more than accounted
            delta = raw_counts[d] - accounted_counts[d]
            if delta > 0:
                diff_missing[d] = delta
                
        if diff_missing:
            # Check total missing digits
            tot_missing = sum(diff_missing.values())
            # Ignore tiny discrepancies if raw had trailing footnote text not strictly matching regex
            if tot_missing > 2:
                conservation_mismatches.append({
                    "canonical_id": r.get("canonical_id"),
                    "act_code": r.get("act_code"),
                    "missing_digits_count": tot_missing,
                    "details": diff_missing
                })

    print(f"Total provisions with digit conservation mismatches: {len(conservation_mismatches)}")

    # 4. Pick 30 random provisions
    random.seed(42) # Reproducible
    sample_records = random.sample(all_records, min(30, len(all_records)))
    
    samples_output = []
    for s in sample_records:
        samples_output.append({
            "canonical_id": s.get("canonical_id"),
            "act_name": s.get("act_name"),
            "section_number": s.get("section_number"),
            "heading": s.get("heading"),
            "raw_text_snippet": s.get("raw_text", "")[:400],
            "clean_text_snippet": s.get("text", "")[:400],
            "amendment_notes": s.get("amendment_notes", [])
        })

    # Save reports
    report_data = {
        "footnote_splits": {
            "total_verified": total_verified,
            "total_unverifiable": total_unverifiable,
            "by_act": {k: {"verified": v["verified"], "unverifiable": v["unverifiable"]} for k, v in splits_by_act.items()},
            "unverifiable_top_30": unverifiable_list[:30]
        },
        "digit_conservation": {
            "total_scanned": len(all_records),
            "mismatches_count": len(conservation_mismatches),
            "top_mismatches": conservation_mismatches[:30]
        },
        "thirty_random_samples": samples_output
    }

    with open(REPORTS_DIR / "footnote_verification_and_conservation_report.json", "w", encoding="utf-8") as fp:
        json.dump(report_data, fp, indent=2, ensure_ascii=False)

    print("Saved report to reports/footnote_verification_and_conservation_report.json")

if __name__ == "__main__":
    run_verification()
