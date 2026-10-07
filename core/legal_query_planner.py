"""
core/legal_query_planner.py

Production-grade Legal Query Understanding Engine for Pakistani Law.
Before any retrieval is executed, every user query is analyzed to extract:
- Legal domains (e.g. criminal law, corporate crime, bail)
- Statutory provisions (e.g. Section 409 PPC, Section 420 PPC, Section 498 CrPC)
- Legal questions / doctrines (e.g. civil dispute vs criminal breach of trust)
- Factual matrix elements (e.g. director loan, consultancy fee, transfer to wife)
- Jurisdiction & required court tiers (Supreme Court, High Courts)
- Specialized multi-lane search queries
"""

import re
import json
import asyncio
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from core.legal_guardrails import (
    decompose_compound_legal_query,
    extract_positive_query_anchors
)


class LegalQueryPlan(BaseModel):
    legal_domain: List[str] = Field(default_factory=list)
    provisions: List[str] = Field(default_factory=list)
    legal_questions: List[str] = Field(default_factory=list)
    factual_matrix: List[str] = Field(default_factory=list)
    jurisdiction: str = "Pakistan"
    required_authorities: List[str] = Field(default_factory=lambda: ["Supreme Court of Pakistan", "High Courts"])
    search_lanes: List[Dict[str, str]] = Field(default_factory=list)


PLANNER_SYSTEM_PROMPT = """You are a senior Pakistani legal research director and legal query planner.
Analyze the user's legal scenario and produce an actionable, structured legal research plan.

Identify:
1. legal_domain: Specific areas of Pakistani law (e.g. "criminal law", "corporate crime", "pre-arrest bail", "banking law", "civil procedure").
2. provisions: Exact canonical statutory provisions mentioned or directly engaged (e.g. "Section 409 PPC", "Section 420 PPC", "Section 498 CrPC", "Section 497 CrPC").
3. legal_questions: Precise substantive legal doctrines and issues to research (e.g. "civil dispute vs criminal breach of trust", "dishonest intention at inception vs subsequent contractual breach", "applicability of Section 409 PPC to company directors as agents", "grounds for pre-arrest bail under Section 498 CrPC where civil recovery is intended").
4. factual_matrix: Key material facts from the prompt (e.g. "Rs. 45 million fund transfer", "transfer to wife's account under consultancy fees", "undocumented director loan defense", "FIR lodged by company").
5. jurisdiction: "Pakistan"
6. required_authorities: Court hierarchy needed (e.g. ["Supreme Court of Pakistan", "High Courts"]).
7. search_lanes: 3 to 5 targeted, highly distinct search subqueries for vector and BM25 search engines. Each lane must focus on a single doctrinal issue.

Output ONLY valid JSON matching this schema:
{
  "legal_domain": ["..."],
  "provisions": ["..."],
  "legal_questions": ["..."],
  "factual_matrix": ["..."],
  "jurisdiction": "Pakistan",
  "required_authorities": ["Supreme Court of Pakistan", "High Courts"],
  "search_lanes": [
    {"lane": "offence_ingredients", "query": "..."},
    {"lane": "civil_vs_criminal", "query": "..."},
    {"lane": "bail_doctrine", "query": "..."},
    {"lane": "corporate_fiduciary", "query": "..."}
  ]
}
"""


def create_deterministic_fallback_plan(query: str) -> LegalQueryPlan:
    """
    Robust rule-based fallback if LLM planner fails or is unreachable.
    Leverages domain heuristics, anchor extraction, and query decomposition.
    """
    q_low = query.lower()
    anchors = extract_positive_query_anchors(query)
    decomposed = decompose_compound_legal_query(query)

    provisions = []
    # Identify standard provisions
    sec_matches = re.findall(r'(?:sections?|secs?\.?)\s*([0-9]+(?:-[a-z])?(?:\s*(?:and|&|,)\s*[0-9]+(?:-[a-z])?)*)\s*(ppc|crpc|cpc|qso)?', q_low)
    for m, statute in sec_matches:
        stat_suffix = statute.upper() if statute else ("PPC" if "409" in m or "420" in m or "406" in m else "CrPC")
        nums = re.findall(r'[0-9]+(?:-[a-z])?', m)
        for num in nums:
            provisions.append(f"Section {num} {stat_suffix}")

    # Fallback to extracted anchors
    for a in anchors:
        if a.startswith("section ") and a not in [p.lower() for p in provisions]:
            provisions.append(a.title())

    # Domains
    domains = []
    if any(k in q_low for k in ["fir", "bail", "ppc", "crpc", "offence", "accused", "arrest", "police"]):
        domains.append("criminal law")
    if any(k in q_low for k in ["director", "company", "shareholder", "board", "funds"]):
        domains.append("corporate crime")
    if any(k in q_low for k in ["pre-arrest bail", "bail", "498", "497"]):
        domains.append("pre-arrest bail")
    if not domains:
        domains.append("general law")

    # Legal questions
    questions = []
    if any(k in q_low for k in ["civil", "criminal", "breach of trust", "loan"]):
        questions.append("civil dispute vs criminal breach of trust (dishonest intention at inception)")
    if any(k in q_low for k in ["director", "409", "misappropriat"]):
        questions.append("applicability of Section 409 PPC to company director managing corporate funds")
    if any(k in q_low for k in ["bail", "498", "arrest"]):
        questions.append("grounds for pre-arrest bail under Section 498 CrPC (mala fide and ulterior motive)")

    lanes = []
    for i, dq in enumerate(decomposed):
        lane_name = f"lane_{i+1}"
        if "409" in dq or "breach of trust" in dq:
            lane_name = "offence_ingredients"
        elif "civil dispute" in dq or "dishonest intention" in dq:
            lane_name = "civil_vs_criminal"
        elif "498" in dq or "bail" in dq:
            lane_name = "bail_doctrine"
        elif "director" in dq or "company" in dq:
            lane_name = "corporate_fiduciary"
        lanes.append({"lane": lane_name, "query": dq})

    return LegalQueryPlan(
        legal_domain=domains,
        provisions=provisions,
        legal_questions=questions,
        factual_matrix=[query[:250]],
        jurisdiction="Pakistan",
        required_authorities=["Supreme Court of Pakistan", "High Courts"],
        search_lanes=lanes
    )


async def analyze_legal_query(query: str, ai_client_fn=None) -> LegalQueryPlan:
    """
    Analyzes user query and returns a structured LegalQueryPlan.
    Tries AI planner first; safely falls back to deterministic planner on any error or timeout.
    """
    if not query or len(query.strip()) < 10:
        return create_deterministic_fallback_plan(query)

    if ai_client_fn:
        try:
            user_msg = f"User Legal Query:\n\"\"\"{query}\"\"\""
            resp = await asyncio.wait_for(
                ai_client_fn(
                    system=PLANNER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                    temperature=0.0,
                    max_tokens=1500
                ),
                timeout=12.0
            )
            raw_text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
            m_json = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if m_json:
                data = json.loads(m_json.group(0))
                # Normalize provisions
                provisions = data.get("provisions", [])
                if not provisions:
                    fallback = create_deterministic_fallback_plan(query)
                    provisions = fallback.provisions

                search_lanes = data.get("search_lanes", [])
                if not search_lanes:
                    fallback = create_deterministic_fallback_plan(query)
                    search_lanes = fallback.search_lanes

                return LegalQueryPlan(
                    legal_domain=data.get("legal_domain", ["criminal law"]),
                    provisions=provisions,
                    legal_questions=data.get("legal_questions", []),
                    factual_matrix=data.get("factual_matrix", []),
                    jurisdiction=data.get("jurisdiction", "Pakistan"),
                    required_authorities=data.get("required_authorities", ["Supreme Court of Pakistan", "High Courts"]),
                    search_lanes=search_lanes
                )
        except Exception:
            # Fallback cleanly without stopping execution
            pass

    # Deterministic fallback
    return create_deterministic_fallback_plan(query)
