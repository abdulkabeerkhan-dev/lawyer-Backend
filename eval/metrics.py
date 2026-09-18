"""
Scoring functions for the retrieval eval.

rank_of_correct_chunk / recall / mean_reciprocal_rank / recall_confidence_interval
are carried over near-verbatim from Lawglance's eval/metrics.py (Apache 2.0) —
they're generic IR metrics, nothing Section-specific to change. What's added
here is refusal_accuracy, which Lawglance has no equivalent for: it scores
the "should this query find nothing" cases separately from the "should this
query find X" cases, since averaging them into one recall number would hide
whether the guardrail is actually holding.
"""

import math


def rank_of_correct_chunk(
    retrieved_citations: list[str], correct_citation: str
) -> int | None:
    """1-indexed position of correct_citation in retrieved_citations, or None if absent."""
    if correct_citation not in retrieved_citations:
        return None
    return retrieved_citations.index(correct_citation) + 1


def recall(ranks: list[int | None]) -> float:
    """Fraction of ranks that are not None. Only pass ranks from should_refuse=False items."""
    if not ranks:
        raise ValueError("ranks must not be empty")
    return sum(1 for r in ranks if r is not None) / len(ranks)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    """Average of 1/rank across ranks, treating None as 0."""
    if not ranks:
        raise ValueError("ranks must not be empty")
    return sum(1 / r if r is not None else 0 for r in ranks) / len(ranks)


def recall_confidence_interval(ranks: list[int | None]) -> tuple[float, float]:
    """95% Wilson score interval for recall — more reliable than the normal approximation at small n."""
    z = 1.96
    n = len(ranks)
    p_hat = recall(ranks)
    denominator = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denominator
    half_width = (z / denominator) * math.sqrt(
        p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)
    )
    return center - half_width, center + half_width


def refusal_accuracy(refusal_results: list[bool]) -> float:
    """Fraction of should_refuse=True items where retrieval correctly returned
    zero groundable candidates. Each entry is True if that item correctly
    refused, False if it wrongly surfaced candidates (the FALLBACK_FLOOR bug).

    Score this SEPARATELY from recall/MRR. A pipeline can have perfect recall
    on "find the case" queries and still be broken on "correctly find nothing"
    queries — that's exactly what happened when FALLBACK_FLOOR dropped to 0.50.
    """
    if not refusal_results:
        raise ValueError("refusal_results must not be empty")
    return sum(1 for r in refusal_results if r) / len(refusal_results)
