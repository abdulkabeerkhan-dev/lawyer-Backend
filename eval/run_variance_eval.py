import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os
import sys
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from eval.harness import evaluate_single_case, get_git_commit_hash
from main import process_query_job, jobs_store, QueryRequest, CLAUDE_MODEL
from eval.llm_judge import JUDGE_MODEL

MAX_CONCURRENT_JOBS = 2

async def execute_case_run(
    case: Dict[str, Any],
    run_idx: int,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    cid = case["id"]
    async with semaphore:
        print(f"\n[RUN {run_idx+1}/3] Starting {cid}: {case['query'][:65]}...", flush=True)
        job_id = f"eval_var_{cid}_r{run_idx+1}_{int(time.time()*1000)}"
        jobs_store[job_id] = {
            "status": "pending",
            "stage": "starting",
            "stage_timings": {"job_start": time.perf_counter()},
            "created_at": time.time(),
            "user_id": f"variance_eval_r{run_idx+1}"
        }
        
        t0 = time.perf_counter()
        req = QueryRequest(query_text=case["query"])
        err_msg = None
        try:
            await process_query_job(job_id=job_id, request=req, authenticated_user_id=f"variance_eval_r{run_idx+1}")
        except Exception as ex:
            err_msg = str(ex)
            print(f"[FAIL] Run {run_idx+1} {cid} error: {ex}", file=sys.stderr, flush=True)

        t_total = time.perf_counter() - t0
        job_data = jobs_store.get(job_id, {})
        res_data = job_data.get("result", {})
        memo_text = res_data.get("answer") or ""
        citations = res_data.get("citations", [])

        is_notice_only = memo_text.strip().startswith("⚠️ **[FAIL-CLOSED REVIEW GATE NOTICE]**") and len(memo_text.strip().split("\n")) < 15
        is_usable = bool(memo_text.strip() and len(memo_text) > 400 and not is_notice_only and err_msg is None)

        print(f"[RUN {run_idx+1}/3] Finished {cid} in {t_total:.1f}s. Memo len: {len(memo_text)}. Usable: {is_usable}. Evaluating...", flush=True)

        eval_res = await evaluate_single_case(case, memo_text, citations)
        eval_res["run_index"] = run_idx + 1
        eval_res["latency_s"] = round(t_total, 2)
        eval_res["memo_length"] = len(memo_text)
        eval_res["is_usable_memo"] = is_usable
        eval_res["error"] = err_msg

        return eval_res

async def main():
    gold_path = os.path.join(WORKSPACE_DIR, "eval", "gold_set_examples.json")
    with open(gold_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    dev_cases = [c for c in cases if c.get("split") != "Held-out"]
    print("=" * 80)
    print("MULTI-RUN VARIANCE EVALUATION (3 RUNS)")
    print(f"Git Commit: {get_git_commit_hash()}")
    print(f"Generator Model: {CLAUDE_MODEL}")
    print(f"Judge Model: {JUDGE_MODEL}")
    print(f"Dev Cases: {len(dev_cases)} (Runs: 3, Total Executions: {len(dev_cases) * 3})")
    print(f"Max Concurrency: {MAX_CONCURRENT_JOBS}")
    print("=" * 80)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    all_runs_results = [[], [], []]
    
    progress_file = os.path.join(WORKSPACE_DIR, "eval", "results", "variance_eval_progress.json")
    os.makedirs(os.path.dirname(progress_file), exist_ok=True)

    for run_idx in range(3):
        print(f"\n=== BEGINNING RUN {run_idx+1} OF 3 ===", flush=True)
        tasks = [execute_case_run(c, run_idx, semaphore) for c in dev_cases]
        run_results = await asyncio.gather(*tasks)
        all_runs_results[run_idx] = run_results

        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump({
                "completed_runs": run_idx + 1,
                "all_runs": all_runs_results
            }, f, indent=2)

    run_summaries = []
    for r_idx, run_res in enumerate(all_runs_results):
        n = len(run_res)
        pass_rate = sum(1 for r in run_res if r["passed"]) / max(1, n)
        auth_recall = sum(r["metrics"]["key_authority_recall"] for r in run_res) / max(1, n)
        claim_support = sum(r["metrics"]["claim_support_rate"] for r in run_res) / max(1, n)
        cit_prec = sum(r["metrics"]["citation_precision"] for r in run_res) / max(1, n)
        fl_acc = sum(r["metrics"]["forum_limitation_accuracy"] for r in run_res) / max(1, n)
        curr_cov = sum(1.0 if r["metrics"]["currency_check_passed"] else 0.0 for r in run_res) / max(1, n)
        scope_viols = sum(r["metrics"]["scope_violations_count"] for r in run_res)
        unusable_count = sum(1 for r in run_res if not r.get("is_usable_memo", True))
        avg_lat = sum(r.get("latency_s", 0) for r in run_res) / max(1, n)

        run_summaries.append({
            "run": r_idx + 1,
            "overall_pass_rate": round(pass_rate, 4),
            "key_authority_recall": round(auth_recall, 4),
            "claim_support_rate": round(claim_support, 4),
            "citation_precision": round(cit_prec, 4),
            "forum_limitation_accuracy": round(fl_acc, 4),
            "currency_label_coverage": round(curr_cov, 4),
            "scope_violations_count": scope_viols,
            "unusable_memos_count": unusable_count,
            "avg_latency_s": round(avg_lat, 2)
        })

    def calc_mean_and_range(key: str):
        vals = [s[key] for s in run_summaries]
        mean_val = sum(vals) / len(vals)
        min_val = min(vals)
        max_val = max(vals)
        return {
            "mean": round(mean_val, 4),
            "min": round(min_val, 4),
            "max": round(max_val, 4),
            "range_str": f"{min_val:.4f} - {max_val:.4f}"
        }

    variance_stats = {
        "overall_pass_rate": calc_mean_and_range("overall_pass_rate"),
        "key_authority_recall": calc_mean_and_range("key_authority_recall"),
        "claim_support_rate": calc_mean_and_range("claim_support_rate"),
        "citation_precision": calc_mean_and_range("citation_precision"),
        "forum_limitation_accuracy": calc_mean_and_range("forum_limitation_accuracy"),
        "currency_label_coverage": calc_mean_and_range("currency_label_coverage"),
        "scope_violations_count": calc_mean_and_range("scope_violations_count"),
        "unusable_memos_count": calc_mean_and_range("unusable_memos_count"),
        "avg_latency_s": calc_mean_and_range("avg_latency_s")
    }

    case_breakdown = {}
    for c in dev_cases:
        cid = c["id"]
        c_runs = []
        for r_idx in range(3):
            match = next((r for r in all_runs_results[r_idx] if r["id"] == cid), None)
            if match:
                c_runs.append({
                    "run": r_idx + 1,
                    "passed": match["passed"],
                    "failed_reasons": match["failed_reasons"],
                    "claim_support": match["metrics"]["claim_support_rate"],
                    "authority_recall": match["metrics"]["key_authority_recall"],
                    "memo_length": match.get("memo_length", 0),
                    "is_usable": match.get("is_usable_memo", True),
                    "latency_s": match.get("latency_s", 0)
                })
        passed_runs = sum(1 for cr in c_runs if cr["passed"])
        case_breakdown[cid] = {
            "area": c.get("area"),
            "passed_runs": f"{passed_runs}/3",
            "runs": c_runs
        }

    final_report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "git_commit": get_git_commit_hash(),
        "model_generator": CLAUDE_MODEL,
        "model_judge": JUDGE_MODEL,
        "total_cases": len(dev_cases),
        "total_runs": 3,
        "variance_stats": variance_stats,
        "run_summaries": run_summaries,
        "case_breakdown": case_breakdown
    }

    report_json_path = os.path.join(WORKSPACE_DIR, "eval", "results", "variance_eval_report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2)

    report_md_path = os.path.join(WORKSPACE_DIR, "eval", "results", "variance_eval_report.md")
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# Empirical Multi-Run Variance Evaluation Report (3 Runs)\n\n")
        f.write(f"- **Git Commit**: `{get_git_commit_hash()}`\n")
        f.write(f"- **Generator Model**: `{CLAUDE_MODEL}`\n")
        f.write(f"- **LLM Judge Model**: `{JUDGE_MODEL}`\n")
        f.write(f"- **Evaluated**: 7 Dev Cases across 3 independent runs (21 total executions)\n\n")
        
        f.write("## 1. Variance Summary Across 3 Runs (Mean & Range)\n\n")
        f.write("| Metric | Run 1 | Run 2 | Run 3 | Mean | Range (Min - Max) |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")
        
        m_map = [
            ("Overall Pass Rate", "overall_pass_rate", True),
            ("Key Authority Recall", "key_authority_recall", True),
            ("Claim Support Rate", "claim_support_rate", True),
            ("Citation Precision", "citation_precision", True),
            ("Forum & Limitation Accuracy", "forum_limitation_accuracy", True),
            ("Currency Label Coverage", "currency_label_coverage", True),
            ("Scope Violations Count", "scope_violations_count", False),
            ("Cases With No Usable Memo", "unusable_memos_count", False),
            ("Average Latency (s)", "avg_latency_s", False),
        ]
        for label, k, is_pct in m_map:
            v1 = run_summaries[0][k]
            v2 = run_summaries[1][k]
            v3 = run_summaries[2][k]
            mean_v = variance_stats[k]["mean"]
            r_str = variance_stats[k]["range_str"]
            if is_pct:
                f.write(f"| **{label}** | {v1*100:.1f}% | {v2*100:.1f}% | {v3*100:.1f}% | **{mean_v*100:.1f}%** | {variance_stats[k]['min']*100:.1f}% - {variance_stats[k]['max']*100:.1f}% |\n")
            else:
                f.write(f"| **{label}** | {v1} | {v2} | {v3} | **{mean_v}** | {r_str} |\n")
        
        f.write("\n## 2. Per-Case Consistency Across Runs\n\n")
        f.write("| Case ID | Legal Area | Pass Consistency | Run 1 Pass | Run 2 Pass | Run 3 Pass | Notes / Failure Reasons |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |\n")
        for cid, data in case_breakdown.items():
            r1 = data["runs"][0] if len(data["runs"]) > 0 else {}
            r2 = data["runs"][1] if len(data["runs"]) > 1 else {}
            r3 = data["runs"][2] if len(data["runs"]) > 2 else {}
            p1 = "PASS" if r1.get("passed") else "FAIL"
            p2 = "PASS" if r2.get("passed") else "FAIL"
            p3 = "PASS" if r3.get("passed") else "FAIL"
            reasons = set(r1.get("failed_reasons", []) + r2.get("failed_reasons", []) + r3.get("failed_reasons", []))
            r_str = "; ".join(reasons) if reasons else "None"
            f.write(f"| **{cid}** | {data['area']} | **{data['passed_runs']}** | {p1} | {p2} | {p3} | {r_str} |\n")

    print("\n" + "=" * 80)
    print("VARIANCE EVALUATION COMPLETE")
    print(f"Saved JSON report: {report_json_path}")
    print(f"Saved Markdown report: {report_md_path}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
