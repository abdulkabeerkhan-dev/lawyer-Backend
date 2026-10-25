"""
core/statute_tiers.py

Canonical Enum for Pakistan Legal Research Platform Statute Tiers.
Replaces fragmented, inconsistent string spellings across the codebase.
"""

from enum import Enum

class StatuteTier(str, Enum):
    INGESTED_UNREVIEWED = "ingested_unreviewed"
    PAGE_VERIFIED = "page_verified"
    TITLE_ONLY = "title_only"
    DISPUTED = "disputed"
    REVIEWED = "reviewed"

def normalize_statute_tier(val: str) -> str:
    """Normalizes legacy and inconsistent tier strings to canonical StatuteTier."""
    if not val:
        return StatuteTier.INGESTED_UNREVIEWED.value
    s = str(val).strip().lower()
    if "dispute" in s:
        return StatuteTier.DISPUTED.value
    if "page" in s and "verif" in s:
        return StatuteTier.PAGE_VERIFIED.value
    if "title" in s or s in ("title_only", "title_only_record"):
        return StatuteTier.TITLE_ONLY.value
    if s in ("reviewed", "human_reviewed", "advocate_approved"):
        return StatuteTier.REVIEWED.value
    return StatuteTier.INGESTED_UNREVIEWED.value
