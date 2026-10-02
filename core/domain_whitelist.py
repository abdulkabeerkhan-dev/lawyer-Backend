"""
Single Source of Truth for Whitelisted Tier 1 Government and Court Domains in Pakistan.

PROVENANCE & DOCUMENTARY SOURCES:
1. Statutory Tier 1 Portals:
   - pakistancode.gov.pk: Official electronic repository of Federal Laws, Ministry of Law and Justice, Govt. of Pakistan.
   - na.gov.pk: National Assembly of Pakistan (official legislative bills and acts repository).
   - senate.gov.pk: Senate of Pakistan (official parliamentary bills and acts repository).
   - punjablaws.gov.pk: Punjab Code, Law and Parliamentary Affairs Department, Govt. of Punjab.
   - sindhlaws.gov.pk: Sindh Code, Law Department, Govt. of Sindh.
   - kpcode.gov.pk / kparchives.gov.pk: Official KP provincial laws repository.
   - balochistan.gov.pk: Government of Balochistan official portal.

2. Judicial Tier 1 Portals (Official Constitutional Courts of Record):
   - supremecourt.gov.pk: Supreme Court of Pakistan (PKNIC / NTC registered official apex repository).
   - federalshariatcourt.gov.pk: Federal Shariat Court of Pakistan (NTC registered official portal under Constitution Art. 203C).
     (Note: fsc.gov.pk is a legacy shorthand redirect; canonical domain is federalshariatcourt.gov.pk).
   - lhc.gov.pk and sys.lhc.gov.pk: Lahore High Court and its Case Management System.
   - shc.gov.pk: High Court of Sindh.
   - phc.gov.pk: Peshawar High Court.
   - ihc.gov.pk: Islamabad High Court.
   - balochistanhighcourt.gov.pk and bhc.gov.pk: High Court of Balochistan.

NOTE ON FCC:
The Federal Constitutional Court was established under the 27th Constitutional Amendment (passed late 2025, hearing cases Nov 2025), not the 26th (which reformed judicial appointments, suo motu powers, and constitutional benches).
The real reason for excluding 'fcc.gov.pk' is that the hostname has not been confirmed or delegated on PKNIC / NTC as an active digital repository.
Speculative hostnames like 'fcc.gov.pk' are strictly excluded from Tier 1 whitelists until verified live with official registry delegation.
"""

import urllib.parse
from typing import Set, Dict, Optional

# Statutory Portals (Federal and Provincial)
STATUTORY_TIER_1_DOMAINS: Set[str] = {
    "pakistancode.gov.pk",
    "na.gov.pk",
    "senate.gov.pk",
    "punjablaws.gov.pk",
    "sindhlaws.gov.pk",
    "kpcode.gov.pk",
    "kparchives.gov.pk",
    "balochistan.gov.pk",
}

# Judicial Portals (Apex and Constitutional High Courts)
COURT_TIER_1_DOMAINS: Set[str] = {
    "supremecourt.gov.pk",
    "federalshariatcourt.gov.pk",
    "fsc.gov.pk",
    "lhc.gov.pk",
    "sys.lhc.gov.pk",
    "shc.gov.pk",
    "caselaw.shc.gov.pk",
    "phc.gov.pk",
    "ihc.gov.pk",
    "balochistanhighcourt.gov.pk",
    "bhc.gov.pk",
}

# Unified Set of All Tier 1 Hostnames
ALL_TIER_1_DOMAINS: Set[str] = STATUTORY_TIER_1_DOMAINS | COURT_TIER_1_DOMAINS

# Mapping from domain to canonical court title
COURT_DOMAIN_NAMES: Dict[str, str] = {
    "supremecourt.gov.pk": "Supreme Court of Pakistan",
    "federalshariatcourt.gov.pk": "Federal Shariat Court",
    "fsc.gov.pk": "Federal Shariat Court",
    "lhc.gov.pk": "Lahore High Court",
    "sys.lhc.gov.pk": "Lahore High Court",
    "shc.gov.pk": "High Court of Sindh",
    "caselaw.shc.gov.pk": "High Court of Sindh",
    "phc.gov.pk": "Peshawar High Court",
    "ihc.gov.pk": "Islamabad High Court",
    "balochistanhighcourt.gov.pk": "High Court of Balochistan",
    "bhc.gov.pk": "High Court of Balochistan",
}


def extract_hostname(url_or_domain: str) -> str:
    """Extracts and normalizes the lowercase hostname from a URL or domain string."""
    if not url_or_domain:
        return ""
    text = str(url_or_domain).strip().lower()
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    try:
        parsed = urllib.parse.urlparse(text)
        netloc = parsed.netloc or parsed.path.split("/")[0]
        netloc = netloc.split(":")[0]  # Remove port if present
        return netloc.lower().strip()
    except Exception:
        return ""


def is_whitelisted_tier1_domain(url_or_domain: str) -> bool:
    """
    Checks if a URL or hostname belongs to a verified Tier 1 government or court domain.
    Prevents subdomain spoofing (e.g. evil.com/?ref=na.gov.pk or na.gov.pk.evil.com).
    """
    hostname = extract_hostname(url_or_domain)
    if not hostname:
        return False
    return any(hostname == d or hostname.endswith("." + d) for d in ALL_TIER_1_DOMAINS)


def is_whitelisted_court_url(url_or_domain: str) -> bool:
    """Checks if a URL belongs to a verified Tier 1 constitutional court repository."""
    hostname = extract_hostname(url_or_domain)
    if not hostname:
        return False
    return any(hostname == d or hostname.endswith("." + d) for d in COURT_TIER_1_DOMAINS)


def derive_court_from_url(url_or_domain: str) -> Optional[str]:
    """Derives canonical court name from a whitelisted court URL."""
    hostname = extract_hostname(url_or_domain)
    for domain, court_name in COURT_DOMAIN_NAMES.items():
        if hostname == domain or hostname.endswith("." + domain):
            return court_name
    return None
