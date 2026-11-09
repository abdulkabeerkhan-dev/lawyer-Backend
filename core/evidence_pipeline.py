"""
core/evidence_pipeline.py

Pipeline Orchestrator for Stages 4, 5, and 6 of the Legal Research Pipeline Fix Spec:
- Stage 4: Strict Evidence Pack assembly (S1..Sn, C1..Cn) with two-way cross linking.
- Stage 5: Grounded prompting and JSON generation directives (zero external memory).
- Stage 6: Deterministic code-level verification, honest badging, and markdown rendering.
"""

import json
import logging
import re
from typing import Dict, List, Any, Tuple, Optional, Set

from core.case_integrity import verify_case_integrity, sanitize_ratio_text, normalize_citation
from core.evidence_pack import EvidencePack, assemble_evidence_pack
from core.evidence_verifier import EvidenceVerifier, format_verified_memo_to_markdown
from core.unified_statute_store import get_unified_statute_store

logger = logging.getLogger(__name__)


ACT_CODE_MAP = {
    "PPC": "PPC_1860",
    "PAKISTAN PENAL CODE": "PPC_1860",
    "PENAL CODE": "PPC_1860",
    "CRPC": "CRPC_1898",
    "CRIMINAL PROCEDURE": "CRPC_1898",
    "CODE OF CRIMINAL PROCEDURE": "CRPC_1898",
    "CPC": "CPC_1908",
    "CIVIL PROCEDURE": "CPC_1908",
    "CODE OF CIVIL PROCEDURE": "CPC_1908",
    "LIMITATION": "LIMITATION_1908",
    "LIMITATION ACT": "LIMITATION_1908",
    "SPECIFIC RELIEF": "SRA_1877",
    "SRA": "SRA_1877",
    "CONTRACT": "CONTRACT_1872",
    "CONTRACT ACT": "CONTRACT_1872",
    "TPA": "TPA_1882",
    "TRANSFER OF PROPERTY": "TPA_1882",
    "QSO": "QSO_1984",
    "QANUN-E-SHAHADAT": "QSO_1984",
    "CONST": "CONST_1973",
    "CONSTITUTION": "CONST_1973",
    "BENAMI": "BENAMI_2017",
    "FAMILY COURTS": "FAMILY_COURTS_1964",
    "FAMILY COURTS ACT": "FAMILY_COURTS_1964",
    "FCA": "FAMILY_COURTS_1964",
    "MFLO": "MFLO_1961",
    "MUSLIM FAMILY LAWS": "MFLO_1961",
    "DMMA": "DMMA_1939",
    "DISSOLUTION OF MUSLIM MARRIAGES": "DMMA_1939",
    "GWA": "GWA_1890",
    "GUARDIANS AND WARDS": "GWA_1890",
    "FIO": "FIO_2001",
    "FINANCIAL INSTITUTIONS": "FIO_2001",
    "NEGOTIABLE INSTRUMENTS": "NI_ACT_1881",
    "NI ACT": "NI_ACT_1881",
    "NIA": "NI_ACT_1881",
    "ARBITRATION": "ARBITRATION_1940",
    "RENT": "PRPA_2009",
    "PRPA": "PRPA_2009",
    "PUNJAB RENTED PREMISES": "PRPA_2009",
    "SRPO": "SRPO_1979",
    "SINDH RENTED PREMISES": "SRPO_1979",
    "CIVIL SERVANTS": "CIVIL_SERVANTS_1973",
    "LAND REVENUE": "LAND_REVENUE_1967",
    "ILLEGAL DISPOSSESSION": "ILLEGAL_DISPOSSESSION_2005",
    "PECA": "PECA_2016",
    "ELECTRONIC CRIMES": "PECA_2016",
    "TRADEMARKS": "TRADEMARKS_2001",
    "TRADEMARK": "TRADEMARKS_2001",
    "COPYRIGHT": "COPYRIGHT_1962",
    "SHARIAT APPLICATION": "SHARIAT_APPLICATION_1962",
    "SHARIAT": "SHARIAT_APPLICATION_1962",
    "PARTITION ACT": "PARTITION_1893",
    "PARTITION": "PARTITION_1893",
    "WOMEN PROPERTY": "WOMEN_PROPERTY_RIGHTS_2020",
    "COMPANIES ACT": "COMPANIES_2017",
    "COMPANIES": "COMPANIES_2017",
}


def _int_to_roman(num: int) -> str:
    val = [50, 40, 10, 9, 5, 4, 1]
    syb = ["L", "XL", "X", "IX", "V", "IV", "I"]
    res = ""
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            res += syb[i]
            num -= val[i]
        i += 1
    return res


def normalize_provision_string_to_canonical_id(s: str) -> Optional[str]:
    """
    Normalizes human-readable provision references (e.g. 'Section 489-F PPC', 'Article 64-A Limitation Act')
    or raw canonical IDs into authoritative canonical IDs (e.g. 'PPC_1860_SEC_489F').
    """
    if not s:
        return None
    s_str = str(s).strip()
    if re.match(r'^[A-Z0-9_]+_(?:SEC|ART|ORD|RULE)_[0-9A-Z_()]+$', s_str, re.IGNORECASE):
        return s_str.upper()

    m_ord_rule = re.search(r'(?:order|ord\.?)\s*([0-9IVXLCDM]+)\s*(?:rule|r\.?)\s*([0-9]+[A-Za-z]?)', s_str, re.I)
    if m_ord_rule and any(k in s_str.upper() for k in ["CPC", "CIVIL PROCEDURE", "CODE OF CIVIL"]):
        ord_val = m_ord_rule.group(1).upper()
        r_val = m_ord_rule.group(2).upper()
        if ord_val.isdigit():
            ord_val = _int_to_roman(int(ord_val))
        return f"CPC_1908_ORD_{ord_val}_R_{r_val}"

    m_ord_only = re.search(r'(?:order|ord\.?)\s*([0-9IVXLCDM]+)', s_str, re.I)
    if m_ord_only and any(k in s_str.upper() for k in ["CPC", "CIVIL PROCEDURE", "CODE OF CIVIL"]):
        ord_val = m_ord_only.group(1).upper()
        if ord_val.isdigit():
            ord_val = _int_to_roman(int(ord_val))
        return f"CPC_1908_ORD_{ord_val}"

    act_code = None
    s_upper = s_str.upper()
    for kw, code in sorted(ACT_CODE_MAP.items(), key=lambda x: -len(x[0])):
        if kw in s_upper:
            act_code = code
            break

    is_art = bool(re.search(r'\b(?:article|art)\b', s_str, re.I))
    is_ord = bool(re.search(r'\b(?:order|ord)\b', s_str, re.I))
    unit = "ART" if is_art else ("ORD" if is_ord else "SEC")

    m_num = re.search(r'(?:section|sec\.?|article|art\.?|order|ord\.?|s\.)\s*([0-9IVXLCDM]+[A-Za-z]?(?:-[A-Za-z])?)', s_str, re.I)
    if not m_num:
        m_num = re.search(r'([0-9]+[A-Za-z]?(?:-[A-Za-z])?)', s_str)
    if not m_num:
        return None

    num_str = m_num.group(1).upper().replace('-', '')
    roman_map = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
        'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15, 'XVI': 16, 'XVII': 17, 'XVIII': 18,
        'XIX': 19, 'XX': 20, 'XXI': 21, 'XXXVII': 37, 'XXXVIII': 38, 'XXXIX': 39
    }
    if num_str in roman_map and unit != "ORD":
        num_str = str(roman_map[num_str])

    if act_code:
        return f"{act_code}_{unit}_{num_str}"
    return None



def execute_stage4_evidence_pack(
    verified_statutory_provisions: List[Dict[str, Any]],
    precedent_cards: List[Dict[str, Any]],
    query_text: str,
    query_plan: Any = None
) -> Tuple[EvidencePack, List[Dict[str, Any]]]:
    """
    Executes Stage 4 of the pipeline:
    1. Filters precedent cards through deterministic case integrity rules.
    2. Gathers and normalizes admitted statutory provisions.
    3. Performs two-way cross-linking (statutes pull cases, cases pull invoked statutes).
    4. Assembles immutable EvidencePack with S1..Sn and C1..Cn IDs.
    """
    domain = "civil"
    if query_plan and getattr(query_plan, "legal_domain", None):
        domain = query_plan.legal_domain[0]

    # 1. Filter case precedents through case integrity engine
    clean_cases = []
    for card in precedent_cards:
        is_valid, reason, sanitized = verify_case_integrity(
            card,
            query_domain=domain,
            sub_topic=query_text,
            query_text=query_text
        )
        if is_valid:
            clean_cases.append(sanitized)
        else:
            logger.warning(f"[STAGE4_INTEGRITY_DROP] Excluded precedent '{card.get('citation')}': {reason}")

    # 2. Gather statutory provisions and build admitted_cids gate
    statute_records: List[Dict[str, Any]] = []
    seen_provisions = set()
    admitted_cids: Set[str] = set()

    for p in (verified_statutory_provisions or []):
        cid = p.get("canonical_id")
        if cid:
            admitted_cids.add(str(cid).strip().upper())

    try:
        from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern
        plan_dom = getattr(query_plan, "primary_domain", None) if query_plan else None
        decomp = extract_legal_issues_from_fact_pattern(query_text, planner_domain=plan_dom)
        for issue in getattr(decomp, "issues", []):
            for prov in getattr(issue, "controlling_provisions", []):
                norm_cid = normalize_provision_string_to_canonical_id(prov)
                if norm_cid:
                    admitted_cids.add(norm_cid.upper())
    except Exception as e:
        logger.warning(f"Error extracting controlling provisions for cross-linker gate: {e}")

    if query_plan:
        plan_provisions = (
            (getattr(query_plan, "statutory_provisions", []) or []) +
            (getattr(query_plan, "provisions", []) or [])
        )
        for prov in plan_provisions:
            norm_cid = normalize_provision_string_to_canonical_id(prov)
            if norm_cid:
                admitted_cids.add(norm_cid.upper())

    fused_num_map = {
        "252": "52", "253": "53", "257": "57", "259": "59",
        "261": "61", "263": "63", "264": "64", "266": "66",
        "267": "67", "268": "68", "269": "69", "270": "70",
        "271": "71", "276": "76", "277": "77", "278": "78",
        "279": "79", "280": "80", "228": "28"
    }

    for p in (verified_statutory_provisions or []):
        cid = str(p.get("canonical_id") or "")
        display = str(p.get("display_name") or "")
        act_code = str(p.get("act_code") or "")
        is_art = "_ART_" in cid or p.get("provision_type") == "article" or "article" in display.lower()

        sec_num = str(p.get("section_number") or p.get("section") or p.get("sec") or p.get("primary_num") or "").strip()
        if not sec_num:
            m_cid = re.search(r'_(?:SEC|ART|RULE)_([0-9]+[A-Za-z]?(?:_[0-9]+)?)', cid, re.IGNORECASE)
            if m_cid:
                sec_num = m_cid.group(1).replace("_", "(") + (")" if "_" in m_cid.group(1) else "")
            else:
                m_disp = re.search(r'(?:Section|Article|Order|Rule|Sec\.?|s\.)\s*([0-9IVXLCDM]+[A-Za-z]?(?:\s*\([0-9]+\))?)', display, re.IGNORECASE)
                if m_disp:
                    sec_num = m_disp.group(1).strip()
                else:
                    sec_num = cid or "1"
        if sec_num in fused_num_map:
            sec_num = fused_num_map[sec_num]

        act_name = str(p.get("act_name") or p.get("act") or "").strip()
        if not act_name:
            if "LIMITATION" in (act_code + cid).upper():
                act_name = "Limitation Act, 1908"
            elif "BENAMI" in (act_code + cid).upper():
                act_name = "Benami Transactions (Prohibition) Act, 2017"
            elif "CPC" in (act_code + cid).upper() or "CIVIL_PROCEDURE" in (act_code + cid).upper():
                act_name = "Code of Civil Procedure, 1908"
            elif "CRPC" in (act_code + cid).upper() or "CRIMINAL_PROCEDURE" in (act_code + cid).upper():
                act_name = "Code of Criminal Procedure, 1898"
            elif "PPC" in (act_code + cid).upper() or "PENAL_CODE" in (act_code + cid).upper():
                act_name = "Pakistan Penal Code, 1860"
            elif "SPECIFIC_RELIEF" in (act_code + cid).upper():
                act_name = "Specific Relief Act, 1877"
            elif display and "," in display:
                act_name = display.split(",", 1)[-1].strip()
            else:
                act_name = display or act_code or "Statute"

        txt = p.get("text_cleaned") or p.get("text") or p.get("section_text") or ""
        if isinstance(txt, dict):
            txt = " ".join(str(v) for v in txt.values())
        txt = str(txt).strip()

        key = f"{act_name.upper()}_{sec_num.upper()}"
        if key not in seen_provisions and txt:
            seen_provisions.add(key)
            unit_label = "Article" if is_art else ("Order" if "_ORD_" in cid else "Section")
            statute_records.append({
                "act_name": act_name,
                "section_number": sec_num,
                "provision_type": "article" if is_art else "section",
                "text": txt,
                "title": p.get("title") or p.get("section_title") or f"{unit_label} {sec_num}",
                "year": p.get("year"),
                "jurisdiction": p.get("jurisdiction") or "Federal / Provincial",
                "status": p.get("status") or "in_force",
                "amendment_history": p.get("amendment_history") or ""
            })

    # 2b. Domain Anchor Injections (Limitation Act money suit provisions gated by admitted_cids)
    lower_q = query_text.lower()
    store = get_unified_statute_store()
    if "limitation" in lower_q and any(k in lower_q for k in ["money", "recovery", "debt", "loan", "price of goods"]):
        try:
            for l_cid in [
                "LIMITATION_1908_ART_57",
                "LIMITATION_1908_ART_58",
                "LIMITATION_1908_ART_64A",
                "LIMITATION_1908_ART_115",
                "LIMITATION_1908_ART_62",
                "LIMITATION_1908_ART_120",
                "LIMITATION_1908_SEC_3"
            ]:
                if admitted_cids and l_cid not in admitted_cids:
                    continue
                if l_cid not in seen_provisions:
                    prov = store.get_by_canonical_id(l_cid)
                    if prov and prov.get("text"):
                        seen_provisions.add(l_cid)
                        is_art = "_ART_" in l_cid
                        num = str(prov.get("primary_num") or l_cid.split("_")[-1])
                        statute_records.append({
                            "act_name": "Limitation Act, 1908",
                            "section_number": num,
                            "provision_type": "article" if is_art else "section",
                            "text": prov["text"],
                            "title": prov.get("title") or (f"Article {num}" if is_art else f"Section {num}"),
                            "status": "in_force"
                        })
        except Exception as e:
            logger.warning(f"Limitation injection error: {e}")

    # 2c. Direct injection of admitted controlling statutory provisions for identified issues
    try:
        for cid in admitted_cids:
            if cid not in seen_provisions:
                prov = store.get_by_canonical_id(cid)
                if prov and prov.get("text"):
                    seen_provisions.add(cid)
                    is_art = "_ART_" in cid
                    is_ord = "_ORD_" in cid
                    unit_label = "Article" if is_art else ("Order" if is_ord else "Section")
                    num = str(prov.get("primary_num") or cid.split("_")[-1])
                    statute_records.append({
                        "act_name": prov.get("act_name") or prov.get("act_code") or "Statute",
                        "section_number": num,
                        "provision_type": "article" if is_art else ("order" if is_ord else "section"),
                        "text": prov["text"],
                        "title": prov.get("title") or f"{unit_label} {num}",
                        "year": prov.get("year"),
                        "jurisdiction": prov.get("jurisdiction") or "Federal / Provincial",
                        "status": "in_force"
                    })
    except Exception as e:
        logger.warning(f"Error populating admitted controlling provisions: {e}")

    # 3. Two-way cross linking: Cases pull statutes invoked (GATED BY ADMITTED_CIDS)
    for c in clean_cases:
        invoked_list = c.get("statutes_invoked") or []
        for inv in invoked_list:
            inv_str = inv.get("name") if isinstance(inv, dict) else str(inv)
            # Try to resolve statute provision from unified store
            m_sec = re.search(r'(?:section|sec\.?|article|art\.?|order|ord\.?|s\.)\s*([0-9IVXLCDM]+[A-Za-z]?(?:\(\d+\))?)', inv_str, re.IGNORECASE)
            if m_sec:
                sec_found = m_sec.group(1)
                for act_kw in [
                    "BENAMI", "SPECIFIC RELIEF", "CIVIL PROCEDURE", "CPC", "CONTRACT",
                    "LIMITATION", "TRANSFER OF PROPERTY", "CRIMINAL PROCEDURE", "CRPC", "PPC"
                ]:
                    if act_kw in inv_str.upper():
                        key = f"{act_kw}_{sec_found.upper()}"
                        if key not in seen_provisions:
                            try:
                                prov = store.get_provision(act_kw, sec_found)
                                if prov and prov.get("text"):
                                    res_cid = prov.get("canonical_id")
                                    # ISSUE-MEMBERSHIP GATE: Discard if not relevant to any identified issue
                                    if admitted_cids:
                                        if not res_cid or res_cid.upper() not in admitted_cids:
                                            continue
                                    seen_provisions.add(key)
                                    if res_cid:
                                        seen_provisions.add(res_cid.upper())
                                    statute_records.append({
                                        "act_name": prov.get("act_name") or act_kw,
                                        "section_number": sec_found,
                                        "text": prov["text"],
                                        "title": prov.get("title") or f"Section {sec_found}",
                                        "status": "in_force"
                                    })
                            except Exception:
                                pass

    # Assemble EvidencePack
    pack = assemble_evidence_pack(statute_records=statute_records, case_records=clean_cases)
    return pack, clean_cases


def build_stage5_prompts(
    evidence_pack: EvidencePack,
    user_query: str,
    query_plan: Any = None
) -> Tuple[str, str]:
    """
    Builds Stage 5 system and user prompts enforcing strict grounding and JSON schema output.
    """
    system_prompt = (
        "You are Section AI, Pakistan's verified judicial intelligence and legal research system.\n"
        "Your task is to draft a rigorous, verified Research Memorandum answering the user's legal query.\n\n"
        "HARD NON-NEGOTIABLE GROUNDING RULES:\n"
        "1. EXCLUSIVE ADMISSIBLE SOURCES: You may rely ONLY on the verified statutory sections and judicial precedents "
        "provided in the VERIFIED EVIDENCE PACK below. Do NOT use outside knowledge, memory, or external citations.\n"
        "2. MANDATORY SOURCE CITATION TAGS: Every factual assertion, legal finding, and option MUST be immediately followed "
        "by its source ID tag: [S1], [S2], [C1], [C2], etc.\n"
        "3. VERBATIM STATUTE QUOTES: Every statute section discussed must be quoted verbatim in quotation marks directly from the pack, "
        "followed by a plain English explanation of its operational effect.\n"
        "4. CASE RATIOS STRICTLY AS RECORDED: For judicial precedents, state ONLY the ratio decidendi as recorded in the pack. "
        "Do NOT extrapolate, infer unstated holdings, or synthesize fictional propositions.\n"
        "5. GAPS & MISSING POINTS: If the evidence pack does not resolve a specific issue or legal sub-question, you MUST state "
        "'Not found in the available sources' and list the unaddressed issue under the 'gaps' array. NEVER guess or fabricate law.\n"
        "6. NO ABSOLUTE OR PERSUASIVE LANGUAGE: Never use absolute terms ('must', 'exclusively', 'cannot') in unquoted text unless "
        "the retrieved provision explicitly commands it. Use objective judicial phrasing: 'the retrieved provision states...', "
        "'under the recorded precedent...'.\n"
        "7. STRICT JSON SCHEMA: You must format your ENTIRE output as a single valid JSON object matching the schema below. "
        "Do NOT wrap the JSON in Markdown code fences if possible, or wrap cleanly in ```json ... ```.\n\n"
        "REQUIRED OUTPUT JSON SCHEMA:\n"
        "{\n"
        "  \"question\": \"The legal question analyzed\",\n"
        "  \"short_answer\": [\n"
        "    {\"text\": \"Direct judicial finding answering the query\", \"sources\": [\"S1\", \"C1\"]}\n"
        "  ],\n"
        "  \"statutes\": [\n"
        "    {\"id\": \"S1\", \"quote\": \"Verbatim quote from section text in pack\", \"plain_explanation\": \"Plain words explanation\"}\n"
        "  ],\n"
        "  \"cases\": [\n"
        "    {\"id\": \"C1\", \"ratio_as_recorded\": \"The exact ratio decidendi from the pack\", \"relevance\": \"Operational application to query\"}\n"
        "  ],\n"
        "  \"options_described_by_sources\": [\n"
        "    {\"text\": \"Procedural or pleading step authorized by the retrieved sources\", \"sources\": [\"S1\", \"C1\"]}\n"
        "  ],\n"
        "  \"gaps\": [\n"
        "    \"Points or issues not found in the available sources\"\n"
        "  ],\n"
        "  \"needs_lawyer_review\": true\n"
        "}\n"
    )

    pack_content = evidence_pack.format_pack_for_llm()

    user_prompt = (
        f"USER LEGAL QUERY:\n{user_query}\n\n"
        f"{pack_content}\n\n"
        "INSTRUCTIONS:\n"
        "Synthesize the research memorandum strictly grounded in the evidence pack above.\n"
        "Output ONLY the valid JSON object conforming to the required schema."
    )

    return system_prompt, user_prompt


def execute_stage6_verification_and_rendering(
    raw_llm_response: str,
    evidence_pack: EvidencePack,
    fallback_query: str = ""
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Executes Stage 6 of the pipeline:
    1. Extracts and validates the JSON output from the drafting model.
    2. Runs all 8 deterministic verification checks in code.
    3. Renders the honest research memorandum in Markdown format for the client.
    """
    memo_json = {}
    clean_text = raw_llm_response.strip()

    # Try JSON extraction
    try:
        # Check if wrapped in ```json
        m_fence = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', clean_text)
        if m_fence:
            memo_json = json.loads(m_fence.group(1))
        else:
            m_brace = re.search(r'\{[\s\S]*\}', clean_text)
            if m_brace:
                memo_json = json.loads(m_brace.group(0))
            else:
                memo_json = json.loads(clean_text)
    except Exception as parse_err:
        logger.warning(f"JSON parsing fallback in Stage 6: {parse_err}")
        # Build schema from raw markdown/text without truncating mid-sentence
        paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
        short_ans = []
        for p in paragraphs[:6]:
            if not p.startswith("#") and len(p) > 20:
                short_ans.append({"text": p, "sources": list(evidence_pack.statutes.keys())[:1] + list(evidence_pack.cases.keys())[:1]})
        if not short_ans and paragraphs:
            short_ans.append({"text": paragraphs[0], "sources": []})

        memo_json = {
            "question": fallback_query or "Legal Inquiry",
            "short_answer": short_ans,
            "statutes": [
                {"id": sid, "quote": s.get("text", "")[:300], "plain_explanation": f"Operational provision of {s.get('act_name')}."}
                for sid, s in list(evidence_pack.statutes.items())[:3]
            ],
            "cases": [
                {"id": cid, "ratio_as_recorded": c.get("ratio", ""), "relevance": "Retrieved superior court precedent."}
                for cid, c in list(evidence_pack.cases.items())[:3]
            ],
            "options_described_by_sources": [
                {"text": "Counsel must review certified copies of trial court records.", "sources": list(evidence_pack.cases.keys())[:1]}
            ],
            "gaps": ["Detailed evidentiary evaluation subject to primary record inspection."],
            "needs_lawyer_review": True
        }

    # Run deterministic verification checks
    verifier = EvidenceVerifier(evidence_pack)
    verification_report = verifier.verify(memo_json)

    # Render verified Markdown memorandum
    rendered_markdown = format_verified_memo_to_markdown(
        memo_json=memo_json,
        pack=evidence_pack,
        report=verification_report
    )

    return rendered_markdown, verification_report, memo_json
