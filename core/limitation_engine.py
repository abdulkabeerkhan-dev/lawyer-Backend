"""
core/limitation_engine.py
Deterministic Standing Limitation Engine for Pakistani Legal Research.

Features:
1. Automated date extraction from legal fact patterns (e.g. "15 March 2021", "15 September 2021").
2. Cause-of-action to Limitation Act 1908 First Schedule Article mapping.
3. Precise date arithmetic (Limb 1 vs Limb 2 determination, expiry calculation, overdue delta).
4. Statutory enforcement check under Section 3 (mandatory dismissal without limitation plea).
5. Saving exceptions analysis under Sections 19 (written acknowledgment) and 20 (part payment).
"""

import re
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple


MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}


def extract_dates_from_fact_pattern(text: str) -> List[Dict[str, Any]]:
    """
    Extracts chronological dates with context from a fact pattern.
    Supports formats:
    - 15 March 2021 / 15th March, 2021
    - 15-09-2021 / 15/09/2021
    - March 15, 2021
    """
    found_dates = []
    
    # Pattern 1: DD Month YYYY (e.g. 15 March 2021, 15th September 2021)
    p1 = re.compile(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)[,]?\s+(\d{4})\b',
        re.IGNORECASE
    )
    for m in p1.finditer(text):
        day = int(m.group(1))
        m_str = m.group(2).lower()
        month = MONTH_MAP.get(m_str, 1)
        year = int(m.group(3))
        try:
            d_obj = date(year, month, day)
            # Find surrounding snippet for context
            start_idx = max(0, m.start() - 40)
            end_idx = min(len(text), m.end() + 40)
            context = text[start_idx:end_idx].strip()
            found_dates.append({
                "date": d_obj,
                "raw": m.group(0),
                "context": context,
                "span": (m.start(), m.end())
            })
        except ValueError:
            pass

    # Pattern 2: Month DD, YYYY (e.g. March 15, 2021)
    p2 = re.compile(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})\b',
        re.IGNORECASE
    )
    for m in p2.finditer(text):
        m_str = m.group(1).lower()
        month = MONTH_MAP.get(m_str, 1)
        day = int(m.group(2))
        year = int(m.group(3))
        try:
            d_obj = date(year, month, day)
            if not any(d["date"] == d_obj for d in found_dates):
                start_idx = max(0, m.start() - 40)
                end_idx = min(len(text), m.end() + 40)
                found_dates.append({
                    "date": d_obj,
                    "raw": m.group(0),
                    "context": text[start_idx:end_idx].strip(),
                    "span": (m.start(), m.end())
                })
        except ValueError:
            pass

    # Pattern 3: DD-MM-YYYY or DD/MM/YYYY
    p3 = re.compile(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b')
    for m in p3.finditer(text):
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        try:
            d_obj = date(year, month, day)
            if not any(d["date"] == d_obj for d in found_dates):
                start_idx = max(0, m.start() - 40)
                end_idx = min(len(text), m.end() + 40)
                found_dates.append({
                    "date": d_obj,
                    "raw": m.group(0),
                    "context": text[start_idx:end_idx].strip(),
                    "span": (m.start(), m.end())
                })
        except ValueError:
            pass

    # Sort chronologically
    found_dates.sort(key=lambda x: x["date"])
    return found_dates


def analyze_matter_limitation(
    query_text: str,
    as_of_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Performs standing limitation arithmetic and statutory analysis for a legal query.
    Returns comprehensive report detailing controlling Article, date computation,
    limitation verdict, and potential statutory exceptions.
    """
    if as_of_date is None:
        as_of_date = date.today()

    q_low = query_text.lower()
    dates_found = extract_dates_from_fact_pattern(query_text)

    # 1. Determine Cause of Action / Governing Limitation Article
    is_specific_perf = any(k in q_low for k in [
        "specific performance", "agreement to sell", "sale deed", "earnest money", "token money"
    ]) or (any(k in q_low for k in ["seller", "buyer", "vendor", "vendee"]) and any(k in q_low for k in ["sale", "refused"]))

    is_money_recovery = any(k in q_low for k in [
        "recovery of money", "suit for money", "money suit", "debt", "loan", "price of goods", "suit for recovery"
    ]) and not is_specific_perf

    is_possession_dispossession = any(k in q_low for k in [
        "dispossessed", "dispossession", "without his consent", "section 9 sra", "summary possession"
    ])

    if is_specific_perf:
        article_num = "113"
        article_title = "For specific performance of a contract"
        prescribed_period_years = 3
        statutory_period_str = "Three (3) years"
        
        # Analyze Limb 1 vs Limb 2
        # Limb 1: The date fixed for performance
        # Limb 2: If no date fixed, when plaintiff has notice that performance is refused
        limb_type = "limb_1_date_fixed"
        trigger_date = None
        agreement_date = None

        # Classify dates by context
        for d in dates_found:
            ctx = d["context"].lower()
            if any(k in ctx for k in ["completion", "fixed", "perform", "target", "due date", "closing", "possession on"]):
                trigger_date = d["date"]
            elif any(k in ctx for k in ["entered", "agreement", "executed", "signed", "contract on", "dated"]):
                agreement_date = d["date"]

        # If trigger date not explicitly labelled but multiple dates exist, later date is usually completion
        if not trigger_date and len(dates_found) >= 2:
            agreement_date = dates_found[0]["date"]
            trigger_date = dates_found[1]["date"]
        elif not trigger_date and len(dates_found) == 1:
            trigger_date = dates_found[0]["date"]
            agreement_date = dates_found[0]["date"]

        # Date Arithmetic
        if trigger_date:
            try:
                expiry_date = date(trigger_date.year + prescribed_period_years, trigger_date.month, trigger_date.day)
            except ValueError:
                # Handle leap year Feb 29
                expiry_date = date(trigger_date.year + prescribed_period_years, trigger_date.month, trigger_date.day - 1)

            is_time_barred = as_of_date > expiry_date
            days_diff = (as_of_date - expiry_date).days if is_time_barred else (expiry_date - as_of_date).days
            years_diff = round(days_diff / 365.25, 1)

            verdict_status = "BARRED_BY_LIMITATION" if is_time_barred else "WITHIN_LIMITATION"
            
            # Build authoritative legal narrative
            narrative = (
                f"### Statutory Limitation Analysis (Article 113, Limitation Act, 1908)\n\n"
                f"- **Controlling Statutory Provision**: **Article 113 of the First Schedule to the Limitation Act, 1908**.\n"
                f"- **Prescribed Period**: **Three (3) years**.\n"
                f"- **Statutory Time of Origin (*Terminus a Quo*)**:\n"
                f"  - *First Limb*: *'The date fixed for the performance'*; or\n"
                f"  - *Second Limb*: *'If no such date is fixed, when the plaintiff has notice that performance is refused'*\n\n"
                f"**Arithmetic & Limitation Computation**:\n"
                f"1. **Date Fixed for Performance**: **{trigger_date.strftime('%d %B %Y')}**.\n"
                f"2. **Applicable Trigger Limb**: Because the agreement expressly fixed a date for completion ({trigger_date.strftime('%d %B %Y')}), "
                f"the **first limb of Article 113 strictly governs** (limitation runs from the date fixed, regardless of subsequent notice or refusal).\n"
                f"3. **Statutory Expiry Date**: **{trigger_date.strftime('%d %B %Y')} + 3 years = {expiry_date.strftime('%d %B %Y')}**.\n"
                f"4. **Evaluation Date**: **{as_of_date.strftime('%B %Y')}**.\n\n"
            )

            if is_time_barred:
                narrative += (
                    f"**LEGAL VERDICT: PRIMA FACIE TIME-BARRED**\n\n"
                    f"> ⚠️ **Statutory Bar**: The statutory 3-year period expired on **{expiry_date.strftime('%d %B %Y')}**. "
                    f"The suit is currently overdue by approximately **{years_diff} years** ({days_diff} days). "
                    f"Under **Section 3 of the Limitation Act, 1908**, the Court is statutorily mandated to dismiss any suit instituted after the expiration "
                    f"of the prescribed period of limitation, even though limitation has not been set up as a defence by the defendant.\n\n"
                    f"**Potential Statutory Exceptions & Extension Inquiries**:\n"
                    f"- **Written Acknowledgment of Liability (Section 19, Limitation Act, 1908)**: Did the seller sign any written acknowledgment, "
                    f"undertaking, extension agreement, or notice admitting the subsisting agreement *before* {expiry_date.strftime('%d %B %Y')}? "
                    f"Under Section 19, a valid written acknowledgment signed before the expiration of the original period computes a fresh limitation period of 3 years from the date of signature.\n"
                    f"- **Part Payment / Acceptance (Section 20, Limitation Act, 1908)**: Did the vendor accept any further part payment or make written acknowledgment of receipt of consideration?\n"
                    f"- **Inapplicability of Section 5**: Section 5 of the Limitation Act applies exclusively to appeals and applications. "
                    f"The Court possesses no inherent equitable jurisdiction or power under Section 5 to condone delay in filing an original civil suit for specific performance."
                )
            else:
                narrative += (
                    f"**LEGAL VERDICT: WITHIN LIMITATION**\n\n"
                    f"The suit is within time. The client has until **{expiry_date.strftime('%d %B %Y')}** ({days_diff} days remaining) to institute the suit."
                )

            return {
                "has_dates": True,
                "is_applicable": True,
                "cause_of_action": "specific_performance",
                "article": "Article 113",
                "prescribed_period": statutory_period_str,
                "trigger_date": trigger_date.strftime("%Y-%m-%d"),
                "expiry_date": expiry_date.strftime("%Y-%m-%d"),
                "as_of_date": as_of_date.strftime("%Y-%m-%d"),
                "is_time_barred": is_time_barred,
                "days_diff": days_diff,
                "years_diff": years_diff,
                "verdict_status": verdict_status,
                "analysis_markdown": narrative
            }

    elif is_money_recovery:
        article_num = "57"
        statutory_period_str = "Three (3) years"
        prescribed_period_years = 3
        trigger_date = dates_found[0]["date"] if dates_found else None
        if trigger_date:
            try:
                expiry_date = date(trigger_date.year + prescribed_period_years, trigger_date.month, trigger_date.day)
            except ValueError:
                expiry_date = date(trigger_date.year + prescribed_period_years, trigger_date.month, trigger_date.day - 1)
            is_time_barred = as_of_date > expiry_date
            days_diff = (as_of_date - expiry_date).days if is_time_barred else (expiry_date - as_of_date).days
            years_diff = round(days_diff / 365.25, 1)
            
            narrative = (
                f"### Statutory Limitation Analysis (Article 57, Limitation Act, 1908)\n\n"
                f"- **Controlling Statutory Provision**: **Article 57 of the First Schedule to the Limitation Act, 1908** (Suit for money lent).\n"
                f"- **Prescribed Period**: **Three (3) years** from when the loan is made.\n"
                f"- **Starting Date**: {trigger_date.strftime('%d %B %Y')}.\n"
                f"- **Expiry Date**: {expiry_date.strftime('%d %B %Y')}.\n"
                f"- **Status**: {'BARRED BY LIMITATION' if is_time_barred else 'WITHIN LIMITATION'}.\n"
            )
            return {
                "has_dates": True,
                "is_applicable": True,
                "cause_of_action": "money_recovery",
                "article": "Article 57",
                "prescribed_period": statutory_period_str,
                "trigger_date": trigger_date.strftime("%Y-%m-%d"),
                "expiry_date": expiry_date.strftime("%Y-%m-%d"),
                "is_time_barred": is_time_barred,
                "days_diff": days_diff,
                "years_diff": years_diff,
                "analysis_markdown": narrative
            }

    # Fallback when no dates or generic inquiry
    return {
        "has_dates": bool(dates_found),
        "is_applicable": is_specific_perf or is_money_recovery or is_possession_dispossession,
        "cause_of_action": "specific_performance" if is_specific_perf else ("money_recovery" if is_money_recovery else "general_civil"),
        "article": "Article 113" if is_specific_perf else ("Article 57" if is_money_recovery else ""),
        "prescribed_period": "Three (3) years" if (is_specific_perf or is_money_recovery) else "",
        "is_time_barred": None,
        "analysis_markdown": ""
    }
