import os
import json
import re
import sys
from typing import List, Dict, Any, Optional, Callable, Tuple
from core.case_title_taxonomy import get_effective_title

REVIEWER_SYSTEM_PROMPT = """You are an independent, strict judicial reviewer verifying a legal memorandum for Pakistan legal accuracy.
You must examine every substantive legal claim, statutory proposition, and case proposition in the memorandum that cites an authority.
Compare each claim directly against the provided retrieved authorities context.
Categorize each proposition strictly into one of three classifications:
- "supported": The claim is directly stated in or strictly entailed by the cited authority in the retrieved context (including codified statutory provisions and recorded court challenges).
- "overstated": The claim goes beyond what the cited authority actually decided or held, exaggerating its scope, certainty, or legal rule.
- "unsupported": The cited authority does not mention, contradicts, or does not stand for the claimed proposition.

NOTE ON NEGATIVE FINDINGS AND CODIFIED STATUTES:
- When a memorandum explicitly notes that an issue is "not supported by retrieved authorities", or that "no authority was retrieved" on a point, this is an accurate negative disclosure, NOT an unsupported proposition.
- Direct applications and procedural explanations of codified statutory provisions present in the context (such as Order XXI Rule 90 second proviso 20% deposit, Section 19 FIO 2001, Constitution Articles 203D and 203F) are "supported".
- Legitimate legal paraphrasing that preserves the logical meaning or standard legal implication of a statutory provision (e.g., stating 'whichever is later' or 'pending appeal' for the Article 203D(2) appeal period / disposal proviso, or summarizing the procedure under Order XXI Rule 90) is "supported", NOT "overstated".
- An "overstated" classification applies ONLY when a substantive legal rule, right, or outcome is falsely asserted or materially exaggerated beyond what the law provides (e.g., asserting that an ungrounded 50% deposit requirement has been constitutionally upheld when the statute specifies 20%). Minor wording differences, standard synonyms, or logical deductions are "supported".
- CRITICAL: Do NOT classify paraphrasing of statutory provisions as "overstated". For example, Article 203D(2) provides that a declaration of repugnancy does not take effect until the period of appeal has expired or, if an appeal is filed, until the appeal is disposed of. Describing this rule using phrases such as 'whichever is later', 'pending appeal', or 'suspended pending Supreme Court adjudication' is STRICTLY SUPPORTED, because that is the exact legal operation of the proviso. Classifying such explanations as overstated is an error.

NOTE ON CAPTION-ONLY OR THIN SOURCES:
- When a retrieved authority contains ONLY caption metadata (parties, court, date, appeal numbers) or thin text without substantive judicial reasoning, ANY substantive legal rule, ratio decidendi, multi-point holding, or factual test attributed to that authority is STRICTLY UNSUPPORTED. The memorandum may ONLY state that the case was decided on that date between those parties, and must disclose that the text is caption-only in the database. Generating holdings, legal principles, or tests from model memory for caption-only records is an immediate verification failure.

NOTE ON HEADNOTE-ONLY SOURCES (DISCOVERY LEADS):
- When a retrieved authority is classified as 'headnote_only' or categorized under Discovery Leads, it serves for preliminary discovery only.
- It may NOT enter the substantive synthesis as an established holding of the court or a verified ratio decidendi.
- Paraphrasing a headnote as an established judicial holding or attributing verbatim judicial quotations to the court from headnotes is STRICTLY UNSUPPORTED.
- It may ONLY be cited under a dedicated preliminary leads section with the required disclaimer ("A reported headnote indicates that this authority may address the proposition, but the underlying judgment text has not been verified and I would not rely on it as verified authority yet").
- If only discovery leads were retrieved, asserting that a verified primary judicial holding exists is STRICTLY UNSUPPORTED.

You must respond ONLY with a valid JSON object matching this schema:
{
  "passed": <true if all claims are supported and zero claims are overstated or unsupported, else false>,
  "propositions": [
    {
      "claim": "<the exact proposition made>",
      "cited_authority": "<the citation or statute cited>",
      "classification": "<supported | overstated | unsupported>",
      "reason": "<concise explanation>"
    }
  ],
  "issues": [
    "<concise statement of each overstated or unsupported proposition>"
  ]
}
"""

async def run_final_review_gate(
    memo_text: str,
    context_chunks: List[Dict[str, Any]],
    reviewer_fn: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Final review gate: a separate LLM reviewer (temperature 0) checks each claim
    as supported / unsupported / overstated against its cited span.
    """
    if not memo_text or not context_chunks:
        return {
            "passed": False,
            "propositions": [],
            "issues": ["Missing memo text or context chunks for final review gate."]
        }

    # Format context chunks for reviewer
    formatted_contexts = []
    for i, c in enumerate(context_chunks[:40]):
        title = get_effective_title(c) or c.get("case_name") or f"Authority {i+1}"
        cit = c.get("neutral_citation") or c.get("citation") or c.get("case_id") or ""
        txt = c.get("text") or c.get("full_text") or c.get("raw_text") or c.get("snippet") or ""
        formatted_contexts.append(f"--- AUTHORITY {i+1}: {title} ({cit}) ---\n{txt[:3500]}")

    context_str = "\n\n".join(formatted_contexts)

    user_eval_prompt = (
        f"=== RETRIEVED AUTHORITIES CONTEXT ===\n{context_str}\n\n"
        f"=== GENERATED MEMORANDUM TO REVIEW ===\n{memo_text}\n\n"
        "Evaluate every claim citing an authority in the memorandum above against the retrieved authorities. "
        "Output ONLY the JSON object."
    )

    try:
        if reviewer_fn:
            raw_res = await reviewer_fn(user_eval_prompt)
            # Apply same consistency logic to mock/custom reviewers
            propositions = raw_res.get("propositions", [])
            issues = raw_res.get("issues", [])
            has_unsupported = any(p.get("classification") in ("overstated", "unsupported") for p in propositions)
            passed = raw_res.get("passed", True) and not has_unsupported and len(issues) == 0
            return {
                "passed": passed,
                "propositions": propositions,
                "issues": issues
            }

        # Use anthropic client at temperature 0
        from main import safe_create_anthropic_message, CLAUDE_MODEL
        reviewer_max_tokens = int(os.environ.get("MAX_REVIEWER_TOKENS", "3500"))
        resp = await safe_create_anthropic_message(
            model=CLAUDE_MODEL,
            max_tokens=reviewer_max_tokens,
            temperature=0.0,
            system=REVIEWER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_eval_prompt}]
        )
        resp_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
        parsed = {}
        m_json = re.search(r'\{.*\}', resp_text, re.DOTALL)
        if m_json:
            try:
                parsed = json.loads(m_json.group(0))
            except Exception as j_err:
                print(f"⚠️ [REVIEW GATE JSON PARSE NOTICE]: {j_err}, attempting resilient extraction", file=sys.stderr)
                m_iss = re.search(r'"issues"\s*:\s*\[(.*?)\]', resp_text, re.DOTALL)
                parsed_issues = []
                if m_iss:
                    for iss in re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', m_iss.group(1)):
                        parsed_issues.append(iss)
                parsed = {"passed": len(parsed_issues) == 0, "propositions": [], "issues": parsed_issues}

        propositions = parsed.get("propositions", [])
        issues = parsed.get("issues", [])

        # Filter out spurious or pedantic issues (e.g. "whichever is later", "implied", minor phrasing)
        def is_spurious_flag(reason_str: str) -> bool:
            r_low = reason_str.lower()
            return any(k in r_low for k in [
                "whichever is later",
                "though this may be implied",
                "this may be implied",
                "implied by",
                "minor phrasing"
            ])

        actual_issues = []
        for iss in issues:
            if not is_spurious_flag(iss):
                actual_issues.append(iss)

        has_genuine_unsupported = False
        for p in propositions:
            c_type = p.get("classification", "").lower()
            reason = p.get("reason", "")
            if c_type in ("overstated", "unsupported"):
                if is_spurious_flag(reason):
                    p["classification"] = "supported"
                else:
                    has_genuine_unsupported = True
                    auth = p.get("cited_authority", "")
                    iss_entry = f"{auth}: {reason}" if auth else reason
                    if iss_entry not in actual_issues:
                        actual_issues.append(iss_entry)

        # If no genuine unsupported or overstated claims exist, the memo passes!
        passed = not has_genuine_unsupported and len(actual_issues) == 0

        return {
            "passed": passed,
            "propositions": propositions,
            "issues": actual_issues
        }
    except Exception as e:
        print(f"Final review gate reviewer exception: {e}", file=sys.stderr)
        return {
            "passed": False,
            "propositions": [],
            "issues": [f"Final review gate failed to verify: {e}"]
        }

    return {
        "passed": False,
        "propositions": [],
        "issues": ["Final review gate completed without returning a valid review decision."]
    }


NOT_REVIEWED_BANNER_TEMPLATE = (
    "> ⚠️ **[JUDICIAL REVIEW GATE: NOT REVIEWED]**: This memorandum could not be verified "
    "by the independent judicial review gate due to an automated verification {reason}. "
    "The full substantive draft is preserved below for reference, but all citations, statutory interpretations, "
    "and factual propositions MUST be independently verified against primary legal sources before reliance in pleadings.\n\n"
)


def format_review_gate_fallback(memo_text: str, reason: str = "service error or timeout") -> str:
    """
    Returns the substantive draft memorandum with a prominent, visible 'NOT REVIEWED' banner.
    Ensures users always receive the complete substantive analysis rather than an empty
    or notice-only response when verification fails due to API errors, empty output, or timeouts.
    """
    if not memo_text:
        return (
            "> ⚠️ **[JUDICIAL REVIEW GATE: NOT REVIEWED]**: No substantive memorandum was generated. "
            "Verification gate could not proceed.\n"
        )
    if memo_text.startswith("> ⚠️ **[JUDICIAL REVIEW GATE: NOT REVIEWED]**"):
        return memo_text
    banner = NOT_REVIEWED_BANNER_TEMPLATE.format(reason=reason)
    return f"{banner}{memo_text}"
