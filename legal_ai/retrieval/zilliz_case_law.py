"""
legal_ai/retrieval/zilliz_case_law.py

Plan-aware case-law and statute retrieval on Zilliz for the live /query pipeline.

Why this exists: /query in main.py still searched the abandoned Pinecone index
(401 in production, see docs/ZILLIZ_MIGRATION_PLAN.md §10), so dense retrieval
returned nothing and answers were built from keyword-only hits. This module
implements §10.2-§10.3 of the plan and returns candidates in the same shape as
the Pinecone matches that the rest of main.py consumes.

Retrieval per query:
  lane "plan"   : domain == X and array_contains_any(statutes, plan provisions)
  lane "domain" : domain == X
  lane "open"   : no filter (so mis-tagged cases are never lost)
Lanes are fused per case with weighted RRF; filtered lanes carry more weight.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from legal_ai.retrieval.zilliz_search import search_zilliz_hybrid

logger = logging.getLogger(__name__)

# Planner domain (core/legal_query_planner.LegalDomainType) -> domain values
# written into judgments_v1 by scripts/zilliz/enrich.py::classify_domain.
PLANNER_TO_ZILLIZ_DOMAIN: Dict[str, List[str]] = {
    "criminal": ["criminal"],
    "cybercrime": ["criminal"],
    "civil": ["civil"],
    "family": ["family"],
    "rent": ["rent"],
    "constitutional": ["constitutional"],
    "service": ["service"],
    "labour": ["service"],
    "banking": ["banking_commercial"],
    "corporate": ["banking_commercial", "tax_corporate"],
    "taxation": ["tax_corporate"],
    "intellectual_property": ["civil", "banking_commercial"],
    "environmental": ["constitutional"],
}

LANE_WEIGHTS = {"plan": 1.6, "domain": 1.25, "open": 1.0}
RRF_K = 60.0

_CANONICAL_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*_\d{4}_(?:SEC|ART|O|ORD)_[A-Z0-9_]+$")
_YEAR_RE = re.compile(r"\b(19[4-9]\d|20[0-3]\d)\b")
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9_]+$")
_ACT_PREFIX_RE = re.compile(r"^([A-Z][A-Z0-9_]*?_\d{4})_")


def plan_domains(plan: Any) -> List[str]:
    """Map the planner's domain(s) onto Zilliz domain tags, primary first."""
    raw: List[str] = []
    primary = getattr(plan, "primary_domain", None)
    if primary:
        raw.append(str(primary))
    for d in getattr(plan, "legal_domain", None) or []:
        raw.append(str(d))
    out: List[str] = []
    for d in raw:
        key = d.strip().lower().replace("-", "_").replace(" ", "_")
        for z in PLANNER_TO_ZILLIZ_DOMAIN.get(key, []):
            if z not in out:
                out.append(z)
    return out[:2]


def plan_statute_ids(plan: Any) -> List[str]:
    """Canonical statute IDs from the plan, in the form stored in judgments_v1.statutes."""
    ids: List[str] = []
    for p in (getattr(plan, "provisions", None) or []):
        cid = str(p).strip().upper()
        # Zilliz ingestion writes CPC orders as CPC_1908_O_XX_R_18.
        cid = cid.replace("_ORD_", "_O_")
        if _CANONICAL_ID_RE.match(cid) and cid not in ids:
            ids.append(cid)
    return ids[:20]


def _quote_list(values: Iterable[str]) -> str:
    return ", ".join(f'"{v}"' for v in values if _SAFE_VALUE_RE.match(v))


def build_lane_filters(plan: Any) -> List[Tuple[str, Optional[str]]]:
    """Return [(lane_name, filter_expr)] for this plan. Always includes the open lane."""
    domains = plan_domains(plan)
    statutes = plan_statute_ids(plan)
    lanes: List[Tuple[str, Optional[str]]] = []
    domain_expr = None
    if domains:
        domain_expr = f"domain in [{_quote_list(domains)}]"
    if statutes:
        stat_expr = f"array_contains_any(statutes, [{_quote_list(statutes)}])"
        lanes.append(("plan", f"{domain_expr} and {stat_expr}" if domain_expr else stat_expr))
    if domain_expr:
        lanes.append(("domain", domain_expr))
    lanes.append(("open", None))
    return lanes


def _year_from(citation: str, fallback: Any) -> Any:
    m = _YEAR_RE.search(citation or "")
    if m:
        return int(m.group(1))
    return fallback


def to_pipeline_match(cand: Dict[str, Any]) -> Dict[str, Any]:
    """Reshape a zilliz_search candidate into the Pinecone match shape used in main.py."""
    citation = cand.get("citation") or cand.get("case_key") or ""
    year = _year_from(citation, cand.get("year"))
    text = cand.get("text") or cand.get("preview") or ""
    meta = dict(cand.get("metadata") or {})
    meta.update({
        "case_id": cand.get("case_key") or cand.get("case_id"),
        "citation": citation,
        "title": cand.get("title") or citation,
        "case_title": cand.get("title") or citation,
        "court": cand.get("court") or "",
        "year": year,
        "text": text,
        "text_preview": (cand.get("preview") or text)[:400],
        "content_type": cand.get("content_type") or "headnote",
        "legal_domain": cand.get("domain"),
        "statutes_cited": cand.get("statutes_cited") or [],
        "source_type": "Zilliz",
    })
    out = dict(cand)
    out.update({
        "id": cand.get("case_key") or cand.get("id"),
        "year": year,
        "similarity_score": cand.get("score", 0.0),
        "metadata": meta,
    })
    return out


def fuse_lanes(
    lane_results: List[Tuple[str, List[Dict[str, Any]]]],
    plan_statutes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Weighted RRF across lanes, keyed by case. Adds a small boost per matched plan statute."""
    pooled: Dict[str, Dict[str, Any]] = {}
    wanted = set(plan_statutes or [])
    for lane, results in lane_results:
        w = LANE_WEIGHTS.get(lane, 1.0)
        for rank, cand in enumerate(results):
            key = cand.get("case_key") or cand.get("case_id") or cand.get("id")
            if not key:
                continue
            contrib = w / (RRF_K + rank + 1.0)
            slot = pooled.setdefault(key, {"cand": cand, "score": 0.0, "lanes": []})
            slot["score"] += contrib
            slot["lanes"].append(lane)
            if float(cand.get("score", 0.0)) > float(slot["cand"].get("score", 0.0)):
                slot["cand"] = cand
    fused: List[Dict[str, Any]] = []
    for key, slot in pooled.items():
        cand = slot["cand"]
        hits = len(wanted.intersection(cand.get("statutes_cited") or []))
        # Authority prior from zilliz_search (court level, cited_by) is folded in
        # gently so a strong topical match is not buried by a famous but off-topic case.
        rrf = float(cand.get("rrf_score") or 0.0)
        authority = float(cand.get("score", 0.0)) / rrf if rrf > 0 else 1.0
        authority = min(max(authority, 1.0), 1.6)
        final = slot["score"] * (1.0 + 0.15 * min(hits, 3)) * (authority ** 0.5)
        m = to_pipeline_match(cand)
        m.update({
            "score": final,
            "rrf_score": slot["score"],
            "retrieval_lanes": sorted(set(slot["lanes"])),
            "plan_statute_hits": hits,
        })
        fused.append(m)
    fused.sort(key=lambda x: x["score"], reverse=True)
    return fused


async def retrieve_case_law(
    queries: List[str],
    plan: Any,
    top_k: int = 40,
    per_lane_k: int = 30,
) -> List[Dict[str, Any]]:
    """Run every (query x lane) search in parallel and return fused Pinecone-shaped matches."""
    queries = [q.strip() for q in queries if q and q.strip()][:5]
    if not queries:
        return []
    lanes = build_lane_filters(plan)
    jobs = []
    labels: List[str] = []
    for q in queries:
        for lane, expr in lanes:
            jobs.append(search_zilliz_hybrid(query_text=q, top_k=per_lane_k, filter_expr=expr))
            labels.append(lane)
    results = await asyncio.gather(*jobs, return_exceptions=True)
    lane_results: List[Tuple[str, List[Dict[str, Any]]]] = []
    for lane, res in zip(labels, results):
        if isinstance(res, Exception):
            logger.warning("[ZillizCaseLaw] lane %s failed: %s", lane, res)
            continue
        lane_results.append((lane, res or []))
    fused = fuse_lanes(lane_results, plan_statute_ids(plan))
    logger.info(
        "[ZillizCaseLaw] queries=%d lanes=%s fused_cases=%d",
        len(queries), [l for l, _ in lanes], len(fused),
    )
    return fused[:top_k]


async def retrieve_relevant_statutes(
    query: str,
    plan: Any,
    max_new: int = 3,
) -> List[Dict[str, Any]]:
    """
    Semantic statute search on statutes_v3. Returns up to `max_new` provisions the
    planner did not already name, preferring the plan's domain and acts.
    """
    try:
        from legal_ai.retrieval.statute_search import search_statutes_hybrid
    except Exception as e:  # pymilvus missing etc.
        logger.warning("[ZillizCaseLaw] statute search unavailable: %s", e)
        return []
    try:
        hits = await search_statutes_hybrid(query, top_k=12)
    except Exception as e:
        logger.warning("[ZillizCaseLaw] statute search failed: %s", e)
        return []
    have = set(plan_statute_ids(plan)) | {str(p).upper() for p in (getattr(plan, "provisions", None) or [])}
    plan_acts = {m.group(1) for m in (_ACT_PREFIX_RE.match(c) for c in have) if m}
    domains = set(plan_domains(plan))
    preferred, others = [], []
    for h in hits:
        cid = str(h.get("canonical_id") or "").upper()
        if not cid or cid in have:
            continue
        act = str(h.get("act_code") or "").upper()
        dom = str(h.get("domain") or "").lower()
        act_match = bool(act) and any(a.startswith(act) or act.startswith(a) for a in plan_acts)
        if act_match or (dom and dom in domains):
            preferred.append(h)
        else:
            others.append(h)
    # Off-domain statutes only fill in when nothing on-domain came back.
    picked = preferred[:max_new] if preferred else others[:1]
    return picked


def statute_hit_to_verified(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a statutes_v3 hit like core.current_law_verifier output."""
    cid = str(hit.get("canonical_id") or "").upper()
    act_name = hit.get("act_name") or hit.get("act_code") or ""
    sec = hit.get("section") or ""
    unit = "Article" if "_ART_" in cid else "Section"
    display = f"{unit} {sec}, {act_name}".strip(", ") if sec else (act_name or cid)
    return {
        "canonical_id": cid,
        "act_code": hit.get("act_code") or "",
        "display_name": display,
        "status": "Active / In Force" if hit.get("in_force", True) else "Not in force",
        "title": hit.get("title") or display,
        "last_amended": "Official Pakistan Code",
        "text": (hit.get("text") or hit.get("raw_text") or "").strip(),
        "tier": hit.get("tier") or "ingested_unreviewed",
        "source_page": "",
        "content_hash": "",
        "amendment_notice": "",
        "has_amendment": False,
        "retrieved_by": "statutes_v3_semantic",
    }
