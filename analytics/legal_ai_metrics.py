"""
analytics/legal_ai_metrics.py

Production Quality Monitoring & Telemetry Layer for Pakistani Legal AI Pipeline.
Tracks end-to-end metrics across:
- Query understanding accuracy
- Candidate admission & rejection ratios
- Authority score distribution
- Stage latency breakdown
- PDF resolution integrity (0% broken links)
- Review gate verification outcomes
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

METRICS_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "logs", "legal_ai_pipeline_metrics.jsonl"
)


class PipelineMetricsTracker:
    def __init__(self, job_id: str, query_text: str, user_id: str = "anonymous"):
        self.job_id = job_id
        self.query_text = query_text
        self.user_id = user_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.timings: Dict[str, float] = {}
        self.stage_starts: Dict[str, float] = {}
        self.legal_plan: Dict[str, Any] = {}
        self.current_law_verified: List[str] = []
        self.candidate_stats: Dict[str, Any] = {
            "raw_retrieved": 0,
            "quality_rejected": 0,
            "admitted_to_ranking": 0,
            "top_authorities": []
        }
        self.pdf_stats: Dict[str, int] = {
            "total_cards": 0,
            "signed_urls": 0,
            "dynamic_generated": 0,
            "failed_urls": 0
        }
        self.review_gate_status: Dict[str, Any] = {
            "passed": True,
            "issues_count": 0
        }
        self.completed_at: Optional[str] = None
        self.total_duration_sec: float = 0.0

    def start_stage(self, stage_name: str):
        self.stage_starts[stage_name] = time.perf_counter()

    def end_stage(self, stage_name: str):
        if stage_name in self.stage_starts:
            duration = time.perf_counter() - self.stage_starts.pop(stage_name)
            self.timings[stage_name] = round(duration, 3)

    def record_plan(self, plan: Any):
        if hasattr(plan, "dict"):
            self.legal_plan = plan.dict()
        elif isinstance(plan, dict):
            self.legal_plan = plan

    def record_candidate_filtering(self, raw_count: int, rejected_counts: Dict[str, int], admitted_count: int):
        self.candidate_stats["raw_retrieved"] = raw_count
        self.candidate_stats["quality_rejected"] = sum(rejected_counts.values())
        self.candidate_stats["rejection_breakdown"] = rejected_counts
        self.candidate_stats["admitted_to_ranking"] = admitted_count

    def record_ranked_authorities(self, authorities: List[Dict[str, Any]]):
        top_list = []
        for a in authorities[:5]:
            top_list.append({
                "citation": a.get("citation") or a.get("neutral_citation"),
                "court": a.get("court"),
                "authority_score": a.get("authority_score", 0.0)
            })
        self.candidate_stats["top_authorities"] = top_list

    def record_pdf_stats(self, total: int, signed: int, dynamic: int, failed: int = 0):
        self.pdf_stats = {
            "total_cards": total,
            "signed_urls": signed,
            "dynamic_generated": dynamic,
            "failed_urls": failed
        }

    def record_review_gate(self, passed: bool, issues: List[str]):
        self.review_gate_status = {
            "passed": passed,
            "issues_count": len(issues),
            "issues": issues
        }

    def finalize(self):
        self.completed_at = datetime.now(timezone.utc).isoformat()
        if "total" not in self.timings and hasattr(self, "_global_start"):
            self.total_duration_sec = round(time.perf_counter() - self._global_start, 3)
            self.timings["total"] = self.total_duration_sec

        entry = {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "user_id": self.user_id,
            "query_summary": self.query_text[:120],
            "legal_domain": self.legal_plan.get("legal_domain", []),
            "provisions": self.legal_plan.get("provisions", []),
            "timings_sec": self.timings,
            "candidate_stats": self.candidate_stats,
            "pdf_stats": self.pdf_stats,
            "review_gate_status": self.review_gate_status
        }

        try:
            os.makedirs(os.path.dirname(METRICS_LOG_PATH), exist_ok=True)
            with open(METRICS_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ [METRICS NOTICE] Could not append to metrics log: {e}", file=sys.stderr)

        return entry
