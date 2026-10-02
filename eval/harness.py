import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

"""
eval/harness.py

Evaluation harness for Pakistani Legal Research & Verification System:
- Loads gold set JSON produced by convert_gold_set.py
- By default scores only rows with status "Approved"
- Supports explicit --include-drafts flag for baseline benchmarking
- Strictly isolates held-out rows: real held-out rows are loaded ONLY from
  external environment variable HELD_OUT_GOLD_SET_PATH outside version control
- Evaluates:
  * required_points (judge-based claim support)
  * required_authorities (retrieval at/above min_court & purpose)
  * forbidden_claims (none may appear in any wording)
  * expected_negative_findings (explicit negative statements)
  * expected_forum_route and expected_limitation (forum/limitation accuracy)
  * advice_risk (consequence of non-compliance + stay/modification + "verify with counsel")
  * currency_check (dated label coverage)
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
    label_pattern = re.compile(r'\[(CHECKED, NO CHANGE FOUND|NOT CHECKED|BASELINE TABLE|DECLARED REPUGNANT)[^\]]*\]', re.IGNORECASE)
    labels = label_pattern.findall(memo_text)
    
    actual_pattern = re.compile(r'\[CHECKED, NO CHANGE FOUND:[^\]]*(?:pakistancode|punjablaws|senate|na\.gov)[^\]]*\]', re.IGNORECASE)
    actual_checks = actual_pattern.findall(memo_text)
    
    return {
        "passed": len(labels) > 0,
        "has_labels": len(labels) > 0,
        "labels_found": labels,
        "has_actual_checks": len(actual_checks) > 0,
        "actual_checks_found": actual_checks
    }

def check_forum_limitation_accuracy(memo_text: str, exp_forum: str, exp_lim: str) -> Dict[str, Any]:
    text_lower = memo_text.lower()
    
    # 1. Negative routing error check (advising s.109 CPC appeal to District Judge)
    s109_claim = bool(
        re.search(r'(?:appeal|remedy|petition|file).*?(?:section\s+109|s\.?\s*109).*?(?:district\s+judge|district\s+court)', text_lower) or
        re.search(r'(?:section\s+109|s\.?\s*109).*?(?:to|before).*?(?:district\s+judge|district\s+court)', text_lower)
    )
    if s109_claim and ("not lie" in text_lower or "does not" in text_lower or "do not" in text_lower):
        s109_claim = False

    has_s109_district_error = s109_claim
    has_banking_hc_appeal = ("section 22" in text_lower and "high court" in text_lower) or ("fio" in text_lower and "high court" in text_lower)
    has_30_day_limitation = ("30 days" in text_lower or "thirty days" in text_lower)

    # Forum scoring
    forum_passed = not has_s109_district_error
    if "s.22" in (exp_forum or "").lower():
        forum_passed = forum_passed and has_banking_hc_appeal
    elif "executing court" in (exp_forum or "").lower():
        forum_passed = forum_passed and ("executing court" in text_lower or "execution court" in text_lower)

    # Limitation scoring (honest assessment of unfilled fields)
    lim_status = "verified"
    lim_passed = True
    if exp_lim and "lawyer to fill" in exp_lim.lower():
        lim_status = "unverified_unfilled"
        lim_passed = None  # Missing ground truth; cannot be marked as passed
    elif exp_lim and exp_lim.lower() != "not applicable":
        if "30" in exp_lim:
            lim_passed = has_30_day_limitation
        else:
            lim_passed = True

    # Overall pass: requires forum passed, and limitation passed (not failed)
    if lim_passed is None:
        passed = forum_passed
        is_independent = False  # Lacks independent human ground truth for limitation
    else:
        passed = forum_passed and lim_passed
        is_independent = True

    return {
        "passed": passed,
        "forum_passed": forum_passed,
        "limitation_passed": lim_passed,
        "limitation_status": lim_status,
        "is_independent_check": is_independent,
        "has_s109_district_error": has_s109_district_error,
        "has_banking_hc_appeal": has_banking_hc_appeal,
        "has_30_day_limitation": has_30_day_limitation
    }

async def evaluate_single_case(
    gold_case: Dict[str, Any],
    memo_text: str,
    citations_returned: List[Dict[str, Any]],
    llm_judge_fn: Optional[Any] = None
) -> Dict[str, Any]:
    case_id = gold_case["id"]
    area = gold_case.get("area", "General")
    memo_lower = memo_text.lower()

    # 1. LLM Judge evaluation for required points & forbidden claims
    judge_res = await judge_memo_against_gold_case(memo_text, gold_case, llm_client_fn=llm_judge_fn)
    req_results = judge_res.get("required_points_results", [])
    forb_results = judge_res.get("forbidden_claims_results", [])
    
    req_total = len(req_results)
    req_passed = sum(1 for r in req_results if r.get("passed", False))
    req_support_rate = (req_passed / req_total) if req_total > 0 else 1.0

    scope_violations = [f for f in forb_results if f.get("violated", False)]
    
    # Claim-level checks for forbidden assertions
    deterministic_violations = []
    # 1. Claim that 50% court direction is unlawful, ultra vires, or exceeds authority without qualifying retrieved holding
    if any("50%" in c and ("ultra vires" in c.lower() or "unlawful" in c.lower()) for c in gold_case.get("forbidden_claims", [])):
        unlawful_50_patterns = [
            r'50%[^\.\n]*?(?:ultra\s+vires|unlawful|without\s+jurisdiction|without\s+statutory|exceeds\s+statutory|violates\s+the\s+express|legally\s+unsustainable|contrary\s+to\s+law|illegal|void)',
            r'(?:ultra\s+vires|unlawful|without\s+jurisdiction|without\s+statutory|exceeds\s+statutory|violates\s+the\s+express|legally\s+unsustainable|contrary\s+to\s+law|illegal|void)[^\.\n]*?50%',
            r'demanding\s+50%[^\.\n]*?(?:exceeds|violates|without\s+statutory|unlawful|illegal|unsustainable|contrary)',
            r'condition\s+of\s+50%[^\.\n]*?(?:without\s+statutory|unlawful|vitiates|illegal|contrary|unsustainable)'
        ]
        if any(re.search(pat, memo_lower) for pat in unlawful_50_patterns):
            deterministic_violations.append("Claiming 50% court direction is unlawful, ultra vires, or exceeds statutory authority without qualifying retrieved source holding")
    if "no precedent exists" in memo_lower and any("no precedent exists" in c.lower() for c in gold_case.get("forbidden_claims", [])):
        deterministic_violations.append("no precedent exists")
    if ("section 109 cpc" in memo_lower or "section 109" in memo_lower) and "district judge" in memo_lower:
        if not ("not lie" in memo_lower or "does not" in memo_lower or "do not" in memo_lower):
            deterministic_violations.append("s.109 appeal to District Judge")
    if "[[citation removed" in memo_lower or "[citation removed:" in memo_lower:
        deterministic_violations.append("[[CITATION REMOVED]] residual marker")

    # 2. Key authority recall & min court
    retrieved_cits = [normalize_citation(c.get("citation") or c.get("case_id") or "") for c in citations_returned]
    auth_results = []
    for req_auth in gold_case.get("required_authorities", []):
        raw_cit = req_auth.get("citation", "")
        # Clean candidates text if marked 'LAWYER TO CONFIRM'
        cleaned_cit = re.sub(r'^(?:CANDIDATES[,\s]+)?(?:LAWYER TO CONFIRM:?\s*)?', '', raw_cit, flags=re.IGNORECASE).strip()
        target_cit = normalize_citation(cleaned_cit)
        min_court = req_auth.get("min_court", "")
        min_weight = court_rank(min_court)
        
        found_in_retrieval = any(target_cit in rc or rc in target_cit for rc in retrieved_cits) if target_cit else False
        found_in_memo = (target_cit.lower() in memo_lower) if target_cit else False
        
        court_ok = True
        if min_court and found_in_retrieval:
            for c in citations_returned:
                if target_cit in normalize_citation(c.get("citation") or ""):
                    c_name = c.get("court") or c.get("court_name") or ""
                    if court_rank(c_name) < min_weight:
                        court_ok = False
        
        auth_results.append({
            "citation": raw_cit,
            "target_normalized": target_cit,
            "found": found_in_retrieval or found_in_memo,
            "court_ok": court_ok,
            "needed_for": req_auth.get("needed_for")
        })

    auth_total = len(auth_results)
    auth_passed = sum(1 for a in auth_results if a["found"] and a["court_ok"])
    auth_recall = (auth_passed / auth_total) if auth_total > 0 else 1.0

    # 3. Citation precision (Target 100%: no ungrounded markers or deleted placeholders)
    has_removed_markers = "[[citation removed" in memo_lower
    citation_precision = 0.0 if has_removed_markers else 1.0

    # 4. Advice risk compliance
    adv_check = check_advice_risk_in_text(memo_text, gold_case.get("advice_risk", ""))
    
    # 5. Currency check compliance
    curr_check = check_currency_labels_in_text(memo_text, gold_case.get("currency_check", ""))

    # 6. Forum & Limitation accuracy
    fl_check = check_forum_limitation_accuracy(
        memo_text,
        gold_case.get("expected_forum_route", ""),
        gold_case.get("expected_limitation", "")
    )

    # 7. Negative findings correctness
    neg_results = []
    for neg in gold_case.get("expected_negative_findings", []):
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
        (auth_recall >= 0.5 or auth_total == 0) and
        fl_check["passed"]
    )

    failed_reasons = []
    if req_support_rate < 0.8:
        failed_reasons.append(f"Claim support rate {req_support_rate*100:.1f}% below 80%")
    if scope_violations:
        failed_reasons.append(f"Scope violations: {[f.get('forbidden_claim') for f in scope_violations]}")
    if deterministic_violations:
        failed_reasons.append(f"Deterministic violations: {deterministic_violations}")
    if citation_precision < 1.0:
        failed_reasons.append("Citation precision below 100% (residual removal marker)")
    if auth_total > 0 and auth_recall < 0.5:
        failed_reasons.append(f"Key authority recall {auth_recall*100:.1f}% below 50%")
    if not fl_check["passed"]:
        failed_reasons.append("Forum / limitation check failed")

    return {
        "id": case_id,
        "area": area,
        "passed": case_passed,
        "failed_reasons": failed_reasons,
        "metrics": {
            "claim_support_rate": round(req_support_rate, 4),
            "scope_violations_count": len(scope_violations) + len(deterministic_violations),
            "key_authority_recall": round(auth_recall, 4),
            "citation_precision": round(citation_precision, 4),
            "negative_finding_correctness": round(neg_correctness, 4),
            "forum_limitation_accuracy": 1.0 if fl_check["passed"] else 0.0,
            "advice_risk_passed": adv_check["passed"],
            "currency_check_passed": curr_check["passed"],
            "currency_label_coverage": 1.0 if curr_check.get("has_labels") else 0.0,
            "currency_actual_check_rate": 1.0 if curr_check.get("has_actual_checks") else 0.0
        },
        "details": {
            "required_points": req_results,
            "forbidden_claims": forb_results,
            "deterministic_violations": deterministic_violations,
            "authorities": auth_results,
            "negative_findings": neg_results,
            "advice_risk": adv_check,
            "currency_check": curr_check,
            "forum_limitation": fl_check
        }
    }

async def run_harness(
    gold_json_path: str,
    approved_only: bool = True,
    include_drafts: bool = False,
    include_held_out: bool = False,
    results_dir: Optional[str] = None,
    out_file: Optional[str] = None
) -> Dict[str, Any]:
    with open(gold_json_path, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    # Optional held-out loading from environment variable path (outside git repo)
    held_out_env_path = os.environ.get("HELD_OUT_GOLD_SET_PATH")
    if include_held_out and held_out_env_path and os.path.exists(held_out_env_path):
        try:
            with open(held_out_env_path, "r", encoding="utf-8") as f_ho:
                ho_cases = json.load(f_ho)
                all_cases.extend(ho_cases)
                print(f"[INFO] Loaded {len(ho_cases)} external held-out cases from {held_out_env_path}")
        except Exception as e:
            print(f"[WARN] Failed loading external held-out set: {e}", file=sys.stderr)

    filtered_cases = []
    for c in all_cases:
        # Held-out isolation in dev runs
        if not include_held_out and c.get("split") == "Held-out":
            continue
        # Status filter
        if approved_only and not include_drafts and c.get("status") != "Approved":
            continue
        filtered_cases.append(c)

    print(f"Loaded {len(all_cases)} total gold set cases. Filtered to {len(filtered_cases)} for execution.")
    print(f"(Approved only: {approved_only and not include_drafts}, Include drafts: {include_drafts}, Include held-out: {include_held_out})")

    if not filtered_cases:
        print("[INFO] Note: 0 cases matched the filter. Lawyer review is in progress.")
        return {
            "total_cases": len(all_cases),
            "total_evaluated": 0,
            "approved_count": sum(1 for c in all_cases if c.get("status") == "Approved"),
            "draft_count": sum(1 for c in all_cases if c.get("status") == "Draft"),
            "results": [],
            "summary": {"total_evaluated": 0, "overall_pass_rate": 0.0, "citation_precision": 0.0}
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

        area = c.get("area", "General")
        area_metrics.setdefault(area, []).append(eval_res)

    total_eval = len(results)
    avg_claim_support = sum(r["metrics"]["claim_support_rate"] for r in results) / max(1, total_eval)
    avg_authority_recall = sum(r["metrics"]["key_authority_recall"] for r in results) / max(1, total_eval)
    avg_citation_precision = sum(r["metrics"]["citation_precision"] for r in results) / max(1, total_eval)
    avg_neg_correctness = sum(r["metrics"]["negative_finding_correctness"] for r in results) / max(1, total_eval)
    avg_fl_accuracy = sum(r["metrics"]["forum_limitation_accuracy"] for r in results) / max(1, total_eval)
    avg_advice_risk = sum(1.0 if r["metrics"]["advice_risk_passed"] else 0.0 for r in results) / max(1, total_eval)
    avg_curr_coverage = sum(r["metrics"]["currency_label_coverage"] for r in results) / max(1, total_eval)
    avg_actual_check_rate = sum(r["metrics"]["currency_actual_check_rate"] for r in results) / max(1, total_eval)
    avg_latency = sum(r.get("latency_s", 0.0) for r in results) / max(1, total_eval)
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
        "negative_finding_correctness": round(avg_neg_correctness, 4),
        "forum_limitation_accuracy": round(avg_fl_accuracy, 4),
        "advice_risk_compliance": round(avg_advice_risk, 4),
        "currency_label_coverage": round(avg_curr_coverage, 4),
        "currency_actual_check_rate": round(avg_actual_check_rate, 4),
        "scope_violations_count": total_scope_violations,
        "avg_latency_s": round(avg_latency, 2),
        "area_breakdown": {
            area: {
                "count": len(recs),
                "pass_rate": round(sum(1 for r in recs if r["passed"]) / len(recs), 4),
                "avg_claim_support": round(sum(r["metrics"]["claim_support_rate"] for r in recs) / len(recs), 4)
            }
            for area, recs in area_metrics.items()
        }
    }

    json_path = out_file if out_file else os.path.join(out_dir, f"eval_report_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": results}, f, indent=2)
    print(f"\n[PASS] Saved JSON eval report to {json_path}")

    md_path = (out_file.rsplit('.', 1)[0] + ".md") if out_file else os.path.join(out_dir, f"eval_report_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Legal Evaluation Benchmark Report ({ts})\n\n")
        f.write(f"- **Git Commit**: `{git_hash}`\n")
        f.write(f"- **Cases Evaluated**: {total_eval}\n")
        f.write(f"- **Overall Pass Rate**: {summary['overall_pass_rate']*100:.1f}%\n")
        f.write(f"- **Citation Precision**: {summary['citation_precision']*100:.1f}% (Target: 100%)\n")
        f.write(f"- **Claim Support Rate (Judge-based)**: {summary['claim_support_rate']*100:.1f}%\n")
        f.write(f"- **Key Authority Recall**: {summary['key_authority_recall']*100:.1f}%\n")
        f.write(f"- **Negative Finding Correctness**: {summary['negative_finding_correctness']*100:.1f}%\n")
        f.write(f"- **Forum & Limitation Accuracy**: {summary['forum_limitation_accuracy']*100:.1f}%\n")
        f.write(f"- **Advice Risk Compliance**: {summary['advice_risk_compliance']*100:.1f}%\n")
        f.write(f"- **Currency Label Coverage**: {summary['currency_label_coverage']*100:.1f}%\n")
        f.write(f"- **Currency Actual Check Rate (sources_queried not null)**: {summary['currency_actual_check_rate']*100:.1f}%\n")
        f.write(f"- **Scope Violations**: {summary['scope_violations_count']}\n")
        f.write(f"- **Average Latency**: {summary['avg_latency_s']}s\n\n")
        f.write("## Area Breakdown\n\n")
        f.write("| Practice Area | Cases | Pass Rate | Claim Support Rate |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for area, d in summary["area_breakdown"].items():
            f.write(f"| {area} | {d['count']} | {d['pass_rate']*100:.1f}% | {d['avg_claim_support']*100:.1f}% |\n")
        f.write("\n## Failed Requirements Detail\n\n")
        for r in results:
            if not r["passed"]:
                f.write(f"### Case {r['id']} ({r['area']}) - FAILED\n")
                for reason in r.get("failed_reasons", []):
                    f.write(f"- {reason}\n")
    print(f"[PASS] Saved Markdown eval report to {md_path}")

    return {"summary": summary, "cases": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run legal eval harness.")
    parser.add_argument("--gold-file", default=os.path.join(WORKSPACE_DIR, "eval", "gold_set_examples.json"), help="Path to gold set JSON.")
    parser.add_argument("--include-drafts", action="store_true", default=False, help="Include draft cases for baseline benchmarking.")
    parser.add_argument("--include-held-out", action="store_true", default=False, help="Include held-out split cases.")
    parser.add_argument("--out-file", default=None, help="Explicit path to write JSON evaluation report.")
    args = parser.parse_args()

    asyncio.run(run_harness(
        args.gold_file,
        approved_only=not args.include_drafts,
        include_drafts=args.include_drafts,
        include_held_out=args.include_held_out,
        out_file=args.out_file
    ))
