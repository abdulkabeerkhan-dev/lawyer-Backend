"""
legal_ai/ranking/relevance_filter.py

Strict Quality and Relevance Gating Layer for Pakistani Legal AI Pipeline.
Executes BEFORE Authority Ranking to hard-reject:
1. Caption-only, metadata-only, or quarantined records
2. Short stubs (< 100 characters / < 150 words)
3. Foreign jurisdictions (Supreme Court of India, UK, USA)
4. Off-topic subject matters (e.g., narcotics or defamation in commercial fraud queries)
5. Trust gate exclusions
"""

import re
from typing import Dict, List, Any, Tuple, Optional


def filter_candidate_quality_before_ranking(
    raw_candidates: List[Dict[str, Any]],
    query_plan: Any
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Filters raw candidates prior to authority ranking.
    Returns:
        clean_candidates: List of candidates meeting substantive quality standards.
        rejection_counts: Structured dictionary tracking rejections by category.
    """
    clean_candidates: List[Dict[str, Any]] = []
    rejection_counts: Dict[str, int] = {
        "caption_only": 0,
        "insufficient_text": 0,
        "unrelated_subject": 0,
        "foreign_jurisdiction": 0,
        "mismatched_domain": 0,
        "trust_gate_exclusion": 0
    }

    domains = []
    questions_str = ""
    provisions_str = ""

    if query_plan:
        if hasattr(query_plan, "legal_domain") and query_plan.legal_domain:
            domains = [str(d).lower() for d in query_plan.legal_domain]
        elif isinstance(query_plan, dict) and query_plan.get("legal_domain"):
            domains = [str(d).lower() for d in query_plan["legal_domain"]]

        if hasattr(query_plan, "legal_questions") and query_plan.legal_questions:
            questions_str = " ".join([str(q) for q in query_plan.legal_questions]).lower()
        elif isinstance(query_plan, dict) and query_plan.get("legal_questions"):
            questions_str = " ".join([str(q) for q in query_plan["legal_questions"]]).lower()

        if hasattr(query_plan, "provisions") and query_plan.provisions:
            provisions_str = " ".join([str(p) for p in query_plan.provisions]).lower()
        elif isinstance(query_plan, dict) and query_plan.get("provisions"):
            provisions_str = " ".join([str(p) for p in query_plan["provisions"]]).lower()

    is_financial_or_fraud_or_bail = any(k in domains or k in questions_str or k in provisions_str for k in [
        "409", "420", "406", "489-f", "489f", "cheating", "breach of trust", "misappropriat",
        "director", "corporate", "loan", "bail", "498", "497"
    ])

    matter_types = [str(m).lower() for m in getattr(query_plan, "matter_type", [])] if query_plan else []
    target_province = str(getattr(query_plan, "province", "Federal")).strip().title()

    is_rent = "rent" in matter_types or any(k in domains or k in questions_str for k in ["rent", "eviction", "prpa", "tenant"])
    is_adverse_possession = any(k in domains or k in questions_str for k in ["adverse possession", "animus possidendi", "limitation act"])
    is_injunction = any(k in domains or k in questions_str for k in ["injunction", "order xxxix", "o.xxxix", "o.39"])
    is_family = "family" in matter_types or any(k in domains for k in ["family", "khula", "custody", "dower"])

    for c in raw_candidates:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else c
        c_type = str(c.get("content_type") or meta.get("content_type") or "").lower()
        status = str(c.get("retrieval_status") or meta.get("retrieval_status") or "").lower()

        # 1. Hard Drop: Caption-only / metadata-only / quarantined / restricted
        if c_type in ("caption_only", "metadata_only"):
            rejection_counts["caption_only"] += 1
            continue

        if status in ("quarantined", "rejected", "restricted"):
            rejection_counts["trust_gate_exclusion"] += 1
            continue

        title = str(c.get("title") or c.get("case_name") or c.get("case_title") or meta.get("title") or meta.get("case_title") or "").lower()
        court = str(c.get("court") or c.get("court_name") or c.get("canonical_court_name") or meta.get("court") or meta.get("court_name") or "").lower()
        cid = str(c.get("case_id") or meta.get("case_id") or "").lower()

        # 2. Hard Drop: Foreign jurisdictions
        court_norm = court.replace("-", " ")
        if any(fj in court_norm for fj in ["supreme court of india", "india", "delhi high court", "all england", "calcutta", "bombay", "madras", "privy council"]) or cid.startswith("air_") or "state of u. p" in title:
            if "pakistan" not in court_norm:
                rejection_counts["foreign_jurisdiction"] += 1
                continue

        raw_txt = str(c.get("preview") or c.get("full_text") or c.get("snippet") or c.get("text") or meta.get("full_text") or meta.get("text") or "").strip()
        # 3. Hard Drop: Insufficient text length (< 100 chars)
        if len(raw_txt) < 100:
            rejection_counts["insufficient_text"] += 1
            continue

        haystack = f"{title} {raw_txt.lower()} {court_norm}"

        # 4. Hard Drop: Unrelated subject matter
        if is_financial_or_fraud_or_bail:
            # Defamation filter (e.g. Gurmani)
            if any(k in haystack for k in ["mushtaq ahmad gurmani", "z. a. suleri", "defamation", "defamatory", "section 500 ppc", "sec 500"]):
                if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "misappropriat", "entrustment"]):
                    rejection_counts["unrelated_subject"] += 1
                    continue

            # Pure narcotics filter (CNSA)
            if any(k in haystack for k in ["control of narcotic substances act", "cnsa", "charas", "heroin", "opium", "methamphetamine"]):
                if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "consultancy fee"]):
                    rejection_counts["unrelated_subject"] += 1
                    continue

            # Pure murder / 302 PPC filter
            if any(k in haystack for k in ["section 302 ppc", "302/34 ppc", "murder trial", "firearm injury", "post-mortem report"]):
                if not any(k in haystack for k in ["409", "420", "406", "breach of trust"]):
                    rejection_counts["unrelated_subject"] += 1
                    continue

            # Pure rent / tenancy filter (only when query does NOT engage rent/tenancy)
            if not is_rent:
                if any(k in haystack for k in ["rent restriction", "ejectment petition", "fair rent", "tenant", "landlord"]):
                    if not any(k in haystack for k in ["409", "420", "breach of trust", "fir", "bail", "cheque", "489"]):
                        rejection_counts["mismatched_domain"] += 1
                        continue

            # Pure tax / customs / revenue assessment filter
            if any(k in haystack for k in [
                "sales tax act", "income tax ordinance", "appellate tribunal inland revenue",
                "customs duty", "special prosecutor customs", "directorate of intelligence",
                "anti-money laundering act", "customs act", "customs court", "fbr vs"
            ]):
                rejection_counts["mismatched_domain"] += 1
                continue

            # Pure labour / trade union filter
            if any(k in haystack for k in [
                "industrial relations act", "labour court", "trade union", "workman",
                "standing orders ordinance", "wage board"
            ]):
                rejection_counts["mismatched_domain"] += 1
                continue

        if is_rent:
            # Filter out pure murder, narcotics, family khula
            if any(k in haystack for k in ["section 302 ppc", "murder trial", "cnsa", "narcotic", "charas", "heroin", "khula", "dower", "custody of minor"]):
                if not any(k in haystack for k in ["tenant", "landlord", "rent", "prpa", "cheque", "489"]):
                    rejection_counts["mismatched_domain"] += 1
                    continue
            if not is_financial_or_fraud_or_bail and any(k in haystack for k in ["pre-arrest bail", "post-arrest bail"]):
                if not any(k in haystack for k in ["tenant", "landlord", "rent", "prpa"]):
                    rejection_counts["mismatched_domain"] += 1
                    continue
            # Filter out non-binding provincial rent statute if Punjab is target province
            if target_province == "Punjab" and any(k in haystack for k in ["sindh rented premises ordinance", "srpo 1979", "srpo, 1979"]):
                if not any(k in haystack for k in ["punjab", "prpa", "lahore"]):
                    rejection_counts["mismatched_domain"] += 1
                    continue

        if is_adverse_possession or is_injunction:
            # Filter out murder, narcotics, family
            if any(k in haystack for k in ["section 302 ppc", "murder trial", "cnsa", "narcotic", "pre-arrest bail", "khula", "dower"]):
                if not any(k in haystack for k in ["possession", "injunction", "cpc", "limitation", "specific relief"]):
                    rejection_counts["mismatched_domain"] += 1
                    continue

        if is_family:
            if any(k in haystack for k in ["section 302 ppc", "cnsa", "commercial court", "fio 2001", "ejectment petition"]):
                if not any(k in haystack for k in ["family", "guardian", "marriage", "khula", "custody"]):
                    rejection_counts["mismatched_domain"] += 1
                    continue

        clean_candidates.append(c)

    return clean_candidates, rejection_counts


def filter_topic_relevance(
    candidates: List[Dict[str, Any]],
    topics: List[str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """
    Topic-level relevance gating layer.
    Evaluates candidate texts against topic-specific 'relevance.strong' markers.
    Returns:
        passing_candidates: Candidates matching at least one strong marker for any detected topic.
        rejected_candidates: Candidates not passing the topic marker test.
        abstain_topics: Topics for which ZERO candidates matched.
    """
    from legal_ai.verification.doctrinal_rules import TOPICS_SPEC
    if not topics:
        return candidates, [], []

    passing: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    topic_match_counts = {t: 0 for t in topics if t in TOPICS_SPEC}

    for c in candidates:
        text = str(
            c.get("holding") or c.get("headnote") or c.get("text")
            or c.get("preview") or c.get("full_text") or c.get("snippet") or ""
        )
        if not text.strip():
            rejected.append(c)
            continue

        matched_any = False
        for t in topics:
            if t not in TOPICS_SPEC:
                continue
            spec = TOPICS_SPEC[t]
            strong = [p for p in spec["relevance"]["strong"] if re.search(p, text, re.IGNORECASE)]
            if strong:
                topic_match_counts[t] += 1
                matched_any = True

        if matched_any:
            passing.append(c)
        else:
            rejected.append(c)

    abstain_topics = [t for t, count in topic_match_counts.items() if count == 0]
    return passing, rejected, abstain_topics

