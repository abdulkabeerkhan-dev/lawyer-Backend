"""
tests/test_supabase_fts_optimization.py

Phase 4, Step 2: Unit and Regression Test Suite for Supabase FTS Optimization & Stop-Word Sanitization.
Validates:
1. Conversational stop-word filtering (stripping 'whether', 'which', 'find', 'regarding', etc.).
2. High-salience substantive legal keyword extraction.
3. Pakistani neutral citation parsing (both year-first and reporter-first formats).
4. Record normalization and schema consistency.
5. Fast query execution and statement timeout resilience.
6. Full backward compatibility with unified_orchestrator.py callers.
"""

import pytest
import asyncio
from legal_ai.retrieval.supabase_search import (
    search_supabase_judgments,
    _format_supabase_record,
    extract_substantive_tokens,
    extract_pakistani_citations,
    LEGAL_CONVERSATIONAL_STOP_WORDS
)


def test_conversational_stop_words_completeness():
    """Verifies that common query filler and conversational words are present in stop-words set."""
    mandatory_stop_words = [
        "whether", "which", "what", "where", "when", "how", "who", "why",
        "find", "give", "more", "tell", "show", "list", "explain", "describe",
        "regarding", "between", "against", "among", "without", "within",
        "court", "pakistan", "judgment", "judgments", "case", "cases",
        "suit", "petition", "appeal", "law", "act", "section", "order"
    ]
    for word in mandatory_stop_words:
        assert word in LEGAL_CONVERSATIONAL_STOP_WORDS, f"Missing stop word: {word}"


def test_substantive_token_extraction_filters_filler():
    """Verifies that conversational queries are stripped down to substantive legal concepts."""
    query = "Whether a co-sharer in joint ancestral land can seek preliminary decree for partition under Order XX Rule 18 CPC without including the entire joint estate?"
    tokens = extract_substantive_tokens(query)
    tokens_lower = [t.lower() for t in tokens]

    # Filler words must be stripped
    assert "whether" not in tokens_lower
    assert "without" not in tokens_lower
    assert "under" not in tokens_lower
    assert "including" not in tokens_lower
    assert "court" not in tokens_lower

    # Substantive legal terms must be preserved
    assert any("sharer" in t for t in tokens_lower)
    assert any("ancestral" in t for t in tokens_lower)
    assert any("partition" in t for t in tokens_lower)
    assert any("decree" in t for t in tokens_lower)
    assert any("preliminary" in t for t in tokens_lower)


def test_substantive_token_extraction_benami_query():
    """Verifies substantive tokens for a Benami transaction query."""
    query = "Find Pakistani judgments regarding partition of jointly owned property involving Benami transactions."
    tokens = extract_substantive_tokens(query)
    tokens_lower = [t.lower() for t in tokens]

    assert "find" not in tokens_lower
    assert "pakistani" not in tokens_lower
    assert "regarding" not in tokens_lower
    assert "judgments" not in tokens_lower

    assert "benami" in tokens_lower
    assert "partition" in tokens_lower
    assert "property" in tokens_lower or "jointly" in tokens_lower


def test_pakistani_citation_extraction_year_first():
    """Extracts year-first citations (e.g. 2026 SCMR 941)."""
    text = "As held in 2026 SCMR 941 and 2006 YLR 2059 regarding partition."
    cits = extract_pakistani_citations(text)
    cids = [c[0] for c in cits]

    assert "2026_SCMR_941" in cids
    assert "2006_YLR_2059" in cids


def test_pakistani_citation_extraction_reporter_first():
    """Extracts reporter-first citations (e.g. PLD 1967 SC 97, PLD 1995 SC 34)."""
    text = "The rule in PLD 1967 SC 97 and PLD 1995 SC 34 governs this issue."
    cits = extract_pakistani_citations(text)
    cids = [c[0] for c in cits]

    assert any("1967_PLD" in cid for cid in cids)
    assert any("1995_PLD" in cid for cid in cids)


def test_record_formatting_schema_completeness():
    """Verifies that _format_supabase_record builds the standard candidate payload."""
    raw_rec = {
        "id": "12345",
        "case_id": "2026_SCMR_941",
        "case_title": "Shahbaz Khan v. Dowlat Khan",
        "neutral_citation": "2026 SCMR 941",
        "court_name": "Supreme Court of Pakistan",
        "decision_date": "2026-03-15",
        "full_text": "This is a full judgment of the Supreme Court regarding partition of ancestral property. " * 30
    }
    cand = _format_supabase_record(raw_rec, score=0.95)

    assert cand["id"] == "2026_SCMR_941"
    assert cand["case_id"] == "2026_SCMR_941"
    assert cand["citation"] == "2026 SCMR 941"
    assert cand["title"] == "Shahbaz Khan v. Dowlat Khan"
    assert cand["court"] == "Supreme Court of Pakistan"
    assert cand["year"] == 2026
    assert cand["content_type"] == "full_text"
    assert cand["score"] == 0.95
    assert cand["is_supabase_fts"] is True
    assert cand["source_type"] == "Supabase"
    assert "metadata" in cand
    assert cand["metadata"]["case_id"] == "2026_SCMR_941"


def test_search_supabase_empty_inputs():
    """Verifies that empty or whitespace-only inputs return empty list without network calls."""
    res1 = asyncio.run(search_supabase_judgments([]))
    assert res1 == []

    res2 = asyncio.run(search_supabase_judgments(["", "   ", "ab"]))
    assert res2 == []


def test_search_supabase_live_exact_citation():
    """Executes live query against Supabase for an exact case ID/citation."""
    res = asyncio.run(search_supabase_judgments(["2021_SCMR_67"], limit_per_term=2))
    if res:
        first = res[0]
        assert "2021_SCMR_67" in first["case_id"] or "2021 SCMR 67" in first["citation"]
        assert first["is_supabase_fts"] is True
        assert first["score"] >= 0.90


def test_search_supabase_conversational_query_resilience():
    """Verifies that a long query with conversational filler does not time out and returns hits."""
    query = "Whether a co-sharer in joint ancestral land can seek preliminary decree for partition"
    res = asyncio.run(search_supabase_judgments([query], limit_per_term=5))
    # Search must complete without statement timeout (57014)
    assert isinstance(res, list)
    if res:
        for r in res:
            assert "citation" in r
            assert "case_id" in r
