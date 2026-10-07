"""
legal_ai/analytics/telemetry.py

Production-grade Telemetry, Retrieval Observability, and Metrics Logging
for the Pakistani Legal AI Pipeline.

Provides:
1. Exact formatted RETRIEVAL TRACE console logging with source distribution percentages:
   - QUERY PLAN (Sections, Issues)
   - SUPABASE RESULTS (count)
   - PINECONE RESULTS (count)
   - BM25 RESULTS (count)
   - EXTERNAL RESULTS (count)
   - FILTERED BREAKDOWN (- caption only, - wrong jurisdiction, - irrelevant topic, - low quality, - trust gate exclusion)
   - FINAL AUTHORITY POOL (count)
   - FINAL SOURCES (Supabase %, Pinecone %, BM25 %, External %)
2. Unified PipelineMetricsTracker recording detailed telemetry to JSONL logs.
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

METRICS_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "logs", "legal_ai_pipeline_metrics.jsonl"
)


def compute_source_distribution(authorities: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Computes exact percentage distribution across the 4 retrieval engines
    (Supabase, Pinecone, BM25, External) for the final admitted authorities.
    """
    if not authorities:
        return {"Supabase": 0.0, "Pinecone": 0.0, "BM25": 0.0, "External": 0.0}

    counts = {"Supabase": 0, "Pinecone": 0, "BM25": 0, "External": 0}
    total = len(authorities)

    for item in authorities:
        meta = item.get("metadata", {}) if isinstance(item, dict) else getattr(item, "metadata", {}) or {}
        stype = str(
            item.get("source_type")
            or item.get("retrieval_source")
            or meta.get("source_type")
            or meta.get("retrieval_source")
            or ""
        ).lower()

        # Check explicit tags or flags
        if item.get("is_supabase_fts") or meta.get("is_supabase_fts") or "supabase" in stype:
            counts["Supabase"] += 1
        elif item.get("is_external") or meta.get("is_external") or "external" in stype or "web" in stype or "searxng" in stype:
            counts["External"] += 1
        elif "bm25" in stype or item.get("bm25_score") is not None:
            counts["BM25"] += 1
        else:
            # Default dense vector match
            counts["Pinecone"] += 1

    return {
        "Supabase": round((counts["Supabase"] / total) * 100.0, 1),
        "Pinecone": round((counts["Pinecone"] / total) * 100.0, 1),
        "BM25": round((counts["BM25"] / total) * 100.0, 1),
        "External": round((counts["External"] / total) * 100.0, 1),
    }


def format_retrieval_telemetry_block(
    sections: List[str],
    issues: List[str],
    count_supabase: int,
    count_pinecone: int,
    count_bm25: int,
    count_external: int,
    filtered_counts: Dict[str, int],
    final_pool: List[Dict[str, Any]],
    source_distribution: Optional[Dict[str, float]] = None
) -> str:
    """
    Formats the mandatory production retrieval telemetry block strictly matching specification.
    """
    sections_str = ", ".join(sections) if sections else "N/A"
    issues_str = "; ".join(issues) if issues else "N/A"

    if source_distribution is None:
        source_distribution = compute_source_distribution(final_pool)

    cap_only = filtered_counts.get("caption only", 0) + filtered_counts.get("caption_only", 0)
    wrong_jur = filtered_counts.get("wrong jurisdiction", 0) + filtered_counts.get("foreign_jurisdiction", 0)
    irrel_top = (
        filtered_counts.get("irrelevant topic", 0)
        + filtered_counts.get("unrelated_subject", 0)
        + filtered_counts.get("mismatched_domain", 0)
    )
    low_qual = (
        filtered_counts.get("low quality", 0)
        + filtered_counts.get("insufficient_text", 0)
    )
    trust_gate = filtered_counts.get("trust gate exclusion", 0) + filtered_counts.get("trust_gate_exclusion", 0)

    block = (
        f"\nQUERY PLAN:\n"
        f"Sections: {sections_str}\n"
        f"Issues: {issues_str}\n\n"
        f"SUPABASE RESULTS:\n"
        f"count: {count_supabase}\n\n"
        f"PINECONE RESULTS:\n"
        f"count: {count_pinecone}\n\n"
        f"BM25 RESULTS:\n"
        f"count: {count_bm25}\n\n"
        f"EXTERNAL RESULTS:\n"
        f"count: {count_external}\n\n"
        f"FILTERED:\n"
        f"- caption only: {cap_only}\n"
        f"- wrong jurisdiction: {wrong_jur}\n"
        f"- irrelevant topic: {irrel_top}\n"
        f"- low quality: {low_qual}\n"
        f"- trust gate exclusion: {trust_gate}\n\n"
        f"FINAL AUTHORITY POOL:\n"
        f"count: {len(final_pool)}\n\n"
        f"FINAL SOURCES:\n"
        f"Supabase: {source_distribution['Supabase']}%\n"
        f"Pinecone: {source_distribution['Pinecone']}%\n"
        f"BM25: {source_distribution['BM25']}%\n"
        f"External: {source_distribution['External']}%\n"
    )
    return block


def log_retrieval_telemetry(
    sections: List[str],
    issues: List[str],
    count_supabase: int,
    count_pinecone: int,
    count_bm25: int,
    count_external: int,
    filtered_counts: Dict[str, int],
    final_pool: List[Dict[str, Any]],
    source_distribution: Optional[Dict[str, float]] = None
) -> str:
    """
    Constructs and prints the exact retrieval telemetry block to stdout/stderr.
    """
    block = format_retrieval_telemetry_block(
        sections=sections,
        issues=issues,
        count_supabase=count_supabase,
        count_pinecone=count_pinecone,
        count_bm25=count_bm25,
        count_external=count_external,
        filtered_counts=filtered_counts,
        final_pool=final_pool,
        source_distribution=source_distribution
    )
    print(block, flush=True)
    return block


class PipelineMetricsTracker:
    """
    End-to-end JSONL metrics tracker capturing query understanding, stage latencies,
    rejection statistics, and authority quality scores across pipeline executions.
    """
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
            "top_authorities": [],
            "source_distribution": {}
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
        self.warnings: List[str] = []
        self.completed_at: Optional[str] = None
        self.total_duration_sec: float = 0.0

    def record_warning(self, warning: str):
        if not hasattr(self, "warnings"):
            self.warnings = []
        self.warnings.append(str(warning))

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
        self.candidate_stats["source_distribution"] = compute_source_distribution(authorities)

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
