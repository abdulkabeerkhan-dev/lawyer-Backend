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

from legal_ai.verification.doctrinal_rules import (
    PATTERN_RULES,
    classify_matter_type,
    detect_topics,
    rule_matches_sentence,
    build_pre_synthesis_trap_instructions,
)
from legal_ai.verification.statute_matcher import (
    StatuteAuthorityStore,
    get_authority_store,
    normalize_citation,
    find_citations,
    sentences,
    norm_text,
    straighten,
    shingles,
)
from legal_ai.verification.memo_auditor import (
    audit_memo,
    split_cards,
    relevance_for,
    AuditResult,
    Finding,
    RelevanceResult,
    VerificationReport,
)

__all__ = [
    "repair_ocr_citation",
    "parse_pakistan_citation",
    "verify_current_law_for_provisions",
    "format_current_law_context",
    "verify_quotations_in_text",
    "run_final_review_gate",
    "format_review_gate_fallback",
    "PATTERN_RULES",
    "classify_matter_type",
    "detect_topics",
    "rule_matches_sentence",
    "build_pre_synthesis_trap_instructions",
    "StatuteAuthorityStore",
    "get_authority_store",
    "normalize_citation",
    "find_citations",
    "sentences",
    "norm_text",
    "straighten",
    "shingles",
    "audit_memo",
    "split_cards",
    "relevance_for",
    "AuditResult",
    "Finding",
    "RelevanceResult",
    "VerificationReport",
]
