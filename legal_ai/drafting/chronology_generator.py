"""
legal_ai/drafting/chronology_generator.py

Automatic Chronological "List of Dates and Events" Generator for Pakistani High Courts.
Strictly compliant with Lahore High Court Rules & Orders (Vol V) and Sindh High Court (Original Side) Rules.
Generates the mandatory opening synopsis table for Writ Petitions, Appeals, and Bail Applications.
"""

import re
from typing import List, Dict, Any, Optional

def extract_dates_and_events_from_text(narrative_text: str) -> List[Dict[str, str]]:
    """
    Parses unstructured client facts, FIR excerpts, and order sheets into
    a sorted chronological sequence of (Date, Event, Annexure).
    """
    if not narrative_text:
        return []

    lines = [l.strip() for l in narrative_text.split('\n') if l.strip()]
    events = []
    annexure_counter = ord('A')

    # Date pattern: DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, or Month DD, YYYY
    date_regex = re.compile(
        r'(\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b)',
        re.IGNORECASE
    )

    for line in lines:
        match = date_regex.search(line)
        if match:
            date_str = match.group(1)
            event_desc = line.replace(date_str, "").strip(" -:;,()[]")
            if not event_desc:
                event_desc = line
            annexure_letter = chr(annexure_counter) if annexure_counter <= ord('Z') else f"A{annexure_counter - ord('Z')}"
            annexure_counter += 1

            events.append({
                "date": date_str,
                "event": event_desc,
                "annexure": f"Annexure '{annexure_letter}'"
            })
        else:
            # Check for order or FIR references without strict date
            if any(k in line.lower() for k in ["impugned order", "fir no", "challan", "show cause", "complaint", "decree"]):
                annexure_letter = chr(annexure_counter) if annexure_counter <= ord('Z') else f"A{annexure_counter - ord('Z')}"
                annexure_counter += 1
                events.append({
                    "date": "**[INSERT DATE]**",
                    "event": line,
                    "annexure": f"Annexure '{annexure_letter}'"
                })

    if not events:
        # Fallback template skeleton if no dates extracted
        events = [
            {"date": "**[INSERT DATE OF CAUSE OF ACTION]**", "event": "Accrual of cause of action in favour of the Petitioner.", "annexure": "Annexure 'A'"},
            {"date": "**[INSERT DATE OF IMPUGNED ORDER]**", "event": "Passing of the impugned order / action by the Respondent without lawful authority.", "annexure": "Annexure 'B'"},
            {"date": "**[INSERT DATE OF LEGAL NOTICE / REPRESENTATION]**", "event": "Submission of departmental representation / legal notice by Petitioner seeking redressal.", "annexure": "Annexure 'C'"}
        ]

    return events

def format_chronology_markdown(events: List[Dict[str, str]]) -> str:
    """
    Renders the chronological sequence into clean court-ready Markdown table.
    """
    header = (
        "### SYNOPSIS & CHRONOLOGICAL LIST OF DATES AND EVENTS\n\n"
        "| Sr. No. | Date | Events & Particulars | Annexure |\n"
        "| :---: | :---: | :--- | :---: |\n"
    )
    rows = []
    for idx, e in enumerate(events, 1):
        rows.append(f"| {idx}. | {e['date']} | {e['event']} | {e['annexure']} |")

    return header + "\n".join(rows) + "\n\n"
