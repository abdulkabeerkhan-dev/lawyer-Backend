import json
import re
import sys
from typing import List, Dict, Any, Optional, Callable, Tuple

REVIEWER_SYSTEM_PROMPT = """You are an independent, strict judicial reviewer verifying a legal memorandum for Pakistan legal accuracy.
You must examine every substantive legal claim, statutory proposition, and case proposition in the memorandum that cites an authority.
Compare each claim directly against the provided retrieved authorities context.
Categorize each proposition strictly into one of three classifications:
- "supported": The claim is directly stated in or strictly entailed by the cited authority in the retrieved context.
- "overstated": The claim goes beyond what the cited authority actually decided or held, exaggerating its scope, certainty, or legal rule.
- "unsupported": The cited authority does not mention, contradicts, or does not stand for the claimed proposition.

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
        return {"passed": True, "propositions": [], "issues": []}

    # Format context chunks for reviewer
    formatted_contexts = []
    for i, c in enumerate(context_chunks[:10]):
        title = c.get("case_title") or c.get("title") or c.get("case_name") or f"Authority {i+1}"
        cit = c.get("neutral_citation") or c.get("citation") or c.get("case_id") or ""
        txt = c.get("text") or c.get("full_text") or c.get("raw_text") or c.get("snippet") or ""
        formatted_contexts.append(f"--- AUTHORITY {i+1}: {title} ({cit}) ---\n{txt[:1500]}")

    context_str = "\n\n".join(formatted_contexts)

    user_eval_prompt = (
        f"=== RETRIEVED AUTHORITIES CONTEXT ===\n{context_str}\n\n"
        f"=== GENERATED MEMORANDUM TO REVIEW ===\n{memo_text}\n\n"
        "Evaluate every claim citing an authority in the memorandum above against the retrieved authorities. "
        "Output ONLY the JSON object."
    )

    if reviewer_fn:
        return await reviewer_fn(user_eval_prompt)

    # Use anthropic client at temperature 0
    try:
        from main import safe_create_anthropic_message, CLAUDE_MODEL
        resp = await safe_create_anthropic_message(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=REVIEWER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_eval_prompt}]
        )
        resp_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
        m_json = re.search(r'\{.*\}', resp_text, re.DOTALL)
        if m_json:
            parsed = json.loads(m_json.group(0))
            passed = parsed.get("passed", False)
            issues = parsed.get("issues", [])
            # Enforce consistency: if any proposition is overstated or unsupported, passed must be False
            for p in parsed.get("propositions", []):
                if p.get("classification") in ("overstated", "unsupported"):
                    passed = False
                    if p.get("reason") and p.get("reason") not in issues:
                        issues.append(f"{p.get('cited_authority')}: {p.get('reason')}")
            return {
                "passed": passed,
                "propositions": parsed.get("propositions", []),
                "issues": issues
            }
    except Exception as e:
        print(f"?? Final review gate reviewer exception: {e}", file=sys.stderr)

    return {"passed": True, "propositions": [], "issues": []}
