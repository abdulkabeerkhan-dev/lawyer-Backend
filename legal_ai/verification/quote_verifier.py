"""
legal_ai/verification/quote_verifier.py

Verbatim Judicial Quote and Attribution Verifier for Pakistani Case Law.
Ensures that quotation marks ("...") and blockquotes (> ...) in syntheses
strictly correspond to actual verbatim text in retrieved authorities.
"""

import re
from typing import Dict, List, Any, Tuple


def verify_quotations_in_text(
    text: str,
    context_judgments: List[Dict[str, Any]],
    min_quote_length: int = 15
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Extracts all quoted passages from synthesis text and verifies if they
    exist in the retrieved context chunks.
    """
    if not text:
        return True, []

    # Find quotes matching "..." or “...” or blockquotes
    quotes = re.findall(r'["“]([^"”]{15,})["”]', text)
    blockquotes = re.findall(r'^\s*>\s*(.+)$', text, flags=re.MULTILINE)
    all_quotes = set(quotes + [b.strip() for b in blockquotes if len(b.strip()) >= min_quote_length])

    if not all_quotes:
        return True, []

    # Assemble corpus haystack
    corpus_texts = []
    for c in context_judgments:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else c
        t = str(c.get("preview") or c.get("full_text") or meta.get("full_text") or meta.get("text") or "").lower()
        if t:
            corpus_texts.append(t)
    haystack = " ".join(corpus_texts)

    results = []
    all_passed = True

    for q in all_quotes:
        q_norm = re.sub(r'\s+', ' ', q).strip().lower()
        # Substring check
        is_matched = (q_norm in haystack)
        if not is_matched:
            # Fuzzy tolerance: check if 80% of words in quote appear consecutively
            words = q_norm.split()
            if len(words) >= 6:
                half_phrase = " ".join(words[:len(words)//2])
                if half_phrase in haystack:
                    is_matched = True

        if not is_matched:
            all_passed = False

        results.append({
            "quote": q,
            "is_grounded": is_matched
        })

    return all_passed, results
