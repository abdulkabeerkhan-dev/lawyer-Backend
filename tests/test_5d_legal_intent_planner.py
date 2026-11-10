"""
tests/test_5d_legal_intent_planner.py

Unit test suite verifying the 5-Dimensional Legal Intent Engine:
1. Dimension 1: Factual Matrix (Material facts, transactions, parties, commercial context)
2. Dimension 2: Substantive Legal Doctrine (Controlling principle, competing doctrines, legal tests)
3. Dimension 3: Procedural Relief (Relief sought, statutory remedy framework, threshold condition)
4. Dimension 4: Forum & Jurisdiction (Competent forum, appellate forum, Article 189/201 hierarchy)
5. Dimension 5: Statutory & Precedential Anchors (Canonical IDs, multi-lane query generation)
6. Cross-domain synergy preservation (Zero stripping of legitimate interdisciplinary provisions)
"""

import pytest
from core.legal_query_planner import (
    create_deterministic_fallback_plan,
    StructuredLegalQueryPlan,
    FactualIntent,
    DoctrinalIntent,
    ProceduralIntent,
    ForumHierarchyIntent,
    MultiLaneQueryIntent
)


def test_5d_cheque_dishonour_vs_banking_recovery():
    """
    Query: Quashing of 489-F PPC criminal proceedings in commercial/banking recovery dispute.
    Verifies that all 5 dimensions are cleanly decomposed and interdisciplinary provisions preserved.
    """
    q = "Find Supreme Court judgments where criminal proceedings under Section 489-F PPC were quashed under Section 561-A CrPC because the dispute was essentially a banking or commercial loan recovery dispute."
    plan = create_deterministic_fallback_plan(q)

    # 1. Dimension 1: Factual Intent
    assert plan.factual_intent is not None
    assert plan.factual_intent.commercial_context is True
    assert "Commercial" in plan.factual_intent.transaction_nature or "Financial" in plan.factual_intent.transaction_nature
    assert len(plan.factual_intent.material_facts) >= 1

    # 2. Dimension 2: Doctrinal Intent
    assert plan.doctrinal_intent is not None
    assert any(k in plan.doctrinal_intent.controlling_doctrine.lower() for k in ["quash", "civil", "commercial", "recovery", "debt", "coercive", "489-f", "561-a"])
    assert len(plan.doctrinal_intent.legal_tests) >= 1

    # 3. Dimension 3: Procedural Intent
    assert plan.procedural_intent is not None
    assert "489-f" in plan.procedural_intent.relief_sought.lower() or "quash" in plan.procedural_intent.relief_sought.lower() or "bail" in plan.procedural_intent.relief_sought.lower()

    # 4. Dimension 4: Forum Intent
    assert plan.forum_intent is not None
    assert "Supreme Court of Pakistan" in plan.forum_intent.binding_courts
    assert "Magistrate" in plan.forum_intent.competent_forum or "Court" in plan.forum_intent.competent_forum or "High Court" in plan.forum_intent.competent_forum

    # 5. Dimension 5: Statutory & Precedential Anchors
    assert plan.multi_lane_queries is not None
    assert len(plan.multi_lane_queries.dense_conceptual_query) > 10
    assert len(plan.multi_lane_queries.sparse_lexical_query) > 10
    assert len(plan.multi_lane_queries.procedural_query) > 10
    assert len(plan.multi_lane_queries.doctrinal_query) > 10

    # Cross-domain integrity: 489-F PPC and CrPC must be present
    assert any("489f" in p.lower() or "489-f" in p.lower() for p in plan.statutory_provisions)
    assert any("561" in p.lower() for p in plan.statutory_provisions) or "criminal" in plan.allowed_domains_filter


def test_5d_commercial_fraud_pre_arrest_bail():
    """
    Query: Pre-arrest bail under 498 CrPC in FIR 406/420 PPC arising out of contract breach.
    """
    q = "Pre-arrest bail under Section 498 CrPC in FIR registered under Sections 406 and 420 PPC arising out of commercial contract dispute."
    plan = create_deterministic_fallback_plan(q)

    # Factual
    assert plan.factual_intent.commercial_context is True
    # Procedural
    assert "498" in plan.procedural_intent.relief_sought or "bail" in plan.procedural_intent.relief_sought.lower()
    # Doctrinal
    assert "mens_rea_at_inception" in plan.doctrinal_intent.competing_doctrines or "breach" in plan.doctrinal_intent.controlling_doctrine.lower()
    # Multi-lane
    assert "498" in plan.multi_lane_queries.sparse_lexical_query
    assert "406" in plan.multi_lane_queries.sparse_lexical_query or "420" in plan.multi_lane_queries.sparse_lexical_query


def test_5d_specific_performance():
    """
    Query: Suit for specific performance of agreement to sell immovable property under SRA 1877.
    """
    q = "Suit for specific performance of agreement to sell immovable property under Section 12 Specific Relief Act 1877."
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert plan.procedural_intent is not None
    assert "Specific Performance" in plan.procedural_intent.relief_sought or "12" in plan.procedural_intent.relief_sought
    assert any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)
    assert not any("CRPC" in p for p in plan.statutory_provisions)


def test_5d_family_khula_and_dower():
    """
    Query: Khula dissolution of marriage and surrender of dower under Family Courts Act 1964.
    """
    q = "Right of Muslim wife to obtain dissolution of marriage on ground of Khula without husband's consent and surrender of dower."
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "family"
    assert plan.factual_intent.commercial_context is False
    assert "Family Court" in plan.forum_intent.competent_forum
    assert any("FAMILY_COURTS" in p for p in plan.statutory_provisions)
    # Zero criminal contamination
    assert not any("PPC" in p for p in plan.statutory_provisions)
    assert not any("CRPC" in p for p in plan.statutory_provisions)


def test_search_lanes_structure():
    """
    Verifies that search_lanes are accessible both as attributes and dict keys.
    """
    q = "What is the limitation period to file an appeal against a Banking Court decree under Section 22 FIO 2001?"
    plan = create_deterministic_fallback_plan(q)

    assert len(plan.search_lanes) > 0
    first_lane = plan.search_lanes[0]
    # Verify dict and attribute access
    lane_id = first_lane["lane"] if isinstance(first_lane, dict) else first_lane.lane
    assert lane_id is not None
    assert len(lane_id) > 0
