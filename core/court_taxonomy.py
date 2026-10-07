"""
core/court_taxonomy.py

Canonical controlled vocabulary, temporal boundaries, and normalization
engine for the Pakistani Court and Tribunal taxonomy.

Strict Invariants:
1. Historical courts (Federal Court, High Court of West Pakistan, Dhaka High Court,
   Chief Court of Sind, Privy Council) must retain their historically accurate identities
   and never be force-mapped to modern institutions.
2. Temporal guards enforce court existence dates (e.g. Islamabad High Court >= 2007,
   Federal Shariat Court >= 1980, Supreme Court of Pakistan >= 1956).
3. Pinecone vector metadata must never serve as legal authoritative evidence.
"""

import re
from typing import Optional, Tuple, Dict, Any, List, Set

CANONICAL_COURTS: Dict[str, Dict[str, Any]] = {
    # Apex Courts
    "Supreme Court of Pakistan": {
        "tier": "apex",
        "jurisdiction": "national",
        "established_year": 1956,
        "dissolved_year": None,
        "predecessors": ["Federal Court of Pakistan", "Privy Council"],
        "historical": False,
    },
    "Federal Shariat Court": {
        "tier": "apex_special",
        "jurisdiction": "national",
        "established_year": 1980,
        "dissolved_year": None,
        "predecessors": [],
        "historical": False,
    },
    # Provincial and Territorial High Courts
    "Lahore High Court": {
        "tier": "high_court",
        "jurisdiction": "punjab",
        "established_year": 1866,
        "dissolved_year": None,
        "historical": False,
    },
    "High Court of Sindh": {
        "tier": "high_court",
        "jurisdiction": "sindh",
        "established_year": 1970,
        "dissolved_year": None,
        "predecessors": ["Chief Court of Sind", "High Court of West Pakistan"],
        "historical": False,
    },
    "Peshawar High Court": {
        "tier": "high_court",
        "jurisdiction": "khyber_pakhtunkhwa",
        "established_year": 1970,
        "dissolved_year": None,
        "predecessors": ["Judicial Commissioner's Court NWFP", "High Court of West Pakistan"],
        "historical": False,
    },
    "High Court of Balochistan": {
        "tier": "high_court",
        "jurisdiction": "balochistan",
        "established_year": 1976,
        "dissolved_year": None,
        "predecessors": ["High Court of West Pakistan", "High Court of Sindh and Balochistan"],
        "historical": False,
    },
    "Islamabad High Court": {
        "tier": "high_court",
        "jurisdiction": "islamabad_capital_territory",
        "established_year": 2007,
        "dissolved_year": None,
        "predecessors": ["Lahore High Court (Rawalpindi Bench)"],
        "historical": False,
    },
    # Azad Jammu & Kashmir Courts
    "Supreme Court of Azad Jammu and Kashmir": {
        "tier": "apex",
        "jurisdiction": "ajk",
        "established_year": 1974,
        "dissolved_year": None,
        "historical": False,
    },
    "High Court of Azad Jammu and Kashmir": {
        "tier": "high_court",
        "jurisdiction": "ajk",
        "established_year": 1948,
        "dissolved_year": None,
        "historical": False,
    },
    # Gilgit-Baltistan Courts
    "Supreme Appellate Court Gilgit-Baltistan": {
        "tier": "apex",
        "jurisdiction": "gilgit_baltistan",
        "established_year": 2009,
        "dissolved_year": None,
        "historical": False,
    },
    "Chief Court Gilgit-Baltistan": {
        "tier": "high_court",
        "jurisdiction": "gilgit_baltistan",
        "established_year": 2009,
        "dissolved_year": None,
        "historical": False,
    },
    # Statutory Service Tribunals
    "Federal Service Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "federal",
        "established_year": 1973,
        "dissolved_year": None,
        "historical": False,
    },
    "Punjab Service Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "punjab",
        "established_year": 1974,
        "dissolved_year": None,
        "historical": False,
    },
    "Sindh Service Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "sindh",
        "established_year": 1973,
        "dissolved_year": None,
        "historical": False,
    },
    "Khyber Pakhtunkhwa Service Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "khyber_pakhtunkhwa",
        "established_year": 1974,
        "dissolved_year": None,
        "historical": False,
    },
    "Balochistan Service Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "balochistan",
        "established_year": 1974,
        "dissolved_year": None,
        "historical": False,
    },
    # Specialized Labor & Commercial Tribunals
    "Labour Appellate Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "provincial",
        "established_year": 1969,
        "dissolved_year": None,
        "historical": False,
    },
    "Banking Court": {
        "tier": "special_court",
        "jurisdiction": "national",
        "established_year": 1979,
        "dissolved_year": None,
        "historical": False,
    },
    "Board of Revenue": {
        "tier": "revenue_tribunal",
        "jurisdiction": "provincial",
        "established_year": 1955,
        "dissolved_year": None,
        "historical": False,
    },
    "Election Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "national",
        "established_year": 1976,
        "dissolved_year": None,
        "historical": False,
    },
    "Income Tax Appellate Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "federal",
        "established_year": 1941,
        "dissolved_year": None,
        "historical": False,
    },
    "Customs Appellate Tribunal": {
        "tier": "tribunal",
        "jurisdiction": "federal",
        "established_year": 1969,
        "dissolved_year": None,
        "historical": False,
    },
    "Accountability Court": {
        "tier": "special_court",
        "jurisdiction": "federal",
        "established_year": 1999,
        "dissolved_year": None,
        "historical": False,
    },
    # Historical Courts (MUST NEVER be force-mapped to modern equivalents)
    "Federal Court of Pakistan": {
        "tier": "apex",
        "jurisdiction": "national",
        "established_year": 1947,
        "dissolved_year": 1956,
        "successors": ["Supreme Court of Pakistan"],
        "historical": True,
    },
    "High Court of West Pakistan": {
        "tier": "high_court",
        "jurisdiction": "west_pakistan",
        "established_year": 1955,
        "dissolved_year": 1970,
        "successors": ["Lahore High Court", "High Court of Sindh", "Peshawar High Court", "High Court of Balochistan"],
        "historical": True,
    },
    "Dhaka High Court": {
        "tier": "high_court",
        "jurisdiction": "east_pakistan",
        "established_year": 1947,
        "dissolved_year": 1971,
        "successors": ["Supreme Court of Bangladesh"],
        "historical": True,
    },
    "Chief Court of Sind": {
        "tier": "high_court",
        "jurisdiction": "sindh",
        "established_year": 1906,
        "dissolved_year": 1955,
        "successors": ["High Court of West Pakistan"],
        "historical": True,
    },
    "Privy Council": {
        "tier": "apex",
        "jurisdiction": "empire",
        "established_year": 1833,
        "dissolved_year": 1950,
        "successors": ["Federal Court of Pakistan"],
        "historical": True,
    },
    # Foreign / Historical Comparative Courts
    "Supreme Court of India": {
        "tier": "foreign_apex",
        "jurisdiction": "india",
        "established_year": 1950,
        "dissolved_year": None,
        "historical": True,
    },
    "High Court of Judicature Baghdad-ul-Jadid": {
        "tier": "high_court",
        "jurisdiction": "bahawalpur",
        "established_year": 1943,
        "dissolved_year": 1955,
        "successors": ["High Court of West Pakistan"],
        "historical": True,
    },
}


HISTORICAL_COURT_NAMES: Set[str] = {
    name for name, meta in CANONICAL_COURTS.items() if meta.get("historical", False)
}

# Normalization alias map: raw string pattern -> Canonical Name
EXACT_ALIAS_MAP: Dict[str, str] = {
    # Supreme Court
    "supreme court of pakistan": "Supreme Court of Pakistan",
    "supreme court": "Supreme Court of Pakistan",
    "sc": "Supreme Court of Pakistan",
    "scp": "Supreme Court of Pakistan",
    "in the supreme court of pakistan": "Supreme Court of Pakistan",
    "supreme-court-of-pakistan": "Supreme Court of Pakistan",
    # Federal Shariat Court
    "federal shariat court": "Federal Shariat Court",
    "federal shariat court of pakistan": "Federal Shariat Court",
    "fsc": "Federal Shariat Court",
    "federal-shariat-court": "Federal Shariat Court",
    # Lahore High Court
    "lahore high court": "Lahore High Court",
    "lahore high court, lahore": "Lahore High Court",
    "lahore high court lahore": "Lahore High Court",
    "lahore-high-court": "Lahore High Court",
    "lahore-high-court-lahore": "Lahore High Court",
    "lhc": "Lahore High Court",
    "lahore high court rawalpindi bench": "Lahore High Court",
    "lahore high court multan bench": "Lahore High Court",
    "lahore high court bahawalpur bench": "Lahore High Court",
    # Sindh High Court
    "high court of sindh": "High Court of Sindh",
    "sindh high court": "High Court of Sindh",
    "high court of sindh, karachi": "High Court of Sindh",
    "high court of sindh karachi": "High Court of Sindh",
    "karachi-high-court-sindh": "High Court of Sindh",
    "shc": "High Court of Sindh",
    "sindh high court sukkur bench": "High Court of Sindh",
    "sindh high court circuit bench hyderabad": "High Court of Sindh",
    "sindh high court circuit bench larkana": "High Court of Sindh",
    # Peshawar High Court
    "peshawar high court": "Peshawar High Court",
    "peshawar high court, peshawar": "Peshawar High Court",
    "peshawar high court peshawar": "Peshawar High Court",
    "peshawar-high-court": "Peshawar High Court",
    "peshawar-high-court-peshawar": "Peshawar High Court",
    "phc": "Peshawar High Court",
    "peshawar high court abbottabad bench": "Peshawar High Court",
    "peshawar high court mingora bench": "Peshawar High Court",
    "peshawar high court d.i. khan bench": "Peshawar High Court",
    # Balochistan High Court
    "high court of balochistan": "High Court of Balochistan",
    "balochistan high court": "High Court of Balochistan",
    "high court of balochistan, quetta": "High Court of Balochistan",
    "quetta-high-court-balochistan": "High Court of Balochistan",
    "bhc": "High Court of Balochistan",
    "high court of balochistan sibi bench": "High Court of Balochistan",
    # Islamabad High Court
    "islamabad high court": "Islamabad High Court",
    "islamabad high court, islamabad": "Islamabad High Court",
    "islamabad high court islamabad": "Islamabad High Court",
    "ihc": "Islamabad High Court",
    "islamabad-high-court": "Islamabad High Court",
    # AJK Courts
    "supreme court of azad jammu and kashmir": "Supreme Court of Azad Jammu and Kashmir",
    "supreme court of azad jammu & kashmir": "Supreme Court of Azad Jammu and Kashmir",
    "supreme court of ajk": "Supreme Court of Azad Jammu and Kashmir",
    "supreme court ajk": "Supreme Court of Azad Jammu and Kashmir",
    "sc ajk": "Supreme Court of Azad Jammu and Kashmir",
    "ajk sc": "Supreme Court of Azad Jammu and Kashmir",
    "aj&k sc": "Supreme Court of Azad Jammu and Kashmir",
    "high court of azad jammu and kashmir": "High Court of Azad Jammu and Kashmir",
    "high court of azad jammu & kashmir": "High Court of Azad Jammu and Kashmir",
    "high court of ajk": "High Court of Azad Jammu and Kashmir",
    "ajk high court": "High Court of Azad Jammu and Kashmir",
    "ajk hc": "High Court of Azad Jammu and Kashmir",
    # Gilgit-Baltistan Courts
    "supreme appellate court gilgit-baltistan": "Supreme Appellate Court Gilgit-Baltistan",
    "supreme appellate court gb": "Supreme Appellate Court Gilgit-Baltistan",
    "chief court gilgit-baltistan": "Chief Court Gilgit-Baltistan",
    "chief court gb": "Chief Court Gilgit-Baltistan",
    "high court gilgit-baltistan": "Chief Court Gilgit-Baltistan",
    # Federal Service Tribunal
    "federal service tribunal": "Federal Service Tribunal",
    "federal service tribunal islamabad": "Federal Service Tribunal",
    "federal service tribunal karachi": "Federal Service Tribunal",
    "federal service tribunal lahore": "Federal Service Tribunal",
    "fst": "Federal Service Tribunal",
    # Provincial Service Tribunals
    "punjab service tribunal": "Punjab Service Tribunal",
    "service tribunal punjab": "Punjab Service Tribunal",
    "pst": "Punjab Service Tribunal",
    "sindh service tribunal": "Sindh Service Tribunal",
    "service tribunal sindh": "Sindh Service Tribunal",
    "sst": "Sindh Service Tribunal",
    "khyber pakhtunkhwa service tribunal": "Khyber Pakhtunkhwa Service Tribunal",
    "kp service tribunal": "Khyber Pakhtunkhwa Service Tribunal",
    "nwfp service tribunal": "Khyber Pakhtunkhwa Service Tribunal",
    "service tribunal nwfp": "Khyber Pakhtunkhwa Service Tribunal",
    "balochistan service tribunal": "Balochistan Service Tribunal",
    "service tribunal balochistan": "Balochistan Service Tribunal",
    "bst": "Balochistan Service Tribunal",
    # Labor & Banking
    "punjab labour appellate tribunal": "Labour Appellate Tribunal",
    "sindh labour appellate tribunal": "Labour Appellate Tribunal",
    "labour appellate tribunal": "Labour Appellate Tribunal",
    "labour court": "Labour Appellate Tribunal",
    "banking court": "Banking Court",
    # Revenue & Elections
    "board of revenue": "Board of Revenue",
    "west-pakistan-board-of-revenue": "Board of Revenue",
    "board of revenue punjab": "Board of Revenue",
    "board of revenue sindh": "Board of Revenue",
    "election tribunal": "Election Tribunal",
    "income tax appellate tribunal": "Income Tax Appellate Tribunal",
    "income-tax-appellate-tribunal-lahore": "Income Tax Appellate Tribunal",
    "income-tax-appellate-tribunal-pakistan": "Income Tax Appellate Tribunal",
    "customs appellate tribunal": "Customs Appellate Tribunal",
    "accountability court": "Accountability Court",
    # Historical Courts - Preserved Exactly
    "federal court of pakistan": "Federal Court of Pakistan",
    "federal court": "Federal Court of Pakistan",
    "federal-court-of-pakistan": "Federal Court of Pakistan",
    "high court of west pakistan": "High Court of West Pakistan",
    "west pakistan high court": "High Court of West Pakistan",
    "high court west pakistan": "High Court of West Pakistan",
    "dhaka high court": "Dhaka High Court",
    "high court of dacca": "Dhaka High Court",
    "dacca high court": "Dhaka High Court",
    "high court of east pakistan": "Dhaka High Court",
    "- dhaka-high-court": "Dhaka High Court",
    "chief court of sind": "Chief Court of Sind",
    "chief court of sindh": "Chief Court of Sind",
    "sind chief court": "Chief Court of Sind",
    "privy council": "Privy Council",
    "privy-council": "Privy Council",
    "judicial committee of the privy council": "Privy Council",
    # Foreign / Historical Comparative Courts
    "supreme court of india": "Supreme Court of India",
    "supreme-court-india": "Supreme Court of India",
    "supreme court india": "Supreme Court of India",
    # Azad Jammu & Kashmir aliases
    "supreme court azad kashmir": "Supreme Court of Azad Jammu and Kashmir",
    "supreme-court-azad-kashmir": "Supreme Court of Azad Jammu and Kashmir",
    "supreme-court-azad-jammu-and-kashmir": "Supreme Court of Azad Jammu and Kashmir",
    "azad kashmir supreme court": "Supreme Court of Azad Jammu and Kashmir",
    "high court azad kashmir": "High Court of Azad Jammu and Kashmir",
    "high-court-azad-kashmir": "High Court of Azad Jammu and Kashmir",
    # Historical Bahawalpur Courts & Revenue
    "high court of judicature baghdad-ul-jadid": "High Court of Judicature Baghdad-ul-Jadid",
    "high court of judicature baghdad ul jadid": "High Court of Judicature Baghdad-ul-Jadid",
    "high court of baghdad-ul-jadid": "High Court of Judicature Baghdad-ul-Jadid",
    "high court baghdad-ul-jadid": "High Court of Judicature Baghdad-ul-Jadid",
    "baghdad-ul-jadid": "High Court of Judicature Baghdad-ul-Jadid",
    "baghdad ul jadid": "High Court of Judicature Baghdad-ul-Jadid",
    "revenue-decision-punjab": "Board of Revenue",
    "revenue decision punjab": "Board of Revenue",
}


# Generic / placeholder values that represent lack of specific court identity
GENERIC_COURT_PLACEHOLDERS: Set[str] = {
    "court of record",
    "court not identified",
    "high court",
    "superior courts",
    "unresolved",
    "unknown",
    "",
}

def normalize_text_key(s: str) -> str:
    """Normalize text by stripping whitespace, lowercasing, and consolidating separators."""
    if not s:
        return ""
    clean = s.strip().lower()
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = re.sub(r'[\s\.\,\;\:\-\_\/\\\[\]\(\)\'\"]+', ' ', clean)
    return ' '.join(clean.split())

def resolve_canonical_court(raw_name: Optional[str]) -> Optional[str]:
    """
    Resolve any raw court string to its canonical taxonomy name.
    Preserves historical courts; returns None if generic placeholder or unparseable.
    """
    if not raw_name:
        return None
    
    clean = raw_name.strip()
    norm = normalize_text_key(clean)
    
    if norm in GENERIC_COURT_PLACEHOLDERS:
        return None
    
    # 1. Direct match with exact alias map
    if norm in EXACT_ALIAS_MAP:
        return EXACT_ALIAS_MAP[norm]
    
    # 2. Check canonical names directly (case-insensitive)
    for c_name in CANONICAL_COURTS:
        if normalize_text_key(c_name) == norm:
            return c_name
            
    # 3. Handle prefix/bench variants
    # Check historical courts first so they aren't subsumed by general High Court patterns
    if "west pakistan" in norm and ("high court" in norm or "court" in norm):
        return "High Court of West Pakistan"
    if ("dacca" in norm or "dhaka" in norm or "east pakistan" in norm) and "high court" in norm:
        return "Dhaka High Court"
    if "federal court" in norm:
        return "Federal Court of Pakistan"
    if "chief court" in norm and ("sind" in norm or "sindh" in norm):
        return "Chief Court of Sind"
    if "privy council" in norm:
        return "Privy Council"
    if "baghdad-ul-jadid" in norm or "baghdad ul jadid" in norm or "baghdad-ul-jdid" in norm:
        return "High Court of Judicature Baghdad-ul-Jadid"
        
    # Foreign / Regional Apex Courts (must precede generic supreme court match)
    if "india" in norm and ("supreme" in norm or "court" in norm):
        return "Supreme Court of India"


    if "azad kashmir" in norm or "azad jammu" in norm or "ajk" in norm or "aj&k" in norm:
        if "supreme" in norm:
            return "Supreme Court of Azad Jammu and Kashmir"
        if "high court" in norm or "chief" in norm or "court" in norm:
            return "High Court of Azad Jammu and Kashmir"
            
    if "gilgit" in norm or "baltistan" in norm:
        if "supreme" in norm:
            return "Supreme Appellate Court Gilgit-Baltistan"
        if "chief" in norm or "high court" in norm:
            return "Chief Court Gilgit-Baltistan"
            
    # Supreme Court of Pakistan (strictly guarded against foreign/AJK matches)
    if "supreme court" in norm and not ("india" in norm or "azad" in norm or "kashmir" in norm or "ajk" in norm):
        return "Supreme Court of Pakistan"
    if "federal shariat" in norm:
        return "Federal Shariat Court"
    if "islamabad" in norm and "high court" in norm:
        return "Islamabad High Court"
    if "lahore" in norm and "high court" in norm:
        return "Lahore High Court"
    if ("sindh" in norm or "karachi" in norm) and "high court" in norm:
        return "High Court of Sindh"
    if "peshawar" in norm and "high court" in norm:
        return "Peshawar High Court"
    if ("balochistan" in norm or "quetta" in norm) and "high court" in norm:
        return "High Court of Balochistan"
        
    # Tribunals
    if "federal service tribunal" in norm or norm == "fst":
        return "Federal Service Tribunal"
    if "punjab service tribunal" in norm or "service tribunal punjab" in norm:
        return "Punjab Service Tribunal"
    if "sindh service tribunal" in norm or "service tribunal sindh" in norm:
        return "Sindh Service Tribunal"
    if "labour appellate" in norm or "labour court" in norm:
        return "Labour Appellate Tribunal"
    if "banking court" in norm:
        return "Banking Court"
    if "board of revenue" in norm:
        return "Board of Revenue"
    if "income tax appellate" in norm or "income-tax-appellate" in norm:
        return "Income Tax Appellate Tribunal"
    if "election tribunal" in norm:
        return "Election Tribunal"
        
    return None

def is_historical_court(canonical_name: str) -> bool:
    """Check if a canonical court is a historical institution."""
    return canonical_name in HISTORICAL_COURT_NAMES

def validate_court_temporal_bounds(
    canonical_name: str,
    decision_year: Optional[int]
) -> Tuple[bool, Optional[str]]:
    """
    Validates whether a proposed canonical court was temporally active during decision_year.
    Returns (True, None) if valid or year is unknown.
    Returns (False, reason) if decision_year falls outside institutional existence.
    """
    if not decision_year:
        return True, None
        
    meta = CANONICAL_COURTS.get(canonical_name)
    if not meta:
        return True, None
        
    est_year = meta.get("established_year")
    diss_year = meta.get("dissolved_year")
    
    # Specific historical period guards:
    # 1. Islamabad High Court (cannot exist prior to 2007)
    if canonical_name == "Islamabad High Court" and decision_year < 2007:
        return False, (
            f"Temporal mismatch: Islamabad High Court was created in 2007/2010; "
            f"judgment year is {decision_year} (predecessor was Lahore High Court Rawalpindi Bench)."
        )
        
    # 2. Federal Shariat Court (cannot exist prior to 1980)
    if canonical_name == "Federal Shariat Court" and decision_year < 1980:
        return False, (
            f"Temporal mismatch: Federal Shariat Court was established in 1980; "
            f"judgment year is {decision_year}."
        )
        
    # 3. Supreme Court of Pakistan (1956 Constitution onwards)
    if canonical_name == "Supreme Court of Pakistan" and decision_year < 1956:
        return False, (
            f"Temporal mismatch: Supreme Court of Pakistan was created March 23, 1956; "
            f"pre-1956 apex decisions ({decision_year}) belong to Federal Court of Pakistan or Privy Council."
        )
        
    # 4. Federal Court of Pakistan (1947 to 1956)
    if canonical_name == "Federal Court of Pakistan" and (decision_year < 1947 or decision_year > 1956):
        return False, (
            f"Temporal mismatch: Federal Court of Pakistan operated 1947-1956; "
            f"judgment year is {decision_year}."
        )
        
    # 5. High Court of West Pakistan (One Unit: 1955 to 1970)
    if canonical_name == "High Court of West Pakistan" and (decision_year < 1955 or decision_year > 1970):
        return False, (
            f"Temporal mismatch: High Court of West Pakistan existed 1955-1970; "
            f"judgment year is {decision_year}."
        )
        
    # 6. Dhaka High Court (1947 to 1971)
    if canonical_name == "Dhaka High Court" and (decision_year < 1947 or decision_year > 1971):
        return False, (
            f"Temporal mismatch: Dhaka High Court existed 1947-1971; "
            f"judgment year is {decision_year}."
        )
        
    # 7. High Court of Balochistan (created Dec 1976)
    if canonical_name == "High Court of Balochistan" and decision_year < 1976:
        return False, (
            f"Temporal mismatch: High Court of Balochistan was established in 1976; "
            f"judgment year is {decision_year}."
        )
        
    # 8. Supreme Court of India (1950 onwards)
    if canonical_name == "Supreme Court of India" and decision_year < 1950:
        return False, (
            f"Temporal mismatch: Supreme Court of India was established in 1950; "
            f"judgment year is {decision_year}."
        )

    # 9. Supreme Court of Azad Jammu and Kashmir (1974 onwards)
    if canonical_name == "Supreme Court of Azad Jammu and Kashmir" and decision_year < 1974:
        return False, (
            f"Temporal mismatch: Supreme Court of Azad Jammu and Kashmir was established in 1974; "
            f"judgment year is {decision_year}."
        )

    # General bounds check
    if est_year and decision_year < est_year:
        return False, f"Temporal mismatch: {canonical_name} established in {est_year}; judgment year is {decision_year}."
        
    if diss_year and decision_year > diss_year:
        return False, f"Temporal mismatch: {canonical_name} dissolved in {diss_year}; judgment year is {decision_year}."
        
    return True, None

def is_cross_jurisdiction_or_historical_boundary(court_a: Optional[str], court_b: Optional[str]) -> bool:
    """
    Checks if a transition between court_a and court_b crosses jurisdictional boundaries
    (e.g. Pakistan vs AJK, Pakistan vs India) or historical boundaries (e.g. historical vs modern).
    """
    if not court_a or not court_b or court_a == court_b:
        return False
        
    c1 = resolve_canonical_court(court_a) or court_a
    c2 = resolve_canonical_court(court_b) or court_b
    if c1 == c2:
        return False
        
    # 1. Foreign / Territorial Jurisdiction Crossings
    is_ajk_1 = "Azad Jammu and Kashmir" in c1 or "Azad Kashmir" in c1
    is_ajk_2 = "Azad Jammu and Kashmir" in c2 or "Azad Kashmir" in c2
    if is_ajk_1 != is_ajk_2:
        return True
        
    is_india_1 = "India" in c1
    is_india_2 = "India" in c2
    if is_india_1 != is_india_2:
        return True
        
    is_gb_1 = "Gilgit-Baltistan" in c1
    is_gb_2 = "Gilgit-Baltistan" in c2
    if is_gb_1 != is_gb_2:
        return True
        
    # 2. Historical Institution vs Modern Institution Crossings
    h1 = is_historical_court(c1)
    h2 = is_historical_court(c2)
    if h1 != h2:
        return True
        
    # 3. Two different historical institutions (e.g. Federal Court of Pakistan vs Chief Court of Sind)
    if h1 and h2 and c1 != c2:
        return True
        
    # 4. Institutional Tier Mismatches (e.g., Tribunal / Board of Revenue vs Superior Court)
    t1 = CANONICAL_COURTS.get(c1, {}).get("tier")
    t2 = CANONICAL_COURTS.get(c2, {}).get("tier")
    if (t1 in ("revenue_tribunal", "tribunal") and t2 in ("high_court", "apex")) or \
       (t2 in ("revenue_tribunal", "tribunal") and t1 in ("high_court", "apex")):
        return True

    return False

def get_effective_court(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Resolve the runtime effective court for a case record.
    Prioritizes verified canonical_court_name over legacy court_name/court fields.
    Guarantees that downstream subsystems (authority weighting, jurisdiction filtering,
    prompt context, client cards, document export) see the canonical court identity.
    """
    if not record or not isinstance(record, dict):
        return None
    return (
        record.get("canonical_court_name")
        or record.get("court_name")
        or record.get("court")
    )


# ---------------------------------------------------------------------------
# Central Authoritative Judicial Hierarchy & Precedent Weights
# ---------------------------------------------------------------------------
COURT_AUTHORITY_WEIGHTS: Dict[str, float] = {
    "supreme_court": 1.35,
    "high_court": 1.10,
    "tribunal": 0.95,
    "neutral": 1.0,
}


