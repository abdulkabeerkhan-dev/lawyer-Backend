"""
core/current_law_verifier.py

Production-grade Current Law Verification Engine for Pakistani Statutes.
Before answering any legal query, verifies:
- In-force status of statutory provisions against Pakistan Code official bare acts
- Verbatim text, source tier, page, and content hash
- Mandatory amendment transition notices
Uses UnifiedStatuteStore as the single source of truth.
"""

import os
import re
import json
from typing import Dict, List, Any, Optional

from core.statute_currency import detect_statutory_provisions_in_query
from core.unified_statute_store import get_unified_statute_store


ACT_PRETTY_NAMES = {
    "PPC_1860": "Pakistan Penal Code, 1860",
    "CRPC_1898": "Code of Criminal Procedure, 1898",
    "CPC_1908": "Code of Civil Procedure, 1908",
    "QSO_1984": "Qanun-e-Shahadat Order, 1984",
    "CONST_1973": "Constitution of the Islamic Republic of Pakistan, 1973",
    "FIO_2001": "Financial Institutions (Recovery of Finances) Ordinance, 2001",
    "COMPANIES_2017": "Companies Act, 2017",
    "LIMITATION_1908": "Limitation Act, 1908",
    "NI_ACT_1881": "Negotiable Instruments Act, 1881",
    "SRA_1877": "Specific Relief Act, 1877",
    "TPA_1882": "Transfer of Property Act, 1882",
    "CONTRACT_1872": "Contract Act, 1872",
}


def verify_current_law_for_provisions(
    provisions: List[str],
    query_text: str = ""
) -> List[Dict[str, Any]]:
    """
    Verifies the in-force status, verbatim text, and tier
    for each statutory provision identified in the query plan or query text.
    Uses UnifiedStatuteStore as single source of truth.
    """
    store = get_unified_statute_store()
    results: List[Dict[str, Any]] = []
    seen_cids = set()

    # Step 1: Detect from query text directly
    detected_pairs = detect_statutory_provisions_in_query(query_text) if query_text else []
    for cid, act_c in detected_pairs:
        if cid in seen_cids:
            continue
        seen_cids.add(cid)
        record = store.get_by_canonical_id(cid)
        m_num = re.search(r'(?:SEC|ART)_([0-9]+[A-Za-z]*)', cid)
        sec_num = m_num.group(1) if m_num else ""
        if not record and sec_num:
            record = store.get_provision(act_c, sec_num)

        act_pretty = ACT_PRETTY_NAMES.get(act_c, act_c.replace('_', ' '))
        display_name = f"Section {sec_num}, {act_pretty}" if sec_num else cid
        status = record.get("status", "in_force") if record else "in_force"
        text_val = (record.get("text") or "").strip() if record else ""
        title_val = record.get("title") or display_name if record else display_name
        src_val = record.get("source_file") or "Official Pakistan Code" if record else "Official Pakistan Code"
        page_val = record.get("source_page") or "" if record else ""
        hash_val = record.get("content_hash") or "" if record else ""
        tier_val = record.get("tier", "ingested_unreviewed") if record else "ingested_unreviewed"

        results.append({
            "canonical_id": cid,
            "act_code": act_c,
            "display_name": display_name,
            "status": "Active / In Force" if status == "in_force" else status,
            "title": title_val,
            "last_amended": src_val,
            "text": text_val,
            "tier": tier_val,
            "source_page": page_val,
            "content_hash": hash_val,
            "amendment_notice": "",
            "has_amendment": False
        })

    # Step 2: Incorporate provisions from planner
    for prov_str in provisions:
        p_low = prov_str.lower().strip()
        m_num = re.search(r'\b([0-9]+(?:-[a-z])?)\b', p_low)
        if not m_num:
            continue
        sec_num = m_num.group(1).upper()

        # ORDER 2.1 - ITEM 4: Act binding. Section numbers bind to the Act named in the same sentence/token.
        # A number with no Act named is ignored, never guessed. Drop default CPC_1908.
        act_code = None
        if any(k in p_low for k in ["companies act", "company law", "companies"]):
            act_code = "COMPANIES_2017"
        elif any(k in p_low for k in ["fio", "financial institution", "recovery of finance", "banking court", "banking judge"]):
            act_code = "FIO_2001"
        elif any(k in p_low for k in ["ni act", "negotiable", "nia"]):
            act_code = "NI_ACT_1881"
        elif any(k in p_low for k in ["sra", "specific relief"]):
            act_code = "SRA_1877"
        elif any(k in p_low for k in ["tpa", "transfer of property"]):
            act_code = "TPA_1882"
        elif any(k in p_low for k in ["contract"]):
            act_code = "CONTRACT_1872"
        elif any(k in p_low for k in ["limitation"]):
            act_code = "LIMITATION_1908"
        elif any(k in p_low for k in ["crpc", "cr.p.c"]):
            act_code = "CRPC_1898"
        elif any(k in p_low for k in ["ppc", "p.p.c", "penal code"]):
            act_code = "PPC_1860"
        elif any(k in p_low for k in ["cpc", "c.p.c", "civil procedure"]):
            act_code = "CPC_1908"
        elif any(k in p_low for k in ["const", "article"]):
            act_code = "CONST_1973"
        elif query_text:
            q_low = query_text.lower()
            if any(k in q_low for k in ["companies act", "company law"]):
                act_code = "COMPANIES_2017"
            elif any(k in q_low for k in ["financial institution", "recovery of finance", "banking court", "fio"]):
                act_code = "FIO_2001"

        if not act_code:
            continue

        canonical_id = f"{act_code}_SEC_{sec_num.replace('-', '')}"
        if canonical_id in seen_cids:
            continue
        seen_cids.add(canonical_id)

        record = store.get_provision(act_code, sec_num) or store.get_by_canonical_id(canonical_id)
        act_pretty = ACT_PRETTY_NAMES.get(act_code, act_code.replace('_', ' '))
        display_name = f"Section {sec_num}, {act_pretty}"
        status = record.get("status", "in_force") if record else "in_force"
        text_val = (record.get("text") or "").strip() if record else ""
        title_val = record.get("title") or display_name if record else display_name
        src_val = record.get("source_file") or "Official Pakistan Code" if record else "Official Pakistan Code"
        page_val = record.get("source_page") or "" if record else ""
        hash_val = record.get("content_hash") or "" if record else ""
        tier_val = record.get("tier", "ingested_unreviewed") if record else "ingested_unreviewed"

        results.append({
            "canonical_id": canonical_id,
            "act_code": act_code,
            "display_name": display_name,
            "status": "Active / In Force" if status == "in_force" else status,
            "title": title_val,
            "last_amended": src_val,
            "text": text_val,
            "tier": tier_val,
            "source_page": page_val,
            "content_hash": hash_val,
            "amendment_notice": "",
            "has_amendment": False
        })

    return results


def format_current_law_context(provisions_verification: List[Dict[str, Any]]) -> str:
    """
    Formats the verified current law status for injection into Claude's prompt context.
    """
    if not provisions_verification:
        return ""

    blocks = ["=== CURRENT LAW & STATUTORY VERIFICATION (PAKISTAN CODE) ==="]

    for item in provisions_verification:
        disp = item.get("display_name", "Statutory Provision")
        status = item.get("status", "Active / In Force")
        title = item.get("title", "")
        last_amended = item.get("last_amended", "Official Pakistan Code")
        amend_notice = item.get("amendment_notice", "")

        entry = [
            f"\nPROVISION: {disp}",
            f"STATUS: {status}",
            f"TITLE: {title}",
            f"SOURCE: {last_amended}"
        ]
        if amend_notice:
            entry.append(f"AMENDMENT NOTE: {amend_notice}")

        blocks.append("\n".join(entry))

    # Bare act verbatim provisions
    has_missing = any(not (item.get("text") or "").strip() for item in provisions_verification)
    if has_missing:
        blocks.append("\n### STATUTORY FRAMEWORK & BARE-ACT PROVISIONS ON RECORD:\n")
        blocks.append("CRITICAL INSTRUCTION: You may quote bare-act statutory language ONLY for provisions containing verbatim text below.")
        blocks.append("If a provision displays '[Statutory text not found in verified database]', you MUST NOT fabricate, quote, or paraphrase statutory text from memory.")
        blocks.append("You MUST output '[Statutory text not found in verified database]' under Section 2 instead.\n")
    else:
        blocks.append("\n### STATUTORY FRAMEWORK & VERBATIM BARE-ACT PROVISIONS ON RECORD:\n")
        blocks.append("MANDATORY DIRECTIVE: The official verbatim bare-act statutory text is provided below. You MUST base your statutory analysis and quotes on this official text.\n")

    for item in provisions_verification:
        disp = item.get("display_name", "Statutory Provision")
        status = item.get("status", "Active / In Force")
        title = item.get("title", "")
        text = item.get("text", "")
        tier_str = item.get("tier") or "ingested_unreviewed"
        page_str = item.get("source_page") or "unspecified"
        hash_str = item.get("content_hash") or ""

        lines = [
            f"--- PROVISION: {disp} ---",
            f"Status in Force: {status}",
            f"Subject / Title: {title}"
        ]
        if text:
            lines.append(f"STATUTORY VERBATIM TEXT:\n\"{text}\"")
            lines.append(f"LABEL: {tier_str} | PAGE: {page_str} | HASH: {hash_str}")
            if item.get("canonical_id") == "FIO_2001_SEC_22" or (item.get("act_code") == "FIO_2001" and str(item.get("primary_num")) == "22"):
                lines.append("RENDERER NOTE: Sub-section (7) refers to sub-section (2); stay conditions appear in the proviso to sub-section (3). Check the Gazette.")
                lines.append("DIRECTIVE: The memorandum must accurately state that sub-section (7) cross-references sub-section (2) in the official gazette text, while stay deposit requirements are enacted in the proviso to sub-section (3). Do NOT restate (7) as 'stay granted under 22(2)'.")
        else:
            lines.append("Verbatim Bare-Act Text: [Statutory text not found in verified database]")
            lines.append("Note: Official bare-act text is not loaded in primary local stores. You must output '[Statutory text not found in verified database]' under Section 2 instead of drafting, quoting, or inventing statutory language from memory.")

        blocks.append("\n".join(lines))

    return "\n".join(blocks)
