"""
core/signal_rule.py

Decides whether a search hit is evidence of a NEW legislative change.

A page counts only if it names an instrument (Act/Ordinance number and year, an
"(Amendment) Act/Ordinance/Bill, <year>" title, or a Bill with a year) that
  - is dated on or after `since_year`,
  - is not the statute's own base instrument,
  - is not already in the store's known instruments, and
  - is not on a page that predates the last check.
Words such as "amended", "substituted" or "omitted" alone are never enough: every
consolidated bare act contains them in its footnotes.

Limits (document them in the UI help, not here): an amendment older than `since_year`
that the store does not know about will not be flagged. It belongs in the imported text.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Set

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# Roman numerals must be upper-case; (?-i:...) stops "mid", "dim" etc. matching.
_INSTR_RE = re.compile(
    r"\b(?P<kind>(?i:act|ordinance|regulation))\s+(?:(?i:no)\.?\s*)?"
    r"(?P<num>(?-i:[IVXLCDM]+|\d+))\s+(?i:of)\s+(?P<year>(?:19|20)\d{2})\b")
_AMEND_TITLE_RE = re.compile(
    r"(?P<pre>(?:[A-Za-z()'\-]+\s+){0,8})\(\s*(?i:amendment)\s*\)\s*(?P<kind>(?i:act|ordinance|bill))"
    r"\s*,?\s*(?P<year>(?:19|20)\d{2})\b")
_BILL_RE = re.compile(r"\b(?i:bill)\b[^.\n]{0,40}?\b(?P<year>(?:19|20)\d{2})\b")
_STAGE_RE = {
    "assented": re.compile(r"\bassent(?:ed)?\b", re.IGNORECASE),
    "passed": re.compile(r"\bpassed\b", re.IGNORECASE),
    "notified": re.compile(r"\b(?:notified|gazette)\b", re.IGNORECASE),
}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def instrument_key(kind: str, number, year: int) -> str:
    """Canonical key. Use this to seed known_instruments, e.g. instrument_key('ordinance','VIII',1961)."""
    n = roman_to_int(str(number)) if re.fullmatch(r"[IVXLCDM]+", str(number)) else int(number)
    return f"{kind.lower()}:{n}:{int(year)}"


@dataclass
class SignalContext:
    act_code: str
    since_year: int
    last_checked: Optional[date] = None
    known_instruments: Set[str] = field(default_factory=set)
    known_urls: Set[str] = field(default_factory=set)
    base_titles: List[str] = field(default_factory=list)       # e.g. "Muslim Family Laws Ordinance, 1961"
    base_instruments: Set[str] = field(default_factory=set)    # e.g. {instrument_key("ordinance","VIII",1961)}


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    s = str(v)[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _strip_base_titles(text: str, titles: List[str]) -> str:
    for t in titles:
        text = re.sub(re.escape(t), " ", text, flags=re.IGNORECASE)
    return text


def evaluate_signal(hit: Dict, ctx: SignalContext) -> Dict:
    url = str(hit.get("url") or "")
    reasons: List[str] = []
    if url and url in ctx.known_urls:
        return {"is_signal": False, "kind": None, "instrument_keys": [], "stage_hint": None,
                "reasons": ["url already reviewed"]}

    text = _strip_base_titles(f"{hit.get('title', '')} . {hit.get('snippet', '')}", ctx.base_titles)
    found: Dict[str, str] = {}   # key -> kind ("instrument" | "bill")

    for m in _INSTR_RE.finditer(text):
        key = instrument_key(m.group("kind"), m.group("num"), int(m.group("year")))
        if int(m.group("year")) >= ctx.since_year:
            found[key] = "instrument"
    for m in _AMEND_TITLE_RE.finditer(text):
        year, kind = int(m.group("year")), m.group("kind").lower()
        if year >= ctx.since_year:
            key = f"amend:{kind}:{year}:{_slug(m.group('pre'))}"
            found[key] = "bill" if kind == "bill" else "instrument"
    for m in _BILL_RE.finditer(text):
        year = int(m.group("year"))
        if year >= ctx.since_year:
            found.setdefault(f"bill::{year}:{_slug(hit.get('title', ''))[:60]}", "bill")

    new = {k: v for k, v in found.items()
           if k not in ctx.known_instruments and k not in ctx.base_instruments}
    if found and not new:
        reasons.append("only known or base instruments mentioned")

    page_date = _parse_date(hit.get("date"))
    if new and page_date and ctx.last_checked and page_date <= ctx.last_checked:
        reasons.append("page dated on or before the last check")
        new = {}

    if not new:
        if not found:
            reasons.append("no dated instrument or bill named")
        return {"is_signal": False, "kind": None, "instrument_keys": [], "stage_hint": None,
                "reasons": reasons}

    kind = "bill" if all(v == "bill" for v in new.values()) else "instrument"
    stage = next((s for s, rx in _STAGE_RE.items() if rx.search(text)), None)
    return {"is_signal": True, "kind": kind, "instrument_keys": sorted(new), "stage_hint": stage,
            "reasons": ["new instrument named"]}
