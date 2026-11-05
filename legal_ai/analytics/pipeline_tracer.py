"""
Pipeline Tracer: Structured per-stage instrumentation and telemetry for query processing.

Logs one JSON record per stage with:
- stage name
- top 10 case_id, title, court, score
- fallbacks fired (planner fallback, rerank fallback, gate bypass, Supabase breaker, verification block, canned fallback)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class PipelineTracer:
    """
    Captures stage-by-stage retrieval and synthesis telemetry for auditability and gold set evaluation.
    """

    KNOWN_FALLBACKS = [
        "planner_fallback",
        "rerank_fallback",
        "gate_bypass",
        "supabase_breaker",
        "verification_block",
        "canned_fallback",
    ]

    def __init__(self, job_id: str, query_text: str):
        self.job_id = job_id
        self.query_text = query_text
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.stages: List[Dict[str, Any]] = []
        self.fallbacks_summary: Dict[str, bool] = {fb: False for fb in self.KNOWN_FALLBACKS}

    def record_stage(
        self,
        stage: str,
        candidates: Optional[List[Dict[str, Any]]] = None,
        fallbacks: Optional[Dict[str, bool]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Records a single pipeline stage snapshot.
        """
        top_10: List[Dict[str, Any]] = []
        if candidates:
            for c in candidates[:10]:
                meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
                cid = c.get("case_id") or c.get("id") or meta.get("case_id") or "UNKNOWN"
                title = (
                    c.get("title")
                    or c.get("case_name")
                    or c.get("case_title")
                    or meta.get("title")
                    or meta.get("case_title")
                    or ""
                )
                court = (
                    c.get("court")
                    or c.get("court_name")
                    or c.get("canonical_court_name")
                    or meta.get("court")
                    or meta.get("court_name")
                    or "UNKNOWN"
                )
                score = c.get("score") or c.get("rrf_score") or c.get("authority_score") or c.get("rerank_score") or 0.0
                citation = c.get("citation") or meta.get("citation") or ""
                top_10.append({
                    "case_id": str(cid),
                    "citation": str(citation),
                    "title": str(title),
                    "court": str(court),
                    "score": round(float(score), 6) if isinstance(score, (int, float)) else score,
                })

        stage_fallbacks: Dict[str, bool] = {fb: False for fb in self.KNOWN_FALLBACKS}
        if fallbacks:
            for k, v in fallbacks.items():
                stage_fallbacks[k] = bool(v)
                if bool(v):
                    self.fallbacks_summary[k] = True

        entry: Dict[str, Any] = {
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "candidate_count": len(candidates) if candidates is not None else 0,
            "top_10": top_10,
            "fallbacks_fired": stage_fallbacks,
            "extra": extra or {},
        }
        self.stages.append(entry)

    def find_case_in_stages(self, target: str) -> List[Dict[str, Any]]:
        """
        Traces a specific case ID or citation across all stages to see where it enters and exits.
        """
        norm_target = re.sub(r"[\s_-]+", " ", str(target)).strip().lower()
        presence = []
        for s in self.stages:
            stage_name = s["stage"]
            found = False
            rank = None
            score = None
            for idx, c in enumerate(s.get("top_10", [])):
                cid = re.sub(r"[\s_-]+", " ", str(c.get("case_id", ""))).strip().lower()
                cit = re.sub(r"[\s_-]+", " ", str(c.get("citation", ""))).strip().lower()
                title = str(c.get("title", "")).lower()
                if norm_target in cid or norm_target in cit or norm_target in title:
                    found = True
                    rank = idx + 1
                    score = c.get("score")
                    break
            presence.append({
                "stage": stage_name,
                "present": found,
                "rank": rank,
                "score": score,
            })
        return presence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "query_text": self.query_text,
            "created_at": self.created_at,
            "fallbacks_summary": self.fallbacks_summary,
            "stages": self.stages,
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save_to_disk(self, directory: str = "reports/traces") -> str:
        """
        Persists JSON trace record to disk.
        """
        try:
            os.makedirs(directory, exist_ok=True)
            filepath = os.path.join(directory, f"trace_{self.job_id}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.to_json(indent=2))
            return filepath
        except Exception as e:
            logger.warning(f"Failed to persist pipeline trace: {e}")
            return ""
