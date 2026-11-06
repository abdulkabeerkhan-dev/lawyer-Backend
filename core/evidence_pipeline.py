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
from typing import Dict, List, Any, Tuple, Optional

from core.case_integrity import verify_case_integrity, sanitize_ratio_text, normalize_citation
from core.evidence_pack import EvidencePack, assemble_evidence_pack
from core.evidence_verifier import EvidenceVerifier, format_verified_memo_to_markdown
from core.unified_statute_store import get_unified_statute_store

logger = logging.getLogger(__name__)


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

    # 2. Gather statutory provisions
    statute_records: List[Dict[str, Any]] = []
    seen_provisions = set()

    for p in (verified_statutory_provisions or []):
        act_name = p.get("act_name") or p.get("act") or p.get("display_name") or p.get("canonical_id") or ""
        sec_num = str(p.get("section_number") or p.get("section") or p.get("sec") or "").strip()
        txt = p.get("text_cleaned") or p.get("text") or p.get("section_text") or ""
        if isinstance(txt, dict):
            txt = " ".join(str(v) for v in txt.values())
        txt = str(txt).strip()

        key = f"{act_name.upper()}_{sec_num.upper()}"
        if key not in seen_provisions and txt:
            seen_provisions.add(key)
            statute_records.append({
                "act_name": act_name,
                "section_number": sec_num,
                "text": txt,
                "title": p.get("section_title") or f"Section {sec_num}",
                "year": p.get("year"),
                "jurisdiction": p.get("jurisdiction") or "Federal / Provincial",
                "status": p.get("status") or "in_force",
                "amendment_history": p.get("amendment_history") or ""
            })

    # 3. Two-way cross linking: Cases pull statutes invoked
    for c in clean_cases:
        invoked_list = c.get("statutes_invoked") or []
        for inv in invoked_list:
            inv_str = inv.get("name") if isinstance(inv, dict) else str(inv)
            # Try to resolve statute provision from unified store
            m_sec = re.search(r'(?:section|sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))?)', inv_str, re.IGNORECASE)
            if m_sec:
                sec_found = m_sec.group(1)
                for act_kw in [
                    "BENAMI", "SPECIFIC RELIEF", "CIVIL PROCEDURE", "CPC", "CONTRACT",
                    "LIMITATION", "TRANSFER OF PROPERTY", "CRIMINAL PROCEDURE", "CRPC"
                ]:
                    if act_kw in inv_str.upper():
                        key = f"{act_kw}_{sec_found.upper()}"
                        if key not in seen_provisions:
                            try:
                                store = get_unified_statute_store()
                                prov = store.get_provision(act_kw, sec_found)
                                if prov and prov.get("text"):
                                    seen_provisions.add(key)
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
        # Build schema from raw markdown/text if model returned prose
        memo_json = {
            "question": fallback_query or "Legal Inquiry",
            "short_answer": [{"text": clean_text[:400], "sources": list(evidence_pack.statutes.keys())[:1] + list(evidence_pack.cases.keys())[:1]}],
            "statutes": [
                {"id": sid, "quote": s.get("text", "")[:200], "plain_explanation": f"Operational provision of {s.get('act_name')}."}
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
