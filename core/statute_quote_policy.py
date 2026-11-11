"""
Single source of truth for whether a statute record's text may be presented
to a lawyer as verbatim, verified statutory text.

Background (audit 2026-11-11): loaders were forcing ``quoting_allowed=True``
on almost every record, including ``extraction_disputed`` ones and Turso rows
of unknown provenance. ~800 records in data/statutes_v2 have a cleaned
``text``/``verbatim_text`` that no longer matches the official PDF extraction
in ``text_raw`` (e.g. PPC s.302, whose proviso was rewritten). Those were
rendered as "Authentic Verbatim Text" with a Verified badge.

Rule: text is quote-verified only if the record is not marked repealed/not-in-force and
  * tier is ``reviewed`` / ``verified_golden`` (human, signature-checked), or
  * ``verification.status == "official_pdf_match"``: the text was machine-checked
    word-for-word against an official PDF in data/official_pdfs
    (see scripts/verify_statutes_against_official_pdfs.py). The verified field
    (``verbatim_text`` or ``text_raw``) is the one displayed.
Everything else (no official PDF, near-matches, footnote-contaminated text, Turso
``tier_1``/``tier_2`` rows, unknown tiers) is NOT quote-verified.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

VERIFIED_TIERS = frozenset({"reviewed", "verified_golden"})
OFFICIAL_PDF_MATCH = "official_pdf_match"

_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)


def _norm(s: Optional[str]) -> str:
    return _NON_ALNUM.sub("", s or "").lower()


def quoted_text(rec: Dict[str, Any]) -> str:
    """The text a renderer would show as the provision's wording."""
    return str(rec.get("verbatim_text") or rec.get("text") or "").strip()


def _verification(rec: Dict[str, Any]) -> Dict[str, Any]:
    v = rec.get("verification")
    return v if isinstance(v, dict) else {}


def is_quote_verified(rec: Optional[Dict[str, Any]]) -> bool:
    if not rec:
        return False
    if rec.get("in_force") is False:
        return False
    tier = str(rec.get("tier") or "").strip().lower()
    if tier in VERIFIED_TIERS:
        return bool(quoted_text(rec))
    v = _verification(rec)
    if v.get("status") == OFFICIAL_PDF_MATCH:
        field = v.get("matched_field") or "verbatim_text"
        src = rec.get(field) if field == "text_raw" else quoted_text(rec)
        return bool(str(src or "").strip())
    return False


def _tidy(s: str) -> str:
    # The official PDFs encode hyphens as U+00AD (e.g. "fasad­fil­arz", "twenty­five").
    return re.sub(r"[ \t]+", " ", (s or "").replace("­", "-")).strip()


def display_text(rec: Dict[str, Any]) -> str:
    """
    Text to show for a provision. For verified records, the exact field that matched
    the official PDF. Otherwise prefer the direct official-PDF extraction
    (``text_raw``) over a cleaned/rewritten version, since the rewrite is what
    introduced errors such as the PPC s.302 proviso.
    """
    if is_quote_verified(rec) and _verification(rec).get("matched_field") == "text_raw":
        return _tidy(rec.get("text_raw"))
    if is_quote_verified(rec):
        return quoted_text(rec)
    return _tidy(rec.get("text_raw") or quoted_text(rec))


def verification_label(rec: Dict[str, Any]) -> Optional[str]:
    """Human-readable provenance for a verified record, e.g. 'ppc_1860.pdf, p. 106'."""
    tier = str(rec.get("tier") or "").strip().lower()
    if tier in VERIFIED_TIERS and is_quote_verified(rec):
        return "advocate-reviewed"
    v = _verification(rec)
    if is_quote_verified(rec) and v.get("status") == OFFICIAL_PDF_MATCH:
        page = v.get("page")
        return f"matches official text: {v.get('source_pdf')}" + (f", p. {page}" if page else "")
    return None
