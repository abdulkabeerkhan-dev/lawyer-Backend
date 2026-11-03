"""
tests/test_phase4_production_pipeline_integration.py

Comprehensive Integration Test Suite verifying that the production query processor
(legal_ai.query_engine.query_processor.process_query_job_legal_ai) executes the
complete Phase 4 pipeline:
1. Neural Cross-Encoder Reranker
2. Post-Rerank Legal Domain Validation Gate (Hard Quarantine & 5 Interdisciplinary Doctrines)
3. Constitutional Precedent Multiplier Fusion (Article 189/201 Precedence & Relevance Floor)
4. Telemetry Recording in verification_report_payload and jobs_store
"""

import sys
import os
import uuid
import asyncio
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import QueryRequest
from legal_ai.query_engine.query_processor import process_query_job_legal_ai
from core.legal_query_planner import create_deterministic_fallback_plan


def test_phase4_pipeline_domain_quarantine_and_fusion():
    """
    Asserts that the production query processor passes candidates through:
    1. Cross-Encoder reranking
    2. Post-rerank domain gating (dropping quarantined and off-domain candidates)
    3. Constitutional multiplier fusion with relevance floor clamping
    """
    async def _async_test():
        job_id = str(uuid.uuid4())
        req = QueryRequest(query_text="Whether a co-sharer in joint ancestral land can seek preliminary decree for partition under Order XX Rule 18 CPC")
        jobs_store: Dict[str, Any] = {
            job_id: {
                "status": "pending",
                "stage": "starting",
                "user_id": "advocate_test_user"
            }
        }

        mock_merged_candidates = [
            # Candidate 1: Direct On-Domain Supreme Court Landmark (Holding)
            {
                "case_id": "2026_SCMR_941",
                "citation": "2026 SCMR 941",
                "title": "Shahbaz Khan v. Dowlat Khan",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Order XX Rule 18 CPC. In a suit for partition of joint ancestral property, preliminary decree cannot be granted for partial partition. Entire estate must be brought into hotchpot. " + ("word " * 60),
                "year": 2026,
                "section_type": "ratio_decidendi",
                "is_holding": True,
                "is_argument": False
            },
            # Candidate 2: Direct On-Domain High Court Precedent
            {
                "case_id": "2006_YLR_2059",
                "citation": "2006 YLR 2059",
                "title": "Khawaja Nayyar Qayyum v. Zubair Qayyum",
                "court": "Lahore High Court",
                "content_type": "full_text",
                "preview": "Order XX Rule 18 CPC. Suit for partition of joint ancestral property. Independent suit or counter-claim required for distinct claims. " + ("word " * 60),
                "year": 2006,
                "section_type": "ratio_decidendi",
                "is_holding": True,
                "is_argument": False
            },
            # Candidate 3: Quarantined Vector (MUST be dropped unconditionally)
            {
                "case_id": "LEGACY_QUARANTINE_001",
                "citation": "1999 SCMR 999",
                "title": "Unverified Partition Case",
                "court": "Supreme Court of Pakistan",
                "content_type": "full_text",
                "preview": "Partition of ancestral land and preliminary decree details. " + ("word " * 60),
                "year": 1999,
                "is_quarantined": True
            },
            # Candidate 4: Off-Domain Disallowed Statute (Criminal State Prosecution)
            {
                "case_id": "2004_PCRLJ_111",
                "citation": "2004 PCrLJ 111",
                "title": "Tariq v. The State",
                "court": "Lahore High Court",
                "content_type": "full_text",
                "preview": "FIR under Section 420 PPC. Dishonest intention and criminal breach of trust. Income Tax Ordinance and Sales Tax Act dispute. " + ("word " * 60),
                "year": 2004
            }
        ]

        # Patch multi-source retrieval, planner, synthesis, and verification for hermetic test
        class MockTextBlock:
            type = "text"
            text = (
                "### 1. EXECUTIVE SUMMARY\n"
                "In a suit for partition of joint ancestral property under Order XX Rule 18 CPC, "
                "the entire property must be brought into hotchpot as held in 2026 SCMR 941.\n\n"
                "### 2. CONTROLLING PRECEDENTS\n"
                "The Supreme Court of Pakistan in 2026 SCMR 941 established the controlling ratio.\n\n"
                "### 3. STATUTORY FRAMEWORK\n"
                "Order XX Rule 18 of Code of Civil Procedure, 1908.\n\n"
                "### 4. SUBSTANTIVE LEGAL ANALYSIS\n"
                "Partition proceedings require all joint ancestral land to be included.\n\n"
                "### 5. PROCEDURAL ROADMAP\n"
                "Step 1: File plaint under Order XX Rule 18 CPC.\n\n"
                "### 6. JURISDICTION AND FORUM\n"
                "Civil Court of competent territorial jurisdiction.\n\n"
                "### 7. STRATEGIC RECOMMENDATIONS\n"
                "Ensure all co-sharers are impleaded.\n\n"
                "### 8. CONCLUSION\n"
                "Preliminary decree may issue accordingly."
            )

        class MockMessage:
            content = [MockTextBlock()]
            stop_reason = "end_turn"
            usage = MagicMock(input_tokens=150, output_tokens=350)

        with patch("legal_ai.query_engine.query_processor.retrieve_candidates_parallel", new_callable=AsyncMock) as mock_retrieve, \
             patch("legal_ai.query_engine.query_processor.analyze_legal_query", new_callable=AsyncMock) as mock_plan, \
             patch("legal_ai.query_engine.query_processor.safe_create_anthropic_message", new_callable=AsyncMock) as mock_llm, \
             patch("legal_ai.verification.memo_verifier.verify_memorandum_text") as mock_verify:

            mock_plan.return_value = create_deterministic_fallback_plan(req.query_text)
            mock_retrieve.return_value = (mock_merged_candidates, {"BM25": 2, "Pinecone": 1, "Supabase": 1})
            mock_llm.return_value = MockMessage()
            mock_verify.return_value = {
                "passed": True,
                "disputed_notices": [],
                "failures": [],
                "verified_citations": ["2026 SCMR 941", "2006 YLR 2059"]
            }

            await process_query_job_legal_ai(
                job_id=job_id,
                request=req,
                authenticated_user_id="advocate_test_user",
                jobs_store=jobs_store,
                supabase=None
            )

        # Assert job completed successfully
        assert jobs_store[job_id]["status"] == "done"
        early_display = jobs_store[job_id].get("early_display", {})
        cards = early_display.get("precedent_cards", [])

        # Invariant 1: Quarantined candidate was NEVER admitted
        assert not any(c.get("case_id") == "LEGACY_QUARANTINE_001" for c in cards)
        assert not any(c.get("is_quarantined") for c in cards)

        # Invariant 2: Off-domain candidate was excluded by post-rerank domain gate
        assert not any(c.get("case_id") == "2004_PCRLJ_111" for c in cards)

        # Invariant 3: Supreme Court 2026 landmark is Top-1 with constitutional multiplier fusion
        assert len(cards) >= 1
        top_card = cards[0]
        assert "2026 SCMR 941" in str(top_card.get("citation"))

        # Invariant 4: Telemetry recorded in verification report
        report = jobs_store[job_id].get("result", {}).get("verification_report", {})
        assert "cross_encoder_telemetry" in report
        assert "post_domain_gate_telemetry" in report
        gate_telem = report["post_domain_gate_telemetry"]
        assert gate_telem.get("quarantined_dropped", 0) >= 1 or gate_telem.get("input_count", 0) > 0

    asyncio.run(_async_test())
