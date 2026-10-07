"""
legal_ai/verification/authority_validator.py

Independent Judicial Review Gate for Pakistani Legal Memoranda.
Executes an LLM review at temperature 0 to verify every cited proposition
against retrieved judgment text.
"""

from typing import Dict, List, Any, Optional, Callable
from core.final_review_gate import run_final_review_gate, format_review_gate_fallback

__all__ = [
    "run_final_review_gate",
    "format_review_gate_fallback"
]
