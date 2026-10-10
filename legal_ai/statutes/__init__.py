"""
legal_ai/statutes package
"""

from legal_ai.statutes.statute_injector import (
    StatuteInjector,
    get_statute_injector,
    inject_statutory_framework,
    ENABLE_STATUTE_INJECTION
)

__all__ = [
    "StatuteInjector",
    "get_statute_injector",
    "inject_statutory_framework",
    "ENABLE_STATUTE_INJECTION"
]
