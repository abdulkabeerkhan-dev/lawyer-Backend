"""
legal_ai/synthesis
"""

from legal_ai.synthesis.memorandum_generator import (
    REQUIRED_12_FIELDS,
    purge_debug_warnings,
    sanitize_precedent_card,
    enforce_judgment_first_boundaries,
    query_requests_strategy,
    PROHIBITED_JUDGMENT_FIRST_SECTIONS,
    enforce_holding_attribution,
    is_headnote_only_card,
    classify_precedent_authority_level,
    get_authority_classification_tag,
    filter_and_cap_authorities,
    check_missing_statutory_source,
    enforce_missing_statutory_source_warning,
    enforce_proposition_confidence_guardrails,
    log_runtime_diagnostic,
)

__all__ = [
    "REQUIRED_12_FIELDS",
    "purge_debug_warnings",
    "sanitize_precedent_card",
    "enforce_judgment_first_boundaries",
    "query_requests_strategy",
    "PROHIBITED_JUDGMENT_FIRST_SECTIONS",
    "enforce_holding_attribution",
    "is_headnote_only_card",
    "classify_precedent_authority_level",
    "get_authority_classification_tag",
    "filter_and_cap_authorities",
    "check_missing_statutory_source",
    "enforce_missing_statutory_source_warning",
    "enforce_proposition_confidence_guardrails",
    "log_runtime_diagnostic",
]
