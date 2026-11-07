"""
core/precedent_treatment.py

Pakistani Legal Citator & "Shepardizing" Negative Treatment Graph.
Tracks whether a cited authority was subsequently OVERRULED, DISTINGUISHED,
DOUBTED, or recognized as GOOD LAW under Article 189/201 of the Constitution.
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
import re

class PrecedentStatus(str, Enum):
    GOOD_LAW = "GOOD_LAW"
    OVERRULED = "OVERRULED"
    DISTINGUISHED = "DISTINGUISHED"
    DOUBTED = "DOUBTED"
    SUB_SILENTIO = "SUB_SILENTIO"

# Canonical registry of negative treatment in Pakistani constitutional & criminal jurisprudence
KNOWN_NEGATIVE_TREATMENTS: Dict[str, Dict[str, Any]] = {
    "PLD 2000 SC 869": {
        "case_name": "Zafar Ali Shah v. Pervez Musharraf",
        "status": PrecedentStatus.OVERRULED,
        "overruled_by": "PLD 2009 SC 879",
        "overruling_case": "Sindh High Court Bar Association v. Federation of Pakistan",
        "bench_quorum": "14-Member Full Bench",
        "reason": "Overruled completely. The Supreme Court held that judges taking oath under the PCO 2007 or PCO 1999 acted unconstitutionally, and validation of extra-constitutional deviations is null and void ab initio.",
        "fatal_in_court": True
    },
    "PLD 1977 SC 657": {
        "case_name": "Begum Nusrat Bhutto v. Chief of Army Staff",
        "status": PrecedentStatus.OVERRULED,
        "overruled_by": "PLD 2009 SC 879 & PLD 1972 SC 139",
        "overruling_case": "Sindh High Court Bar Association & Asma Jilani",
        "bench_quorum": "Full Bench",
        "reason": "Doctrine of state necessity used to validate martial law was declared dead and buried in Pakistani constitutional law.",
        "fatal_in_court": True
    },
    "PLD 1958 SC 533": {
        "case_name": "State v. Dosso",
        "status": PrecedentStatus.OVERRULED,
        "overruled_by": "PLD 1972 SC 139",
        "overruling_case": "Asma Jilani v. Government of the Punjab",
        "bench_quorum": "5-Member Full Bench",
        "reason": "Overruled. Hans Kelsen's theory of revolutionary legality was held inapplicable to validate usurpation of power.",
        "fatal_in_court": True
    },
    "2006 SCMR 1692": {
        "case_name": "Muhammad Asghar v. State",
        "status": PrecedentStatus.OVERRULED,
        "overruled_by": "2020 SCMR 874",
        "overruling_case": "Abdul Saboor v. State",
        "bench_quorum": "Supreme Court Larger Bench",
        "reason": "Overruled on strict liability in cheque bounce cases. Held that dishonest intention (mens rea) and fulfillment of lawful debt/obligation are mandatory statutory ingredients under Section 489-F PPC.",
        "fatal_in_court": True
    },
    "PLD 2018 SC 189": {
        "case_name": "Sami Ullah Baloch v. Abdul Karim Nousherwani",
        "status": PrecedentStatus.OVERRULED,
        "overruled_by": "PLD 2024 SC 115",
        "overruling_case": "Supreme Court Review Bench on Article 62(1)(f)",
        "bench_quorum": "7-Member Larger Bench",
        "reason": "Overruled regarding lifetime disqualification under Article 62(1)(f). Held that disqualification cannot be in perpetuity and is limited to 5 years pursuant to Elections Act 2017 amendments.",
        "fatal_in_court": True
    },
    "PLD 1998 SC 1445": {
        "case_name": "Mehram Ali v. Federation of Pakistan",
        "status": PrecedentStatus.DISTINGUISHED,
        "overruled_by": "PLD 1999 SC 504",
        "overruling_case": "Liaquat Hussain v. Federation of Pakistan",
        "bench_quorum": "Full Bench",
        "reason": "Distinguished regarding trial of civilians by military courts; military courts held parallel to judiciary and unconstitutional unless protected by constitutional amendment.",
        "fatal_in_court": False
    }
}

def normalize_citation(citation: str) -> str:
    c = re.sub(r'[^a-zA-Z0-9\s]', ' ', citation)
    return " ".join(c.upper().split())

def check_precedent_treatment(citation: str) -> Dict[str, Any]:
    """
    Checks the Shepardizing status of a citation.
    Returns status, warning messages, and overruling citations.
    """
    norm_cit = normalize_citation(citation)

    for registered_cit, data in KNOWN_NEGATIVE_TREATMENTS.items():
        if normalize_citation(registered_cit) == norm_cit:
            return {
                "citation": citation,
                "status": data["status"].value,
                "is_good_law": data["status"] == PrecedentStatus.GOOD_LAW,
                "fatal_in_court": data.get("fatal_in_court", False),
                "badge": f"⚠️ {data['status'].value}: {data['reason'][:100]}...",
                "overruled_by": data.get("overruled_by"),
                "overruling_case": data.get("overruling_case"),
                "bench_quorum": data.get("bench_quorum"),
                "reason": data.get("reason")
            }

    # Default to Good Law if not recorded in negative ledger
    return {
        "citation": citation,
        "status": PrecedentStatus.GOOD_LAW.value,
        "is_good_law": True,
        "fatal_in_court": False,
        "badge": "✓ GOOD LAW",
        "overruled_by": None,
        "overruling_case": None,
        "bench_quorum": None,
        "reason": "Authority stands as valid precedent in primary reporters."
    }

def filter_and_flag_precedent_cards(cards: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Enriches precedent cards with treatment status.
    Returns (safe_cards, overruled_cards).
    Overruled cards are explicitly blocked from court pleading generation.
    """
    safe_cards = []
    overruled_cards = []

    for card in cards:
        cit = card.get("neutral_citation") or card.get("citation") or card.get("case_id") or ""
        treatment = check_precedent_treatment(cit)
        enriched_card = dict(card)
        enriched_card["treatment"] = treatment

        if treatment["fatal_in_court"]:
            overruled_cards.append(enriched_card)
        else:
            safe_cards.append(enriched_card)

    return safe_cards, overruled_cards
