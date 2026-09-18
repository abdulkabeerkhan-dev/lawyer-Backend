"""
Golden QA set for Section's retrieval pipeline.

Adapted from Lawglance's eval/golden_set.py (Apache 2.0) pattern. Key change:
Lawglance matches on exact chunk_text because its retriever exposes no stable
chunk id. Section's Pinecone vectors DO have stable ids (citation, e.g.
"PLD 1967 SC 97"), and our chunking will keep changing as we tune it — so we
match on citation instead of raw text. Matching on citation survives
re-chunking; matching on exact text breaks every time chunk boundaries move.

Each item also carries `should_refuse`. This is the piece Lawglance doesn't
need (it's not a bail/no-bail legal-liability tool) but Section does: some
queries in the golden set are deliberately "no real precedent exists" cases
(e.g. Section 9 CPC commercial eviction). For those, expected_citation is
null and a PASS means retrieval returns nothing groundable / the system
refuses — not that it found a matching case. Mixing "should find X" and
"should find nothing" in one set is what catches regressions like the
FALLBACK_FLOOR change silently breaking refusal behavior.
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, model_validator


class GoldenQAItem(BaseModel):
    """One row of the golden set.

    question: the exact query text to run through the pipeline.
    expected_citation: the citation (matches Pinecone metadata['citation'])
        that MUST appear in the retrieved candidates for this to pass.
        Leave as None only when should_refuse is True.
    should_refuse: True for queries where no real precedent should be
        retrieved and the system should ground nothing / refuse rather
        than answer from general knowledge. False (default) for normal
        "find the right case" queries.
    notes: free text — why this case is in the set, what it's guarding
        against. Not used for scoring, just so future-you (or a teammate)
        knows why a row exists six months from now.
    """

    question: str
    expected_citation: Optional[str] = None
    should_refuse: bool = False
    notes: str = ""

    @model_validator(mode="after")
    def _check_consistency(self):
        if self.should_refuse and self.expected_citation:
            raise ValueError(
                f"Item {self.question!r} has should_refuse=True but also an "
                "expected_citation — a refuse-case can't also require a match."
            )
        if not self.should_refuse and not self.expected_citation:
            raise ValueError(
                f"Item {self.question!r} has no expected_citation and "
                "should_refuse=False — nothing to score against."
            )
        return self


def load_golden_qa_set(path: Path) -> list[GoldenQAItem]:
    """Load and validate the golden QA set from a JSON file."""
    raw_items = json.loads(path.read_text())
    return [GoldenQAItem.model_validate(raw_item) for raw_item in raw_items]


def save_golden_qa_set(items: list[GoldenQAItem], path: Path) -> None:
    """Write the golden QA set back to disk (e.g. after adding new rows)."""
    path.write_text(json.dumps([item.model_dump() for item in items], indent=2))
