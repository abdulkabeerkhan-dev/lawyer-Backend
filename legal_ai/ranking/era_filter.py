"""The workspace's jurisprudence-era toggle.

The frontend sends {era: "modern", min_year: 2018} or {era: "apex", court_filter:
"Supreme Court of Pakistan"} with each query. These used to be dropped on the floor, so the
toggle changed nothing. Apply them to the retrieved cases before ranking and synthesis.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


def _field(req: Any, *names: str) -> Any:
    for n in names:
        v = req.get(n) if isinstance(req, dict) else getattr(req, n, None)
        if v not in (None, "", [], {}):
            return v
    return None


def requested_filters(request: Any) -> Dict[str, Any]:
    era = str(_field(request, "era") or "").strip().lower()
    out: Dict[str, Any] = {}
    min_year = _field(request, "min_year", "year_from")
    if era == "modern" or min_year:
        try:
            out["min_year"] = int(min_year or 2018)
        except (TypeError, ValueError):
            out["min_year"] = 2018
    court = _field(request, "court_filter", "court")
    if era == "apex" or court:
        out["court"] = str(court or "Supreme Court of Pakistan")
    return out


def _year(c: Dict[str, Any]) -> Optional[int]:
    meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
    for v in (c.get("year"), meta.get("year")):
        try:
            if v:
                return int(v)
        except (TypeError, ValueError):
            pass
    for v in (c.get("citation"), meta.get("citation"), c.get("neutral_citation"), meta.get("neutral_citation"),
              c.get("case_id"), meta.get("case_id")):
        m = _YEAR.search(str(v or ""))
        if m:
            return int(m.group(1))
    return None


def _is_court(c: Dict[str, Any], court: str) -> bool:
    meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
    code = str(c.get("court_code") or meta.get("court_code") or "").upper()
    name = " ".join(str(x or "") for x in (c.get("court"), c.get("court_name"), meta.get("court"),
                                           meta.get("court_name"))).lower()
    want = court.lower()
    if "supreme court" in want and "kashmir" not in want and "ajk" not in want:
        if code:
            return code == "SC"
        return "supreme court" in name and not re.search(r"kashmir|aj&k|ajk|india|gilgit|appellate", name)
    return want in name


def apply_request_filters(candidates: List[Dict[str, Any]], request: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    f = requested_filters(request)
    if not f:
        return candidates, {}
    kept = []
    for c in candidates:
        if "min_year" in f:
            y = _year(c)
            if y is None or y < f["min_year"]:
                continue
        if "court" in f and not _is_court(c, f["court"]):
            continue
        kept.append(c)
    return kept, {"filters": f, "before": len(candidates), "after": len(kept)}
