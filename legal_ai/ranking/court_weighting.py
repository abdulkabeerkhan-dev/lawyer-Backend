"""
legal_ai/ranking/court_weighting.py

Single source of truth for Pakistani Court Taxonomy, Judicial Hierarchy,
and Authority Weight Coefficients under Articles 189 and 201 of the Constitution of Pakistan.
"""

import re
from typing import Dict, Any, Optional

# Constitutional Hierarchy Weights:
# Article 189: Supreme Court decisions binding on all other courts in Pakistan.
# Article 201: High Court decisions binding on all subordinate courts within its province.
COURT_TIERS: Dict[str, float] = {
    "supreme_court": 1.00,
    "high_court": 0.85,
    "federal_shariat": 0.80,
    "appellate_tribunal": 0.70,
    "subordinate_court": 0.50,
    "unknown": 0.40
}

COURT_CANONICAL_NAMES: Dict[str, str] = {
    "supreme court of pakistan": "Supreme Court of Pakistan",
    "sc": "Supreme Court of Pakistan",
    "lahore high court": "Lahore High Court",
    "lhc": "Lahore High Court",
    "high court of sindh": "High Court of Sindh",
    "sindh high court": "High Court of Sindh",
    "shc": "High Court of Sindh",
    "peshawar high court": "Peshawar High Court",
    "phc": "Peshawar High Court",
    "islamabad high court": "Islamabad High Court",
    "ihc": "Islamabad High Court",
    "high court of balochistan": "High Court of Balochistan",
    "balochistan high court": "High Court of Balochistan",
    "bhc": "High Court of Balochistan",
    "federal shariat court": "Federal Shariat Court",
    "fsc": "Federal Shariat Court"
}


def normalize_court_name(raw_name: str) -> str:
    """Normalizes raw or abbreviated court names into standard official title."""
    if not raw_name:
        return "Supreme Court of Pakistan"
    clean = str(raw_name).strip()
    low = clean.lower()

    if "supreme court" in low or low == "sc":
        return "Supreme Court of Pakistan"
    if "lahore" in low or low == "lhc":
        return "Lahore High Court"
    if "sindh" in low or low == "shc":
        return "High Court of Sindh"
    if "peshawar" in low or low == "phc":
        return "Peshawar High Court"
    if "islamabad" in low or low == "ihc":
        return "Islamabad High Court"
    if "balochistan" in low or low == "bhc":
        return "High Court of Balochistan"
    if "shariat" in low or low == "fsc":
        return "Federal Shariat Court"
    return clean


def get_court_hierarchy_weight(court_name: str) -> float:
    """
    Returns judicial weight coefficient (0.0 to 1.0) based on Pakistani court hierarchy.
    Supreme Court = 1.0, High Courts = 0.85, Tribunals = 0.70.
    """
    if not court_name:
        return 0.85
    low = str(court_name).lower()
    if "supreme court" in low:
        return COURT_TIERS["supreme_court"]
    if "high court" in low:
        return COURT_TIERS["high_court"]
    if "shariat" in low:
        return COURT_TIERS["federal_shariat"]
    if any(t in low for t in ["tribunal", "appellate", "service", "banking court", "accountability"]):
        return COURT_TIERS["appellate_tribunal"]
    if any(s in low for s in ["session", "district", "magistrate", "civil judge", "family court"]):
        return COURT_TIERS["subordinate_court"]
    return COURT_TIERS["high_court"]


def get_recency_weight(year: Optional[int], current_year: int = 2026) -> float:
    """
    Computes temporal freshness weight for precedents.
    Recent judgments receive subtle precedence, while seminal older precedents remain valid.
    """
    if not year or year < 1947:
        return 0.75
    age = max(0, current_year - year)
    if age <= 3:
        return 1.00
    elif age <= 10:
        return 0.95
    elif age <= 20:
        return 0.90
    elif age <= 35:
        return 0.85
    else:
        return 0.80
