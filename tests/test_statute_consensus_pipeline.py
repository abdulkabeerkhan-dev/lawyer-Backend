"""
tests/test_statute_consensus_pipeline.py

Comprehensive test suite verifying the 5-Stage Dual Track & Consensus Retrieval Pipeline:
1. Stage 1: Dual Track Intent & Statute Router (Track A Conceptual, Track B Regex, Disambiguation Engine)
2. Stage 2: Parallel Multi-Container Fan Out (Container A, Container B, Container C)
3. Stage 3: Consensus Voting & Cross-Verification (>= 2 of 3 consensus gate, Web Tie-Breaker)
4. Stage 4: Grounded Synthesis Assembler (Verified vs Unverified/Gaps blocks)
5. Stage 5: Gate 1 Quote Check & Gate 2 Anti-Pattern Guardrail (Guardian Intervention)
"""

import pytest
import asyncio
from legal_ai.query_engine.statute_router import DualTrackStatuteRouter
from legal_ai.query_engine.consensus_engine import ConsensusVotingEngine
from legal_ai.verification.anti_pattern_guard import AntiPatternGuard
from legal_ai.verification.memo_verifier import MemoVerifier


def test_stage_1_dual_track_router_conceptual_factual():
    """
    Stage 1 Track A: Conceptual & factual phrases map to authoritative provisions.
    """
    router = DualTrackStatuteRouter()

    # Cheque dishonour
    res1 = router.route_query("Cheque bounced for lack of funds. What is the criminal and civil remedy?")
    assert "Section 489-F PPC" in res1["candidate_provisions"]
    assert "PPC_1860" in res1["governing_act_codes"]

    # Without warrant arrest & bail
    res2 = router.route_query("Accused arrested without warrant by police. Can he apply for bail?")
    assert any("496" in p or "497" in p for p in res2["candidate_provisions"])
    assert "CRPC_1898" in res2["governing_act_codes"]

    # Advance sale deed dispute
    res3 = router.route_query("Seller refused to execute the sale deed after taking advance money.")
    assert any("Specific Relief" in p and "12" in p for p in res3["candidate_provisions"])
    assert "SRA_1877" in res3["governing_act_codes"]


def test_stage_1_dual_track_router_disambiguation():
    """
    Stage 1 Engine: Disambiguates collisions (SRA 12 vs CPC 12(2), FIO 22 vs CPC 22).
    """
    router = DualTrackStatuteRouter()

    # Property sale deed dispute with mention of "Section 12" -> SRA 1877, NOT CPC 12
    res_sra = router.route_query("Buyer filed suit under Section 12 for property agreement to sell after seller refused.")
    sra_provs = [p for p in res_sra["candidate_provisions"] if "12" in p]
    assert any("Specific Relief" in p for p in sra_provs)
    assert not any("cpc" in p.lower() for p in sra_provs)

    # Fraudulent decree challenge under Section 12 -> CPC 12(2), NOT SRA 12
    res_cpc = router.route_query("Challenge to ex-parte decree obtained by fraud and misrepresentation under Section 12.")
    cpc_provs = [p for p in res_cpc["candidate_provisions"] if "12" in p]
    assert any("12(2)" in p for p in cpc_provs)
    assert not any("Specific Relief" in p for p in cpc_provs)


def test_stage_2_and_3_consensus_voting_engine():
    """
    Stage 2 & 3: Tri-container fan-out evaluates 2-of-3 consensus.
    """
    async def _run():
        engine = ConsensusVotingEngine()
        query = "Seller refused to execute the sale deed after taking advance money. What remedy does the buyer have?"
        
        res = await engine.execute_consensus_pipeline(query)
        consensus = res["consensus"]

        assert consensus["consensus_gate_passed"] is True
        assert len(res["verified_provisions"]) >= 1

        # Verify that Section 12 SRA passed with >= 2 votes
        sra_12_record = next((vc for vc in res["verified_provisions"] if "12" in vc.get("section_num", "") and vc.get("act_code") == "SRA_1877"), None)
        assert sra_12_record is not None, "SRA Section 12 must be consensus-verified"
        assert sra_12_record["votes"] >= 2
        assert sra_12_record["status"] == "VERIFIED_CLAIM"

    asyncio.run(_run())


def test_stage_4_grounded_synthesis_assembler():
    """
    Stage 4: Assembles structured prompt block separating verified gazette provisions from gaps.
    """
    engine = ConsensusVotingEngine()
    mock_consensus = {
        "verified_claims": [
            {
                "provision": "Section 12 Specific Relief Act, 1877",
                "title": "Cases in which specific performance enforceable",
                "text": "Except as otherwise provided in this Chapter, the specific performance of any contract may in the discretion of the Court be enforced...",
                "votes": 3
            }
        ],
        "disclosed_gaps": [
            "Statutory provision 'Section 999 Arbitrary Act' lacks independent two-source consensus."
        ]
    }

    block = engine.assemble_grounded_synthesis_block(mock_consensus)
    assert "=== VERIFIED STATUTORY PROVISIONS" in block
    assert "Section 12 Specific Relief Act, 1877" in block
    assert "=== UNVERIFIED / DISCLOSED GAPS ===" in block
    assert "Section 999 Arbitrary Act" in block


def test_stage_5_gate_2_anti_pattern_guardrail():
    """
    Stage 5 Gate 2: Neutralizes classic legal hallucinations and applies Guardian Intervention.
    """
    guard = AntiPatternGuard()

    hallucinated_text = (
        "The applicant seeks bail under Article 12 CrPC. Furthermore, Section 199 Constitution "
        "and Section 497 PPC apply. Also Section 138 NI Act can be invoked alongside Act 1882 for bail."
    )

    res = guard.check_text(hallucinated_text)
    assert res["is_clean"] is False
    assert len(res["violations"]) >= 4

    # Verify corrections
    sanitized = res["sanitized_text"]
    assert "Article 12 CrPC" not in sanitized
    assert "Section 12 of the Code of Criminal Procedure, 1898" in sanitized
    assert "Article 199 of the Constitution of Pakistan, 1973" in sanitized
    assert "Section 497 of the Code of Criminal Procedure, 1898" in sanitized
    assert "Section 489-F of the Pakistan Penal Code, 1860" in sanitized

    # Verify Guardian Notice
    notice = guard.format_guardian_notice(res["guardian_interventions"])
    assert "Guardian Intervention Notice" in notice
    assert "Article 12 CrPC" in notice
