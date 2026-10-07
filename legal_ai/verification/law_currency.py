"""
legal_ai/verification/law_currency.py

Statute currency verification and in-force status checker for Pakistan Code.
"""

from typing import Dict, List, Any
from core.current_law_verifier import (
    verify_current_law_for_provisions,
    format_current_law_context
)

__all__ = [
    "verify_current_law_for_provisions",
    "format_current_law_context"
]
