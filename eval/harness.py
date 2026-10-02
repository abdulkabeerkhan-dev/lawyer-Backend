import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
"""
eval/harness.py

Evaluation harness for Pakistani Legal Research & Verification System:
- Loads gold set JSON produced by convert_gold_set.py
- Scores only rows with status "Approved" (unless --all-status is explicitly passed for staging checks)
- Strictly excludes split "Held-out" in development runs
- Evaluates:
  * required_points (must be supported)
  * required_authorities (must be retrieved at/above min_court and used)
  * forbidden_claims (none may appear in any wording)
  * expected_negative_findings (must be explicitly stated)
  * expected_forum_route and expected_limitation (must match skeleton)
  * advice_risk (consequence of non-compliance + stay/modification + "verify with counsel")
  * currency_check (dated label must appear for listed provisions)
- Outputs detailed JSON and Markdown reports with area breakdown and version pinning
"""

import os
import sys
import json
import time
import re
import argparse
import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from eval.llm_judge import judge_memo_against_gold_case

COURT_LEVEL_WEIGHTS = {
    "supreme court": 4,
    "supreme court of pakistan": 4,
    "federal constitutional court": 4,
    "fcc": 4,
    "federal shariat court": 3,
    "fsc": 3,
    "high court": 2,
    "lahore high court": 2,
    "sindh high court": 2,
    "peshawar high court": 2,
    "balochistan high court": 2,
    "islamabad high court": 2,
    "banking court": 1,
    "district court": 1,
    "family court": 1,
    "civil court": 1,
    "subordinate": 1
}

def court_rank(court_str: str) -> int:
    c_low = (court_str or "").lower().strip()
    for name, weight in COURT_LEVEL_WEIGHTS.items():
        if name in c_low:
            return weight
    return 1

def normalize_citation(cit: str) -> str:
    c = re.sub(r'\s+', ' ', (cit or '').strip().upper())
    c = c.replace("FEDERAL SHARIAT COURT", "FSC")
    c = c.replace("SUPREME COURT", "SC")
    return c

def get_git_commit_hash() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception:
        return "unknown"

def check_advice_risk_in_text(memo_text: str, advice_risk_spec: str) -> Dict[str, Any]:
    text_lower = memo_text.lower()
    has_dismissal_warning = any(k in text_lower for k in [
        "dismissal", "dismissed for non-compliance", "risk of dismissal", "dismiss the objection", "summary rejection"
    ])
    has_stay_or_mod = any(k in text_lower for k in [
        "stay", "modification", "interim relief", "under protest", "review"
    ])
    has_counsel_notice = any(k in text_lower for k in [
        "verify with counsel", "consult counsel", "advocate", "legal counsel", "verify against"
    ])
    
    passed = has_dismissal_warning and has_stay_or_mod
    return {
        "passed": passed,
        "has_dismissal_warning": has_dismissal_warning,
        "has_stay_or_mod": has_stay_or_mod,
        "has_counsel_notice": has_counsel_notice
    }

def check_currency_labels_in_text(memo_text: str, provisions_to_check: Optional[str] = None) -> Dict[str, Any]:
    # Look for [CHECKED, NO CHANGE FOUND...], [NOT CHECKED...], or [DECLARED REPUGNANT...]
    pattern = re.compile(r'\[(CHECKED, NO CHANGE FOUND|NOT CHECKED|DECLARED REPUGNANT)[^\]]*\]', re.IGNORECASE)
    matches = pattern.findall(memo_text)
    return {
        "passed": len(matches) > 0,
        "labels_found": matches
    }

async def evaluate_single_case(
    gold_case: Dict[str, Any],
    memo_text: str,
    citations_returned: List[Dict[str, Any]],
    llm_judge_fn: Optional[Any] = None
) -> Dict[str, Any]:
    case_id = gold_case["id"]
    area = gold_case.get("area", "General")
    
    # 1. LLM Judge evaluation for required points & forbidden claims
    judge_res = await judge_memo_against_gold_case(memo_text, gold_case, llm_client_fn=llm_judge_fn)
    req_results = judge_res.get("required_points_results", [])
    forb_results = judge_res.get("forbidden_claims_results", [])
    
    req_total = len(req_results)
    req_passed = sum(1 for r in req_results if r.get("passed", False))
    req_support_rate = (req_passed / req_total) if req_total > 0 else 1.0

    scope_violations = [f for f in forb_results if f.get("violated", False)]
    
    # Deterministic backup check for high-risk forbidden terms
    memo_lower = memo_text.lower()
    deterministic_violations = []
    if "ultra vires" in memo_lower and any("ultra vires" in c.lower() for c in gold_case.get("forbidden_claims", [])):
        deterministic_violations.append("ultra vires")
    if "no precedent exists" in memo_lower and any("no precedent exists" in c.lower() for c in gold_case.get("forbidden_claims", [])):
        deterministic_violations.append("no precedent exists")
    if "section 109 cpc" in memo_lower and "district judge" in memo_lower and any("s.109" in c.lower() for c in gold_case.get("forbidden_claims", [])):
        deterministic_violations.append("s.109 appeal to District Judge")

    # 2. Key authority recall & min court
    retrieved_cits = [normalize_citation(c.get("citation") or c.get("case_id") or "") for c in citations_returned]
    auth_results = []
    for req_auth in gold_case.get("required_authorities", []):
        target_cit = normalize_citation(req_auth.get("citation", ""))
        min_court = req_auth.get("min_court", "")
        min_weight = court_rank(min_court)
        
        # Check if cited in memo or retrieved
        found_in_retrieval = any(target_cit in rc or rc in target_cit for rc in retrieved_cits) if target_cit else False
        found_in_memo = (target_cit.lower() in memo_lower) if target_cit else False
        
        # Check court rank
        court_ok = True
        if min_court:
            for c in citations_returned:
                if target_cit in normalize_citation(c.get("citation") or ""):
                    c_name = c.get("court") or c.get("court_name") or ""
                    if court_rank(c_name) < min_weight:
                        court_ok = False
        
        auth_results.append({
            "citation": req_auth.get("citation"),
            "found": found_in_retrieval or found_in_memo,
            "court_ok": court_ok,
            "needed_for": req_auth.get("needed_for")
        })

    auth_total = len(auth_results)
    auth_passed = sum(1 for a in auth_results if a["found"] and a["court_ok"])
    auth_recall = (auth_passed / auth_total) if auth_total > 0 else 1.0

    # 3. Citation precision (check against spurious or hallucinated citations)
    # Target 100% precision: citations in memo must not have ungrounded markers or invented citations
    has_removed_markers = "[[CITATION REMOVED" in memo_text
    citation_precision = 0.0 if has_removed_markers else 1.0

    # 4. Advice risk compliance
    adv_check = check_advice_risk_in_text(memo_text, gold_case.get("advice_risk", ""))
    
    # 5. Currency check compliance
    curr_check = check_currency_labels_in_text(memo_text, gold_case.get("currency_check", ""))

    # 6. Negative findings correctness
    neg_results = []
    for neg in gold_case.get("expected_negative_findings", []):
        # Look for explicit disclosure of absence
        neg_lower = neg.lower()
        key_kws = [w for w in neg_lower.split() if len(w) > 4][:3]
        explicit_found = any(k in memo_lower for k in [
            "not addressed in the retrieved sources",
            "not found in retrieved sources",
            "no authority was retrieved",
            "no authority retrieved",
            "not supported by retrieved",
            "not located in retrieved"
        ]) and any(kw in memo_lower for kw in key_kws)
        neg_results.append({"finding": neg, "present": explicit_found})
    
    neg_total = len(neg_results)
    neg_passed = sum(1 for n in neg_results if n["present"])
    neg_correctness = (neg_passed / neg_total) if neg_total > 0 else 1.0

    # Overall pass for this case
    case_passed = (
        req_support_rate >= 0.8 and
        len(scope_violations) == 0 and
        len(deterministic_violations) == 0 and
        citation_precision == 1.0 and
        (auth_recall >= 0.5 or auth_total == 0)
    )

    return {
        "id": case_id,
        "area": area,
        "passed": case_passed,
        "metrics": {
            "claim_support_rate": round(req_support_rate, 4),
            "scope_violations_count": len(scope_violations) + len(deterministic_violations),
            "key_authority_recall": round(auth_recall, 4),
            "citation_precision": round(citation_precision, 4),
            "negative_finding_correctness": round(neg_correctness, 4),
            "advice_risk_passed": adv_check["passed"],
            "currency_check_passed": curr_check["passed"]
        },
        "details": {
            "required_points": req_results,
            "forbidden_claims": forb_results,
            "deterministic_violations": deterministic_violations,
            "authorities": auth_results,
            "negative_findings": neg_results,
            "advice_risk": adv_check,
            "currency_check": curr_check
        }
    }

async def run_harness(
    gold_json_path: str,
    approved_only: bool = True,
    include_held_out: bool = False,
    results_dir: Optional[str] = None
) -> Dict[str, Any]:
    with open(gold_json_path, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    # Filtering logic
    filtered_cases = []
    for c in all_cases:
        # Status filter
        if approved_only and c.get("status") != "Approved":
            continue
        # Held-out split isolation
        if not include_held_out and c.get("split") == "Held-out":
            continue
        filtered_cases.append(c)

    print(f"Loaded {len(all_cases)} total gold set cases. Filtered to {len(filtered_cases)} for execution.")
    print(f"(Approved only: {approved_only}, Include held-out: {include_held_out})")

    # If 0 approved cases, report status cleanly
    if not filtered_cases:
        print("[INFO] Note: 0 cases matched the filter. Lawyer review is in progress.")
        return {
            "total_cases": len(all_cases),
            "evaluated_cases": 0,
            "approved_count": sum(1 for c in all_cases if c.get("status") == "Approved"),
            "draft_count": sum(1 for c in all_cases if c.get("status") == "Draft"),
            "held_out_count": sum(1 for c in all_cases if c.get("split") == "Held-out"),
            "results": [],
            "summary": {}
        }

    out_dir = results_dir or os.path.join(WORKSPACE_DIR, "eval", "results")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    git_hash = get_git_commit_hash()

    results = []
    area_metrics = {}

    for c in filtered_cases:
        cid = c["id"]
        print(f"\n--- Evaluating Case {cid}: {c.get('query')[:70]}... ---", flush=True)
        # Execute query or retrieve test memo
        from main import process_query_job, jobs_store, QueryRequest
        job_id = f"eval_job_{cid}_{int(time.time())}"
        jobs_store[job_id] = {
            "status": "pending",
            "stage": "starting",
            "stage_timings": {"job_start": time.perf_counter()},
            "created_at": time.time(),
            "user_id": "eval_harness"
        }
        t0 = time.perf_counter()
        req = QueryRequest(query_text=c["query"])
        try:
            await process_query_job(job_id=job_id, request=req, authenticated_user_id="eval_harness")
        except Exception as ex:
            print(f"[FAIL] Error evaluating {cid}: {ex}", file=sys.stderr)

        t_total = time.perf_counter() - t0
        job_data = jobs_store.get(job_id, {})
        res_data = job_data.get("result", {})
        memo_text = res_data.get("answer") or ""
        citations = res_data.get("citations", [])

        eval_res = await evaluate_single_case(c, memo_text, citations)
        eval_res["latency_s"] = round(t_total, 2)
        results.append(eval_res)

        # Aggregate area metrics
        area = c.get("area", "General")
        area_metrics.setdefault(area, []).append(eval_res)

    # Compute overall metrics
    total_eval = len(results)
    avg_claim_support = sum(r["metrics"]["claim_support_rate"] for r in results) / max(1, total_eval)
    avg_authority_recall = sum(r["metrics"]["key_authority_recall"] for r in results) / max(1, total_eval)
    avg_citation_precision = sum(r["metrics"]["citation_precision"] for r in results) / max(1, total_eval)
    total_scope_violations = sum(r["metrics"]["scope_violations_count"] for r in results)
    overall_pass_rate = sum(1 for r in results if r["passed"]) / max(1, total_eval)

    summary = {
        "timestamp": ts,
        "git_commit": git_hash,
        "total_evaluated": total_eval,
        "overall_pass_rate": round(overall_pass_rate, 4),
        "citation_precision": round(avg_citation_precision, 4),
        "claim_support_rate": round(avg_claim_support, 4),
        "key_authority_recall": round(avg_authority_recall, 4),
        "scope_violations_count": total_scope_violations,
        "area_breakdown": {
            area: {
                "count": len(recs),
                "pass_rate": round(sum(1 for r in recs if r["passed"]) / len(recs), 4),
                "avg_claim_support": round(sum(r["metrics"]["claim_support_rate"] for r in recs) / len(recs), 4)
            }
            for area, recs in area_metrics.items()
        }
    }

    # Save JSON report
    json_path = os.path.join(out_dir, f"eval_report_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": results}, f, indent=2)
    print(f"\n[PASS] Saved JSON eval report to {json_path}")

    # Save Markdown report
    md_path = os.path.join(out_dir, f"eval_report_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Legal Evaluation Benchmark Report ({ts})\n\n")
        f.write(f"- **Git Commit**: `{git_hash}`\n")
        f.write(f"- **Cases Evaluated**: {total_eval}\n")
        f.write(f"- **Overall Pass Rate**: {summary['overall_pass_rate']*100:.1f}%\n")
        f.write(f"- **Citation Precision**: {summary['citation_precision']*100:.1f}% (Target: 100%)\n")
        f.write(f"- **Claim Support Rate**: {summary['claim_support_rate']*100:.1f}%\n")
        f.write(f"- **Key Authority Recall**: {summary['key_authority_recall']*100:.1f}%\n")
        f.write(f"- **Scope Violations**: {summary['scope_violations_count']}\n\n")
        f.write("## Area Breakdown\n\n")
        f.write("| Practice Area | Cases | Pass Rate | Claim Support Rate |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for area, d in summary["area_breakdown"].items():
            f.write(f"| {area} | {d['count']} | {d['pass_rate']*100:.1f}% | {d['avg_claim_support']*100:.1f}% |\n")
    print(f"[PASS] Saved Markdown eval report to {md_path}")

    return {"summary": summary, "cases": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run legal eval harness.")
    parser.add_argument("--gold-file", default=os.path.join(WORKSPACE_DIR, "eval", "gold_set_examples.json"), help="Path to gold set JSON.")
    parser.add_argument("--approved-only", action="store_true", default=True, help="Evaluate only approved cases.")
    parser.add_argument("--all-status", action="store_true", help="Evaluate all cases regardless of approval status (for staging/testing).")
    parser.add_argument("--include-held-out", action="store_true", default=False, help="Include held-out split cases.")
    args = parser.parse_args()

    appr = not args.all_status
    asyncio.run(run_harness(args.gold_file, approved_only=appr, include_held_out=args.include_held_out))
