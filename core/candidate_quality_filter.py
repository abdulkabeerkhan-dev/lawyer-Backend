"""
core/candidate_quality_filter.py

Candidate Quality Filter Gate for Pakistani Legal AI Pipeline.
Executes BEFORE Authority Ranking to eliminate low-quality, incomplete,
caption-only, foreign, or off-topic records so they do not consume ranking or LLM resources.
"""

import re
from typing import Dict, List, Any, Tuple
from core.legal_query_planner import LegalQueryPlan


def filter_candidate_quality_before_ranking(
    raw_candidates: List[Dict[str, Any]],
    query_plan: LegalQueryPlan
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Filters raw candidates prior to authority ranking.
    Returns:
        clean_candidates: List of candidates meeting substantive quality standards.
        rejection_counts: Telemetry of why candidates were dropped.
    """
    clean_candidates: List[Dict[str, Any]] = []
    rejection_counts: Dict[str, int] = {
        "caption_only": 0,
        "insufficient_text": 0,
        "unrelated_subject": 0,
        "foreign_jurisdiction": 0,
        "mismatched_domain": 0
    }

    # Query context markers
    domains = [d.lower() for d in (query_plan.legal_domain or [])]
    questions_str = " ".join(query_plan.legal_questions or []).lower()
    provisions_str = " ".join(query_plan.provisions or []).lower()

    is_financial_or_fraud_or_bail = any(k in domains or k in questions_str or k in provisions_str for k in [
        "409", "420", "406", "489-f", "489f", "cheating", "breach of trust", "misappropriat",
        "director", "corporate", "loan", "bail", "498", "497"
    ])

    for c in raw_candidates:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else c
        c_type = str(c.get("content_type") or meta.get("content_type") or "").lower()
        status = str(c.get("retrieval_status") or meta.get("retrieval_status") or "").lower()

        # 1. Hard Drop: Caption-only / metadata-only / quarantined / rejected
        if c_type in ("caption_only", "metadata_only") or status in ("quarantined", "rejected", "restricted"):
            rejection_counts["caption_only"] += 1
            continue

        title = str(c.get("title") or c.get("case_name") or c.get("case_title") or meta.get("title") or meta.get("case_title") or "").lower()
        court = str(c.get("court") or c.get("court_name") or c.get("canonical_court_name") or meta.get("court") or meta.get("court_name") or "").lower()
        cid = str(c.get("case_id") or meta.get("case_id") or "").lower()

        # 2. Hard Drop: Foreign jurisdictions (e.g. Indian Supreme Court, UK, USA unless cited for foreign persuasive comparative)
        if any(fj in court for fj in ["supreme court of india", "delhi high court", "all-england", "calcutta high court", "bombay high court"]) or cid.startswith("air_"):
            if "pakistan" not in court:
                rejection_counts["foreign_jurisdiction"] += 1
                continue

        raw_txt = str(c.get("preview") or c.get("full_text") or c.get("snippet") or c.get("text") or meta.get("full_text") or meta.get("text") or "").strip()
        # 3. Hard Drop: Insufficient text length (< 100 chars)
        if len(raw_txt) < 100:
            rejection_counts["insufficient_text"] += 1
            continue

        haystack = f"{title} {raw_txt.lower()} {court}"

        # 4. Hard Drop: Unrelated subject matter
        if is_financial_or_fraud_or_bail:
            # Defamation filter (e.g. Gurmani)
            if any(k in haystack for k in ["mushtaq ahmad gurmani", "z. a. suleri", "defamation", "defamatory", "section 500 ppc", "sec 500"]):
                if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "misappropriat", "entrustment", "director loan"]):
                    rejection_counts["unrelated_subject"] += 1
                    continue

            # Pure narcotics filter (CNSA)
            if any(k in haystack for k in ["control of narcotic substances act", "cnsa", "charas", "heroin", "opium", "methamphetamine"]):
                if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "consultancy fee", "director"]):
                    rejection_counts["unrelated_subject"] += 1
                    continue

            # Pure murder / 302 PPC filter
            if any(k in haystack for k in ["section 302 ppc", "302/34 ppc", "murder trial", "firearm injury", "post-mortem report"]):
                if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "director", "cheque"]):
                    rejection_counts["unrelated_subject"] += 1
                    continue

            # Pure rent / tenancy filter
            if any(k in haystack for k in ["rent restriction", "ejectment petition", "fair rent", "tenant", "landlord"]):
                if not any(k in haystack for k in ["409", "420", "breach of trust", "fir", "bail"]):
                    rejection_counts["mismatched_domain"] += 1
                    continue

        clean_candidates.append(c)

    return clean_candidates, rejection_counts
