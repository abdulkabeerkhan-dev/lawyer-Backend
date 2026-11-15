"""Conservative judgment-text classification helpers."""

import re
from typing import Any, Dict


_HEADNOTE_LEVELS = {
    "headnote",
    "headnote_only",
    "editorial_summary",
    "summary",
}
_FULL_TEXT_LEVELS = {"full_judgment", "full_text", "judgment", "order_text"}
_PUBLISHER_METADATA_RE = re.compile(
    r"(?im)^\s*(?:headnotes?|editorial\s+(?:summary|note)|case\s+note|"
    r"reported\s+summary|law\s+reporter\s+digest|pakistan\s+law\s+site|P\.?\s*L\.?\s*S\.?)\b"
)


def classify_judgment_content(record: Dict[str, Any]) -> str:
    """Return a conservative content label, correcting short publisher headnotes."""
    text = str(
        record.get("full_text")
        or record.get("text")
        or record.get("body")
        or ""
    ).strip()
    headnote = str(record.get("headnote") or "").strip()
    declared = str(
        record.get("content_level")
        or record.get("content_type")
        or record.get("text_type")
        or ""
    ).strip().lower().replace("-", "_")

    if declared in ("headnote", "headnote_only"):
        return declared
    if declared in _HEADNOTE_LEVELS:
        return "headnote_only"
    if text and len(text) < 4000 and _PUBLISHER_METADATA_RE.search(text):
        return "headnote_only"
    if not text and headnote:
        return "headnote"
    if not text:
        return "unknown"

    # Use structural judge byline & order parsing to differentiate Type A vs Type B
    try:
        from core.structural_judgment_segmenter import parse_pakistan_law_site_document
        parsed = parse_pakistan_law_site_document(text)
        if parsed.get("content_level") == "full_judgment":
            return "full_judgment"
        else:
            return "headnote"
    except Exception:
        if declared in _FULL_TEXT_LEVELS and len(text.split()) > 200:
            return "full_judgment"
        return "headnote"

