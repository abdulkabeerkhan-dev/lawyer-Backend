"""
core/metadata_enrichment.py

Deterministic Legal-Domain Tagging & Metadata-Enrichment Module for Pakistani Superior Court Judgments.

Phase 4, Step 3 Implementation:
- Versioned metadata schema (v1.0).
- Deterministic legal domain, subdomain, statutory provisions, and bench level classification.
- Strict isolation against generic trigger words (e.g. 'court', 'director', 'petition', 'appeal').
- Grounded in Pakistani statutory taxonomy (PPC, CrPC, CPC, Constitution 1973, FIO 2001, etc.).
- Full compliance with Pinecone metadata constraints (types: str, int, float, bool, List[str]; <40KB size limit).
- Backward compatibility helpers for legacy vectors.
"""

import re
import json
from typing import Dict, List, Any, Optional, Set, Tuple, Literal
from pydantic import BaseModel, Field

METADATA_SCHEMA_VERSION = "1.0"
MAX_PINECONE_METADATA_BYTES = 40960  # Pinecone 40KB hard limit
SAFE_PINECONE_METADATA_BYTES = 38000 # Safety buffer for transmission & headers

LegalDomainType = Literal[
    "civil", "criminal", "constitutional", "family",
    "corporate", "rent", "banking", "taxation", "service",
    "labour", "cybercrime", "intellectual_property", "environmental",
    "general_legal"
]

BenchLevelType = Literal[
    "supreme_court", "high_court", "district_court",
    "special_court_or_tribunal", "unknown"
]

ClassificationSourceType = Literal[
    "statutory_explicit", "doctrinal_rule", "neutral_citation", "unclassified"
]

# Generic terms that MUST NEVER trigger a domain classification on their own
GENERIC_EXCLUSIONS: Set[str] = {
    "court", "courts", "judge", "judges", "justice", "bench",
    "petition", "petitions", "petitioner", "petitioners",
    "appeal", "appeals", "appellant", "appellants",
    "respondent", "respondents", "plaintiff", "defendant",
    "order", "orders", "judgment", "judgments", "case", "cases",
    "law", "laws", "pakistan", "pakistani", "jurisdiction",
    "director", "directors", "office", "official", "applicant",
    "learned", "counsel", "advocate", "hearing", "record", "matter"
}

# Supported Pakistani Legal Domains
ALL_LEGAL_DOMAINS: Set[str] = {
    "civil", "criminal", "constitutional", "family",
    "corporate", "rent", "banking", "taxation", "service",
    "labour", "cybercrime", "intellectual_property", "environmental",
    "general_legal"
}

# Domain Alias Normalization Map (reconciles 'tax'/'taxation', 'labor'/'labour', etc.)
DOMAIN_ALIAS_MAP: Dict[str, str] = {
    "tax": "taxation",
    "taxes": "taxation",
    "revenue": "taxation",
    "customs": "taxation",
    "labor": "labour",
    "employment": "labour",
    "ip": "intellectual_property",
    "intellectual property": "intellectual_property",
    "cyber": "cybercrime",
    "cyber crime": "cybercrime",
    "electronic crime": "cybercrime",
    "electronic_crime": "cybercrime",
    "env": "environmental",
    "environment": "environmental",
    "general": "general_legal",
    "unclassified": "general_legal"
}


def canonicalize_domain_name(domain: str) -> str:
    """
    Canonicalizes arbitrary domain strings, abbreviations, and dialect variations
    into the strict Pakistani legal taxonomy.
    """
    d_norm = (domain or "").strip().lower().replace("-", "_")
    return DOMAIN_ALIAS_MAP.get(d_norm, d_norm if d_norm in ALL_LEGAL_DOMAINS else "general_legal")


# ==============================================================================
# 1. Statutory Provisions & Pattern Catalog
# ==============================================================================

STATUTORY_CATALOG = [
    # --- CRIMINAL ---
    {
        "domain": "criminal",
        "subdomain": "pre_arrest_bail",
        "canonical_provision": "crpc_1898_section_498",
        "patterns": [
            r'\b498\s*cr\.?\s*p\.?\s*c\b',
            r'\bsection\s+498\b.*?\b(?:cr\.?p\.?c|criminal\s+procedure)\b',
            r'\bpre-?arrest\s+bail\b',
            r'\bbail\s+before\s+arrest\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "post_arrest_bail",
        "canonical_provision": "crpc_1898_section_497",
        "patterns": [
            r'\b497\s*cr\.?\s*p\.?\s*c\b',
            r'\bsection\s+497\b.*?\b(?:cr\.?p\.?c|criminal\s+procedure)\b',
            r'\bpost-?arrest\s+bail\b',
            r'\bbail\s+after\s+arrest\b',
            r'\bstatutory\s+delay\b.*?\bbail\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "fir_registration",
        "canonical_provision": "crpc_1898_section_154",
        "patterns": [
            r'\b154\s*cr\.?\s*p\.?\s*c\b',
            r'\bsection\s+154\b.*?\b(?:cr\.?p\.?c|criminal\s+procedure)\b',
            r'\bregistration\s+of\s+fir\b',
            r'\bfirst\s+information\s+report\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "murder_trial",
        "canonical_provision": "ppc_1860_section_302",
        "patterns": [
            r'\b302\s*p\.?\s*p\.?\s*c\b',
            r'\bsection\s+302\b.*?\b(?:p\.?p\.?c|penal\s+code)\b',
            r'\bqatl-?i-?amd\b',
            r'\bcapital\s+sentence\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "attempted_murder",
        "canonical_provision": "ppc_1860_section_324",
        "patterns": [
            r'\b324\s*p\.?\s*p\.?\s*c\b',
            r'\bsection\s+324\b.*?\b(?:p\.?p\.?c|penal\s+code)\b',
            r'\battempt\s+to\s+commit\s+qatl-?i-?amd\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "cheque_dishonour",
        "canonical_provision": "ppc_1860_section_489_f",
        "patterns": [
            r'\b489-?f\s*p\.?\s*p\.?\s*c\b',
            r'\bsection\s+489-?f\b',
            r'\bdishonest(?:ly)?\s+issuing\s+cheque\b',
            r'\bdishonour\s+of\s+cheque\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "criminal_breach_of_trust",
        "canonical_provision": "ppc_1860_section_409",
        "patterns": [
            r'\b409\s*p\.?\s*p\.?\s*c\b',
            r'\bsection\s+409\b.*?\b(?:p\.?p\.?c|penal\s+code)\b',
            r'\bcriminal\s+breach\s+of\s+trust\s+by\s+public\s+servant\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "narcotics",
        "canonical_provision": "cnsa_1997_section_9c",
        "patterns": [
            r'\b9-?[bc]\s*cnsa\b',
            r'\bsection\s+9\s*\([bc]\)\b.*?\bcnsa\b',
            r'\bcontrol\s+of\s+narcotic\s+substances\b',
            r'\brecovery\s+of\s+charas\b',
            r'\brecovery\s+of\s+heroin\b'
        ]
    },
    {
        "domain": "criminal",
        "subdomain": "anti_terrorism",
        "canonical_provision": "ata_1997_section_7",
        "patterns": [
            r'\bsection\s+7\s*ata\b',
            r'\banti-?terrorism\s+act\b',
            r'\b7\s*a\.?\s*t\.?\s*a\b'
        ]
    },

    # --- CIVIL ---
    {
        "domain": "civil",
        "subdomain": "partition",
        "canonical_provision": "transfer_of_property_act_1882_section_44",
        "patterns": [
            r'\bsection\s+44\b.*?\b(?:transfer\s+of\s+property|tpa)\b',
            r'\bsuit\s+for\s+partition\b',
            r'\bpartition\s+of\s+joint\s+property\b',
            r'\bco-?sharer\b.*?\bpartition\b',
            r'\bpartition\s+act\s+1893\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "rejection_of_plaint",
        "canonical_provision": "cpc_1908_order_vii_rule_11",
        "patterns": [
            r'\border\s+vii\s+rule\s+11\b',
            r'\bo\.?\s*7\s*r\.?\s*11\b',
            r'\brejection\s+of\s+plaint\b',
            r'\bcause\s+of\s+action\b.*?\bplaint\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "temporary_injunction",
        "canonical_provision": "cpc_1908_order_xxxix_rule_1_2",
        "patterns": [
            r'\border\s+xxxix\s+rules?\s+1\s+(?:and|&)\s+2\b',
            r'\bo\.?\s*39\s*r\.?\s*1\s*(?:and|&|\,)\s*2\b',
            r'\btemporary\s+injunction\b',
            r'\bprima\s+facie\s+case\b.*?\birreparable\s+loss\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "execution_objection",
        "canonical_provision": "cpc_1908_order_xxi_rule_58",
        "patterns": [
            r'\border\s+xxi\s+rule\s+58\b',
            r'\bo\.?\s*21\s*r\.?\s*58\b',
            r'\bexecution\s+proceedings?\b.*?\bobjection\b',
            r'\bobjection\s+petition\b.*?\bexecution\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "fraud_setting_aside",
        "canonical_provision": "cpc_1908_section_12_2",
        "patterns": [
            r'\bsection\s+12\s*\(\s*2\s*\)\s*c\.?\s*p\.?\s*c\b',
            r'\b12\s*\(\s*2\s*\)\s*cpc\b',
            r'\bapplication\s+under\s+section\s+12\s*\(\s*2\s*\)\b',
            r'\bdecree\s+obtained\s+by\s+fraud\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "specific_performance",
        "canonical_provision": "specific_relief_act_1877_section_12",
        "patterns": [
            r'\bsection\s+12\b.*?\bspecific\s+relief\b',
            r'\bsuit\s+for\s+specific\s+performance\b',
            r'\bagreement\s+to\s+sell\b.*?\bspecific\s+performance\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "declaratory_suit",
        "canonical_provision": "specific_relief_act_1877_section_42",
        "patterns": [
            r'\bsection\s+42\b.*?\bspecific\s+relief\b',
            r'\bsuit\s+for\s+declaration\b',
            r'\bdeclaratory\s+decree\b'
        ]
    },
    {
        "domain": "civil",
        "subdomain": "civil_revision",
        "canonical_provision": "cpc_1908_section_115",
        "patterns": [
            r'\bsection\s+115\s*c\.?\s*p\.?\s*c\b',
            r'\bcivil\s+revision\b',
            r'\brevisional\s+jurisdiction\b.*?\bcpc\b'
        ]
    },

    # --- CONSTITUTIONAL ---
    {
        "domain": "constitutional",
        "subdomain": "high_court_writ",
        "canonical_provision": "constitution_1973_article_199",
        "patterns": [
            r'\barticle\s+199\b',
            r'\bwrit\s+petition\b',
            r'\bconstitutional\s+petition\b',
            r'\bwrit\s+of\s+mandamus\b',
            r'\bwrit\s+of\s+certiorari\b',
            r'\bwrit\s+of\s+habeas\s+corpus\b',
            r'\bwrit\s+of\s+quo\s+warranto\b'
        ]
    },
    {
        "domain": "constitutional",
        "subdomain": "original_jurisdiction_sc",
        "canonical_provision": "constitution_1973_article_184_3",
        "patterns": [
            r'\barticle\s+184\s*\(\s*3\s*\)\b',
            r'\b184\s*\(\s*3\s*\)\b',
            r'\bpublic\s+interest\s+litigation\b.*?\bsupreme\s+court\b',
            r'\bsuo\s+motu\b'
        ]
    },
    {
        "domain": "constitutional",
        "subdomain": "fundamental_rights",
        "canonical_provision": "constitution_1973_fundamental_rights",
        "patterns": [
            r'\bfundamental\s+rights?\b.*?\bconstitution\b',
            r'\barticle\s+(?:9|10-?a|14|25)\b.*?\bconstitution\b'
        ]
    },

    # --- FAMILY ---
    {
        "domain": "family",
        "subdomain": "khula",
        "canonical_provision": "family_courts_act_1964_section_5",
        "patterns": [
            r'\bkhula\b',
            r'\bdissolution\s+of\s+marriage\b.*?\bkhula\b',
            r'\bdissolution\s+of\s+muslim\s+marriages\s+act\b'
        ]
    },
    {
        "domain": "family",
        "subdomain": "custody_and_guardianship",
        "canonical_provision": "guardians_and_wards_act_1890_section_25",
        "patterns": [
            r'\bguardians\s+and\s+wards\s+act\b',
            r'\bsection\s+25\b.*?\bguardians\b',
            r'\bcustody\s+of\s+minor\b',
            r'\bwelfare\s+of\s+the\s+minor\b',
            r'\bhizanat\b'
        ]
    },
    {
        "domain": "family",
        "subdomain": "dower_and_maintenance",
        "canonical_provision": "mflo_1961_section_9",
        "patterns": [
            r'\bmaintenance\s+of\s+(?:wife|children|minor)\b',
            r'\brecovery\s+of\s+dower\b',
            r'\bdower\s+amount\b',
            r'\bsection\s+9\b.*?\bmflo\b',
            r'\bmuslim\s+family\s+laws\s+ordinance\b'
        ]
    },

    # --- BANKING ---
    {
        "domain": "banking",
        "subdomain": "leave_to_defend",
        "canonical_provision": "fio_2001_section_10",
        "patterns": [
            r'\bfinancial\s+institutions\s*\(?recovery\s+of\s+finances\)?\s+ordinance\b',
            r'\bfio\s+2001\b',
            r'\bsection\s+10\b.*?\bfio\b',
            r'\bleave\s+to\s+defend\b.*?\b(?:suit|banking)\b',
            r'\bstatement\s+of\s+account\b.*?\bfinance\b'
        ]
    },
    {
        "domain": "banking",
        "subdomain": "recovery_of_finance",
        "canonical_provision": "fio_2001_section_9",
        "patterns": [
            r'\bsection\s+9\b.*?\bfio\b',
            r'\bsuit\s+for\s+recovery\s+of\s+finance\b',
            r'\bfinancial\s+institution\b.*?\bcustomer\b',
            r'\bcost\s+of\s+funds\b'
        ]
    },

    # --- CORPORATE ---
    {
        "domain": "corporate",
        "subdomain": "oppression_and_mismanagement",
        "canonical_provision": "companies_act_2017_section_286",
        "patterns": [
            r'\bcompanies\s+act\s+2017\b',
            r'\bcompanies\s+ordinance\s+1984\b',
            r'\bsection\s+286\b.*?\bcompanies\b',
            r'\boppression\b.*?\bminority\s+shareholders\b',
            r'\bpetition\s+under\s+section\s+286\b'
        ]
    },
    {
        "domain": "corporate",
        "subdomain": "winding_up",
        "canonical_provision": "companies_act_2017_section_301",
        "patterns": [
            r'\bwinding\s+up\s+of\s+company\b',
            r'\bsection\s+301\b.*?\bcompanies\b',
            r'\bunable\s+to\s+pay\s+its\s+debts\b.*?\bcompany\b'
        ]
    },

    # --- RENT ---
    {
        "domain": "rent",
        "subdomain": "eviction_personal_need",
        "canonical_provision": "punjab_rented_premises_act_2009_section_15",
        "patterns": [
            r'\bpunjab\s+rented\s+premises\s+act\b',
            r'\bprpa\s+2009\b',
            r'\bsindh\s+rented\s+premises\s+ordinance\b',
            r'\bsrpo\s+1979\b',
            r'\burban\s+rent\s+restriction\s+ordinance\b',
            r'\bejectment\s+petition\b',
            r'\bbona\s+fide\s+personal\s+need\b',
            r'\btenant\b.*?\blandlord\b.*?\beviction\b'
        ]
    },

    # --- TAXATION ---
    {
        "domain": "taxation",
        "subdomain": "sales_tax",
        "canonical_provision": "sales_tax_act_1990_section_8",
        "patterns": [
            r'\bsales\s+tax\s+act\s+1990\b',
            r'\bsection\s+8\b.*?\bsales\s+tax\b',
            r'\binput\s+tax\s+adjustment\b',
            r'\bdisallowance\s+of\s+input\s+tax\b',
            r'\bfederal\s+board\s+of\s+revenue\b.*?\bsales\s+tax\b'
        ]
    },
    {
        "domain": "taxation",
        "subdomain": "income_tax",
        "canonical_provision": "income_tax_ordinance_2001_section_111",
        "patterns": [
            r'\bincome\s+tax\s+ordinance\s+2001\b',
            r'\bsection\s+111\b.*?\bincome\s+tax\b',
            r'\bunexplained\s+income\b',
            r'\bassessment\s+order\b.*?\bcommissioner\s+inland\s+revenue\b'
        ]
    },

    # --- SERVICE ---
    {
        "domain": "service",
        "subdomain": "service_tribunal_appeal",
        "canonical_provision": "service_tribunals_act_1973_section_4",
        "patterns": [
            r'\bservice\s+tribunals\s+act\s+1973\b',
            r'\bfederal\s+service\s+tribunal\b',
            r'\bcivil\s+servants\s+act\s+1973\b',
            r'\bsection\s+4\b.*?\bservice\s+tribunals?\b',
            r'\bseniority\s+and\s+promotion\b.*?\bcivil\s+servant\b',
            r'\bterms\s+and\s+conditions\s+of\s+service\b'
        ]
    },

    # --- LABOUR ---
    {
        "domain": "labour",
        "subdomain": "industrial_dispute",
        "canonical_provision": "industrial_relations_act_2012_section_33",
        "patterns": [
            r'\bindustrial\s+relations\s+act\b',
            r'\bira\s+2012\b',
            r'\bnational\s+industrial\s+relations\s+commission\b',
            r'\bnirc\b',
            r'\bunfair\s+labour\s+practice\b',
            r'\bworkmen(?:\'s)?\s+compensation\s+act\b',
            r'\bpayment\s+of\s+wages\s+act\b'
        ]
    },

    # --- CYBERCRIME ---
    {
        "domain": "cybercrime",
        "subdomain": "peca_offence",
        "canonical_provision": "peca_2016_section_20",
        "patterns": [
            r'\bprevention\s+of\s+electronic\s+crimes\s+act\b',
            r'\bpeca\s+2016\b',
            r'\bsection\s+20\b.*?\bpeca\b',
            r'\bdignity\s+of\s+natural\s+person\b.*?\belectronic\b',
            r'\bcyber\s+terrorism\b'
        ]
    },

    # --- INTELLECTUAL PROPERTY ---
    {
        "domain": "intellectual_property",
        "subdomain": "trademark_copyright",
        "canonical_provision": "trade_marks_ordinance_2001",
        "patterns": [
            r'\btrade\s+marks\s+ordinance\s+2001\b',
            r'\bcopyright\s+ordinance\s+1962\b',
            r'\bpatents\s+ordinance\s+2000\b',
            r'\binfringement\s+of\s+trade\s*mark\b',
            r'\bdeceptively\s+similar\s+mark\b',
            r'\bpassing\s+off\b'
        ]
    },

    # --- ENVIRONMENTAL ---
    {
        "domain": "environmental",
        "subdomain": "environmental_protection",
        "canonical_provision": "pepa_1997_section_16",
        "patterns": [
            r'\bpakistan\s+environmental\s+protection\s+act\b',
            r'\bpepa\s+1997\b',
            r'\benvironmental\s+protection\s+order\b',
            r'\binitial\s+environmental\s+examination\b',
            r'\benvironmental\s+impact\s+assessment\b'
        ]
    }
]


# ==============================================================================
# 2. Pydantic Metadata Schema
# ==============================================================================

class LegalChunkMetadata(BaseModel):
    """
    Standardized, versioned metadata schema for Pakistani legal vector chunks.
    Fully compliant with Pinecone storage requirements.
    """
    metadata_schema_version: str = Field(default=METADATA_SCHEMA_VERSION)
    legal_domain: LegalDomainType = Field(default="general_legal")
    subdomain: str = Field(default="unspecified")
    statutory_provisions: List[str] = Field(default_factory=list)
    bench_level: BenchLevelType = Field(default="unknown")
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    classification_source: ClassificationSourceType = Field(default="unclassified")
    source_document_id: str = Field(default="")

    def to_pinecone_dict(self) -> Dict[str, Any]:
        """Convert to dict with verified Pinecone-compatible types."""
        return {
            "metadata_schema_version": str(self.metadata_schema_version),
            "legal_domain": str(self.legal_domain),
            "subdomain": str(self.subdomain),
            "statutory_provisions": [str(p) for p in self.statutory_provisions],
            "bench_level": str(self.bench_level),
            "classification_confidence": round(float(self.classification_confidence), 4),
            "classification_source": str(self.classification_source),
            "source_document_id": str(self.source_document_id)
        }


# ==============================================================================
# 3. Bench-Level Extraction
# ==============================================================================

def extract_bench_level(court_name: str, text_snippet: str = "", citation: str = "") -> BenchLevelType:
    """
    Deterministically determines the bench level hierarchy from court metadata,
    neutral citation, or header text.
    """
    combined = f"{court_name} {citation} {text_snippet[:600]}".lower()

    # 1. Supreme Court
    if (
        "supreme court" in combined or
        re.search(r'\b(?:sc|scmr)\b', combined) or
        "apex court" in combined
    ):
        return "supreme_court"

    # 2. High Court
    if (
        "high court" in combined or
        re.search(r'\b(?:lhc|shc|phc|bhc|ihc)\b', combined) or
        re.search(r'\b(?:lahore|sindh|peshawar|balochistan|islamabad)\s+high\s+court\b', combined) or
        re.search(r'\b(?:pld|pcrli|clc|mld|ylr)\s+(?:19|20)\d{2}\s+(?:lah|kar|pesh|quetta|ihc)\b', combined)
    ):
        return "high_court"

    # 3. Special Courts & Tribunals
    if any(k in combined for k in [
        "banking court", "service tribunal", "federal service tribunal",
        "nirc", "national industrial relations", "appellate tribunal",
        "special court", "customs tribunal", "environmental protection tribunal",
        "anti-terrorism court", "accountability court"
    ]):
        return "special_court_or_tribunal"

    # 4. District & Subordinate Courts
    if any(k in combined for k in [
        "district and sessions", "sessions judge", "additional sessions judge",
        "senior civil judge", "civil judge", "judicial magistrate",
        "family judge", "rent controller"
    ]):
        return "district_court"

    return "unknown"


# ==============================================================================
# 4. Domain & Subdomain Classifier
# ==============================================================================

def classify_legal_text(
    text: str,
    title: str = "",
    citation: str = "",
    court: str = ""
) -> Tuple[LegalDomainType, str, List[str], float, ClassificationSourceType]:
    """
    Deterministically classifies legal domain, subdomain, statutory provisions,
    confidence, and classification source.
    """
    searchable = f"{title}\n{citation}\n{court}\n{text}".strip()
    searchable_lower = searchable.lower()

    # Check for empty or negligible input
    if not text.strip() or len(text.strip()) < 30:
        return "general_legal", "unspecified", [], 0.0, "unclassified"

    matched_provisions: List[str] = []
    domain_scores: Dict[str, float] = {}
    subdomain_candidates: Dict[str, str] = {}

    # --------------------------------------------------------------------------
    # Step A: Statutory Provisions & Distinctive Phrases
    # --------------------------------------------------------------------------
    for entry in STATUTORY_CATALOG:
        domain = entry["domain"]
        subdomain = entry["subdomain"]
        provision = entry["canonical_provision"]

        hit_count = 0
        for pat in entry["patterns"]:
            if re.search(pat, searchable_lower):
                hit_count += 1

        if hit_count > 0:
            if provision not in matched_provisions:
                matched_provisions.append(provision)
            
            # Weight: multiple pattern hits give higher confidence
            score_increment = 1.0 + (0.2 * (hit_count - 1))
            domain_scores[domain] = domain_scores.get(domain, 0.0) + score_increment
            if domain not in subdomain_candidates:
                subdomain_candidates[domain] = subdomain

    # If statutory provisions matched clearly
    if domain_scores:
        # Sort domains by score descending
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        primary_domain, top_score = sorted_domains[0]
        chosen_subdomain = subdomain_candidates.get(primary_domain, "unspecified")

        # Check for ambiguity: if top two domains both have statutory provisions and are closely matched
        if len(sorted_domains) > 1:
            second_domain, second_score = sorted_domains[1]
            if abs(top_score - second_score) <= 0.35 or (top_score > 0 and (second_score / top_score) >= 0.80):
                # Ambiguous classification: conflicting domain signals without clear dominance
                confidence = 0.50
                return "general_legal", "ambiguous_cross_domain", matched_provisions, confidence, "statutory_explicit"

        confidence = min(0.95, 0.85 + (0.02 * top_score))
        return primary_domain, chosen_subdomain, matched_provisions, confidence, "statutory_explicit"

    # --------------------------------------------------------------------------
    # Step B: Reporter Citation Heuristics (Specialized Journals)
    # --------------------------------------------------------------------------
    cit_upper = citation.upper()
    if "PCRLJ" in cit_upper:
        return "criminal", "unspecified", [], 0.75, "neutral_citation"
    if "CLD" in cit_upper:
        return "corporate", "unspecified", [], 0.75, "neutral_citation"
    if "PLC" in cit_upper:
        return "labour", "unspecified", [], 0.75, "neutral_citation"
    if "PTD" in cit_upper:
        return "taxation", "unspecified", [], 0.75, "neutral_citation"

    # --------------------------------------------------------------------------
    # Step C: Fallback to General / Unclassified
    # --------------------------------------------------------------------------
    # Document contains legal text but lacks sufficient domain markers
    return "general_legal", "unspecified", [], 0.30, "unclassified"


# ==============================================================================
# 5. Pinecone Metadata Validation & Serialization
# ==============================================================================

def validate_pinecone_metadata_types(metadata: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validates that all dictionary values are strictly Pinecone-supported types:
    - str, int, float, bool, or list of str.
    Rejects nested dicts, lists of numbers, lists of mixed types, or None values.
    """
    for key, value in metadata.items():
        if value is None:
            return False, f"Key '{key}' has None value, which is not supported by Pinecone."
        
        if isinstance(value, (str, int, float, bool)):
            continue
        elif isinstance(value, list):
            if not all(isinstance(item, str) for item in value):
                return False, f"Key '{key}' is a list containing non-string items, which Pinecone rejects."
        else:
            return False, f"Key '{key}' has unsupported type '{type(value).__name__}' for Pinecone."

    return True, None


def sanitize_metadata_for_pinecone(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes arbitrary metadata dictionary into strict Pinecone-compatible types:
    - Converts numbers to int/float.
    - Flattens or stringifies nested objects.
    - Drops unsupported values.
    """
    sanitized: Dict[str, Any] = {}
    for key, val in metadata.items():
        if val is None:
            continue
        if isinstance(val, (bool, int, float)):
            sanitized[key] = val
        elif isinstance(val, str):
            sanitized[key] = val
        elif isinstance(val, list):
            # Only keep lists if all elements can be strings
            str_list = [str(x) for x in val if x is not None]
            sanitized[key] = str_list
        elif isinstance(val, dict):
            # Pinecone rejects nested dicts: serialize to JSON string
            sanitized[key] = json.dumps(val, ensure_ascii=False)
        else:
            sanitized[key] = str(val)

    return sanitized


def enforce_pinecone_size_limit(
    metadata: Dict[str, Any],
    max_bytes: int = SAFE_PINECONE_METADATA_BYTES
) -> Dict[str, Any]:
    """
    Ensures total JSON serialized byte size of metadata remains strictly below
    Pinecone's limit (40KB). If payload is too large, progressively truncates
    'text' or 'text_preview' fields while preserving all structural metadata.
    """
    meta_copy = dict(metadata)
    serialized = json.dumps(meta_copy, ensure_ascii=False).encode('utf-8')
    current_size = len(serialized)

    if current_size <= max_bytes:
        return meta_copy

    # If oversize, prioritize truncating 'text'
    if "text" in meta_copy and isinstance(meta_copy["text"], str):
        excess = current_size - max_bytes
        orig_text = meta_copy["text"]
        # Reduce text by excess plus safety margin
        new_len = max(100, len(orig_text) - excess - 256)
        meta_copy["text"] = orig_text[:new_len] + "... [truncated for Pinecone size limit]"

    # Re-check size
    serialized = json.dumps(meta_copy, ensure_ascii=False).encode('utf-8')
    if len(serialized) <= max_bytes:
        return meta_copy

    # If still oversize, truncate 'text_preview'
    if "text_preview" in meta_copy and isinstance(meta_copy["text_preview"], str):
        meta_copy["text_preview"] = meta_copy["text_preview"][:100]

    return meta_copy


# ==============================================================================
# 6. Primary Chunk & Document Enrichment Entrypoint
# ==============================================================================

def enrich_chunk_metadata(
    chunk_text: str,
    base_metadata: Optional[Dict[str, Any]] = None,
    document_id: str = ""
) -> Dict[str, Any]:
    """
    Primary ingestion enrichment function for Pakistani legal chunks.
    Combines base metadata with deterministic classification and ensures
    Pinecone compliance.
    """
    base = dict(base_metadata or {})

    # Extract source identifiers
    doc_id = str(
        document_id or
        base.get("case_id") or
        base.get("judgment_id") or
        base.get("canonical_id") or
        ""
    ).strip()

    title = str(base.get("case_title") or base.get("title") or "").strip()
    citation = str(base.get("citation") or base.get("neutral_citation") or "").strip()
    court = str(base.get("court") or base.get("court_name") or "").strip()

    # Deterministic Classification
    legal_domain, subdomain, provisions, confidence, source = classify_legal_text(
        text=chunk_text,
        title=title,
        citation=citation,
        court=court
    )

    # Bench-Level Extraction
    bench_level = extract_bench_level(
        court_name=court,
        text_snippet=chunk_text,
        citation=citation
    )

    # Construct schema object
    enrichment = LegalChunkMetadata(
        metadata_schema_version=METADATA_SCHEMA_VERSION,
        legal_domain=legal_domain,
        subdomain=subdomain,
        statutory_provisions=provisions,
        bench_level=bench_level,
        classification_confidence=confidence,
        classification_source=source,
        source_document_id=doc_id
    )

    # Merge base metadata with enriched fields (enrichment adds new fields; does not delete legacy fields)
    enriched_dict = {
        **base,
        **enrichment.to_pinecone_dict()
    }

    # Ensure chunk text is included if not already present
    if "text" not in enriched_dict:
        enriched_dict["text"] = chunk_text
    if "text_preview" not in enriched_dict:
        enriched_dict["text_preview"] = chunk_text[:200]

    # Sanitize types and enforce Pinecone size bounds
    sanitized = sanitize_metadata_for_pinecone(enriched_dict)
    valid_size_meta = enforce_pinecone_size_limit(sanitized)

    return valid_size_meta


# ==============================================================================
# 7. Backward Compatibility Helpers for Legacy Vectors
# ==============================================================================

def is_enriched_vector(metadata: Dict[str, Any]) -> bool:
    """Checks whether a Pinecone vector metadata dict contains Step 3 enrichment."""
    return (
        metadata is not None and
        metadata.get("metadata_schema_version") == METADATA_SCHEMA_VERSION and
        "legal_domain" in metadata
    )


def normalize_legacy_vector_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapts legacy vector metadata on-the-fly without requiring physical database migration.
    Legacy vectors receive safe default classification fields.
    """
    if is_enriched_vector(metadata):
        return metadata

    meta_copy = dict(metadata or {})
    court = str(meta_copy.get("court") or meta_copy.get("court_name") or "")
    bench = extract_bench_level(court, meta_copy.get("text_preview", ""))

    legacy_enrichment = {
        "metadata_schema_version": "0.0_legacy",
        "legal_domain": "general_legal",
        "subdomain": "unspecified",
        "statutory_provisions": [],
        "bench_level": bench,
        "classification_confidence": 0.0,
        "classification_source": "unclassified",
        "source_document_id": str(meta_copy.get("case_id") or meta_copy.get("judgment_id") or "")
    }

    return {**meta_copy, **legacy_enrichment}
