"""
legal_ai/verification
"""

from legal_ai.verification.citation_validator import (
    repair_ocr_citation,
    parse_pakistan_citation
)
from legal_ai.verification.law_currency import (
    verify_current_law_for_provisions,
    format_current_law_context
)
from legal_ai.verification.quote_verifier import verify_quotations_in_text
from legal_ai.verification.authority_validator import (
    run_final_review_gate,
    format_review_gate_fallback
)

__all__ = [
    "repair_ocr_citation",
    "parse_pakistan_citation",
    "verify_current_law_for_provisions",
    "format_current_law_context",
    "verify_quotations_in_text",
    "run_final_review_gate",
    "format_review_gate_fallback"
]
