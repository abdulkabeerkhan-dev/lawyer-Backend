import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
"""
eval/llm_judge.py

Independent LLM judge that evaluates a legal memorandum against a Gold Set row:
- required_points: evaluates whether each required point is supported in the memo.
- forbidden_claims: evaluates whether any forbidden claim appears in any wording.
- advice_risk: evaluates whether consequence of non-compliance and proper procedural advice appear.
- expected_negative_findings: checks for explicit "not found in retrieved sources" statements.

Also includes calibration harness to measure agreement rate against hand-labeled samples.
"""

import json
import re
import sys
import asyncio
from typing import Dict, Any, List, Optional

LLM_JUDGE_SYSTEM_PROMPT = """You are an objective legal evaluation judge for Pakistani legal research memoranda.
You will be provided:
1. A generated legal research memorandum.
2. A list of required legal points that MUST be supported.
3. A list of forbidden claims that MUST NOT appear in any wording (including synonyms, paraphrases, or implied assertions).
4. Advice-risk requirements and expected negative findings.

You must examine the memorandum carefully and evaluate each item strictly against the actual text.

Evaluate:
1. "required_points": For each point in the list, determine if the proposition is substantively addressed and supported in the memo.
   - "passed": true/false
   - "evidence": quote or concise explanation from the memo
2. "forbidden_claims": For each forbidden claim, determine if the claim appears in ANY wording in the memo.
   - "violated": true/false (true means the forbidden claim WAS made, which is a violation!)
   - "quote": exact quote from memo where the forbidden claim appears, or "" if not found
3. "advice_risk": Did the memo adequately warn of consequences of non-compliance (e.g. dismissal of petition, auction confirmation) and recommend safe legal steps (stay, modification, review)?
   - "passed": true/false
   - "reason": explanation
4. "negative_findings": Did the memo explicitly state that no authority was found for the expected negative findings?
   - "passed": true/false
   - "reason": explanation

You must respond ONLY with a valid JSON object matching this schema:
{
  "required_points_results": [
    {"point": "<text of required point>", "passed": <true|false>, "evidence": "<quote or explanation>"}
  ],
  "forbidden_claims_results": [
    {"forbidden_claim": "<text of forbidden claim>", "violated": <true|false>, "quote": "<quote if violated or empty>"}
  ],
  "advice_risk_result": {
    "passed": <true|false>,
    "reason": "<explanation>"
  },
  "negative_findings_result": {
    "passed": <true|false>,
    "reason": "<explanation>"
  }
}
"""

async def judge_memo_against_gold_case(
    memo_text: str,
    gold_case: Dict[str, Any],
    llm_client_fn: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Evaluates a single memo against a gold set case row.
    """
    req_pts = gold_case.get("required_points", [])
    forb_claims = gold_case.get("forbidden_claims", [])
    adv_risk = gold_case.get("advice_risk", "")
    neg_finds = gold_case.get("expected_negative_findings", [])

    user_prompt = (
        f"=== LEGAL MEMORANDUM TO EVALUATE ===\n{memo_text}\n\n"
        f"=== REQUIRED POINTS ===\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(req_pts)) + "\n\n"
        f"=== FORBIDDEN CLAIMS ===\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(forb_claims)) + "\n\n"
        f"=== ADVICE RISK REQUIREMENT ===\n{adv_risk or 'None'}\n\n"
        f"=== EXPECTED NEGATIVE FINDINGS ===\n" + "\n".join(f"{i+1}. {f}" for i, f in enumerate(neg_finds)) + "\n\n"
        "Evaluate strictly and output ONLY the JSON object."
    )

    if llm_client_fn:
        return await llm_client_fn(user_prompt)

    try:
        from main import safe_create_anthropic_message, CLAUDE_MODEL
        resp = await safe_create_anthropic_message(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=LLM_JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        resp_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
        m_json = re.search(r'\{.*\}', resp_text, re.DOTALL)
        if m_json:
            return json.loads(m_json.group(0))
    except Exception as e:
        print(f"[WARN] LLM Judge exception: {e}", file=sys.stderr)

    # Fallback default empty structure
    return {
        "required_points_results": [{"point": p, "passed": False, "evidence": "Judge error"} for p in req_pts],
        "forbidden_claims_results": [{"forbidden_claim": c, "violated": False, "quote": ""} for c in forb_claims],
        "advice_risk_result": {"passed": False, "reason": "Judge error"},
        "negative_findings_result": {"passed": False, "reason": "Judge error"}
    }

async def calibrate_judge(
    samples: List[Dict[str, Any]],
    llm_client_fn: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Calibrates the LLM judge against hand-labelled memo/row pairs.
    Each sample dict must contain:
    - memo_text: str
    - gold_case: dict
    - expected_required_passed: list of bool
    - expected_forbidden_violated: list of bool
    Returns agreement rate statistics.
    """
    total_checks = 0
    agreements = 0
    details = []

    for i, sample in enumerate(samples):
        res = await judge_memo_against_gold_case(
            memo_text=sample["memo_text"],
            gold_case=sample["gold_case"],
            llm_client_fn=llm_client_fn
        )
        # Check required points agreement
        exp_req = sample.get("expected_required_passed", [])
        actual_req = [r.get("passed", False) for r in res.get("required_points_results", [])]
        for exp, act in zip(exp_req, actual_req):
            total_checks += 1
            if exp == act:
                agreements += 1

        # Check forbidden claims agreement
        exp_forb = sample.get("expected_forbidden_violated", [])
        actual_forb = [f.get("violated", False) for f in res.get("forbidden_claims_results", [])]
        for exp, act in zip(exp_forb, actual_forb):
            total_checks += 1
            if exp == act:
                agreements += 1

        details.append({
            "sample_index": i,
            "sample_id": sample.get("gold_case", {}).get("id", f"sample_{i}"),
            "req_agreed": exp_req == actual_req[:len(exp_req)],
            "forb_agreed": exp_forb == actual_forb[:len(exp_forb)]
        })

    rate = (agreements / total_checks) if total_checks > 0 else 1.0
    return {
        "total_checks": total_checks,
        "agreements": agreements,
        "agreement_rate": round(rate, 4),
        "details": details
    }
