"""
tests/test_bug4_irrelevant_case_filter.py
Verification test for Bug 4: Irrelevant case (2017 SCMR 287 - Dr. Faisal Masud vs LDA plot allotment)
filtered out from company law queries by cross-encoder reranker and domain gates.
"""

from legal_ai.ranking.cross_encoder_reranker import _heuristic_legal_cross_score
from core.authority_ranking import is_irrelevant_subject, rank_and_filter_authorities
from core.legal_query_planner import create_deterministic_fallback_plan
from core.post_rerank_domain_gate import partition_candidates_into_ranking_buckets, assemble_generation_context


def test_2017_scmr_287_blocked_from_corporate_query():
    query = (
        "Minority shareholder alleging oppression and mismanagement by majority directors under "
        "Section 286 Companies Act 2017 for siphoning corporate assets and illegal share allotment."
    )
    plan = create_deterministic_fallback_plan(query)
    assert plan.primary_domain == "corporate"

    cand_irrelevant = {
        "citation": "2017 SCMR 287",
        "title": "Dr. Faisal Masud v. Lahore Development Authority",
        "court": "Supreme Court of Pakistan",
        "year": 2017,
        "legal_domain": "civil",
        "domain": "general_legal",
        "score": 0.40,
        "rerank_score": 0.40,
        "semantic_relevance_score": 0.40,
        "text": (
            "Lahore Development Authority Act 1975 -- Plot allotment -- Cancellation of allotment "
            "of residential plot by LDA -- Exemption policy -- Bona fide purchaser -- Rights of allottee "
            "in respect of civic property and plots allotted by development authority. Code of Civil Procedure 1908 Section 9."
        )
    }

    cand_legitimate_corporate = {
        "citation": "2021 CLD 500",
        "title": "Tariq Mehmood v. ABC Textile Mills Ltd.",
        "court": "Lahore High Court",
        "year": 2021,
        "legal_domain": "corporate",
        "domain": "corporate",
        "score": 0.85,
        "rerank_score": 0.85,
        "semantic_relevance_score": 0.85,
        "text": (
            "Companies Act 2017 Section 286 -- Oppression and mismanagement -- Siphoning of company assets "
            "by majority directors to private sister concern -- Petition by minority shareholder holding 15% shares -- "
            "Maintainability of petition before Company Bench -- Powers of Court under Section 287."
        )
    }

    # 1. Test Heuristic Cross-Encoder Reranker Score
    score_irrelevant = _heuristic_legal_cross_score(query, cand_irrelevant, plan)
    score_legit = _heuristic_legal_cross_score(query, cand_legitimate_corporate, plan)

    assert score_irrelevant <= 0.05, f"Irrelevant case score should be <= 0.05, got {score_irrelevant}"
    assert score_legit >= 0.50, f"Legitimate corporate case score should be >= 0.50, got {score_legit}"

    # 2. Test is_irrelevant_subject in authority ranking
    assert is_irrelevant_subject(cand_irrelevant, plan) is True, "is_irrelevant_subject should return True for 2017 SCMR 287"
    assert is_irrelevant_subject(cand_legitimate_corporate, plan) is False, "is_irrelevant_subject should return False for legitimate corporate case"

    # 3. Test post-rerank domain gate partitioning
    partitioned, telem = partition_candidates_into_ranking_buckets(
        [cand_irrelevant, cand_legitimate_corporate],
        plan,
        strict_mode=True
    )

    assert cand_irrelevant.get("ranking_bucket") == 3, f"Expected bucket 3 for irrelevant case, got {cand_irrelevant.get('ranking_bucket')}"
    assert cand_irrelevant.get("validation_status") == "DEMOTED_OFF_DOMAIN"
    assert cand_legitimate_corporate.get("ranking_bucket") == 1
    assert cand_legitimate_corporate.get("validation_status") == "APPROVED_ON_DOMAIN"

    # 4. Test assemble_generation_context
    context_text, included, telem_ctx, audit = assemble_generation_context(
        [cand_irrelevant, cand_legitimate_corporate],
        plan,
        strict_mode=True
    )

    included_citations = [c.get("citation") for c in included]
    assert "2017 SCMR 287" not in included_citations, "2017 SCMR 287 must NEVER appear in included generation context"
    assert "2021 CLD 500" in included_citations, "Legitimate corporate case must be included in generation context"


if __name__ == "__main__":
    test_2017_scmr_287_blocked_from_corporate_query()
    print("Test passed successfully!")
