"""
legal_ai/retrieval/query_planner.py

Fast, structured Query Planner for Pakistani Legal AI retrieval.
Architecture:
1. Deterministic Code-First Extraction:
   - Explicit references (e.g. 's.302 PPC', '497 CrPC', 'Order VII Rule 11 CPC', 'Art 199')
     parsed and canonicalized via resolve_statute_id.
   - Defined terms matched against data/definitions_index.json.
2. Claude LLM Call (claude-haiku-4-5 / claude-3-5-sonnet):
   - Returns JSON: {area_of_law, forum, likely_acts, defined_terms, explicit_refs}.
   - Code-parsed explicit refs and defined terms are preserved and merged.
3. Fallback:
   - If LLM is unavailable or fails, rule-based deterministic classifier runs instantly.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from legal_ai.retrieval.statute_resolver import resolve_statute_id
from legal_ai.retrieval.statute_search import normalize_statute_query_spelling, get_section
from legal_ai.config import get_anthropic_client, CLAUDE_MODEL

logger = logging.getLogger(__name__)

_DEFINITIONS_INDEX: Optional[Dict[str, Any]] = None

def _get_definitions_index() -> Dict[str, Any]:
    global _DEFINITIONS_INDEX
    if _DEFINITIONS_INDEX is not None:
        return _DEFINITIONS_INDEX
    base_dir = Path(__file__).resolve().parent.parent.parent
    idx_path = base_dir / "data" / "definitions_index.json"
    if idx_path.exists():
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                _DEFINITIONS_INDEX = json.load(f)
        except Exception as e:
            logger.debug(f"Failed to load definitions index: {e}")
            _DEFINITIONS_INDEX = {}
    else:
        _DEFINITIONS_INDEX = {}
    return _DEFINITIONS_INDEX


# Common act shorthand mapping to canonical act codes
ACT_SHORTHAND_MAP = {
    "PPC": "PPC_1860",
    "CRPC": "CRPC_1898",
    "CPC": "CPC_1908",
    "CONST": "CONST_1973",
    "CONSTITUTION": "CONST_1973",
    "QSO": "QSO_1984",
    "FIO": "FIO_2001",
    "NAO": "NAO_1999",
    "ITO": "ITO_2001",
    "INCOME TAX": "ITO_2001",
    "SALES TAX": "SALES_TAX_1990",
    "CNSA": "CNSA_1997",
    "ATA": "ATA_1997",
    "PRPA": "PRPA_2009",
    "SRPO": "SRPO_1979",
    "TPA": "TPA_1882",
    "TRANSFER OF PROPERTY": "TPA_1882",
    "CONTRACT": "CONTRACT_1872",
    "CONTRACT ACT": "CONTRACT_1872",
    "SRA": "SRA_1877",
    "SPECIFIC RELIEF": "SRA_1877",
    "LIMITATION": "LIMITATION_1908",
    "COMPANIES ORDINANCE": "COMPANIES_1984",
    "COMPANIES ACT": "COMPANIES_2017",
}


def parse_explicit_references(query: str) -> List[Dict[str, Any]]:
    """
    Deterministically parses explicit statutory references in the user query.
    Examples:
      - 's.302 PPC' -> {act: 'PPC_1860', section: '302', canonical_id: 'PPC_1860_SEC_302'}
      - '497 CrPC' -> {act: 'CRPC_1898', section: '497', canonical_id: 'CRPC_1898_SEC_497'}
      - 'Order VII Rule 11 CPC' -> {act: 'CPC_1908', section: 'ORD_VII_R_11', canonical_id: 'CPC_1908_ORD_VII_R_11'}
      - 'Art 199' / 'Article 199 Constitution' -> {act: 'CONST_1973', section: '199', canonical_id: 'CONST_1973_ART_199'}
      - 'Section 11 Sales Tax Act' -> {act: 'SALES_TAX_1990', section: '11', canonical_id: 'SALES_TAX_1990_SEC_11'}
    """
    if not query:
        return []

    norm_q = normalize_statute_query_spelling(query)
    results = []
    seen_cids = set()

    # 1. CPC Order and Rule patterns: e.g. "Order 7 Rule 11", "O. VII R. 11", "Order VII Rule 11 CPC"
    cpc_pattern = re.compile(
        r'\b(?:Order|Ord|O\.?)\s*([0-9IVXLCDM]+)\s*(?:Rule|R\.?)\s*([0-9A-Za-z]+)(?:\s*(?:of\s+(?:the\s+)?)?(?:CPC|Civil\s+Procedure\s+Code))?\b',
        re.IGNORECASE
    )
    for m in cpc_pattern.finditer(norm_q):
        ord_num = m.group(1).upper()
        rule_num = m.group(2).upper()
        sec_str = f"Order {ord_num} Rule {rule_num}"
        cand_id = resolve_statute_id(f"CPC_1908_ORDER_{ord_num}_RULE_{rule_num}")
        if cand_id and cand_id not in seen_cids:
            seen_cids.add(cand_id)
            results.append({
                "raw": m.group(0),
                "act_code": "CPC_1908",
                "section": sec_str,
                "canonical_id": cand_id,
                "confidence": "high"
            })

    # 2. Constitutional / QSO Articles: e.g. "Article 199", "Art 10A", "Art. 199 of the Constitution", "Art 17 QSO"
    art_pattern = re.compile(
        r'\b(?:Article|Art\.?)\s*(\d+[A-Za-z]?)(?:\s*(?:of\s+(?:the\s+)?)?(Constitution|Const|QSO|Qanun-e-Shahadat))?\b',
        re.IGNORECASE
    )
    for m in art_pattern.finditer(norm_q):
        art_num = m.group(1).upper()
        act_hint = m.group(2)
        act_code = "CONST_1973"
        if act_hint and any(q in act_hint.upper() for q in ["QSO", "QANUN"]):
            act_code = "QSO_1984"

        cand_id = resolve_statute_id(f"{act_code}_ART_{art_num}")
        if cand_id and cand_id not in seen_cids:
            seen_cids.add(cand_id)
            results.append({
                "raw": m.group(0),
                "act_code": act_code,
                "section": art_num,
                "canonical_id": cand_id,
                "confidence": "high"
            })

    # 3. Section + Act: e.g. "s.302 PPC", "Section 497 CrPC", "Section 111 ITO", "s. 2(g) FIO", "Section 11 Sales Tax"
    sec_act_pattern = re.compile(
        r'\b(?:Section|Sec\.?|S\.)\s*(\d+[A-Za-z]?(?:\s*\([0-9A-Za-z]+\))?)\s*(?:of\s+(?:the\s+)?)?([A-Za-z\s]+(?:Act|Ordinance|PPC|CrPC|CPC|FIO|NAO|ITO|CNSA|ATA|PRPA|SRPO|SRA|TPA|QSO))?\b',
        re.IGNORECASE
    )
    for m in sec_act_pattern.finditer(norm_q):
        sec_num = m.group(1).strip()
        act_raw = (m.group(2) or "").strip().upper()
        # Look up act shorthand
        act_code = None
        for k, v in ACT_SHORTHAND_MAP.items():
            if k in act_raw:
                act_code = v
                break

        if act_code:
            res = get_section(act_code, sec_num)
            if res and res.get("canonical_id"):
                cid = res["canonical_id"]
                if cid not in seen_cids:
                    seen_cids.add(cid)
                    results.append({
                        "raw": m.group(0),
                        "act_code": act_code,
                        "section": sec_num,
                        "canonical_id": cid,
                        "confidence": "high"
                    })

    # 4. Number + Act shorthand: e.g. "302 PPC", "497 CrPC", "489-F PPC", "561-A CrPC", "115 CPC", "42 SRA"
    num_act_pattern = re.compile(
        r'\b(\d+[A-Za-z]?(?:[\-_][A-Za-z])?)\s+(PPC|CRPC|CPC|FIO|NAO|ITO|QSO|SRA|TPA|CNSA|ATA)\b',
        re.IGNORECASE
    )
    for m in num_act_pattern.finditer(norm_q):
        sec_num = m.group(1).upper()
        act_shorthand = m.group(2).upper()
        act_code = ACT_SHORTHAND_MAP.get(act_shorthand)
        if act_code:
            res = get_section(act_code, sec_num)
            if res and res.get("canonical_id"):
                cid = res["canonical_id"]
                if cid not in seen_cids:
                    seen_cids.add(cid)
                    results.append({
                        "raw": m.group(0),
                        "act_code": act_code,
                        "section": sec_num,
                        "canonical_id": cid,
                        "confidence": "high"
                    })

    return results


def match_defined_terms(query: str) -> List[str]:
    """
    Matches query terms against data/definitions_index.json.
    Normalizes spelling (willful <-> wilful).
    """
    if not query:
        return []
    idx = _get_definitions_index()
    if not idx:
        return []

    norm_q = normalize_statute_query_spelling(query).lower()
    matches = []

    # Check key multi-word phrases first
    for term in idx.keys():
        t_low = term.lower()
        if len(t_low) >= 4 and t_low in norm_q:
            # Word boundary check
            pattern = r'\b' + re.escape(t_low) + r'\b'
            if re.search(pattern, norm_q):
                matches.append(term)

    # Sort by length descending to prioritize specific phrases
    matches.sort(key=lambda x: len(x), reverse=True)
    return matches[:10]


def rule_based_fallback_plan(query: str) -> Dict[str, Any]:
    """
    Fast rule-based query plan fallback when LLM is unavailable.
    """
    q_low = query.lower()
    explicit_refs = parse_explicit_references(query)
    defined_terms = match_defined_terms(query)

    area_of_law = "general_legal"
    forum = "High Court"
    likely_acts = []

    # Inferred area of law
    if any(k in q_low for k in ["bail", "fir", "arrest", "murder", "theft", "ppc", "crpc", "cognizable", "challan", "police"]):
        area_of_law = "criminal"
        forum = "Sessions Court"
        likely_acts = ["PPC_1860", "CRPC_1898"]
    elif any(k in q_low for k in ["loan", "bank", "finance", "repay", "recovery", "borrower", "fio", "default"]):
        area_of_law = "banking"
        forum = "Banking Court"
        likely_acts = ["FIO_2001", "NAO_1999"]
    elif any(k in q_low for k in ["tax", "income tax", "sales tax", "assessment", "audit", "fbr", "ito"]):
        area_of_law = "taxation"
        forum = "Appellate Tribunal Inland Revenue"
        likely_acts = ["ITO_2001", "SALES_TAX_1990"]
    elif any(k in q_low for k in ["constitution", "fundamental rights", "writ", "art 199", "article 199", "184(3)"]):
        area_of_law = "constitutional"
        forum = "High Court"
        likely_acts = ["CONST_1973"]
    elif any(k in q_low for k in ["rent", "eviction", "landlord", "tenant", "rented premises", "premises"]):
        area_of_law = "rent"
        forum = "Rent Controller"
        likely_acts = ["PRPA_2009", "SRPO_1979"]
    elif any(k in q_low for k in ["suit", "injunction", "decree", "cpc", "order vii", "plaint", "rejection"]):
        area_of_law = "civil"
        forum = "Civil Court"
        likely_acts = ["CPC_1908", "SRA_1877"]

    # Incorporate acts from explicit refs
    for ref in explicit_refs:
        act = ref.get("act_code")
        if act and act not in likely_acts:
            likely_acts.insert(0, act)

    return {
        "area_of_law": area_of_law,
        "forum": forum,
        "likely_acts": likely_acts,
        "defined_terms": defined_terms,
        "explicit_refs": explicit_refs
    }


async def plan_statute_query(query: str) -> Dict[str, Any]:
    """
    Plans legal retrieval for a statutory query.
    1. Deterministically parses explicit citations (s.302 PPC, 497 CrPC, etc.)
    2. Matches statutory definition terms (e.g. willful default)
    3. Prompts Claude for area_of_law, forum, and likely_acts in JSON format
    4. Merges code-parsed references and falls back safely if LLM is unavailable.
    """
    if not query or not query.strip():
        return {
            "area_of_law": "general_legal",
            "forum": "High Court",
            "likely_acts": [],
            "defined_terms": [],
            "explicit_refs": []
        }

    # Step 1: Code-first explicit citations & definitions extraction
    code_explicit_refs = parse_explicit_references(query)
    code_defined_terms = match_defined_terms(query)

    client = get_anthropic_client()
    if not client:
        fallback = rule_based_fallback_plan(query)
        fallback["explicit_refs"] = code_explicit_refs
        fallback["defined_terms"] = code_defined_terms
        return fallback

    # Step 2: Structured Claude Call
    system_prompt = (
        "You are an expert Pakistani Legal Retrieval Query Planner.\n"
        "Analyze the user query and return ONLY a valid JSON object with these exact keys:\n"
        "{\n"
        '  "area_of_law": "<criminal|civil|banking|constitutional|taxation|corporate|rent|family|service>",\n'
        '  "forum": "<High Court|Supreme Court|Banking Court|Sessions Court|Civil Court|Rent Controller|etc>",\n'
        '  "likely_acts": ["<ACT_CODE_1>", "<ACT_CODE_2>"],\n'
        '  "defined_terms": ["<term1>"],\n'
        '  "explicit_refs": ["<citation1>"]\n'
        "}\n"
        "Common Act codes: PPC_1860, CRPC_1898, CPC_1908, CONST_1973, FIO_2001, NAO_1999, ITO_2001, SALES_TAX_1990, QSO_1984, PRPA_2009, SRA_1877, TPA_1882.\n"
        "Return NO explanation, NO markdown formatting outside the JSON."
    )

    try:
        from legal_ai.config import apply_model_compat
        response = await client.messages.create(**apply_model_compat(dict(
            model=CLAUDE_MODEL,
            max_tokens=400,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Analyze query: {query}"}]
        )))
        # thinking models put a thinking block first; read the text blocks only
        raw_text = "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text").strip()
        # Clean json backticks if any
        raw_text = re.sub(r'^```json\s*', '', raw_text)
        raw_text = re.sub(r'^```\s*', '', raw_text)
        raw_text = re.sub(r'\s*```$', '', raw_text).strip()
        parsed = json.loads(raw_text)

        # Merge code-parsed items
        merged_refs = list(code_explicit_refs)
        merged_terms = list(set(parsed.get("defined_terms", []) + code_defined_terms))
        merged_acts = list(parsed.get("likely_acts", []))
        for ref in code_explicit_refs:
            act = ref.get("act_code")
            if act and act not in merged_acts:
                merged_acts.insert(0, act)

        return {
            "area_of_law": parsed.get("area_of_law", "general_legal"),
            "forum": parsed.get("forum", "High Court"),
            "likely_acts": merged_acts,
            "defined_terms": merged_terms,
            "explicit_refs": merged_refs
        }
    except Exception as e:
        logger.debug(f"[QueryPlanner] LLM call failed, falling back to rule-based planner: {e}")
        fallback = rule_based_fallback_plan(query)
        fallback["explicit_refs"] = code_explicit_refs
        fallback["defined_terms"] = code_defined_terms
        return fallback


# Alias for compatibility
plan_legal_query = plan_statute_query
