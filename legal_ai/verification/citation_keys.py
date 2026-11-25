"""
legal_ai/verification/citation_keys.py

One normal form for Pakistani law-report citations, so every check agrees on what
counts as the same case:

    "PLD 2004 SC 62", "2004 PLD 62", "2004_PLD_SC_62", "P L D 2004 Supreme Court 62"
        -> ("2004", "PLD", "62")

Also: find every citation key in a text, and check which keys exist in the
judgment corpus (Supabase full_judgments).
"""
from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

Key = Tuple[str, str, str]  # (year, journal, page)

_JOURNALS = {
    "PLD", "SCMR", "CLC", "YLR", "PCRLJ", "MLD", "CLD", "PTD", "PLC", "PLC(CS)", "NLR", "PLJ", "SBLR",
    "GBLR", "KLR", "CLR", "PSC", "PCTLR", "PLR", "SCJ",
}
# Court tokens that sit between journal/year and page in some citation styles.
_COURTS = ["SC", "FSC", "LAH", "KAR", "PESH", "QUETTA", "ISL", "AJK", "SHC", "LHC", "PHC", "BHC", "IHC",
           "AJKHC", "AJKSC", "GBSAC", "GBCC", "SUPREME", "COURT", "LAHORE", "KARACHI", "PESHAWAR",
           "BALOCHISTAN", "ISLAMABAD", "FEDERAL", "SHARIAT", "HIGH", "SUPREME COURT"]
_COURT_RX = r"(?:(?:Supreme\s+Court|Federal\s+Shariat\s+Court|[A-Z][A-Za-z]{1,10}\.?)\s+)?"
_J_RX = r"(?:PLD|P\.?\s?L\.?\s?D|SCMR|S\.?\s?C\.?\s?M\.?\s?R|CLC|YLR|P\.?\s?Cr\.?\s?L\.?\s?J|PCRLJ|MLD|CLD|PTD|PLC\s?\(\s?CS\s?\)|PLC|NLR|PLJ|SBLR|GBLR|KLR|CLR|PSC|PCTLR|PLR|SCJ)"
_CITE_RX = re.compile(
    rf"\b(?:(?P<j1>{_J_RX})\s+(?P<y1>(?:18|19|20)\d\d)\s+{_COURT_RX}(?P<p1>\d{{1,5}})"
    rf"|(?P<y2>(?:18|19|20)\d\d)\s+(?P<j2>{_J_RX})\s+{_COURT_RX}(?P<p2>\d{{1,5}}))\b",
    re.IGNORECASE,
)
_ID_RX = re.compile(r"^((?:18|19|20)\d\d)_([A-Z()]+)_(?:[A-Z]+_)?(\d{1,5})$")


def _norm_journal(j: str) -> str:
    j = re.sub(r"[\s.]", "", j.upper())
    return "PLC(CS)" if j.startswith("PLC(CS") else j


def citation_key(text: str) -> Optional[Key]:
    """The key of the first citation in `text` (or of a case_id like 2004_PLD_SC_62)."""
    if not text:
        return None
    m = _ID_RX.match(str(text).strip().upper().replace(" ", "_"))
    if m and _norm_journal(m.group(2)) in _JOURNALS:
        return (m.group(1), _norm_journal(m.group(2)), str(int(m.group(3))))
    m = _CITE_RX.search(str(text))
    if not m:
        return None
    j, y, p = (m.group("j1"), m.group("y1"), m.group("p1")) if m.group("j1") else (m.group("j2"), m.group("y2"), m.group("p2"))
    return (y, _norm_journal(j), str(int(p)))


def keys_in_text(text: str) -> Set[Key]:
    out: Set[Key] = set()
    for m in _CITE_RX.finditer(text or ""):
        j, y, p = (m.group("j1"), m.group("y1"), m.group("p1")) if m.group("j1") else (m.group("j2"), m.group("y2"), m.group("p2"))
        out.add((y, _norm_journal(j), str(int(p))))
    return out


def iter_citations(text: str):
    """(raw_text, start, end, key) for every citation in `text`."""
    for m in _CITE_RX.finditer(text or ""):
        j, y, p = (m.group("j1"), m.group("y1"), m.group("p1")) if m.group("j1") else (m.group("j2"), m.group("y2"), m.group("p2"))
        yield m.group(0), m.start(), m.end(), (y, _norm_journal(j), str(int(p)))


def case_id_candidates(key: Key) -> List[str]:
    """full_judgments.case_id forms a citation can take: 2004_PLD_62 and 2004_PLD_SC_62 style."""
    y, j, p = key
    base = [f"{y}_{j}_{p}"]
    for c in ("SC", "FSC", "LAH", "KAR", "PESH", "QUETTA", "ISL", "LHC", "SHC", "PHC", "BHC", "IHC", "AJKHC", "AJK"):
        base.append(f"{y}_{j}_{c}_{p}")
    return base


# ------------------------------------------------------------------ corpus lookup
_known: "OrderedDict[Key, bool]" = OrderedDict()
_lock = threading.Lock()
_MAX = 4096


def known_in_corpus(keys: Iterable[Key], timeout_s: float = 3.0) -> Dict[Key, Optional[bool]]:
    """key -> True (in corpus), False (not found), None (could not check). Never raises."""
    keys = list(dict.fromkeys(k for k in keys if k))
    out: Dict[Key, Optional[bool]] = {}
    todo: List[Key] = []
    with _lock:
        for k in keys:
            if k in _known:
                out[k] = _known[k]
            else:
                todo.append(k)
    if not todo:
        return out
    try:
        from legal_ai.config import get_supabase_client
        sb = get_supabase_client()
    except Exception:
        sb = None
    if sb is None:
        out.update({k: None for k in todo})
        return out
    try:
        found: Set[Key] = set()
        for i in range(0, len(todo), 20):
            chunk = todo[i:i + 20]
            ids = [cid for k in chunk for cid in case_id_candidates(k)]
            # select only small columns: never pull judgment text for an existence check
            res = sb.table("full_judgments").select("case_id, neutral_citation").in_("case_id", ids).execute()
            for row in res.data or []:
                k = citation_key(row.get("case_id") or "") or citation_key(row.get("neutral_citation") or "")
                if k:
                    found.add(k)
            missing = [k for k in chunk if k not in found]
            if missing:
                forms = []
                for (y, j, p) in missing:
                    forms += [f"{j} {y} {p}", f"{y} {j} {p}"]
                res = sb.table("full_judgments").select("case_id, neutral_citation").in_("neutral_citation", forms).execute()
                for row in res.data or []:
                    k = citation_key(row.get("neutral_citation") or "")
                    if k:
                        found.add(k)
        with _lock:
            for k in todo:
                out[k] = k in found
                _known[k] = out[k]
                while len(_known) > _MAX:
                    _known.popitem(last=False)
    except Exception as err:
        logger.warning(f"[citation_keys] corpus lookup failed: {err}")
        out.update({k: None for k in todo if k not in out})
    return out


def format_key(key: Key) -> str:
    y, j, p = key
    return f"{y} {j} {p}"
