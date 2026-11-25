"""Fixes from the Nov 25 2026 system audit."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.parametrize("raw,expected", [
    ("criminal", "criminal"),
    ("Family Law", "family"),
    ("tax", "tax_corporate"),
    ("banking", "banking_commercial"),
    ("service matters", "service"),
    ("unknown", None),
    (None, None),
])
def test_planner_domain_maps_to_stored_label(raw, expected):
    from legal_ai.retrieval.supabase_search import _corpus_domain
    assert _corpus_domain(raw) == expected


def test_search_queries_exclude_blocked_rows():
    """Every full-text / title search over full_judgments filters out rejected, quarantined
    and restricted rows (10,674 headnote fragments and 291 mismatched texts live there)."""
    flt = 'retrieval_status.not.in.(rejected,quarantined,restricted)'
    for path, n in [("main.py", 4), ("legal_ai/retrieval/supabase_search.py", 2),
                    ("legal_ai/search/judgment_search_service.py", 1)]:
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        assert src.count(flt) >= n, path
    main = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    for m in re.finditer(r"\.text_search\('(?:fts_headnote|case_title)'", main):
        window = main[max(0, m.start() - 300):m.start()]
        assert flt in window


def test_unverified_quote_stripper_matches_curly_quotes():
    main = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    pats = re.findall(r"re\.sub\(r'(\^\\s\*>\\s\*\[[^']+)'", main)
    assert len(pats) == 2
    for p in pats:
        assert re.search(p, "> “The court held X”", re.M)
        assert re.search(p, '> "plain quote"', re.M)
        assert not re.search(p, "> not a quote", re.M)


def test_limitation_articles_have_period_text():
    """Article 113 lost its period and start date in the staging file that feeds Zilliz."""
    rows = json.load(open(os.path.join(ROOT, "data/statutes_v3_staging/LIMITATION_1908.json"), encoding="utf-8"))
    by_id = {r["canonical_id"]: r for r in rows}
    art = by_id.get("LIMITATION_1908_ART_113")
    if art is None:  # article lives in the legacy file
        rows = json.load(open(os.path.join(ROOT, "data/statutes_v3_staging/statutes_v2_legacy.json"), encoding="utf-8"))
        art = {r["canonical_id"]: r for r in rows}["LIMITATION_1908_ART_113"]
    assert "Three years" in art["text"]
    assert "notice that performance is refused" in art["text"]
