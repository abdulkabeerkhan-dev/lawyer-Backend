"""
legal_ai/retrieval/turso_fts_index.py

Keyword (BM25) search over the full Turso corpus via the SQLite FTS5 index
`case_texts_fts` (141k cases), exposed with the same interface as
`hybrid_search.BM25Index` so existing callers work unchanged:

    index.search(query, top_k) -> List[(doc_id, score, metadata)]
    index.corpus_size          -> int (> 0 when usable)

Why: the in-memory `bm25_index.pkl` covers only 9,749 cases (~7% of the corpus,
no PCRLJ at all), and is disabled entirely on low-memory hosts. Hybrid fusion was
therefore biased toward that small slice.

Falls back to the in-memory index (if provided) when Turso is unavailable or
returns nothing.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Generic English stop words + conversational filler common in lawyer questions.
# Legal terms (bail, murder, cheque, partition, ...) are deliberately NOT here.
_STOP = frozenset("""
a an the and or but in on at to for of with by from is was were be been being have has had do does did
will would could should may might shall can this that these those there here where when how what which who
whom whose not no nor so if then than too very just also about above after before between into through
during each some such only own same other its his her their our my your am are it he she they we you i me
him them us any all more most there's what's whether please help tell explain find give list show want need
client clients yesterday today tomorrow recently someone person people man woman case cases matter issue
issues question regarding related relevant pakistan pakistani law laws legal under against filed file
""".split())

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-/.][A-Za-z0-9]+)*")
_PARTS_RE = re.compile(r"[A-Za-z0-9]+")
_COURT_IN_TITLE = re.compile(r"\b([A-Z]+(?:-[A-Z]+)*-(?:HIGH-COURT|SUPREME-COURT|SHARIAT-COURT)(?:-[A-Z]+)*|SUPREME-COURT)\b")
_GENERIC_COURTS = {"", "high court / appellate tribunal", "unknown"}

MAX_TERMS = 14

# Terms present in more than this share of documents add cost but little ranking
# signal (e.g. "section" 33%, "procedure" 45%, portal boilerplate ~95%).
CORPUS_DOCS = 141_481
MAX_DOC_FRACTION = 0.25

# Column weights for bm25(): case_id, neutral_citation, case_title, headnote,
# holding, statutory_provisions, full_text
_BM25_WEIGHTS = "0.0, 8.0, 2.0, 3.0, 3.0, 3.0, 1.0"

# Rank inside FTS5 first (uses its ORDER BY rank fast path), then join only the
# top rows. Joining before ranking took 11-17 s on Turso; this form takes ~1 s.
_SQL = f"""
SELECT c.case_id, c.neutral_citation, c.case_title, c.court_name, c.year, c.journal,
       c.content_level, substr(c.full_text, 1, 2500) AS text, t.rank AS rank
FROM (
    SELECT rowid, rank FROM case_texts_fts
    WHERE case_texts_fts MATCH ? AND rank MATCH 'bm25({_BM25_WEIGHTS})'
    ORDER BY rank LIMIT ?
) t
JOIN case_texts c ON c.rowid = t.rowid
ORDER BY t.rank
"""

_DOC_FREQ: Optional[Dict[str, int]] = None


def _doc_freq() -> Dict[str, int]:
    """Document frequencies of high-frequency terms (data/fts_term_doc_freq.json)."""
    global _DOC_FREQ
    if _DOC_FREQ is None:
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fts_term_doc_freq.json")
        try:
            with open(path, encoding="utf-8") as f:
                _DOC_FREQ = {k: int(v) for k, v in json.load(f).items()}
        except Exception as err:
            logger.warning(f"[TursoFTS] term frequency file unavailable: {err}")
            _DOC_FREQ = {}
    return _DOC_FREQ


def build_fts_query(text: str, max_terms: int = MAX_TERMS) -> str:
    """
    Turn a natural-language question into an FTS5 OR-query.

    The previous implementation ANDed every word of the question, so a long
    question ("my client was arrested yesterday under section 302...") matched
    almost nothing. Here: drop stop/filler words and near-universal terms, keep
    legal tokens, turn section references like "489-F" or "s.497" into
    adjacent-token phrases, and OR the terms so BM25 ranks documents matching
    more of them higher.
    """
    if not text:
        return ""
    df = _doc_freq()
    max_df = int(CORPUS_DOCS * MAX_DOC_FRACTION)
    terms: List[str] = []
    seen = set()
    for tok in _TOKEN_RE.findall(text):
        low = tok.lower()
        if low in _STOP:
            continue
        parts = _PARTS_RE.findall(low)
        if not parts:
            continue
        if len(parts) == 1:
            p = parts[0]
            if len(p) < 2 and not p.isdigit():
                continue
            if df.get(p, 0) > max_df:
                continue
            term = f'"{p}"'
        else:
            term = '"' + " ".join(parts) + '"'
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return " OR ".join(terms)


def _derive_court(row: Dict[str, Any]) -> str:
    court = str(row.get("court_name") or "").strip()
    if court.lower() not in _GENERIC_COURTS:
        return court
    m = _COURT_IN_TITLE.search(str(row.get("case_title") or ""))
    if m:
        return m.group(1).replace("-", " ").title()
    if str(row.get("journal") or "").upper() == "SCMR":
        return "Supreme Court of Pakistan"
    return court or "Unknown"


def _derive_year(row: Dict[str, Any]) -> Optional[int]:
    try:
        y = int(row.get("year") or 0)
    except (TypeError, ValueError):
        y = 0
    if 1900 <= y <= 2100:
        return y
    m = re.search(r"\b(19\d{2}|20\d{2})\b", str(row.get("neutral_citation") or ""))
    return int(m.group(1)) if m else None


def _clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    return _COURT_IN_TITLE.sub("", t).strip(" -\t")


def keyword_backend() -> str:
    import os
    return os.environ.get("KEYWORD_SEARCH_BACKEND", "turso_fts").strip().lower()


def wrap_keyword_index(in_memory_index: Any) -> Any:
    """
    Returns the keyword index production should use. Default: Turso FTS over the
    full corpus, with the in-memory pickle (if loaded) as fallback.
    Set KEYWORD_SEARCH_BACKEND=pickle to restore the old behaviour.
    """
    if keyword_backend() == "pickle":
        return in_memory_index
    if isinstance(in_memory_index, TursoFTSIndex):
        return in_memory_index
    return TursoFTSIndex(fallback=in_memory_index)


class TursoFTSIndex:
    """BM25Index-compatible keyword search over Turso FTS5."""

    def __init__(self, fallback: Any = None, timeout: int = 6, corpus_size_hint: int = 141_481):
        self.fallback = fallback
        self.timeout = timeout
        self._corpus_size_hint = corpus_size_hint
        self.last_backend: str = "none"
        self.last_latency_ms: float = 0.0

    @property
    def corpus_size(self) -> int:
        # Callers guard on corpus_size > 0. Turso availability is checked per query.
        return self._corpus_size_hint

    @property
    def doc_metadata(self) -> List[Dict[str, Any]]:
        # memo_verifier builds a known-citation set from this; keep the fallback's.
        return list(getattr(self.fallback, "doc_metadata", None) or [])

    def search(self, query: str, top_k: int = 40) -> List[Tuple[str, float, Dict[str, Any]]]:
        fts_query = build_fts_query(query)
        results: List[Tuple[str, float, Dict[str, Any]]] = []
        if fts_query:
            results = self._search_turso(fts_query, top_k)
        if results:
            self.last_backend = "turso_fts"
            return results
        if self.fallback is not None and getattr(self.fallback, "corpus_size", 0) > 0:
            self.last_backend = "in_memory_bm25_fallback"
            try:
                return self.fallback.search(query, top_k=top_k)
            except Exception as err:  # pragma: no cover - defensive
                logger.warning(f"[TursoFTS] fallback BM25 failed: {err}")
        self.last_backend = "none"
        return []

    def _search_turso(self, fts_query: str, top_k: int) -> List[Tuple[str, float, Dict[str, Any]]]:
        try:
            from core.turso_client import execute_turso_pipeline
            from core.hierarchical_legal_chunker import HierarchicalLegalChunker
        except Exception as err:  # pragma: no cover
            logger.warning(f"[TursoFTS] import error: {err}")
            return []
        t0 = time.time()
        res = execute_turso_pipeline(
            [{"sql": _SQL, "args": [{"type": "text", "value": fts_query},
                                    {"type": "integer", "value": int(top_k)}]}],
            timeout=self.timeout, max_retries=1,
        )
        self.last_latency_ms = (time.time() - t0) * 1000
        if not res or "rows" not in res[0]:
            if res and res[0].get("error"):
                logger.warning(f"[TursoFTS] query error: {res[0].get('error')} (q={fts_query[:120]})")
            return []
        out: List[Tuple[str, float, Dict[str, Any]]] = []
        for row in res[0]["rows"]:
            case_id = str(row.get("case_id") or "")
            if not case_id:
                continue
            score = -float(row.get("rank") or 0.0)  # SQLite bm25(): lower is better
            text = HierarchicalLegalChunker.clean_portal_debris(row.get("text") or "")
            title = _clean_title(row.get("case_title"))
            citation = str(row.get("neutral_citation") or case_id.replace("_", " "))
            meta = {
                "case_id": case_id,
                "citation": citation,
                "neutral_citation": citation,
                "title": title,
                "case_title": title,
                "court": _derive_court(row),
                "year": _derive_year(row),
                "journal": row.get("journal"),
                "text": text,
                "content_type": "full_text",
                "content_level": row.get("content_level"),
                "chunk_index": 0,
                "retrieval_backend": "turso_fts",
            }
            out.append((case_id, score, meta))
        return out
