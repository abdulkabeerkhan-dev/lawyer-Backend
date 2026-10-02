import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import asyncio
from eval.llm_judge import calibrate_judge, JUDGE_MODEL, JUDGE_PROMPT_VERSION

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

async def main():
    samples_path = os.path.join(os.path.dirname(__file__), "calibration_samples.json")
    with open(samples_path, "r", encoding="utf-8") as f:
        samples = json.load(f)
        
    print("=" * 80)
    print("LLM JUDGE CALIBRATION SUITE")
    print(f"Judge Model: {JUDGE_MODEL} (Generator writer: claude-haiku-4-5-20251001)")
    print(f"Judge Prompt Version: {JUDGE_PROMPT_VERSION}")
    print(f"Evaluating {len(samples)} hand-labeled samples (10 positive, 10 negative)...")
    print("=" * 80)
    
    results = await calibrate_judge(samples)
    
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    report_file = os.path.join(results_dir, "judge_calibration_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"Total Checks: {results['total_checks']}")
    print(f"Agreements: {results['agreements']}")
    print(f"Agreement Rate: {results['agreement_rate'] * 100:.2f}%")
    print(f"Saved detailed report to: {report_file}")
    
    # Assert acceptable agreement rate (> 80%)
    if results['agreement_rate'] >= 0.80:
        print("[PASS] LLM Judge Calibration passed threshold (>= 80%).")
    else:
        print("[FAIL] LLM Judge Calibration failed threshold (< 80%).")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
