"""
tests/test_e2e_real_queries.py

End-to-end test suite running real, unmocked queries through the production pipeline:
1. Unseen Query 1: PPC Section 406 (criminal breach of trust vs commercial dispute & pre-arrest bail)
2. Unseen Query 2: Specific Relief Act 1877 (specific performance of contract, readiness & willingness)
3. Unseen Query 3: Limitation on a Promissory Note (Limitation Act 1908 Art. 73/80 & NI Act 1881)

Contains strict legal content assertions:
- PPC 406 penalty matches injected bare-act text (seven years, no mandatory fine).
- Limitation memo names an article only if injected (Article 73/80, strictly NO Article 181).
- No quotation marks around statute text unless matching injected text.
- Every 'Court held' sentence traceable to retrieved headnotes.
"""

import sys
import os
import re
import uuid
import asyncio
from typing import List, Dict, Any
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import QueryRequest
from legal_ai.query_engine.query_processor import process_query_job_legal_ai
from legal_ai.statutes.statute_injector import inject_statutory_framework
from core.legal_query_planner import create_deterministic_fallback_plan


def check_statute_quotes_grounded(memo: str, injected_statutes: str) -> None:
    """
    Asserts that any double-quoted string containing statutory phrasing
    matches the injected bare-act text verbatim.
    """
    quotes = re.findall(r'"([^"\n]{15,})"', memo)
    stat_markers = [
        "punished", "imprisonment", "fine", "commits criminal breach",
        "period of limitation", "time from which", "payable on demand",
        "contract", "specific performance", "injunction", "suit for",
        "valuable security", "dishonestly", "readiness", "willingness"
    ]
    inj_norm = " ".join(injected_statutes.lower().split())
    for q in quotes:
        q_low = q.lower()
        if any(m in q_low for m in stat_markers):
            q_norm = " ".join(q_low.split())
            assert q_norm in inj_norm, (
                f"Statutory quote '{q}' is not grounded in injected bare-act text."
            )


def check_court_held_traceable_to_precedents(memo: str, precedent_cards: List[Dict[str, Any]]) -> None:
    """
    Asserts that every 'Court held' sentence is traceable to the retrieved
    judgment text / headnotes in precedent_cards.
    """
    held_matches = re.finditer(
        r'(?:[\*\-]?\s*\*{0,2}(?:The\s+)?Court\s+held\*{0,2}\s*:\s*)([^\n]+)',
        memo,
        re.IGNORECASE
    )
    combined_retrieved = " ".join([
        f"{c.get('holding', '')} {c.get('preview', '')} {c.get('ratio_decidendi', '')} {c.get('important_paragraphs', '')} {c.get('full_text', '')}"
        for c in precedent_cards
    ]).lower()

    for m in held_matches:
        held_stmt = m.group(1).strip()
        stop_words = {"court", "supreme", "bench", "matter", "section", "article", "holding", "order", "pakistan", "petitioner", "respondent"}
        words = [
            w.lower() for w in re.findall(r'[a-zA-Z0-9_\-]+', held_stmt)
            if len(w) >= 5 and w.lower() not in stop_words
        ]
        if len(words) >= 3:
            overlap = sum(1 for w in words if w in combined_retrieved)
            assert overlap / len(words) >= 0.35, (
                f"Holding statement '{held_stmt[:60]}' has insufficient grounding in retrieved precedents."
            )


async def _run_live_pipeline_query(query_text: str) -> dict:
    job_id = str(uuid.uuid4())
    req = QueryRequest(query_text=query_text)
    jobs_store = {
        job_id: {
            "status": "pending",
            "stage": "starting",
            "user_id": "test_e2e_live_user"
        }
    }
    await process_query_job_legal_ai(job_id, req, "test_e2e_live_user", jobs_store, supabase=None)
    job_entry = jobs_store.get(job_id, {})
    status = job_entry.get("status")
    result = job_entry.get("result", {})
    return {
        "job_id": job_id,
        "status": status,
        "result": result,
        "memo": result.get("answer") or result.get("model_answer") or "",
        "citations": result.get("citations", []),
        "precedent_cards": result.get("precedent_cards", [])
    }


def test_e2e_unseen_query_1_ppc_406_breach_of_trust():
    query = (
        "What are the essential ingredients of criminal breach of trust under Section 406 PPC, "
        "whether a commercial transaction or loan default constitutes an offence under Section 406 PPC, "
        "and what are the governing superior court principles for grant of pre-arrest bail under Section 498 CrPC?"
    )
    res = asyncio.run(_run_live_pipeline_query(query))
    assert res["status"] == "done"
    memo = res["memo"]
    assert len(memo) > 1000

    # 1. Statutory engagement & penalty matching injected bare-act text
    assert "406" in memo
    assert "498" in memo or "bail" in memo.lower()
    # PPC 406 bare act penalty is up to seven years (amended by Ord. XXXIII of 1981, s. 2)
    assert any(k in memo.lower() for k in ["seven years", "7 years"])
    # Fine is not mandatory in bare act ("or with fine, or with both")
    assert "mandatory fine" not in memo.lower()
    # Bare act text was injected; no false unavailability warning
    assert "statutory text unavailable" not in memo.lower()

    # 2. Schedule II & Section 497 non-prohibitory clause status
    # Section 406 and 420 must not be called bailable as of right under Section 496
    assert not re.search(r'\b(?:420|406)\b[^.\n]{0,50}\bbailable as of right\b', memo, re.IGNORECASE)
    assert not re.search(r'\b(?:420|406)\b[^.\n]{0,50}\bgoverned by section 496\b', memo, re.IGNORECASE)

    # 3. Commercial dispute distinction
    assert any(k in memo.lower() for k in ["commercial", "civil dispute", "entrustment", "dishonest"])

    # 4. Statute quotation verification against injector
    plan = create_deterministic_fallback_plan(query)
    inj = inject_statutory_framework(plan, query)
    check_statute_quotes_grounded(memo, inj["statute_block"])

    # 5. Holding attribution strictly grounded in retrieved precedent cards
    check_court_held_traceable_to_precedents(memo, res["precedent_cards"])

    # 6. Zero artificial certifications or word counts
    assert "Counsel's Certification" not in memo
    assert "Word Count:" not in memo


def test_e2e_unseen_query_2_specific_relief_act_specific_performance():
    query = (
        "What are the essential conditions for obtaining a decree for specific performance "
        "of a contract for sale of immovable property under the Specific Relief Act, 1877, "
        "and what is the doctrine of readiness and willingness to perform in Pakistan?"
    )
    res = asyncio.run(_run_live_pipeline_query(query))
    assert res["status"] == "done"
    memo = res["memo"]
    assert len(memo) > 1000

    # 1. Statutory provisions engaged
    assert any(k in memo.lower() for k in ["section 12", "s. 12", "s.12"])
    assert any(k in memo.lower() for k in ["section 22", "s. 22", "s.22"])
    assert any(k in memo.lower() for k in ["section 24", "s. 24", "s.24"])
    # Must engage limitation period under Article 113 of Limitation Act 1908
    assert any(k in memo.lower() for k in ["article 113", "art. 113", "art 113", "three years", "3 years"])

    # 2. Readiness and willingness doctrine
    assert any(k in memo.lower() for k in ["readiness", "willingness"])

    # 3. Quotation and holding grounding
    plan = create_deterministic_fallback_plan(query)
    inj = inject_statutory_framework(plan, query)
    check_statute_quotes_grounded(memo, inj["statute_block"])
    check_court_held_traceable_to_precedents(memo, res["precedent_cards"])

    # 4. Zero artificial certifications
    assert "Counsel's Certification" not in memo
    assert "Word Count:" not in memo


def test_e2e_unseen_query_3_limitation_promissory_note():
    query = (
        "What is the limitation period for instituting a suit for recovery of money "
        "based on a promissory note under the Limitation Act, 1908 and the Negotiable Instruments Act, 1881 in Pakistan?"
    )
    res = asyncio.run(_run_live_pipeline_query(query))
    assert res["status"] == "done"
    memo = res["memo"]
    assert len(memo) > 1000

    # 1. Limitation article names: must name Article 73, Article 80, or Article 64A
    assert any(k in memo.lower() for k in ["article 73", "art. 73", "art 73", "article 80", "art. 80", "art 80", "article 64a", "art. 64a"])
    # Must state 3 years
    assert any(k in memo.lower() for k in ["three years", "3 years"])

    # 2. Strict negative boundary: MUST NOT cite Article 181 for promissory note suit
    assert "article 181" not in memo.lower()
    assert "art. 181" not in memo.lower()
    assert "art 181" not in memo.lower()

    # 3. Zero foreign Indian Section 138 NI Act criminal leakage
    assert "twice the amount of the cheque" not in memo
    assert "30 days" not in memo or "30-day notice" not in memo.lower()

    # 4. Quotation and holding grounding
    plan = create_deterministic_fallback_plan(query)
    inj = inject_statutory_framework(plan, query)
    check_statute_quotes_grounded(memo, inj["statute_block"])
    check_court_held_traceable_to_precedents(memo, res["precedent_cards"])

    # 5. Zero artificial certifications
    assert "Counsel's Certification" not in memo
    assert "Word Count:" not in memo


if __name__ == "__main__":
    queries = [
        ("Query 1 (PPC s.406 Criminal Breach of Trust)",
         "What are the essential ingredients of criminal breach of trust under Section 406 PPC, whether a commercial transaction default constitutes criminal breach of trust, and what are the principles for pre-arrest bail under Section 498 CrPC?"),
        ("Query 2 (Specific Relief Act Specific Performance)",
         "What are the essential conditions for obtaining a decree for specific performance of a contract for sale of immovable property under the Specific Relief Act, 1877, and what is the doctrine of readiness and willingness to perform in Pakistan?"),
        ("Query 3 (Limitation on Promissory Note)",
         "What is the limitation period for instituting a suit for recovery of money based on a promissory note under the Limitation Act, 1908 and the Negotiable Instruments Act, 1881 in Pakistan?")
    ]
    for label, q in queries:
        print(f"\n{'='*70}\n[RUNNING REAL QUERY] {label}\nQuery: {q}\n{'='*70}")
        out = asyncio.run(_run_live_pipeline_query(q))
        print(f"Status: {out['status']}")
        print(f"Precedents Found: {len(out['precedent_cards'])}")
        print(f"\n--- ACTUAL MEMORANDUM OUTPUT ({len(out['memo'])} chars) ---\n")
        print(out["memo"])
        print(f"\n{'='*70}\n")
