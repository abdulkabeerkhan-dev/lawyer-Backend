"""
legal_ai/verification/statute_matcher.py

Statute matching, text normalization, and authority grounding.
Binds to verified bare acts in data/statute_tables and data/statute_versions.
"""

from __future__ import annotations
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from legal_ai.verification.doctrinal_rules import PROVISIONS_SPEC, TOPICS_SPEC, ACT_ALIASES

_SMART = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-"
}


def straighten(s: str) -> str:
    """Straighten smart quotes and dashes."""
    for k, v in _SMART.items():
        s = s.replace(k, v)
    return s


def norm_text(s: str) -> str:
    """Aggressive normalisation for quote matching (case, punctuation, whitespace)."""
    s = straighten(unicodedata.normalize("NFKC", s)).lower()
    s = re.sub(r"-\s*\n\s*", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_COURT = {
    "supreme": "SC",
    "lahore": "Lah.",
    "karachi": "Kar.",
    "sindh": "Kar.",
    "peshawar": "Pesh.",
    "quetta": "Quetta",
    "balochistan": "Quetta",
    "islamabad": "Isl.",
}

_COURT_TOKENS = r"(?:SC|Supreme Court|Lah\.?|Kar\.?|Pesh\.?|Quetta|Isl\.?)"
_YEAR_FIRST = r"(?:SCMR|YLR|CLD|CLC|MLD|PCrLJ|PTD|PLC|GBLR)"


def court_code(court: Optional[str]) -> Optional[str]:
    if not court:
        return None
    c = court.lower()
    for k, v in _COURT.items():
        if k in c:
            return v
    return None


def _canon_court(tok: str) -> str:
    t = tok.strip().lower().rstrip(".")
    if t in ("sc", "supreme court"):
        return "SC"
    return {"lah": "Lah.", "kar": "Kar.", "pesh": "Pesh.", "quetta": "Quetta", "isl": "Isl."}.get(t, tok)


def normalize_citation(raw: str, court: Optional[str] = None) -> Tuple[str, bool]:
    """
    Return (canonical, resolved).
    PLD form: 'PLD 2025 SC 502'.
    Others: '2026 SCMR 190'.
    """
    s = re.sub(r"\s+", " ", raw.strip())
    m = re.fullmatch(rf"(?i)PLD (\d{{4}}) ({_COURT_TOKENS}) (\d+)", s)
    if m:
        return f"PLD {m.group(1)} {_canon_court(m.group(2))} {m.group(3)}", True
    m = re.fullmatch(r"(?i)(\d{4}) PLD (\d+)", s)
    if m:
        code = court_code(court)
        if code:
            return f"PLD {m.group(1)} {code} {m.group(2)}", True
        return f"PLD {m.group(1)} ? {m.group(2)}", False
    m = re.fullmatch(rf"(?i)(\d{{4}}) ({_YEAR_FIRST}) (\d+)", s)
    if m:
        return f"{m.group(1)} {m.group(2).upper()} {m.group(3)}", True
    return s, False


CITE_RES = [
    re.compile(r"\b\d{4}\s+PLD\s+\d+\b", re.I),
    re.compile(rf"\bPLD\s+\d{{4}}\s+{_COURT_TOKENS}\s+\d+\b", re.I),
    re.compile(rf"\b\d{{4}}\s+{_YEAR_FIRST}\s+\d+\b", re.I),
]


def find_citations(text: str) -> List[Tuple[str, int, int]]:
    out, seen = [], set()
    for rx in CITE_RES:
        for m in rx.finditer(text):
            if (m.start(), m.end()) not in seen:
                seen.add((m.start(), m.end()))
                out.append((m.group(0), m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


_SPLIT = re.compile(
    r'(?<=[a-z0-9\)"\u201d])(?<!\bv)(?<!\bs)(?<!\bss)(?<!\bno)(?<!\bnos)(?<!\bvs)(?<!\bart)(?<!\bsec)'
    r'\.\s+(?=[A-Z"\u201c(])'
)


def sentences(text: str) -> List[str]:
    out = []
    for para in re.split(r"\n+", text):
        for s in _SPLIT.split(para):
            s = s.strip()
            if s:
                out.append(s)
    return out


def shingles(s: str, n: int = 4) -> Set[str]:
    w = s.split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


@dataclass
class JudgmentRecord:
    citation: str
    title: str
    text: str
    norm: str


class StatuteAuthorityStore:
    """
    Authority store: loaded bare acts, provisions, and judgment texts.
    Caches verified statute text and provides shingle/quote matching.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path(__file__).resolve().parent.parent.parent
        self.provisions: List[Dict[str, Any]] = [dict(p) for p in PROVISIONS_SPEC]
        self.judgments: Dict[str, JudgmentRecord] = {}
        self.citation_index: Dict[str, Dict[str, Any]] = {}
        self._load_local_indices()

    def _load_local_indices(self) -> None:
        # Load citation_index if available
        ci_path = self.workspace_root / "data" / "citation_index.json"
        if ci_path.exists():
            try:
                for row in json.loads(ci_path.read_text(encoding="utf-8")):
                    c, _ = normalize_citation(row.get("citation", ""), row.get("court"))
                    self.citation_index[c] = row
            except Exception:
                pass

    @staticmethod
    def key(p: Dict[str, Any]) -> str:
        return f"{p['act']}:{p['kind']}:{p['id']}"

    def provision(self, key: str) -> Optional[Dict[str, Any]]:
        return next((p for p in self.provisions if self.key(p) == key), None)

    def statute_text(self, key: str) -> Optional[str]:
        p = self.provision(key)
        return p.get("text") if p else None

    def statute_reviewed(self, key: str) -> bool:
        p = self.provision(key)
        return bool(p and p.get("text") and p.get("reviewed_by"))

    def all_statute_texts(self) -> List[str]:
        return [p["text"] for p in self.provisions if p.get("text")]

    def add_judgment(self, text: str, citation: Optional[str] = None, title: str = "") -> Optional[str]:
        if not text.strip():
            return None
        cit = citation
        if not cit:
            # detect citation from text header
            head = text[:4000]
            m = re.search(r"P\s*L\s*D\s+(\d{4})\s+Supreme\s+Court\s+(\d+)", head, re.I)
            if m:
                cit = f"PLD {m.group(1)} SC {m.group(2)}"
            else:
                m = re.search(r"(PLD\s+\d{4}\s+SC\s+\d+)", head, re.I)
                if m:
                    cit = normalize_citation(m.group(1))[0]
                else:
                    m = re.search(r"(\d{4})\s+PLD\s+(\d+)", head, re.I)
                    if m:
                        court = "Supreme Court" if re.search(r"supreme", head, re.I) else None
                        cit = normalize_citation(m.group(0), court)[0]
                    else:
                        m = re.search(r"(\d{4})\s+(SCMR|YLR|CLD|CLC|MLD)\s+(\d+)", head, re.I)
                        if m:
                            cit = normalize_citation(m.group(0))[0]

        if not cit:
            return None

        cit_norm, ok = normalize_citation(cit, "Supreme Court" if "SC" in cit else None)
        cit_final = cit_norm if ok else cit
        self.judgments[cit_final] = JudgmentRecord(cit_final, title, text, norm_text(text))
        self.citation_index.setdefault(cit_final, {"citation": cit_final, "title": title})
        return cit_final

    def register_citation(self, citation: str, court: Optional[str] = None, title: str = "") -> str:
        c, ok = normalize_citation(citation, court)
        if ok:
            self.citation_index.setdefault(c, {"citation": c, "court": court, "title": title})
        return c

    def resolve_pld(self, year: str, page: str) -> Optional[str]:
        hits = [c for c in self.citation_index if re.fullmatch(rf"PLD {year} \S+ {page}", c)]
        return hits[0] if len(hits) == 1 else None


_GLOBAL_STORE: Optional[StatuteAuthorityStore] = None


def get_authority_store() -> StatuteAuthorityStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = StatuteAuthorityStore()
    return _GLOBAL_STORE
