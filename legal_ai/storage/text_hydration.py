"""
Fill judgment text into Supabase `full_judgments` rows from outside Supabase.

Supabase free tier caps the database at 500 MB, so `full_text`, `headnote` and
`ratio_decidendi` are moved, verbatim, to Cloudflare R2 (legal_ai.storage.r2_text_store)
and nulled in Supabase. Callers keep reading `full_judgments` exactly as before:
the Supabase client is wrapped (see `wrap_supabase_client`) so any row that comes
back with one of those fields empty gets it filled, by row id, from R2.

Optional fallback (ZILLIZ_FULLTEXT_FALLBACK=true): rebuild text from Zilliz
`judgments_v1` chunks. Off by default because chunks are not a verbatim copy.

Rows whose text still lives in Supabase (new uploads) are returned untouched.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

TEXT_FIELDS = ("full_text", "headnote", "ratio_decidendi")
HYDRATED_TABLES = {"full_judgments", "citation_crosswalk"}
# Database functions that return full_judgments rows (with `id`) and text columns.
HYDRATED_RPCS = {"search_judgments_structured"}

# Reading order used to stitch a judgment back together from its sections.
SECTION_ORDER = ["preamble", "headnote", "facts", "issues", "arguments", "analysis",
                 "holding", "ratio", "order"]
_RATIO_SECTIONS = ("holding", "ratio")
_RATIO_MAX_CHARS = 1500  # Supabase stored ratio_decidendi as a capped snippet.

_HEADER_RE = re.compile(r"^\[[^\]\n]{0,600}\]\s*\n+")
_JOURNALS = ["PLC(CS)", "PLD", "SCMR", "CLC", "YLR", "MLD", "PCRLJ", "PLC", "CLD", "PTD", "KLR",
             "NLR", "PLJ", "SBLR", "GBLR", "PCTLR", "PSC", "CLR"]

# Supabase court_name (free text) -> Zilliz court_code (same rules as the backfill).
_COURT_RULES: List[Tuple[str, str]] = [
    (r"federal\s+shariat", "FSC"),
    (r"supreme\s+appell", "GBSAC"),
    (r"supreme\s+court", "SC"),
    (r"lahore", "LHC"),
    (r"sindh|karachi", "SHC"),
    (r"peshawar", "PHC"),
    (r"balochistan|quetta", "BHC"),
    (r"islamabad", "IHC"),
    (r"azad|ajk", "AJKHC"),
]

_CACHE_MAX = 512
_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off", "")


def zilliz_fallback_enabled() -> bool:
    return _flag("ZILLIZ_FULLTEXT_FALLBACK", "false") and bool(
        os.environ.get("ZILLIZ_URI") and os.environ.get("ZILLIZ_TOKEN"))


def hydration_enabled() -> bool:
    from legal_ai.storage.r2_text_store import r2_configured
    return _flag("TEXT_HYDRATE", "true") and (r2_configured() or zilliz_fallback_enabled())


# ------------------------------------------------------------------ keys
def citation_key(raw: Optional[str]) -> Optional[str]:
    """'PLD 1989 Lah. 64' / '2018_PLC(CS)_237' -> '1989 PLD 64' (the Zilliz `citation` field)."""
    if not raw:
        return None
    u = str(raw).upper().replace("PLC (CS)", "PLC(CS)").replace("P CR L J", "PCRLJ")
    u = u.replace("P.CR.L.J", "PCRLJ").replace("PCR.LJ", "PCRLJ")
    u = re.sub(r"[.\[\]]", " ", u).replace("(CS)", "__CS__")
    u = re.sub(r"[()]", " ", u).replace("__CS__", "(CS)")
    toks = u.replace("_", " ").split()
    if not toks or len(toks) > 8:
        return None
    year = next((t for t in toks if re.fullmatch(r"(19|20)\d\d", t)), None)
    journal = next((t for t in toks if t in _JOURNALS), None)
    page = next((t for t in reversed(toks) if re.fullmatch(r"\d{1,5}", t) and t != year), None)
    if not (year and journal and page):
        return None
    return f"{year} {journal} {int(page)}"


def row_citation_key(row: Dict[str, Any]) -> Optional[str]:
    return citation_key(row.get("neutral_citation")) or citation_key(row.get("case_id"))


def court_code(court_name: Optional[str]) -> Optional[str]:
    s = (court_name or "").lower()
    for pat, code in _COURT_RULES:
        if re.search(pat, s):
            return code
    return None


# ------------------------------------------------------------------ assembly
def _chunk_sort_key(chunk: Dict[str, Any]) -> Tuple[int, str]:
    sec = str(chunk.get("section") or "").lower()
    rank = SECTION_ORDER.index(sec) if sec in SECTION_ORDER else len(SECTION_ORDER)
    return rank, str(chunk.get("chunk_id") or "")


def strip_header(text: str) -> str:
    return _HEADER_RE.sub("", text or "", count=1).strip()


def assemble_case(chunks: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    ordered = sorted(chunks, key=_chunk_sort_key)
    bodies = [(str(c.get("section") or "").lower(), strip_header(c.get("text") or "")) for c in ordered]
    bodies = [(s, b) for s, b in bodies if b]
    full_text = "\n\n".join(b for _, b in bodies)
    headnote = "\n\n".join(b for s, b in bodies if s == "headnote")
    ratio = "\n\n".join(b for s, b in bodies if s in _RATIO_SECTIONS)[:_RATIO_MAX_CHARS].strip()
    return {"full_text": full_text, "headnote": headnote, "ratio_decidendi": ratio}


def _pick_case(groups: Dict[str, List[Dict[str, Any]]], court: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """Several courts can share one 'YEAR JOURNAL PAGE'; prefer the row's court."""
    if not groups:
        return None
    if len(groups) == 1:
        return next(iter(groups.values()))
    if court:
        same = [g for g in groups.values() if str(g[0].get("court_code") or "").upper() == court]
        if len(same) == 1:
            return same[0]
    return None  # ambiguous: leave the row as it is rather than show the wrong judgment


# ------------------------------------------------------------------ Zilliz fetch
def _query_chunks(citations: List[str], timeout_s: float) -> List[Dict[str, Any]]:
    from legal_ai.config import get_zilliz_client, ZILLIZ_COLLECTION
    from legal_ai.retrieval.zilliz_search import is_zilliz_circuit_open

    if not citations or is_zilliz_circuit_open():
        return []
    client = get_zilliz_client()
    if client is None:
        return []
    flt = "citation in [" + ",".join('"%s"' % c.replace('"', "") for c in citations) + "]"
    return client.query(
        collection_name=ZILLIZ_COLLECTION,
        filter=flt,
        output_fields=["chunk_id", "case_key", "citation", "court_code", "section", "text"],
        limit=16384,
        timeout=timeout_s,
    ) or []


def fetch_case_texts(wanted: List[Tuple[str, Optional[str]]], timeout_s: float = 5.0) -> Dict[Tuple[str, Optional[str]], Dict[str, str]]:
    """(citation, court_code) pairs -> assembled texts. Cached; never raises."""
    out: Dict[Tuple[str, Optional[str]], Dict[str, str]] = {}
    todo: List[Tuple[str, Optional[str]]] = []
    with _cache_lock:
        for key in dict.fromkeys(wanted):
            ck = f"{key[0]}|{key[1] or ''}"
            if ck in _cache:
                _cache.move_to_end(ck)
                if _cache[ck]:
                    out[key] = _cache[ck]
            else:
                todo.append(key)
    if not todo:
        return out

    started = time.time()
    try:
        chunks = _query_chunks(sorted({c for c, _ in todo}), timeout_s)
    except Exception as e:
        logger.warning(f"[TextHydration] chunk fetch failed for {len(todo)} cases: {e}")
        return out

    by_cit: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for ch in chunks:
        by_cit.setdefault(str(ch.get("citation")), {}).setdefault(str(ch.get("case_key")), []).append(ch)

    with _cache_lock:
        for key in todo:
            picked = _pick_case(by_cit.get(key[0], {}), key[1])
            texts = assemble_case(picked) if picked else {}
            _cache[f"{key[0]}|{key[1] or ''}"] = texts
            _cache.move_to_end(f"{key[0]}|{key[1] or ''}")
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
            if texts:
                out[key] = texts
    logger.info(f"[TextHydration] rebuilt {len(out)}/{len(wanted)} judgments from {len(chunks)} chunks "
                f"in {time.time() - started:.2f}s")
    return out


# ------------------------------------------------------------------ row hydration
def _iter_row_dicts(data: Any) -> Iterable[Dict[str, Any]]:
    rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        yield row
        nested = row.get("full_judgments")  # citation_crosswalk embeds full_judgments(*)
        for sub in (nested if isinstance(nested, list) else [nested]):
            if isinstance(sub, dict):
                yield sub


def _missing_fields(row: Dict[str, Any]) -> List[str]:
    # A row that still carries its full_text was never trimmed: its empty headnote or
    # ratio is genuinely empty, so don't spend a lookup on it.
    if (row.get("full_text") or "").strip():
        return []
    return [f for f in TEXT_FIELDS if f in row and not (row.get(f) or "").strip()]


def _fill(row: Dict[str, Any], missing: List[str], texts: Dict[str, Any], source: str) -> None:
    for f in missing:
        if (texts.get(f) or "").strip():
            row[f] = texts[f]
    row.setdefault("text_source", source)


def hydrate_rows(data: Any, timeout_s: float = 5.0) -> Any:
    """Fill empty full_text/headnote/ratio_decidendi in place (R2 by id, then optional Zilliz). Never raises."""
    if not hydration_enabled():
        return data
    try:
        from legal_ai.storage.r2_text_store import get_texts, r2_configured

        targets = [(row, _missing_fields(row)) for row in _iter_row_dicts(data)]
        targets = [(row, m) for row, m in targets if m]
        if not targets:
            return data

        if r2_configured():
            texts = get_texts([row.get("id") for row, _ in targets if row.get("id")], timeout_s=timeout_s)
            still = []
            for row, missing in targets:
                rec = texts.get(str(row.get("id") or ""))
                if rec:
                    _fill(row, missing, rec, "r2")  # R2 is the verbatim copy: its empty fields stay empty
                else:
                    still.append((row, missing))
            targets = still

        if targets and zilliz_fallback_enabled():
            keyed = [(row, m, (row_citation_key(row), court_code(row.get("court_name") or row.get("canonical_court_name"))))
                     for row, m in targets]
            keyed = [t for t in keyed if t[2][0]]
            ztexts = fetch_case_texts([t[2] for t in keyed], timeout_s=timeout_s) if keyed else {}
            for row, missing, key in keyed:
                if ztexts.get(key):
                    _fill(row, missing, ztexts[key], "zilliz")
    except Exception as e:
        logger.warning(f"[TextHydration] hydration skipped: {e}")
    return data


# ------------------------------------------------------------------ client wrapper
class _HydratingBuilder:
    """Proxies a postgrest request builder; hydrates rows when `.execute()` runs."""

    __slots__ = ("_inner", "_add_id")

    def __init__(self, inner: Any, add_id: bool = False):
        self._inner = inner
        self._add_id = add_id

    def execute(self, *a, **kw):
        res = self._inner.execute(*a, **kw)
        data = getattr(res, "data", None)
        if data:
            hydrate_rows(data)
        return res

    def __getattr__(self, name: str):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def call(*a, **kw):
            if name == "select" and self._add_id and a:
                a = (_with_id(a[0]),) + tuple(a[1:])
            out = attr(*a, **kw)
            return _HydratingBuilder(out, self._add_id) if hasattr(out, "execute") else out
        return call


def _with_id(columns: Any) -> Any:
    """R2 lookups are by row id, so make sure explicit column lists include it."""
    if not isinstance(columns, str):
        return columns
    top = [c.strip() for c in columns.split(",")]
    if "*" in top or "id" in top or not any(c in TEXT_FIELDS for c in top):
        return columns
    return columns + ", id"


class HydratingSupabaseClient:
    """Wraps a supabase Client; `.table('full_judgments')` results get text from Zilliz."""

    def __init__(self, inner: Any):
        object.__setattr__(self, "_inner", inner)

    def table(self, name: str, *a, **kw):
        b = self._inner.table(name, *a, **kw)
        return _HydratingBuilder(b, name == "full_judgments") if name in HYDRATED_TABLES else b

    def from_(self, name: str, *a, **kw):
        b = self._inner.from_(name, *a, **kw)
        return _HydratingBuilder(b, name == "full_judgments") if name in HYDRATED_TABLES else b

    def rpc(self, fn: str, *a, **kw):
        b = self._inner.rpc(fn, *a, **kw)
        return _HydratingBuilder(b) if fn in HYDRATED_RPCS else b

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any):
        setattr(self._inner, name, value)


def wrap_supabase_client(client: Any) -> Any:
    if client is None or isinstance(client, HydratingSupabaseClient):
        return client
    return HydratingSupabaseClient(client)
