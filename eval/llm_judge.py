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

Decoupled from main.py writer pipeline:
- Uses dedicated JUDGE_MODEL (defaults to claude-sonnet-4-5-20250929; distinct from writer claude-haiku-4-5-20251001)
- Prompt version: v1.0-pak-legal-eval
- Independent system prompt and calibration runner.
"""

import os
import json
import re
import sys
import asyncio
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-4-5-20250929")
JUDGE_PROMPT_VERSION = "v1.0-pak-legal-eval"

LLM_JUDGE_SYSTEM_PROMPT = """You are an objective legal evaluation judge for Pakistani legal research memoranda.
Prompt Version: v1.0-pak-legal-eval

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
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured in environment or .env")
        
        workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        default_headers = {}
        if workspace_id:
            default_headers["anthropic-workspace-id"] = workspace_id

        client = anthropic.AsyncAnthropic(
            api_key=api_key,
            default_headers=default_headers if default_headers else None
        )
        resp = await client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=LLM_JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        resp_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
        candidate = None
        m_codeblock = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', resp_text, re.DOTALL)
        if m_codeblock:
            candidate = m_codeblock.group(1)
        else:
            m_brace = re.search(r'\{.*\}', resp_text, re.DOTALL)
            if m_brace:
                candidate = m_brace.group(0)
        
        if candidate:
            try:
                return json.loads(candidate)
            except Exception:
                # Remove unescaped internal control characters
                cleaned = re.sub(r'[\x00-\x1f]', ' ', candidate)
                return json.loads(cleaned)
    except Exception as e:
        print(f"[WARN] LLM Judge exception ({JUDGE_MODEL}): {e}", file=sys.stderr)

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
    Returns agreement rate statistics, model used, and prompt version.
    """
    total_checks = 0
    agreements = 0
    details = []

    sem = asyncio.Semaphore(5)
    async def eval_sample(i, sample):
        async with sem:
            res = await judge_memo_against_gold_case(
                memo_text=sample["memo_text"],
                gold_case=sample["gold_case"],
                llm_client_fn=llm_client_fn
            )
            return i, sample, res

    evaluated = await asyncio.gather(*(eval_sample(i, s) for i, s in enumerate(samples)))
    evaluated.sort(key=lambda x: x[0])

    for i, sample, res in evaluated:
        # Check required points agreement
        exp_req = sample.get("expected_required_passed", [])
        actual_req = [r.get("passed", False) for r in res.get("required_points_results", [])]
        sample_req_agreed = 0
        sample_req_total = len(exp_req)
        for exp, act in zip(exp_req, actual_req):
            total_checks += 1
            if exp == act:
                agreements += 1
                sample_req_agreed += 1

        # Check forbidden claims agreement
        exp_forb = sample.get("expected_forbidden_violated", [])
        actual_forb = [f.get("violated", False) for f in res.get("forbidden_claims_results", [])]
        sample_forb_agreed = 0
        sample_forb_total = len(exp_forb)
        for exp, act in zip(exp_forb, actual_forb):
            total_checks += 1
            if exp == act:
                agreements += 1
                sample_forb_agreed += 1

        details.append({
            "sample_index": i,
            "sample_id": sample.get("gold_case", {}).get("id", f"sample_{i}"),
            "req_agreed_ratio": f"{sample_req_agreed}/{sample_req_total}" if sample_req_total else "N/A",
            "forb_agreed_ratio": f"{sample_forb_agreed}/{sample_forb_total}" if sample_forb_total else "N/A",
            "all_agreed": (sample_req_agreed == sample_req_total and sample_forb_agreed == sample_forb_total)
        })

    rate = (agreements / total_checks) if total_checks > 0 else 1.0
    return {
        "judge_model": JUDGE_MODEL,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "total_samples": len(samples),
        "total_checks": total_checks,
        "agreements": agreements,
        "agreement_rate": round(rate, 4),
        "details": details
    }
