"""
core/statute_lookup.py

ORDER 1.13 - ITEM 3: DETERMINISTIC STATUTE LOOKUP MODE
For 'what does section N of <act> say' queries:
- Returns stored text deterministically with tier, source page, content hash, and banners.
- Zero model calls (LLM bypassed completely).
- Returns 'not in verified store' for missing provisions (never 'does not exist').
- Returns quarantined notice for quarantined acts.
- Acts as deterministic fallback whenever a research memorandum is blocked by the verifier.
"""

import re
from typing import Dict, List, Any, Optional

from core.unified_statute_store import get_unified_statute_store
from core.statutory_validator import parse_statutory_citation

QUARANTINED_ACTS = {
    "PECA_2016", "AMLA_2010", "ARBITRATION_1940", "MFLO_1961",
    "ITO_2001", "LAND_REVENUE_1967", "NI_ACT_1881", "CNSA_1997"
}

DISPUTED_WARNING_BANNER = (
    "> [!WARNING] DISPUTED STATUTORY TEXT — HUMAN CHECK REQUIRED\n"
    "> Official prints of this provision contain contested variations. "
    "Independent verification against authenticated Gazette prints is required before formal court reliance."
)

STATUTE_QUERY_PATTERNS = [
    # "What does section 22 of FIO say?" / "What does Section 489-F PPC say?"
    r'(?:what\s+does\s+)?(?:section|sec\.?|s\.|article|art\.?|order|ord\.?)\s*([a-zA-Z0-9\-\(\)]+)(?:\s+(?:of\s+(?:the\s+)?|in\s+)?([a-zA-Z0-9\s,\.\(\)\-]+?))?\s*(?:say\??|provide\??|state\??|read\??)\b',
    # "Text of section 22 FIO" / "Provide text of Section 415 PPC"
    r'(?:text|statutory\s+text|wording)\s+of\s+(?:section|sec\.?|s\.|article|art\.?|order|ord\.?)\s*([a-zA-Z0-9\-\(\)]+)(?:\s+(?:of\s+(?:the\s+)?|in\s+)?([a-zA-Z0-9\s,\.\(\)\-]+?))?\b',
    # Direct shorthand: "Section 22 FIO", "489-F PPC", "Section 497 CrPC"
    r'^\s*(?:section|sec\.?|s\.|article|art\.?|order|ord\.?)\s*([a-zA-Z0-9\-\(\)]+)\s+([a-zA-Z0-9\s,\.\(\)\-]+?)\s*\??$'
]


def is_statute_lookup_query(query_text: str) -> bool:
    """Detects whether a user query is asking for deterministic statute text."""
    q = query_text.strip().lower()
    for pat in STATUTE_QUERY_PATTERNS:
        if re.search(pat, q, re.I):
            return True
    return False


def statute_lookup(query_text: str) -> Dict[str, Any]:
    """
    Executes deterministic statute lookup.
    Bypasses model call completely.
    """
    store = get_unified_statute_store()
    clean_q = query_text.strip()

    # Parse citation from query
    parsed = parse_statutory_citation(clean_q)
    act_code = parsed.get("act_code") if parsed and parsed.get("is_valid") else None
    primary_num = parsed.get("primary_num") if parsed and parsed.get("is_valid") else None
    rule_num = parsed.get("rule_num") if parsed and parsed.get("is_valid") else None

    # Fallback regex extraction if parse_statutory_citation didn't capture both
    if not act_code or not primary_num:
        m_sec_act = re.search(r'\b(?:section|sec\.?|s\.|article|art\.?)\s*(\d+[A-Za-z]?(?:-[A-Za-z]+)?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z0-9\s,\(\)]+)', clean_q, re.I)
        if m_sec_act:
            raw_sec = m_sec_act.group(1).upper()
            raw_act = m_sec_act.group(2).lower()
            if "fio" in raw_act or "financial institutions" in raw_act:
                act_code, primary_num = "FIO_2001", raw_sec
            elif "ppc" in raw_act or "penal code" in raw_act:
                act_code, primary_num = "PPC_1860", raw_sec
            elif "crpc" in raw_act or "criminal procedure" in raw_act:
                act_code, primary_num = "CRPC_1898", raw_sec
            elif "cpc" in raw_act or "civil procedure" in raw_act:
                act_code, primary_num = "CPC_1908", raw_sec
            elif "limitation" in raw_act:
                act_code, primary_num = "LIMITATION_1908", raw_sec
            elif "tpa" in raw_act or "property" in raw_act:
                act_code, primary_num = "TPA_1882", raw_sec
            elif "stamp" in raw_act:
                act_code, primary_num = "STAMP_1899", raw_sec
            elif "registration" in raw_act:
                act_code, primary_num = "REGISTRATION_1908", raw_sec
            elif "bco" in raw_act or "banking companies" in raw_act:
                act_code, primary_num = "BCO_1962", raw_sec
            elif "contract" in raw_act:
                act_code, primary_num = "CONTRACT_1872", raw_sec

    # 1. Quarantined Act check
    if act_code in QUARANTINED_ACTS:
        return {
            "status": "quarantined",
            "is_quarantined": True,
            "act_code": act_code,
            "message": f"Act '{act_code}' is quarantined pending official gazette page-verification. Operative text is withheld.",
            "no_model_call": True
        }

    if not act_code or not primary_num:
        return {
            "status": "not_in_store",
            "message": f"Could not resolve statutory citation from query: '{query_text}'. Provision is not in verified store.",
            "no_model_call": True
        }

    # 2. Look up provision in unified store
    rec = None
    if rule_num and act_code == "CPC_1908":
        cid = f"CPC_1908_ORD_{str(primary_num).upper()}_R_{str(rule_num).upper()}"
        rec = store.get_by_canonical_id(cid)
    else:
        rec = store.get_provision(act_code, str(primary_num))

    # 3. Missing provision check
    if not rec:
        return {
            "status": "not_in_store",
            "act_code": act_code,
            "provision_num": primary_num,
            "message": f"Provision '{primary_num}' of Act '{act_code}' is not in verified store",
            "no_model_call": True
        }

    # 4. Operative provision found
    tier = rec.get("tier", "ingested_unreviewed")
    banners = []
    if tier == "disputed":
        banners.append(DISPUTED_WARNING_BANNER)

    return {
        "status": "success",
        "canonical_id": rec.get("canonical_id"),
        "title": rec.get("title"),
        "statutory_text": rec.get("text") or rec.get("statutory_text"),
        "tier": tier,
        "source_page": rec.get("source_page"),
        "content_hash": rec.get("content_hash"),
        "in_force": rec.get("in_force", True),
        "page_verified": rec.get("page_verified", False),
        "quoting_allowed": rec.get("quoting_allowed", False),
        "banners": banners,
        "no_model_call": True
    }


def get_verified_statute_fallback(query_text: str) -> List[Dict[str, Any]]:
    """Returns verified statute fallback objects for blocked memorandums."""
    lookup_res = statute_lookup(query_text)
    if lookup_res.get("status") == "success":
        banners_text = "\n\n".join(lookup_res.get("banners", []))
        disp_txt = f"{banners_text}\n\n{lookup_res.get('statutory_text')}" if banners_text else lookup_res.get("statutory_text")
        return [{
            "canonical_id": lookup_res.get("canonical_id"),
            "display_name": lookup_res.get("title"),
            "tier": lookup_res.get("tier"),
            "source_page": lookup_res.get("source_page"),
            "content_hash": lookup_res.get("content_hash"),
            "is_disputed": lookup_res.get("tier") == "disputed",
            "text": disp_txt
        }]
    return []
