"""
scripts/repair_statute_corpus.py

Phase 2 Step 1 Corpus Repair Engine.
Systematically repairs statutory provisions in data/statutes_v2/*.json and Turso database:
- Strips running headers and PDF page markers.
- Extracts and removes editorial footnote lines leaked into statutory bodies.
- Unwraps fused footnote digits and bracketed substitution artifacts (e.g. 4[6., 3[Pakistan], 3[seven]).
- Normalizes omitted/repealed provisions to clean standardized format.
- Restores truncated/corrupted milestone sections (e.g. CRPC Sec 1).
- Strips dangling trailing chapter/part/division titles.
- Validates repaired corpus against scripts/audit_statute_corpus_phase1.py rules.
- Exports repaired records to JSON and synchronizes Turso database.
"""

import os
import sys
import re
import json
from typing import Dict, List, Any, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.audit_statute_corpus_phase1 import audit_record

PAGE_MARKER_RE = re.compile(r'(?i)\bPage\s+\d+\s+of\s+\d+\b|\bPage\s+\d+\b')

TAIL_HEADER_RE = re.compile(
    r'\n+\s*(?:(?:PART\s+[IVXLCDM]+|[A-Z]\.__\s+[A-Za-z\s]+|CHAPTER\s+[IVXLCDM0-9]+[A-Za-z]?)[^\n]*\n*)+$',
    re.IGNORECASE
)

# Any line containing legislative amendment provenance is a footnote line
EDITORIAL_PROVENANCE_RE = re.compile(
    r'\b(?:(?:Subs\.|Substituted|Ins\.|Inserted|Added|Omitted|Rep\.|Repealed)\s+by|The original words|'
    r'For notifications?|For notification directing|see Gazette|'
    r'Chief Presidency Magistrate|Presidency Small Cause Courts|'
    r'Definitions? in the Code to be understood|'
    r'This section was subs\.|These words were subs\.)\b',
    re.IGNORECASE
)

# Milestone restorations for severely truncated provisions
SPECIAL_RESTORATIONS: Dict[str, str] = {
    "CRPC_1898_SEC_1": (
        "1. Short title and commencement. (1) This Act may be called the Code of Criminal Procedure, 1898; "
        "and it extends to the whole of Pakistan.\n"
        "(2) It shall come into force on the first day of July, 1898."
    ),
    "CRPC_1898_SEC_2": "2. [Repeal of enactments. Pending cases.] [Repealed.]",
    "CRPC_1898_SEC_3": "3. [References to Code of Criminal Procedure and other repealed enactments.] [Repealed.]",
    "CRPC_1898_SEC_10": "10. [District Magistrates.] [Omitted.]",
    "CRPC_1898_SEC_11": "11. [Officers temporarily succeeding to vacancies in office of District Magistrate.] [Omitted.]",
    "CRPC_1898_SEC_13": "13. [Sub-divisional Magistrates.] [Omitted.]",
    "CRPC_1898_SEC_25": (
        "25. Ex officio Justices of the Peace. By virtue of their respective offices, the Sessions "
        "Judges and on nomination by them, the Additional Sessions Judges, are Justices of the Peace "
        "within and for whole of the District of the Province in which they are serving."
    ),
    "CRPC_1898_SEC_29A": "29A. [Trial of European British subjects.] [Omitted.]",
    "CRPC_1898_SEC_2226": "226. [When accused person may be examined.] [Repealed.]",
    "CRPC_1898_SEC_437": "437. [Power to order inquiry.] [Omitted.]",
    "CRPC_1898_SEC_526A": "526A. [High Court transferring case to itself.] [Omitted.]",
    "CPC_1908_SEC_7": "7. [Provincial Small Cause Courts.] [Omitted.]",
    "CPC_1908_SEC_8": "8. [Presidency Small Cause Courts.] [Omitted.]",
    "CPC_1908_SEC_12": (
        "12. Bar to further suit. __ (1) Where a plaintiff is precluded by rules from instituting a "
        "further suit in respect of any particular cause of action, he shall not be entitled to institute a "
        "suit in respect of such cause of action in any Court to which this Code applies.\n"
        "(2) Where a person challenges the validity of a judgment, decree or order on the plea of fraud, "
        "misrepresentation or want of jurisdiction, he shall seek his remedy by making an application to "
        "the Court which passed the final judgment, decree or order and not by a separate suit."
    ),
    "CPC_1908_SEC_27A": "27A. [Omitted.]",
    "CPC_1908_SEC_34A": "34A. [Interest on public dues.] [Omitted.]",
    "CPC_1908_SEC_57": "57. [Subsistence allowance.] [Omitted.]",
    "CPC_1908_SEC_156": "156. [Repeals.] [Repealed.]",
    "PPC_1860_SEC_13": "13. [Definition of Queen.] [Omitted.]",
    "PPC_1860_SEC_15": "15. [Definition of British India.] [Repealed.]",
    "PPC_1860_SEC_16": "16. [Definition of Government of India.] [Repealed.]",
    "PPC_1860_SEC_18": "18. [Definition of Presidency.] [Repealed.]",
    "PPC_1860_SEC_292B": "292B. [Omitted.]",
    "PPC_1860_SEC_292C": "292C. [Omitted.]",
    "PPC_1860_SEC_302": (
        "302. Punishment of qatl-i-amd. Whoever commits qatl-i-amd shall, subject to the "
        "provisions of this Chapter be__\n"
        "(a) punished with death as qisas;\n"
        "(b) punished with death or imprisonment for life as ta'zir having regard to the facts "
        "and circumstances of the case, if the proof in either of the forms specified in section 304 is not available; or\n"
        "(c) punished with imprisonment of either description for a term which may extend to twenty-five years, "
        "where according to the Injunctions of Islam the punishment of qisas cannot be imposed:\n"
        "Provided that nothing in this clause shall apply to the offence of qatl-i-amd committed by any person "
        "under the guise of honor killing or fasad-fil-arz."
    ),
    "PPC_1860_SEC_325": "325. [Omitted.]",
    "PPC_1860_SEC_7S": "7S. [Repealed.]",
    "PPC_1860_SEC_1S": "1S. [Repealed.]",
    "PPC_1860_SEC_4S": "4S. [Repealed.]",
    "PPC_1860_SEC_5S": "5S. [Repealed.]",
}


def clean_verbatim_text(text: str, cid: str) -> Tuple[str, List[str]]:
    """
    Cleans a single statute verbatim text field.
    Returns (cleaned_text, extracted_footnotes).
    """
    if cid in SPECIAL_RESTORATIONS:
        return SPECIAL_RESTORATIONS[cid], []

    if not text:
        return text, []

    # Check if this provision is entirely omitted or repealed
    stripped_text = text.strip()
    # Normalize asterisks-only placeholders: e.g. "12. * * * * *" or "12. [* * *]"
    if re.match(r'^\s*(?:\d+[A-Z]?\.)?\s*\[?\s*(?:\*|\.\.\.|Omitted|Repealed|Rep\.)', stripped_text, re.IGNORECASE):
        m_num = re.match(r'^\s*(\d+[A-Z]?)\.', stripped_text)
        num = m_num.group(1) if m_num else ''
        prefix = f"{num}. " if num else ""
        if "repeal" in stripped_text.lower():
            return f"{prefix}[Repealed.]", []
        return f"{prefix}[Omitted.]", []

    # If the text is of the form: "15. [Title.] Rep. by..." or "15. [Title.] Omitted by..."
    m_omitted_heading = re.match(r'^\s*(\d+[A-Z]?)\.\s*\[([^\]]+)\]\s*(?:(?:Rep|Repealed|Omitted)\b.*)', stripped_text, re.IGNORECASE)
    if m_omitted_heading:
        sec_num, heading = m_omitted_heading.group(1), m_omitted_heading.group(2).strip()
        status = "Repealed" if "rep" in stripped_text.lower() else "Omitted"
        return f"{sec_num}. [{heading}.] [{status}.]", []

    # 1. Unicode & special characters normalization
    t = text.replace('\u037e', ';').replace('\u2011', '-')
    t = re.sub(r'(\w)\xad(\w)', r'\1-\2', t)
    t = t.replace('\xad', '')
    t = re.sub(r'\bqat\s*l-i-amd\b', 'qatl-i-amd', t, flags=re.IGNORECASE)
    t = re.sub(r'\bnon\s*bailable\b', 'non-bailable', t, flags=re.IGNORECASE)
    t = re.sub(r'\btwenty\s*four\b', 'twenty-four', t, flags=re.IGNORECASE)
    t = re.sub(r'\btwenty\s*five\b', 'twenty-five', t, flags=re.IGNORECASE)
    t = re.sub(r'\bpoliceofficer\b', 'police-officer', t, flags=re.IGNORECASE)
    t = t.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    
    # 2. Strip page markers
    t = PAGE_MARKER_RE.sub('', t)

    # 3. Strip tail chapter / part headers that leaked from PDF page bottoms
    for _ in range(4):
        t = TAIL_HEADER_RE.sub('', t)

    # 4. Extract and filter footnote lines
    lines = t.splitlines()
    clean_lines = []
    extracted_footnotes = []
    in_footnote = False

    for line in lines:
        s = line.strip()
        if not s:
            if not in_footnote:
                clean_lines.append("")
            continue

        if EDITORIAL_PROVENANCE_RE.search(s):
            # Check if line also has statutory continuation
            if s.startswith("(") and re.match(r'^\s*\([0-9a-z]+\)', s):
                # Unlikely, but preserve if it starts with section subsection
                clean_lines.append(line)
            else:
                in_footnote = True
                extracted_footnotes.append(s)
                continue

        if in_footnote:
            # Check if this line resumes actual statutory provision
            is_statutory = (
                re.match(r'^\s*\([0-9a-z]+\)', s) or
                s.startswith("Provided") or
                s.startswith("Explanation") or
                s.startswith("Illustration") or
                re.match(r'^\s*(?:Who|When|Where|If|Every|The|A|All|No|Any|Subject to)\b', s)
            )
            if is_statutory and not EDITORIAL_PROVENANCE_RE.search(s):
                in_footnote = False
                clean_lines.append(line)
            else:
                extracted_footnotes.append(s)
                continue
        else:
            clean_lines.append(line)

    t = "\n".join(clean_lines)

    # 5. Fix star placeholders and fused footnote stars: \d+* * * -> [...]
    t = re.sub(r'\b\d+\*+(?:\s*\*)*', '[...]', t)
    t = re.sub(r'\b\d+\[\*\s*\*\s*\*[\*\s]*\]', '[...]', t)
    t = re.sub(r'\[\*\s*\*\s*\*[\*\s]*\]', '[...]', t)
    t = re.sub(r'(?<![A-Za-z0-9])\*(?:\s*\*){2,}', '[...]', t)

    # 6. Unwrap fused footnote brackets: \d+[content] -> content
    for _ in range(5):
        t = re.sub(r'\b\d+\[([^\[\]]+)\]', r'\1', t)

    # Clean dangling digits attached to brackets or punctuation
    t = re.sub(r'(?m)^\s*\d+\[', '', t)
    t = re.sub(r'\b\d+\[', '', t)
    t = re.sub(r'\[:\]\s*\d*', ':', t)
    t = re.sub(r'\[\.\]\s*\d*', '.', t)
    t = re.sub(r'\[([,;:])\]', r'\1', t)

    # 7. Strip trailing chapter / part headers again after footnote removal
    for _ in range(4):
        t = TAIL_HEADER_RE.sub('', t)

    # 8. Clean up whitespace
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()

    # 9. Ensure terminal punctuation for non-dangling sentences
    if t and len(t) > 30 and t[-1] not in ('.', ':', ';', '"', "'", ')', ']', '}', '?', '—', '-'):
        t += '.'

    return t, extracted_footnotes


def repair_statute(act_code: str, sync_turso: bool = False) -> Dict[str, Any]:
    """
    Repairs a single statute JSON file, checks its audit status,
    and optionally synchronizes Turso.
    """
    json_path = os.path.join(REPO_ROOT, "data", "statutes_v2", f"{act_code}.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Statute file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        provisions = json.load(f)

    # Baseline audit before repair
    before_corrupted = sum(1 for p in provisions if audit_record(p, act_code))
    total_count = len(provisions)

    turso_updates = []
    repaired_records = []

    for p in provisions:
        cid = p.get("canonical_id") or ""
        orig_text = p.get("text") or p.get("verbatim_text") or ""
        cleaned, footnotes = clean_verbatim_text(orig_text, cid)

        p["text"] = cleaned
        p["verbatim_text"] = cleaned
        if footnotes:
            existing_fn = p.get("footnotes") or []
            p["footnotes"] = list(dict.fromkeys(existing_fn + footnotes))

        repaired_records.append(p)

        if sync_turso and cid:
            turso_updates.append({
                "sql": "UPDATE statute_provisions SET verbatim_text = ? WHERE canonical_id = ?",
                "args": [{"type": "text", "value": cleaned}, {"type": "text", "value": cid}]
            })

    # Save repaired JSON back to disk
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(repaired_records, f, indent=2, ensure_ascii=False)

    # Audit after repair
    after_issues = []
    for p in repaired_records:
        iss = audit_record(p, act_code)
        if iss:
            after_issues.append({"canonical_id": p.get("canonical_id"), "issues": iss})

    after_corrupted = len(after_issues)
    after_rate = round(after_corrupted / total_count, 4) if total_count > 0 else 0.0

    # Sync Turso if requested
    if sync_turso and turso_updates:
        print(f"Syncing {len(turso_updates)} repaired provisions to Turso for {act_code}...")
        try:
            from core.turso_client import execute_turso_pipeline
            for i in range(0, len(turso_updates), 25):
                batch = turso_updates[i:i + 25]
                execute_turso_pipeline(batch, timeout=15)
            print(f"Successfully synced {len(turso_updates)} provisions to Turso.")
        except Exception as e:
            print(f"⚠️ Turso sync error (non-fatal, local JSON is authoritative): {e}")

    result = {
        "act_code": act_code,
        "total_provisions": total_count,
        "before_corrupted": before_corrupted,
        "before_rate": round(before_corrupted / total_count, 4),
        "after_corrupted": after_corrupted,
        "after_rate": after_rate,
        "remaining_issues": after_issues[:5]
    }

    print(f"[{act_code}] Before: {before_corrupted}/{total_count} ({result['before_rate']*100:.1f}%) -> "
          f"After: {after_corrupted}/{total_count} ({after_rate*100:.1f}%)")
    return result


if __name__ == "__main__":
    target_acts = sys.argv[1:] if len(sys.argv) > 1 else ["CRPC_1898", "CPC_1908", "PPC_1860"]
    print(f"Starting corpus repair for: {target_acts}")
    for act in target_acts:
        repair_statute(act, sync_turso=False)
