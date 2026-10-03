"""
Quote Attribution Verifier
Phase 2 Component: Verifies direct quotes against retrieved context text,
catches cross-case quote misattribution, and attaches deterministic warning banners.
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any

SIMILARITY_THRESHOLD = 0.85
MIN_QUOTE_LENGTH = 25  # Minimum character length to treat as substantive quotation

from core.legal_guardrails import is_structural_or_title_quote


def normalize_text(text: str) -> str:
    """Normalize text for OCR noise, punctuation differences, and whitespace."""
    if not text:
        return ""
    # Lowercase
    t = text.lower()
    # Normalize smart quotes and dashes
    t = re.sub(r'[\u2018\u2019\u201A\u201B\u2032\u2035]', "'", t)
    t = re.sub(r'[\u201C\u201D\u201E\u201F\u2033\u2036]', '"', t)
    t = re.sub(r'[\u2013\u2014\u2015]', '-', t)
    # Remove all punctuation, leaving alphanumeric and spaces
    t = re.sub(r'[^\w\s]', ' ', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def token_similarity(sub_tokens: List[str], full_tokens: List[str]) -> Tuple[float, int, int]:
    """
    Computes maximum token-level fuzzy match between a sequence of tokens and a larger text.
    Uses sliding window of length len(sub_tokens) +- 20%.
    """
    sub_len = len(sub_tokens)
    if sub_len == 0 or len(full_tokens) == 0:
        return 0.0, 0, 0

    sub_str = " ".join(sub_tokens)
    best_score = 0.0
    best_start = 0
    best_end = 0

    # Step size for sliding window
    step = max(1, sub_len // 4)
    window_sizes = [sub_len, int(sub_len * 1.1), int(sub_len * 0.9)]

    for w_size in window_sizes:
        if w_size <= 0:
            continue
        for i in range(0, max(1, len(full_tokens) - w_size + 1), step):
            window = full_tokens[i:i + w_size]
            win_str = " ".join(window)
            ratio = SequenceMatcher(None, sub_str, win_str).quick_ratio()
            if ratio > best_score:
                # Calculate real ratio if quick_ratio is high enough
                if ratio > 0.7:
                    exact_ratio = SequenceMatcher(None, sub_str, win_str).ratio()
                    if exact_ratio > best_score:
                        best_score = exact_ratio
                        best_start = i
                        best_end = i + w_size
                else:
                    best_score = ratio

            if best_score >= 0.98:
                return best_score, best_start, best_end

    return best_score, best_start, best_end


def fuzzy_contains(quote: str, source_text: str, threshold: float = SIMILARITY_THRESHOLD) -> Tuple[bool, float]:
    """
    Checks if a quote is contained within source_text with similarity >= threshold.
    Handles OCR errors, typographical variations, and small formatting differences.
    """
    norm_quote = normalize_text(quote)
    norm_source = normalize_text(source_text)

    if not norm_quote or not norm_source:
        return False, 0.0

    # 1. Exact substring check (instant match)
    if norm_quote in norm_source:
        return True, 1.0

    quote_tokens = norm_quote.split()
    source_tokens = norm_source.split()

    if len(quote_tokens) < 3:
        # For short tokens, exact match only
        score = SequenceMatcher(None, norm_quote, norm_source).ratio()
        return score >= threshold, score

    score, _, _ = token_similarity(quote_tokens, source_tokens)
    return score >= threshold, score


CITATION_PATTERN = re.compile(
    r'\b(?:(?:PLD|AIR|PLJ|SCMR|CLC|PCrLJ|PTD|PLC|MLD|YLR|CLD|GBLR|KLR)\s+(?:19|20)\d{2}(?:\s+[A-Za-z]+)?|'
    r'(?:19|20)\d{2}\s+(?:PLD|SCMR|CLC|PCrLJ|PTD|PLC|MLD|YLR|CLD|GBLR|KLR|[A-Za-z]+)(?:\s+[A-Za-z]+)?)\s+\d+\b',
    re.IGNORECASE
)


def extract_quotes_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extracts substantive direct quotes and blockquotes from generated text,
    associating each quote with nearby case citations.
    Returns list of dicts: {"quote": ..., "attributed_citation": ..., "start": ..., "end": ...}
    """
    quotes = []

    # 1. Quoted passages in quotation marks ("..." or “...”)
    quote_matches = re.finditer(r'["“]([^"”]{25,})["”]', text)
    for m in quote_matches:
        q_text = m.group(1).strip()
        start_pos = m.start()
        end_pos = m.end()

        # Find nearest citation preceding or succeeding the quote within 300 characters
        preceding = text[max(0, start_pos - 300):start_pos]
        cit_matches = list(CITATION_PATTERN.finditer(preceding))
        if cit_matches:
            attributed_cit = cit_matches[-1].group(0).strip()
        else:
            succeeding = text[end_pos:min(len(text), end_pos + 300)]
            succ_match = CITATION_PATTERN.search(succeeding)
            attributed_cit = succ_match.group(0).strip() if succ_match else None

        quotes.append({
            "quote": q_text,
            "start": start_pos,
            "end": end_pos,
            "attributed_citation": attributed_cit,
            "type": "inline_quote"
        })

    # 2. Markdown blockquotes (> ...)
    for m in re.finditer(r'(?:^|\n)>\s*(.+)', text):
        line_clean = m.group(1).strip()
        if len(line_clean) > MIN_QUOTE_LENGTH + 1:
            q_text = line_clean.lstrip(">").strip()
            q_text = re.sub(r'^["“]|["”]$', '', q_text).strip()
            if len(q_text) >= MIN_QUOTE_LENGTH:
                start_pos = m.start()
                preceding = text[max(0, start_pos - 300):start_pos]
                cit_matches = list(CITATION_PATTERN.finditer(preceding))
                attributed_cit = cit_matches[-1].group(0).strip() if cit_matches else None
                quotes.append({
                    "quote": q_text,
                    "start": start_pos,
                    "end": m.end(),
                    "attributed_citation": attributed_cit,
                    "type": "blockquote"
                })

    return quotes


def verify_quote_attribution(
    quote: str,
    attributed_citation: Optional[str],
    context_payload: Dict[str, str],
    threshold: float = SIMILARITY_THRESHOLD
) -> Dict[str, Any]:
    """
    Verifies a quote against context_payload (dict mapping citation -> text chunk(s)).
    If attributed_citation doesn't contain the quote, checks other cases to detect
    cross-case misattribution (e.g. Farooq Imran vs. Tahir Umar holding).
    """
    if is_structural_or_title_quote(quote):
        return {
            "is_verified": True,
            "status": "structural_or_title",
            "attributed_citation": attributed_citation,
            "matched_citation": None,
            "similarity_score": 1.0,
            "quote": quote,
            "message": "Quote is a structural heading or title phrase."
        }

    # 1. Check primary attributed case
    primary_key = None
    if attributed_citation:
        if attributed_citation in context_payload:
            primary_key = attributed_citation
        else:
            for k in context_payload:
                if k.strip().upper() == attributed_citation.strip().upper():
                    primary_key = k
                    break

    if primary_key:
        source_txt = context_payload[primary_key]
        verified, score = fuzzy_contains(quote, source_txt, threshold)
        if verified:
            return {
                "is_verified": True,
                "status": "verified",
                "attributed_citation": attributed_citation,
                "matched_citation": primary_key,
                "similarity_score": round(score, 4),
                "quote": quote
            }

    # 2. Check all other candidate citations in context payload (misattribution check)
    best_alt_cit = None
    best_alt_score = 0.0

    for cit, txt in context_payload.items():
        if primary_key and cit == primary_key:
            continue
        elif not primary_key and attributed_citation and cit.strip().upper() == attributed_citation.strip().upper():
            continue
        verified, score = fuzzy_contains(quote, txt, threshold)
        if score > best_alt_score:
            best_alt_score = score
            best_alt_cit = cit

    if best_alt_score >= threshold:
        return {
            "is_verified": False,
            "status": "misattributed_corrected",
            "attributed_citation": attributed_citation,
            "matched_citation": best_alt_cit,
            "similarity_score": round(best_alt_score, 4),
            "quote": quote,
            "message": f"Quote was attributed to '{attributed_citation}', but was verified in '{best_alt_cit}'."
        }

    return {
        "is_verified": False,
        "status": "unverified",
        "attributed_citation": attributed_citation,
        "matched_citation": None,
        "similarity_score": round(best_alt_score, 4),
        "quote": quote,
        "message": "Quoted passage could not be verified against any retrieved source text."
    }


def sanitize_unverified_quotes(generated_text: str, unverified_quotes: List[str]) -> str:
    """
    Option A: Silent Sanitization.
    Takes the generated LLM text and a list of unverified quote strings.
    Instead of exposing warning banners, it quietly strips quotation marks 
    from unverified extractions, converting them into smooth, unquoted prose.
    Preserves all surrounding whitespace and token boundaries.
    """
    if not generated_text or not unverified_quotes:
        return generated_text

    sanitized_text = generated_text

    for quote in unverified_quotes:
        if not quote:
            continue

        q_strip = quote.strip()
        if not q_strip:
            continue

        # Safe replacement: replace quotation marks around q_strip while preserving surrounding spaces
        pattern = r'(?<=\S)?\s*["“\'‘]\s*' + re.escape(q_strip) + r'\s*["”\'’]\s*(?=\S)?'

        def _safe_replace(match):
            m_start, m_end = match.span()
            before_char = sanitized_text[m_start - 1] if m_start > 0 else ""
            after_char = sanitized_text[m_end] if m_end < len(sanitized_text) else ""

            lead_space = " " if before_char and before_char not in " \n\t([{“\"\'‘#*`>" else ""
            trail_space = " " if after_char and after_char not in " \n\t.,;:!?)’”\'’]}#*`" else ""
            return f"{lead_space}{q_strip}{trail_space}"

        # Try exact pattern replacement
        if re.search(r'["“\'‘]\s*' + re.escape(q_strip) + r'\s*["”\'’]', sanitized_text):
            sanitized_text = re.sub(pattern, _safe_replace, sanitized_text)
        else:
            # Fallback for exact variants
            for variant in (f'"{quote}"', f'“{quote}”', f"'{quote}'", f'‘{quote}’'):
                if variant in sanitized_text:
                    sanitized_text = sanitized_text.replace(variant, q_strip)

    return sanitized_text


def verify_text_quotes(
    text: str,
    context_payload: Dict[str, str],
    threshold: float = SIMILARITY_THRESHOLD,
    silent_sanitize: bool = False
) -> Dict[str, Any]:
    """
    End-to-end verification of all quotes in generated text against retrieved context.
    Returns audit details, sanitized text (Option A), and a deterministic warning disclosure banner if needed.
    """
    quotes = extract_quotes_from_text(text)
    verified = []
    misattributed = []
    unverified = []

    for q in quotes:
        quote_text = q.get("quote", "")
        if is_structural_or_title_quote(quote_text):
            continue
        result = verify_quote_attribution(
            quote=quote_text,
            attributed_citation=q.get("attributed_citation"),
            context_payload=context_payload,
            threshold=threshold
        )
        if result["status"] == "verified":
            verified.append(result)
        elif result["status"] == "misattributed_corrected":
            misattributed.append(result)
        else:
            unverified.append(result)

    unverified_quote_strings = [u["quote"] for u in unverified if u.get("quote")]
    sanitized_text = sanitize_unverified_quotes(text, unverified_quote_strings)

    warning_banner = None
    if misattributed or (unverified and not silent_sanitize):
        lines = []
        if misattributed:
            lines.append("⚠️ **Quote Attribution Correction**:")
            for m in misattributed:
                q_snippet = m['quote'][:70] + ('...' if len(m['quote']) > 70 else '')
                lines.append(f"- \"{q_snippet}\" was attributed to `{m['attributed_citation']}`, but actually appears in `{m['matched_citation']}`.")

        if unverified and not silent_sanitize:
            lines.append("⚠️ **Unverified Quotation Notice**:")
            for u in unverified:
                q_snippet = u['quote'][:70] + ('...' if len(u['quote']) > 70 else '')
                lines.append(f"- \"{q_snippet}\" could not be verified against the retrieved source judgment text — please confirm before citing in pleadings.")

        warning_banner = "\n".join(lines) if lines else None

    return {
        "verified_count": len(verified),
        "misattributed_count": len(misattributed),
        "unverified_count": len(unverified),
        "verified": verified,
        "misattributed": misattributed,
        "unverified": unverified,
        "sanitized_text": sanitized_text,
        "warning_banner": warning_banner
    }

