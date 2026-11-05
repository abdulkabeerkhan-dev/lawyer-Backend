"""
core/bench_quorum.py

Pakistani Bench Strength & Quorum Weighting Engine.
Enforces Article 189 & Article 201 binding precedent hierarchy:
- Full Bench / Larger Bench (5+ judges) binds Division Bench (2 judges).
- Division Bench binds Single Bench.
- Applies relevance-gating: Quorum multiplier ONLY activates if semantic relevance score >= 0.70,
  preventing off-topic larger bench judgments from outscoring on-point division bench precedents.
"""

import re
from typing import Dict, Any, List

def calculate_quorum_multiplier(case_record: Dict[str, Any], semantic_relevance: float = 1.0) -> float:
    """
    Computes quorum boost multiplier (1.0x to 1.50x) based on bench composition.
    Only applies if semantic_relevance >= 0.70 (relevance-gating).
    """
    # Section 4 Invariant: Relevance-gated multiplier
    if semantic_relevance < 0.70:
        return 1.0

    raw_text = " ".join([
        str(case_record.get("case_title", "")),
        str(case_record.get("headnote", "")),
        str(case_record.get("judges", "")),
        str(case_record.get("bench_type", ""))
    ]).lower()

    # 1. Full Bench / 5+ Judges / Constitutional Bench
    if any(k in raw_text for k in ["full bench", "larger bench", "14-member", "11-member", "7-member", "5-member", "constitutional bench"]):
        return 1.50

    # 2. 3-4 Member Bench
    if any(k in raw_text for k in ["3-member", "4-member", "three judges", "four judges", "larger bench"]):
        return 1.35

    # 3. Division Bench (DB / 2 Judges)
    if any(k in raw_text for k in ["division bench", "d.b.", "d.b", "two judges"]):
        return 1.20

    # 4. Supreme Court baseline (at least 2-3 judges typically)
    journal = str(case_record.get("journal", "")).upper()
    if journal in ("SCMR", "PSC") or "supreme court" in str(case_record.get("court_name", "")).lower():
        return 1.25

    # 5. Single Bench (SB / 1 Judge)
    return 1.05

def apply_bench_quorum_reranking(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reranks candidate cases by applying relevance-gated quorum weights to baseline scores.
    """
    for c in candidates:
        base_score = float(c.get("score") or c.get("relevance_score") or 0.5)
        multiplier = calculate_quorum_multiplier(c, semantic_relevance=base_score)
        c["quorum_multiplier"] = multiplier
        c["effective_score"] = round(base_score * multiplier, 4)

    return sorted(candidates, key=lambda x: x.get("effective_score", 0), reverse=True)
