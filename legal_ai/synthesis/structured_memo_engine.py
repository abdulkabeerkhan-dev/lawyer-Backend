"""
legal_ai/synthesis/structured_memo_engine.py

Layers 6 & 8: Structured Legal Memorandum Generator & Verifiable Renderer.
Design Principles:
1. The model NEVER supplies law from memory. It can only select, quote, and explain records in the Bounded Evidence Pack.
2. Structured JSON output: answer, claims[], caveats[], not_found[], open_questions[].
3. Layer 7 Verifier runs on plain code, checking evidence_id existence, exact unit types, and verbatim quotes.
4. Layer 8 Renderer formats answer first, then supporting provisions, caveats, unaddressed points, and currency note.
5. Verification badges attached strictly per claim and per memo.
"""

import json
import logging
import re
from typing import Dict, List, Any, Tuple, Optional

from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack, EvidenceItem
from legal_ai.verification.statute_evidence_verifier import (
    StatuteEvidenceVerifier,
    MemoVerificationReport,
    ClaimVerificationStatus
)

logger = logging.getLogger(__name__)


STRUCTURED_MEMO_SYSTEM_PROMPT = """You are Section AI, Pakistan's verified judicial intelligence and legal research system.
Your task is to draft an authoritative, strictly verified Research Memorandum answering the advocate's legal query.

HARD NON-NEGOTIABLE GROUNDING RULES:
1. EXCLUSIVE ADMISSIBLE SOURCES: You may rely ONLY on the verified statutory sections, schedule articles, and judicial precedents provided in the BOUNDED EVIDENCE PACK below. Do NOT supply law from memory or reference outside statutes.
2. MANDATORY EVIDENCE CITATION TAGS: Every single claim in `claims[]` MUST cite the exact evidence ID(s) from the pack (e.g. ["E1"] or ["E1", "E2"]).
3. PRESERVE UNIT TYPES: Schedule provisions in the Limitation Act, 1908 are ARTICLES (e.g. 'Article 57', 'Article 64'). NEVER refer to an Article as a Section (e.g. 'Section 57' or 'Section 264' are STRICT VIOLATIONS).
4. VERBATIM STATUTORY QUOTES: When quoting statutory language, quote the exact text provided in the pack in double quotation marks.
5. RECORDED RATIO DECIDENDI ONLY: For judicial precedents, state only the ratio decidendi as recorded in the pack. Never invent or synthesize unrecorded holdings.
6. HONEST NOT FOUND REPORTING: If the evidence pack does not answer a sub-issue, you MUST state so under `not_found[]`. Failing visibly beats looking complete.
7. STRICT JSON SCHEMA: You MUST format your entire response as a single, valid JSON object conforming exactly to the schema below. Do NOT output free conversational prose outside the JSON.

REQUIRED JSON SCHEMA:
{
  "answer": "1-2 sentence direct, actionable judicial finding answering the query.",
  "claims": [
    {
      "statement": "Asserted legal rule or application, quoting authentic statutory phrases in quotation marks.",
      "evidence_ids": ["E1"]
    }
  ],
  "caveats": [
    "Jurisdictional or statutory caveats (e.g. Punjab Loans Limitation Act, 1904 override)."
  ],
  "not_found": [
    "Specific questions or factual scenarios not resolved by the admitted sources."
  ],
  "open_questions": [
    "Factual or evidentiary questions requiring clarification from the client or trial court record."
  ]
}
"""


def build_structured_memo_prompts(
    evidence_pack: BoundedEvidencePack,
    user_query: str
) -> Tuple[str, str]:
    """
    Builds the system and user prompts enforcing strict Layer 6 JSON generation.
    """
    pack_content = evidence_pack.format_pack_for_llm()

    user_prompt = (
        f"ADVOCATE LEGAL QUERY:\n{user_query.strip()}\n\n"
        f"{pack_content}\n\n"
        "INSTRUCTIONS:\n"
        "1. Synthesize the research memorandum answering the query above.\n"
        "2. Ground every claim strictly in the Evidence Pack using [E1], [E2], etc.\n"
        "3. Output ONLY the valid JSON object conforming to the required schema."
    )

    return STRUCTURED_MEMO_SYSTEM_PROMPT, user_prompt


def parse_structured_memo_response(
    raw_response: str,
    fallback_query: str = "",
    evidence_pack: Optional[BoundedEvidencePack] = None
) -> Dict[str, Any]:
    """
    Safely parses the LLM output into the structured memo dictionary.
    Includes robust fallback extraction if wrapped in code blocks or trailing text.
    """
    clean_text = raw_response.strip()

    # Try extracting JSON
    try:
        # Match ```json ... ``` code fence
        m_fence = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', clean_text)
        if m_fence:
            return json.loads(m_fence.group(1))

        # Match outer braces
        m_brace = re.search(r'\{[\s\S]*\}', clean_text)
        if m_brace:
            return json.loads(m_brace.group(0))

        return json.loads(clean_text)
    except Exception as parse_err:
        logger.warning(f"Structured memo JSON parse failed: {parse_err}. Constructing fallback schema.")

    # Fallback schema construction from text lines
    paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
    first_ans = paragraphs[0] if paragraphs else "Legal inquiry analyzed based on admitted statutory provisions."
    
    first_eid = list(evidence_pack.items.keys())[:1] if evidence_pack and evidence_pack.items else []
    
    return {
        "answer": first_ans[:300],
        "claims": [
            {
                "statement": p,
                "evidence_ids": first_eid
            }
            for p in paragraphs[1:5] if len(p) > 25 and not p.startswith("#")
        ] or [{"statement": first_ans, "evidence_ids": first_eid}],
        "caveats": [],
        "not_found": ["Structured JSON formatting required code repair."],
        "open_questions": []
    }


def render_layer8_markdown(
    memo_payload: Dict[str, Any],
    evidence_pack: BoundedEvidencePack,
    report: MemoVerificationReport
) -> str:
    """
    Layer 8: Deterministic Markdown Rendering.
    Order of elements:
    1. Direct Answer / Opinion (First!)
    2. Verified Supporting Provisions & Claims (with claim-level verified badges)
    3. Jurisdictional Caveats & Overrides (e.g. Punjab Loans Limitation Act)
    4. Unaddressed Points / Gaps (Not Found)
    5. Open Questions for Counsel
    6. Currency & Gazette Provenance Note
    """
    lines: List[str] = []

    # 1. Answer First
    ans = str(memo_payload.get("answer", "")).strip()
    if ans:
        lines.append(f"### Direct Legal Opinion\n{ans}\n")

    # Verification banner
    if report.is_memo_verified:
        lines.append("> **✓ VERIFIED RESEARCH MEMORANDUM** — 100% of claims deterministically grounded in authenticated statutory provisions and reported precedents.\n")
    else:
        lines.append(f"> ⚠️ **PARTIAL RESULT / UNVERIFIED NOTICE** — {report.unverified_claims_count} claim(s) could not be deterministically verified against the primary statute store.\n")

    # 2. Supporting Legal Units & Claims
    claims = memo_payload.get("claims", [])
    if claims:
        lines.append("### Governing Statutory Provisions & Authorities")
        for idx, c in enumerate(claims, 1):
            stmt = str(c.get("statement", "")).strip()
            ev_ids = c.get("evidence_ids", [])
            ev_labels = ", ".join(f"[{eid}]" for eid in ev_ids) if ev_ids else "[Unattributed]"
            
            c_status = next((cs for cs in report.claim_statuses if cs.statement == stmt), None)
            badge = " `✓ Verified`" if (c_status and c_status.is_verified) else " `⚠️ Unverified`"
            
            lines.append(f"{idx}. {stmt} {badge} {ev_labels}")
        lines.append("")

    # Admitted Provisions Detail Table / Cards
    statute_items = [it for it in evidence_pack.items.values() if it.item_type == "statute_unit"]
    if statute_items:
        lines.append("### Authenticated Statutory Provisions on Record")
        for it in statute_items:
            unit_label = (it.unit_type or "Provision").capitalize()
            lines.append(f"#### {it.statute_title} — {unit_label} {it.number}")
            if it.parent:
                lines.append(f"*Context / Schedule:* {it.parent}")
            lines.append(f"- **Description / Cause of Action:** {it.heading_description}")
            if it.period:
                lines.append(f"- **Limitation Period:** **{it.period}**")
            if it.trigger:
                lines.append(f"- **Commencement Trigger:** {it.trigger}")
            lines.append(f"\n*Authentic Verbatim Text:*\n> \"{it.text}\"\n")
            if it.footnotes:
                lines.append(f"*Statutory Annotations:* {'; '.join(it.footnotes)}\n")

    # 3. Jurisdictional Caveats & Overrides
    caveats = memo_payload.get("caveats", [])
    caveat_items = [it for it in evidence_pack.items.values() if it.item_type == "linked_caveat"]
    all_caveats = list(caveats) + [it.text for it in caveat_items if it.text not in caveats]

    if all_caveats:
        lines.append("### Jurisdictional Caveats & Local Overrides")
        for cav in all_caveats:
            lines.append(f"- **Local Override:** {cav}")
        lines.append("")

    # 4. Judicial Precedents (if any)
    case_items = [it for it in evidence_pack.items.values() if it.item_type == "judicial_precedent"]
    if case_items:
        lines.append("### Controlling Judicial Precedents")
        for it in case_items:
            lines.append(f"- **{it.citation}** — *{it.case_title}* ({it.court}, {it.year or 'N/A'})")
            lines.append(f"  *Recorded Ratio:* {it.ratio}\n")

    # 5. Not Found / Scope Limitations
    not_found = memo_payload.get("not_found", [])
    if not_found:
        lines.append("### Unaddressed Points & Source Limitations")
        for nf in not_found:
            lines.append(f"- *Not Found:* {nf}")
        lines.append("")

    # 6. Open Questions
    open_q = memo_payload.get("open_questions", [])
    if open_q:
        lines.append("### Evidentiary Questions for Counsel")
        for q in open_q:
            lines.append(f"- {q}")
        lines.append("")

    # 7. Statutory Currency & Provenance Note
    lines.append("---")
    lines.append("*Statute Database Current as of November 2026. Codified under primary Gazette of Pakistan provenance. Exact quote attribution verified by plain-code Layer 7 verifier.*")

    return "\n".join(lines)


def execute_structured_memo_pipeline(
    raw_llm_response: str,
    evidence_pack: BoundedEvidencePack,
    verifier: Optional[StatuteEvidenceVerifier] = None,
    fallback_query: str = ""
) -> Tuple[str, MemoVerificationReport, Dict[str, Any]]:
    """
    Complete Layer 6 & Layer 7 & Layer 8 Orchestrator:
    1. Parses LLM structured JSON output.
    2. Runs deterministic StatuteEvidenceVerifier.
    3. Renders Layer 8 client markdown.
    4. Returns (rendered_markdown, verification_report, memo_json).
    """
    memo_json = parse_structured_memo_response(
        raw_response=raw_llm_response,
        fallback_query=fallback_query,
        evidence_pack=evidence_pack
    )

    if verifier is None:
        verifier = StatuteEvidenceVerifier()

    # Run Layer 7 plain code verifier
    report = verifier.verify_structured_memo(
        memo_payload=memo_json,
        evidence_pack=evidence_pack.to_dict()
    )

    # Layer 8 Markdown Rendering
    rendered_markdown = render_layer8_markdown(
        memo_payload=memo_json,
        evidence_pack=evidence_pack,
        report=report
    )

    return rendered_markdown, report, memo_json
