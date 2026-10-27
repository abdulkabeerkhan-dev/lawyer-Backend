"""
core/quote_by_reference.py

ORDER 2.0 — STEP 4: QUOTE BY REFERENCE & VERBATIM SYSTEM EXPANSION
Goal: The model cites a provision by ID using {{QUOTE:<canonical_id>}} or {{QUOTE:<canonical_id>#<subsection>}}.
The system pastes the verbatim text in from data/statutes_v2.
No model writes it. No model rewords it.
Any model-typed blockquote must match text_raw byte-for-byte or is BLOCKED with a word-level diff.
"""

import os
import re
import difflib
import hashlib
from typing import Dict, Any, Tuple, Optional, List

from core.unified_statute_store import get_unified_statute_store

QUOTE_PLACEHOLDER_PATTERN = re.compile(
    r'\{\{QUOTE:([A-Za-z0-9_]+)(?:#([a-zA-Z0-9_\-\(\)]+))?\}\}'
)

def format_system_blockquote(rec: Dict[str, Any], subsection: Optional[str] = None) -> str:
    """
    Formats the verbatim blockquote with system source line.
    Header: Act, section, PDF page, extractor agreement, 'Text-layer extract, not human-reviewed'
    """
    act = rec.get("act") or rec.get("act_code", "ACT")
    sec = rec.get("section") or rec.get("primary_num", "")
    page_start = rec.get("page_start") or rec.get("source_page", "?")
    agreement = rec.get("extractor_agreement", "exact")
    text_raw = rec.get("text_raw") or rec.get("text", "")
    
    # If subsection is specified, find subsection if possible, otherwise keep full text
    content = text_raw.strip()
    if subsection:
        clean_sub = subsection.strip("() ")
        # Try to match e.g. "(1)" or "1."
        sub_pat = re.compile(rf'(?:^|\n)\s*(?:\({clean_sub}\)|{clean_sub}\.)\s*(.*?)(?=(?:\n\s*(?:\(\d+\)|\d+\.)|\Z))', re.S)
        m = sub_pat.search(content)
        if m:
            content = f"({clean_sub}) " + m.group(1).strip()
            sec = f"{sec}#{subsection}"

    # Prefix each line with >
    quoted_lines = []
    for line in content.splitlines():
        quoted_lines.append(f"> {line}" if line.strip() else ">")
    body_quoted = "\n".join(quoted_lines)

    source_header = (
        f"> [!QUOTE] {act}, Section {sec} (PDF page {page_start}, extractor agreement: {agreement})\n"
        f"> Text-layer extract, not human-reviewed\n"
        f">"
    )
    return f"{source_header}\n{body_quoted}"

def expand_quote_placeholder(placeholder: str) -> Tuple[bool, str, Optional[str]]:
    """
    Expands a single {{QUOTE:<canonical_id>}} placeholder into a verbatim blockquote.
    Returns (success, expanded_text, block_reason).
    """
    m = QUOTE_PLACEHOLDER_PATTERN.match(placeholder.strip())
    if not m:
        return False, "", f"INVALID_SYNTAX: '{placeholder}' does not match {{QUOTE:<canonical_id>}} syntax."

    cid = m.group(1).strip().upper()
    sub = m.group(2).strip() if m.group(2) else None

    store = get_unified_statute_store()
    rec = store.get_by_canonical_id(cid)

    if not rec:
        return False, "", f"UNKNOWN_CANONICAL_ID: Provision '{cid}' not found in verified store statutes_v2."

    tier = rec.get("tier", "heading_only")
    quoting_allowed = rec.get("quoting_allowed", False)

    if tier in ("extraction_disputed", "heading_only") or not quoting_allowed:
        return False, "", (
            f"DISPUTED_TIER_BLOCKED: Provision '{cid}' has tier='{tier}' "
            f"(quoting_allowed={quoting_allowed}). Quoting is blocked."
        )

    expanded = format_system_blockquote(rec, subsection=sub)
    return True, expanded, None

def expand_all_quote_placeholders(memo_text: str) -> Tuple[bool, str, List[str]]:
    """
    Scans memo text, expands all placeholders.
    If ANY placeholder is blocked, returns (False, original_text, [block_reasons]).
    Otherwise returns (True, expanded_memo, []).
    """
    matches = list(QUOTE_PLACEHOLDER_PATTERN.finditer(memo_text))
    if not matches:
        return True, memo_text, []

    block_reasons = []
    replacements = []

    for m in matches:
        raw_ph = m.group(0)
        ok, expanded, reason = expand_quote_placeholder(raw_ph)
        if not ok:
            block_reasons.append(reason)
        else:
            replacements.append((raw_ph, expanded))

    if block_reasons:
        return False, memo_text, block_reasons

    result_text = memo_text
    for raw_ph, exp in replacements:
        result_text = result_text.replace(raw_ph, exp, 1)

    return True, result_text, []

def verify_model_typed_statute_quote(canonical_id: str, typed_quote: str) -> Tuple[bool, str]:
    """
    Verifies a model-typed blockquote against text_raw.
    Must match byte-for-byte or is BLOCKED with a word-level diff.
    """
    store = get_unified_statute_store()
    rec = store.get_by_canonical_id(canonical_id.strip().upper())
    if not rec:
        return False, f"UNKNOWN_CANONICAL_ID: '{canonical_id}' not found in verified store."

    text_raw = rec.get("text_raw") or rec.get("text", "")
    clean_typed = typed_quote.strip()
    clean_stored = text_raw.strip()

    if clean_typed == clean_stored:
        return True, "EXACT_BYTE_MATCH"

    # Compute word-level diff
    typed_words = clean_typed.split()
    stored_words = clean_stored.split()
    word_diff = list(difflib.unified_diff(
        stored_words, typed_words,
        fromfile="verified_store_text_raw",
        tofile="model_typed_quote",
        lineterm=""
    ))
    diff_str = "\n".join(word_diff[:25])
    return False, f"BLOCKED: Model-typed quote does not match text_raw byte-for-byte.\nWord diff:\n{diff_str}"
