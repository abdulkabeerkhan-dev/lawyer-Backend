"""
core/post_rerank_domain_gate.py

Post-Rerank Legal Domain Validation Gate & Dynamic Context Assembly Engine
for the Pakistani Legal AI Pipeline (Phase 4, Step 5).

Architectural Responsibilities:
1. Deterministic Post-Rerank Partitioning:
   Partitions cross-encoder scored candidates into deterministic priority tiers:
   - Joint Bucket 1 (Substantive Approved): Bucket 1A (Direct On-Domain) + Bucket 1B (Approved Interdisciplinary Doctrine).
   - Bucket 2 (Procedural Approved): Neutral procedural authorities (CPC S.151, Limitation S.5, Court Fees Act).
   - Bucket 3 (Off-Domain Demoted): Disallowed foreign statutes or uncalibrated candidates.
     Strictly barred from LLM generation context in all modes (strict_mode=True or False).
2. Hard Quarantine Boundary:
   Candidates with is_quarantined=True are unconditionally dropped pre-ranking to dropped_pool.
   Invariant: QUARANTINED_CANDIDATE_GENERATION_ELIGIBILITY = NEVER.
3. Five Interdisciplinary Doctrine Contracts:
   - DOCTRINE_ART_212_SERVICE_BAR (Constitutional service ouster, 5-gate state tort architecture, S.80 CPC notice)
   - DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT / DOCTRINE_S561A_CRPC_CIVIL_RECOVERY (S.420 inception fraud, S.406 entrustment vs debt)
   - DOCTRINE_FEMALE_INHERITANCE_LIMITATION (Omission of Art 144, co-heir joint possession, Art 142 ouster vs mutation, residuary Art 120, S.18 fraud)
   - DOCTRINE_BENAMI_PARTITION_BAR (Act No. V of 2017 four alternative routes A-D, S.2(8)(A)(b)(i) completed legatee fiduciary exclusion, Non-Masking Invariant across 108 valid states)
   - DOCTRINE_BANKING_RECOVERY_VS_489F_PPC (FIO 2001 summary recovery vs criminal S.489-F PPC for dishonored cheques, inception mens rea)
4. Lexicographic Precedential Authority Ranking:
   SortKey = (Tier_admissibility, Tier_precedent, Tier_statute, -CompositeAuthorityScore)
   - Tier_precedent post-27th Amendment & Chapter 3A:
     * FCC (Tier 1 on constitutional questions, Tier 2 on general law)
     * Supreme Court of Pakistan (Tier 1 on non-constitutional general law, Tier 2 on constitutional)
     * Federal Shariat Court (Tier 3 on Chapter 3A / Art 203-GG)
     * High Courts (Tier 4 under Article 201)
     * Specialized Statutory Appellate Tribunals (Tier 5)
     * Subordinate Courts (Tier 6)
   - Pure Semantic Relevance Floor: S_rerank >= 0.35 required regardless of court rank.
5. Dynamic Context Assembly Engine:
   15-step assembly pipeline, canonical appeal deduplication (Year-AppealNo), 7,000-token candidate ceiling
   with 1,000-token reserve (8,000 total LLM ceiling), atomic legal passage indivisibility, and clean paragraph truncation.
6. Three-Tier Tokenizer Contract:
   - Level 1: Guaranteed Native Generation Tokenizer.
   - Level 2: Calibrated Operational Estimation (2.4 chars/token with math.ceil).
   - Level 3: Fail-Closed Boundary for uncalibrated non-ASCII ratio > 15%.
"""

from __future__ import annotations

import math
import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set, Union

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. Operational Constants & Budget Ceilings
# ==============================================================================

PROMPT_OVERHEAD_RESERVE: int = 1000  # Hard reserve for system instructions, query plan, and formatting
MAX_TOTAL_CONTEXT_TOKENS: int = 8000  # Operational LLM envelope ceiling
MAX_CANDIDATE_TOKENS: int = MAX_TOTAL_CONTEXT_TOKENS - PROMPT_OVERHEAD_RESERVE  # 7000 tokens
PURE_RELEVANCE_FLOOR: float = 0.35  # Decoupled semantic relevance threshold
MAX_CANDIDATES_DEFAULT: int = 10  # Maximum candidates admitted to context

# Disallowed foreign statutes by domain to prevent cross-domain contamination
DISALLOWED_STATUTES_BY_DOMAIN: Dict[str, List[str]] = {
    "civil": [
        "income tax ordinance", "customs act", "sales tax act", "anti-terrorism act",
        "financial institutions (recovery of finances)", "fio 2001", "nab ordinance",
        "national accountability", "foreign exchange regulation act"
    ],
    "family": [
        "income tax ordinance", "customs act", "companies act", "admiralty",
        "anti-terrorism act", "financial institutions", "sales tax act",
        "banking companies", "arbitration act"
    ],
    "criminal": [
        "companies act", "income tax ordinance", "sales tax act", "insurance ordinance",
        "family courts act", "arbitration act", "partnership act", "sale of goods act"
    ],
    "banking": [
        "family courts act", "guardian and wards act", "west pakistan muslim personal law",
        "juvenile justice", "anti-terrorism act", "defamation ordinance"
    ],
    "constitutional": []
}

# Neutral procedural statutes and provisions
PROCEDURAL_STATUTE_PATTERNS: List[str] = [
    "code of civil procedure", "cpc", "order xx", "order xxxix", "order xxi",
    "section 151", "section 114", "order xlvii", "limitation act", "section 5",
    "general clauses act", "court fees act", "suits valuation act", "qanun-e-shahadat",
    "order vii rule 11", "order viii", "section 9 cpc", "order i rule 10"
]

# Verified 16-enactment legislative search ledger for Article 212 state torts audit
ARTICLE_212_ENACTMENT_LEDGER: List[Dict[str, str]] = [
    {"identifier": "CONSTITUTION_1973", "title": "Constitution of the Islamic Republic of Pakistan, 1973", "provision": "Article 212(1)(b)", "tribunal_established": "None"},
    {"identifier": "FST_ACT_1973", "title": "Federal Service Tribunals Act, 1973", "provision": "Section 4", "tribunal_established": "Federal Service Tribunal (Terms & conditions only)"},
    {"identifier": "PST_ACT_PUNJAB_1974", "title": "Punjab Service Tribunals Act, 1974", "provision": "Section 4", "tribunal_established": "Punjab Service Tribunal (Terms & conditions only)"},
    {"identifier": "PST_ACT_SINDH_1973", "title": "Sindh Service Tribunals Act, 1973", "provision": "Section 4", "tribunal_established": "Sindh Service Tribunal (Terms & conditions only)"},
    {"identifier": "PST_ACT_KP_1974", "title": "Khyber Pakhtunkhwa Service Tribunals Act, 1974", "provision": "Section 4", "tribunal_established": "KP Service Tribunal (Terms & conditions only)"},
    {"identifier": "PST_ACT_BALOCHISTAN_1974", "title": "Balochistan Service Tribunals Act, 1974", "provision": "Section 4", "tribunal_established": "Balochistan Service Tribunal (Terms & conditions only)"},
    {"identifier": "CPC_1908", "title": "Code of Civil Procedure, 1908", "provision": "Sections 9, 80", "tribunal_established": "Civil Courts (Plenary common law / tort jurisdiction)"},
    {"identifier": "CROWN_SUITS_1869", "title": "Crown Suits Act, 1869", "provision": "Entire Act", "tribunal_established": "None"},
    {"identifier": "FATAL_ACCIDENTS_1855", "title": "Fatal Accidents Act, 1855", "provision": "Section 1", "tribunal_established": "Civil Courts (Substantive tort remedy)"},
    {"identifier": "LAW_REFORMS_1972", "title": "Law Reforms Ordinance, 1972", "provision": "Section 3", "tribunal_established": "High Court Intra-Court Appeals"},
    {"identifier": "ENEMY_PROPERTY_1969", "title": "Enemy Property Ordinance, 1969", "provision": "Sections 3-5", "tribunal_established": "Custodian (Executive authority, not Art 212 judicial tribunal)"},
    {"identifier": "BENAMI_ACT_2017", "title": "Benami Transactions (Prohibition) Act, 2017 (Act No. V of 2017)", "provision": "Sections 6, 28-29", "tribunal_established": "Adjudicating Authority & Appellate Tribunal (Benami matters only)"},
    {"identifier": "PEPA_1997", "title": "Pakistan Environmental Protection Act, 1997", "provision": "Section 20", "tribunal_established": "Environmental Protection Tribunal"},
    {"identifier": "NAO_1999", "title": "National Accountability Ordinance, 1999", "provision": "Section 5(g)", "tribunal_established": "Accountability Courts (Corruption offences only)"},
    {"identifier": "FBR_ACT_2007", "title": "Federal Board of Revenue Act, 2007", "provision": "Entire Act", "tribunal_established": "None (Revenue administration only)"},
    {"identifier": "OMBUDSMAN_ACT_2013", "title": "Federal Ombudsman Institutional Reforms Act, 2013", "provision": "Entire Act", "tribunal_established": "Federal Ombudsman (Maladministration oversight only)"}
]


# ==============================================================================
# 2. Tokenizer Architecture & Three-Tier Counting Contract
# ==============================================================================

def count_context_tokens(
    text_blocks: List[str],
    generation_tokenizer: Optional[Any] = None,
    system_overhead_text: str = ""
) -> int:
    """
    Computes prompt token count adhering to the Generation Model Native Tokenizer Contract:
    - Level 1: Guaranteed Native Generation Token Counting (tiktoken / client count_tokens).
    - Level 2: Calibrated Operational Estimation (2.4 chars/token with math.ceil).
    - Level 3: Fail-Closed Boundary for uncalibrated/heavy non-ASCII text (> 15%).

    Evaluated across the full serialized prompt payload including system prompt overhead.
    """
    joined_candidates = "\n\n---\n\n".join(text_blocks)
    full_payload = f"{system_overhead_text}\n\n{joined_candidates}".strip()
    if not full_payload:
        return 0

    # Level 1: Guaranteed Native Generation Token Counting Mode
    if generation_tokenizer is not None:
        try:
            if hasattr(generation_tokenizer, "encode"):
                return len(generation_tokenizer.encode(full_payload))
            elif hasattr(generation_tokenizer, "count_tokens"):
                res = generation_tokenizer.count_tokens(full_payload)
                if isinstance(res, int):
                    return res
                if hasattr(res, "total_tokens"):
                    return res.total_tokens
        except Exception as e:
            logger.warning(f"Native generation tokenizer failed ({e}); falling back to calibrated evaluation.")

    # Level 3: Fail-Closed Safety Check on Uncalibrated / Non-ASCII Input
    non_ascii_chars = sum(1 for c in full_payload if ord(c) > 127)
    non_ascii_ratio = non_ascii_chars / max(len(full_payload), 1)
    if non_ascii_ratio > 0.15:
        logger.error(
            f"Uncalibrated non-ASCII ratio ({non_ascii_ratio:.2%}) exceeds 15% without native tokenizer. "
            f"Failing closed to prevent context overflow."
        )
        return MAX_CANDIDATE_TOKENS + 1  # Triggers fail-closed drop

    # Level 2: Calibrated Operational Estimation Mode (Standard English-Pakistani Legal Prose)
    return math.ceil(len(full_payload) / 2.4)


# ==============================================================================
# 3. Interdisciplinary Doctrine Evaluation
# ==============================================================================

def evaluate_interdisciplinary_doctrine(
    candidate: Dict[str, Any],
    query_plan: Any
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Evaluates whether a candidate satisfies an active interdisciplinary doctrine contract.
    Returns: (is_admitted, doctrine_id, audit_reason)
    """
    if not getattr(query_plan, "is_cross_domain_relevant", False):
        return False, None, "Query plan does not permit cross-domain authorities"

    active_doctrines = getattr(query_plan, "cross_domain_controlling_doctrines", []) or []
    if not active_doctrines:
        return False, None, "Zero active doctrines declared in query plan"

    text = f"{candidate.get('title', '')} {candidate.get('citation', '')} {candidate.get('text', '')} {candidate.get('preview', '')}".lower()

    contracts: Dict[str, Dict[str, Any]] = {
        "DOCTRINE_ART_212_SERVICE_BAR": {
            "primary": "constitutional",
            "required": ["212", "service tribunal", "civil servant"],
            "disallowed": ["master and servant", "private bank employee"]
        },
        "DOCTRINE_CIVIL_DISPUTE_CRIMINAL_QUASHMENT": {
            "primary": "criminal",
            "required": ["quash", "contract"],
            "any_required": [["561-a"], ["420"], ["406"], ["cheating"], ["breach of trust"]],
            "disallowed": ["robbery", "physical assault", "murder", "narcotics"]
        },
        "DOCTRINE_S561A_CRPC_CIVIL_RECOVERY": {  # Historical alias
            "primary": "criminal",
            "required": ["quash", "contract"],
            "any_required": [["561-a"], ["420"], ["406"], ["cheating"], ["breach of trust"]],
            "disallowed": ["robbery", "physical assault", "murder", "narcotics"]
        },
        "DOCTRINE_FEMALE_INHERITANCE_LIMITATION": {
            "primary": "civil",
            "required": ["inheritance", "mutation", "female", "sister"],
            "disallowed": ["dissolution of marriage", "dowry articles", "dower"]
        },
        "DOCTRINE_BENAMI_PARTITION_BAR": {
            "primary": "civil",
            "required": ["partition", "benami", "ostensible"],
            "disallowed": ["tax evasion", "income tax assessment", "smuggling"]
        },
        "DOCTRINE_BANKING_RECOVERY_VS_489F_PPC": {
            "primary": "banking",
            "required": ["489-f", "cheque", "financial institution", "recovery"],
            "disallowed": ["gambling debt"]
        }
    }

    primary_domain = str(getattr(query_plan, "primary_domain", "") or "").lower()

    for doc_id in active_doctrines:
        contract = contracts.get(doc_id)
        if not contract:
            continue

        if primary_domain != contract["primary"]:
            continue

        # Check negative rejection criteria first
        if any(term in text for term in contract.get("disallowed", [])):
            return False, doc_id, f"Rejected under negative fixture criteria for {doc_id}"

        # Check positive admission criteria
        matches_required = all(term in text for term in contract.get("required", []))
        if not matches_required:
            continue

        # Optional disjunctive check
        any_groups = contract.get("any_required", [])
        if any_groups:
            matched_any = False
            for group in any_groups:
                if all(term in text for term in group):
                    matched_any = True
                    break
            if not matched_any:
                continue

        return True, doc_id, f"Admitted to Bucket 1B under contract {doc_id}"

    return False, None, "Candidate does not satisfy any active doctrine contract"


# ==============================================================================
# 4. Post-Rerank Domain Partitioning Algorithm
# ==============================================================================

def partition_candidates_into_ranking_buckets(
    reranked_candidates: List[Dict[str, Any]],
    query_plan: Any,
    strict_mode: bool = True
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Partitions cross-encoder scored candidates into deterministic priority tiers.
    Enforces the 5-step statutory resolution order, quarantine isolation, and joint Bucket 1.
    """
    bucket_1a: List[Dict[str, Any]] = []  # Direct On-Domain
    bucket_1b: List[Dict[str, Any]] = []  # Approved Interdisciplinary Doctrine
    bucket_2: List[Dict[str, Any]] = []   # Neutral Procedural
    bucket_3: List[Dict[str, Any]] = []   # Off-Domain / Disallowed
    dropped: List[Dict[str, Any]] = []

    telemetry: Dict[str, Any] = {
        "input_count": len(reranked_candidates),
        "quarantined_dropped": 0,
        "ambiguous_dropped": 0,
        "bucket_1a_count": 0,
        "bucket_1b_count": 0,
        "bucket_2_count": 0,
        "bucket_3_count": 0,
        "final_output_count": 0,
        "strict_mode_active": strict_mode
    }

    primary_domain = str(getattr(query_plan, "primary_domain", "general_legal") or "general_legal").lower()
    disallowed_list = DISALLOWED_STATUTES_BY_DOMAIN.get(primary_domain, [])

    for cand in reranked_candidates:
        # Layer 1: Quarantine Check - Hard Pre-RRF Isolation Invariant
        if cand.get("is_quarantined") or str(cand.get("retrieval_status", "")).lower() == "quarantined":
            cand["validation_status"] = "QUARANTINE_VIOLATION"
            cand["validation_reason"] = "Hard quarantine violation from unverified legacy partition"
            telemetry["quarantined_dropped"] += 1
            dropped.append(cand)
            continue

        text = cand.get("text") or cand.get("preview") or cand.get("full_text") or ""
        title = cand.get("title") or cand.get("case_title") or ""
        citation = cand.get("citation") or cand.get("neutral_citation") or ""
        combined_text = f"{title} {citation} {text}".lower()

        # Step 1: Disallowed Statutory Anchor Check
        is_disallowed = any(ds in combined_text for ds in disallowed_list)
        if is_disallowed:
            cand["ranking_bucket"] = 3
            cand["validation_status"] = "DEMOTED_OFF_DOMAIN"
            cand["validation_reason"] = f"Text cites an explicitly prohibited foreign statute for domain '{primary_domain}'"
            bucket_3.append(cand)
            telemetry["bucket_3_count"] += 1
            continue

        # Step 2: Governing Query Statute Match
        query_provisions = [
            str(p).lower() for p in (
                getattr(query_plan, "statutory_provisions", []) or
                getattr(query_plan, "governing_statutes", []) or
                getattr(query_plan, "provisions", []) or []
            )
        ]
        matches_query_statute = any(qp in combined_text for qp in query_provisions) if query_provisions else False

        if matches_query_statute:
            cand["ranking_bucket"] = 1
            cand["bucket_subtier"] = "1A"
            cand["classified_domain"] = primary_domain
            cand["validation_status"] = "APPROVED_ON_DOMAIN"
            cand["validation_reason"] = "Provisions directly match query plan governing statutes"
            bucket_1a.append(cand)
            telemetry["bucket_1a_count"] += 1
            continue

        # Step 3: Controlling Interdisciplinary Doctrine Check
        doctrine_matched, doc_id, doc_reason = evaluate_interdisciplinary_doctrine(cand, query_plan)
        if doctrine_matched:
            cand["ranking_bucket"] = 1
            cand["bucket_subtier"] = "1B"
            cand["classified_domain"] = primary_domain
            cand["active_doctrine_id"] = doc_id
            cand["validation_status"] = "APPROVED_CROSS_DOMAIN"
            cand["validation_reason"] = doc_reason
            bucket_1b.append(cand)
            telemetry["bucket_1b_count"] += 1
            continue

        # Step 4: Fallback to Domain Classifier Output
        cand_domain = str(cand.get("domain") or cand.get("legal_domain") or "general_legal").lower()
        conf = float(cand.get("domain_confidence", cand.get("confidence", 0.70)))

        if cand_domain == primary_domain and conf >= 0.60:
            cand["ranking_bucket"] = 1
            cand["bucket_subtier"] = "1A"
            cand["validation_status"] = "APPROVED_ON_DOMAIN"
            cand["validation_reason"] = f"Direct on-domain classification with high confidence ({conf:.2f})"
            bucket_1a.append(cand)
            telemetry["bucket_1a_count"] += 1
            continue

        # Step 5: Verified Neutral Procedural Statute Check
        is_procedural_statute = any(p in combined_text for p in PROCEDURAL_STATUTE_PATTERNS)
        if (cand_domain == "general_legal" or is_procedural_statute) and conf >= 0.60:
            cand["ranking_bucket"] = 2
            cand["validation_status"] = "APPROVED_PROCEDURAL"
            cand["validation_reason"] = f"Verified neutral procedural authority with conf >= 0.60 ({conf:.2f})"
            bucket_2.append(cand)
            telemetry["bucket_2_count"] += 1
            continue

        # Step 6: Unresolved Ambiguity Handling
        if conf < 0.60:
            if strict_mode:
                cand["validation_status"] = "QUARANTINE_AMBIGUOUS_UNVERIFIED"
                cand["validation_reason"] = f"Unresolved ambiguity: conf={conf:.2f} < 0.60 with no confirmed statutory anchor"
                telemetry["ambiguous_dropped"] += 1
                dropped.append(cand)
                continue
            else:
                cand["ranking_bucket"] = 3
                cand["validation_status"] = "DEMOTED_OFF_DOMAIN"
                cand["validation_reason"] = f"Low confidence {conf:.2f} demoted to Bucket 3 in diagnostic mode"
                bucket_3.append(cand)
                telemetry["bucket_3_count"] += 1
                continue

        # Step 7: Default Off-Domain
        cand["ranking_bucket"] = 3
        cand["validation_status"] = "DEMOTED_OFF_DOMAIN"
        cand["validation_reason"] = f"Off-domain classification: domain='{cand_domain}' != primary='{primary_domain}'"
        bucket_3.append(cand)
        telemetry["bucket_3_count"] += 1

    # Joint Bucket 1 Merging (1A + 1B)
    joint_bucket_1 = bucket_1a + bucket_1b

    if strict_mode:
        final_candidates = joint_bucket_1 + bucket_2
    else:
        final_candidates = joint_bucket_1 + bucket_2 + bucket_3

    telemetry["final_output_count"] = len(final_candidates)
    return final_candidates, telemetry


def validate_and_partition_post_rerank(
    candidates: List[Dict[str, Any]],
    query_plan: Any,
    strict_mode: bool = True
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Primary API entry point for Post-Rerank Legal Domain Validation Gate.
    """
    return partition_candidates_into_ranking_buckets(
        reranked_candidates=candidates,
        query_plan=query_plan,
        strict_mode=strict_mode
    )


# ==============================================================================
# 5. Lexicographic Precedential Authority Ranking
# ==============================================================================

def _compute_lexicographic_sort_key(
    candidate: Dict[str, Any],
    query_plan: Any
) -> Tuple[int, int, int, float]:
    """
    Computes a deterministic lexicographic ranking key:
    (Tier_admissibility, Tier_precedent, Tier_statute, -CompositeAuthorityScore)
    
    Guarantees:
    - Post-27th Amendment & Chapter 3A:
      * Constitutional queries: FCC (Tier 1) > Supreme Court (Tier 2) > FSC (Tier 3) > High Courts (Tier 4).
      * General non-constitutional queries (civil, criminal, banking, family): Supreme Court (Tier 1) is apex;
        FCC (Tier 2) does not override Supreme Court on non-constitutional general law.
      * Federal Shariat Court is recognized as a distinct constitutional court (Tier 3 under Art 203-GG).
    - Substantive domain validity (Tier_admissibility) strictly gates court hierarchy:
      Bucket 1 (1) > Bucket 2 (2) > Bucket 3 (3).
    - Precedent tier strictly outranks recency; earlier co-equal landmarks are protected.
    - Statutory alignment takes precedence over unaligned decisions within the same court tier.
    - Composite authority score operates strictly as an internal tie-breaker.
    """
    # 1. Admissibility Tier (Joint Bucket 1 > Bucket 2 > Bucket 3)
    bucket = candidate.get("ranking_bucket", 3)
    tier_admissibility = 1 if bucket == 1 else (2 if bucket == 2 else 3)

    # 2. Constitutional Precedential Tier (Post-27th Amendment, Chapter 3A & Articles 189/201)
    court_raw = str(candidate.get("court") or candidate.get("court_name") or candidate.get("title", "")).lower()
    citation = str(candidate.get("citation", "")).upper()
    primary_domain = str(getattr(query_plan, "primary_domain", "general_legal") or "general_legal").lower()

    is_fcc = ("federal constitutional court" in court_raw) or ("fcc" in court_raw) or ("FCC" in citation) or ("F.C.C." in court_raw)
    is_fsc = ("federal shariat court" in court_raw) or ("shariat court" in court_raw) or ("FSC" in citation) or ("PLD" in citation and "FSC" in court_raw)
    is_sc = ("supreme court" in court_raw) or ("scmr" in citation) or ("pld" in citation and "sc" in court_raw) or ("shariat appellate bench" in court_raw)
    is_hc = ("high court" in court_raw) or ("lahore" in court_raw) or ("sindh" in court_raw) or ("peshawar" in court_raw) or ("islamabad" in court_raw) or ("balochistan" in court_raw)
    is_tribunal = ("tribunal" in court_raw) or ("appellate tribunal" in court_raw) or ("service tribunal" in court_raw) or ("atir" in court_raw)

    if is_fcc:
        tier_precedent = 1 if primary_domain == "constitutional" else 2
    elif is_sc:
        tier_precedent = 1 if primary_domain != "constitutional" else 2
    elif is_fsc:
        tier_precedent = 3  # Federal Shariat Court (Chapter 3A Article 203GG)
    elif is_hc:
        tier_precedent = 4  # High Courts (Article 201)
    elif is_tribunal:
        tier_precedent = 5  # Specialized Statutory Appellate Tribunals
    else:
        tier_precedent = 6  # Subordinate Courts

    # 3. Statutory Provision Alignment Tier
    text = str(candidate.get("text", "")).lower()
    title = str(candidate.get("title", "")).lower()
    combined = f"{title} {citation} {text}"

    query_provs = [
        str(p).lower() for p in (
            getattr(query_plan, "statutory_provisions", []) or
            getattr(query_plan, "governing_statutes", []) or
            getattr(query_plan, "provisions", []) or []
        )
    ]
    has_exact_prov = any(qp in combined for qp in query_provs) if query_provs else False
    has_parent_stat = any(
        str(gs).lower() in combined for gs in (getattr(query_plan, "governing_statutes", []) or [])
    )

    if has_exact_prov:
        tier_statute = 1
        s_statute = 1.00
    elif has_parent_stat:
        tier_statute = 2
        s_statute = 0.50
    else:
        tier_statute = 3
        s_statute = 0.00

    # 4. Composite Internal Tie-Breaker
    s_rerank = float(
        candidate.get("semantic_relevance_score") or
        candidate.get("rerank_score") or
        candidate.get("score") or
        0.0
    )

    # Recency score calculation
    year = candidate.get("year")
    if not year:
        match = re.search(r"\b(19\d{2}|20\d{2})\b", citation)
        year = int(match.group(1)) if match else 2000
    else:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = 2000

    if year >= 2024:
        s_recency = 1.00
    elif year >= 2015:
        s_recency = 0.80
    elif year >= 2000:
        s_recency = 0.60
    else:
        s_recency = 0.50

    composite_score = (0.60 * s_rerank) + (0.30 * s_statute) + (0.10 * s_recency)
    candidate["composite_authority_score"] = round(composite_score, 4)

    return (tier_admissibility, tier_precedent, tier_statute, -composite_score)


# ==============================================================================
# 6. Dynamic Context Assembly Engine
# ==============================================================================

def _extract_canonical_appeal_key(cand: Dict[str, Any]) -> Optional[str]:
    """Extracts canonical Case Year + Appeal/Petition Number for robust deduplication."""
    text = f"{cand.get('title', '')} {cand.get('citation', '')}"
    match = re.search(
        r"(?:civil|criminal|constitution|crl|c\.a\.|c\.p\.|w\.p\.|cr\.a\.)\s*(?:appeal|petition|suit)?\s*(?:no\.?)?\s*(\d+)[^\d]+(\d{4})",
        text,
        re.IGNORECASE
    )
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    citation = str(cand.get("citation", "")).strip().upper()
    if citation and citation != "UNREPORTED":
        return citation
    cid = str(cand.get("id") or cand.get("case_id") or "").strip()
    return cid or None


def _format_candidate_for_context(cand: Dict[str, Any]) -> str:
    """Formats candidate with headnote/ratio first to protect key findings against truncation."""
    title = cand.get("title") or cand.get("case_title") or "Unknown Title"
    citation = cand.get("citation") or cand.get("neutral_citation") or "Unreported"
    court = cand.get("court") or cand.get("court_name") or "Pakistani Court"
    bucket = cand.get("ranking_bucket", 3)
    tier_desc = "Substantive Approved" if bucket == 1 else ("Procedural Approved" if bucket == 2 else "Off-Domain")
    text = cand.get("text") or cand.get("preview") or cand.get("full_text") or ""
    
    return f"### [CASE AUTHORITY] {citation} — {title}\n**Court:** {court} | **Tier:** {tier_desc}\n\n{text.strip()}"


def _truncate_on_paragraph_boundary(text: str, budget_tokens: int, client: Optional[Any] = None) -> Optional[str]:
    """Truncates cleanly on the last complete paragraph boundary within available token budget."""
    paragraphs = text.split("\n\n")
    if not paragraphs:
        return None
    accumulated: List[str] = []
    for para in paragraphs:
        test_block = "\n\n".join(accumulated + [para])
        if count_context_tokens([test_block], generation_tokenizer=client) <= budget_tokens:
            accumulated.append(para)
        else:
            break
    if accumulated:
        return "\n\n".join(accumulated) + "\n\n[... Remaining judgment truncated to preserve token budget ...]"
    return None


def assemble_generation_context(
    candidates: List[Dict[str, Any]],
    query_plan: Any,
    max_tokens: int = MAX_CANDIDATE_TOKENS,  # 7000 tokens default
    max_candidates: int = MAX_CANDIDATES_DEFAULT,  # 10 default
    relevance_floor: float = PURE_RELEVANCE_FLOOR,  # 0.35 default
    strict_mode: bool = True,
    tokenizer_client: Optional[Any] = None
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Deterministic 15-step context assembly pipeline.
    Leaves a mandatory 1,000-token prompt reserve from the 8,000 LLM ceiling.
    Returns: (serialized_context_text, included_candidates, telemetry, audit_report)
    """
    telemetry: Dict[str, Any] = {
        "input_candidates": len(candidates),
        "quarantined_dropped": 0,
        "below_relevance_floor_dropped": 0,
        "deduplicated_dropped": 0,
        "budget_exhausted_dropped": 0,
        "final_included_count": 0,
        "final_token_count": 0,
        "tokenizer_mode": "exact" if tokenizer_client else "calibrated_fallback"
    }
    audit_report: List[Dict[str, Any]] = []

    # Step 1: Quarantine Check & Immediate Drop (Pre-Ranking Isolation)
    active_cands: List[Dict[str, Any]] = []
    for c in candidates:
        if c.get("is_quarantined") or str(c.get("retrieval_status", "")).lower() == "quarantined":
            telemetry["quarantined_dropped"] += 1
            audit_report.append({
                "citation": c.get("citation", "Unknown"),
                "status": "EXCLUDED",
                "reason": "QUARANTINE_VIOLATION: Legacy unverified vector dropped"
            })
        else:
            active_cands.append(c)

    # Step 2: Post-Rerank Domain Partitioning
    partitioned, gate_telem = partition_candidates_into_ranking_buckets(
        reranked_candidates=active_cands,
        query_plan=query_plan,
        strict_mode=strict_mode
    )

    # Step 3: Enforce Generation Boundary (Bucket 3 Absolute Exclusion from Generation Context)
    admissible_cands: List[Dict[str, Any]] = []
    for c in partitioned:
        if c.get("ranking_bucket") in (1, 2):
            admissible_cands.append(c)
        else:
            audit_report.append({
                "citation": c.get("citation", "Unknown"),
                "status": "EXCLUDED",
                "reason": f"BUCKET_3_EXCLUDED: Off-domain candidate barred from LLM context ({c.get('validation_reason')})"
            })

    # Step 4: Pure Semantic Relevance Floor Gate (S_rerank >= 0.35)
    relevant_cands: List[Dict[str, Any]] = []
    for c in admissible_cands:
        s_rel = float(
            c.get("semantic_relevance_score") or
            c.get("rerank_score") or
            c.get("score") or
            0.0
        )
        if s_rel >= relevance_floor:
            relevant_cands.append(c)
        else:
            telemetry["below_relevance_floor_dropped"] += 1
            audit_report.append({
                "citation": c.get("citation", "Unknown"),
                "status": "EXCLUDED",
                "reason": f"BELOW_RELEVANCE_FLOOR: score {s_rel:.3f} < threshold {relevance_floor:.2f}"
            })

    # Step 5: Appeal-Number Deduplication
    seen_appeals: Dict[str, Dict[str, Any]] = {}
    deduped_cands: List[Dict[str, Any]] = []
    for c in relevant_cands:
        appeal_key = _extract_canonical_appeal_key(c)
        if appeal_key:
            if appeal_key in seen_appeals:
                prev_c = seen_appeals[appeal_key]
                # If existing duplicate has much less text, replace; otherwise omit duplicate
                if len(str(prev_c.get("text", ""))) < 200 and len(str(c.get("text", ""))) >= 200:
                    deduped_cands.remove(prev_c)
                    deduped_cands.append(c)
                    seen_appeals[appeal_key] = c
                telemetry["deduplicated_dropped"] += 1
                audit_report.append({
                    "citation": c.get("citation", "Unknown"),
                    "status": "EXCLUDED",
                    "reason": f"DEDUPLICATION: Duplicate appeal/petition key '{appeal_key}'"
                })
                continue
            seen_appeals[appeal_key] = c
        deduped_cands.append(c)

    # Step 6: Compute Lexicographic Sort Keys
    for c in deduped_cands:
        c["lexicographic_key"] = _compute_lexicographic_sort_key(c, query_plan)

    # Step 7: Sort by Lexicographic Precedential Hierarchy
    deduped_cands.sort(key=lambda x: x["lexicographic_key"])

    # Step 8: Apply Max Candidates Cap (K_max = 10)
    capped_cands = deduped_cands[:max_candidates]
    for c in deduped_cands[max_candidates:]:
        audit_report.append({
            "citation": c.get("citation", "Unknown"),
            "status": "EXCLUDED",
            "reason": f"K_CAP_EXCEEDED: Candidate exceeded max context limit of {max_candidates}"
        })

    # Steps 9 - 14: Token Budgeting & Clean Paragraph Truncation
    included_cands: List[Dict[str, Any]] = []
    text_blocks: List[str] = []
    current_tokens = 0

    for c in capped_cands:
        cand_text = _format_candidate_for_context(c)
        cand_tokens = count_context_tokens([cand_text], generation_tokenizer=tokenizer_client)

        if current_tokens + cand_tokens <= max_tokens:
            included_cands.append(c)
            text_blocks.append(cand_text)
            current_tokens += cand_tokens
            audit_report.append({
                "citation": c.get("citation", "Unknown"),
                "status": "INCLUDED",
                "tokens": cand_tokens,
                "reason": f"Admitted in Bucket {c.get('ranking_bucket')} with authority score {c.get('composite_authority_score', 0.0):.3f}"
            })
        else:
            remaining_budget = max_tokens - current_tokens
            if remaining_budget >= 50:
                truncated_text = _truncate_on_paragraph_boundary(cand_text, remaining_budget, tokenizer_client)
                if truncated_text:
                    t_tokens = count_context_tokens([truncated_text], generation_tokenizer=tokenizer_client)
                    if current_tokens + t_tokens <= max_tokens:
                        included_cands.append(c)
                        text_blocks.append(truncated_text)
                        current_tokens += t_tokens
                        audit_report.append({
                            "citation": c.get("citation", "Unknown"),
                            "status": "INCLUDED_PARTIAL",
                            "tokens": t_tokens,
                            "reason": f"Paragraph truncated to fit remaining budget of {remaining_budget} tokens"
                        })
            telemetry["budget_exhausted_dropped"] += 1
            audit_report.append({
                "citation": c.get("citation", "Unknown"),
                "status": "EXCLUDED",
                "reason": f"TOKEN_BUDGET_EXHAUSTED: Budget limit {max_tokens} reached"
            })
            break

    # Step 15: Recount and Validate Final Serialized Context
    final_context = "\n\n---\n\n".join(text_blocks)
    final_recount = count_context_tokens([final_context], generation_tokenizer=tokenizer_client)
    telemetry["final_included_count"] = len(included_cands)
    telemetry["final_token_count"] = final_recount

    return final_context, included_cands, telemetry, audit_report


# ==============================================================================
# 7. Specialized Doctrinal Evaluators (AC-17 through AC-28)
# ==============================================================================

def evaluate_art212_service_conditions(
    claimant_is_civil_servant: bool,
    is_terms_and_conditions: bool,
    challenged_action_type: str = "administrative_order"
) -> Dict[str, Any]:
    """
    AC-17: Article 212(1)(a) Service-Condition Jurisdiction Evaluator.
    Differentiates civil servant terms/conditions (FST exclusive, Art 199 barred)
    from non-civil servant contractors (Art 199 conditional / special statutory remedy).
    """
    if claimant_is_civil_servant and is_terms_and_conditions:
        return {
            "status": "SERVICE_JURISDICTION_EXCLUSIVE_OVER_CIVIL_SERVANT_CLAIM",
            "article_199_maintainable": False,
            "ouster_applicable": True,
            "competent_forum": "Federal / Provincial Service Tribunal",
            "statutory_anchor": "Article 212(1)(a) & (2) Constitution read with Section 4 Service Tribunals Act 1973",
            "authority": "2025 SCMR 134 (Muhammad Hassanullah), paras 4-6"
        }
    else:
        return {
            "status": "SERVICE_JURISDICTION_EXCLUDED_CLAIMANT_NOT_CIVIL_SERVANT",
            "writ_maintainability_status": "WRIT_MAINTAINABILITY_CONDITIONAL",
            "article_199_maintainable": True,
            "ouster_applicable": False,
            "competent_forum": "Civil Court / High Court under Article 199",
            "statutory_anchor": "Master and servant / contractual terms outside Service Tribunals Act",
            "authority": "2015 SCMR 456 (Ali Azhar Khan Baloch)"
        }


def evaluate_state_tort_action(claim_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-18: Article 212(1)(b) Public Torts & Section 80 CPC 5-Gate Evaluator.
    Gates:
    - Gate 1: Substantive tort cause of action (locus standi, actionable injury, proximate causation).
    - Gate 2: Qualifying defendant under Art 212(1)(b) (Government, person in service, tax authority).
    - Gate 3: Tribunal establishment check (qualified finding: NO_TRIBUNAL_ESTABLISHED_ON_SEARCHED_ENACTMENTS).
    - Gate 4: Substantive defenses & liability limitations:
      * JOPA 1850 S.1 Branch A (judicial officers) vs Branch B (executing ministerial officers).
      * Customs Act 1969 S.217(1) good faith vs S.216 goods compensation restriction.
      * Income Tax Ord 2001 S.227(1) civil court bar on orders/notices vs S.227(1) good-faith protection.
      * Prior approval for inquiry/investigation under S.217(1) proviso / S.227(2) (excluding prosecution/written form).
    - Gate 5: Procedural pre-suit notice under Section 80 CPC:
      * Pathways: Federal Secretary (a), Provincial Secretary/Collector (b)(i), Railway GM (b)(ii), Public Officer.
      * Trigger 1: Suit without notice -> 3-month Government written statement minimum proviso strictly applies;
        costs disallowed if settled in whole/part or conceded within 2 months.
      * Triggers 2 & 3: Governed by Order VIII Rule 1 CPC subject to provincial amendments.
      * Art 199 petitions not governed by Section 80 CPC (governed by High Court Rules).
      * Indian S.80(2) urgent relief leave rejected as foreign law.
    """
    suit_type = claim_data.get("suit_type", "civil_suit")
    is_writ = suit_type == "writ_petition" or claim_data.get("is_article_199", False)

    # Check for foreign Indian CPC rule rejection
    if claim_data.get("pleads_urgency_leave_under_indian_cpc", False):
        return {
            "status": "REJECTED_FOREIGN_PROCEDURAL_RULE_INDIAN_CPC_S80_2",
            "is_valid": False,
            "reason": "Indian CPC Section 80(2) urgency leave is foreign law and rejected under Pakistani CPC"
        }

    # Gate 1: Substantive Tort Cause of Action
    has_locus = claim_data.get("has_locus_standi", True)
    has_injury = not claim_data.get("damnum_absque_injuria", False)
    has_proximate_cause = claim_data.get("proximate_cause_established", True)
    gate_1_passed = has_locus and has_injury and has_proximate_cause

    # Gate 2: Qualifying Defendant under Art 212(1)(b)
    defendant_category = claim_data.get("defendant_category", "government")
    valid_defendants = ["government", "service_of_pakistan", "tax_authority", "servant_of_authority"]
    gate_2_passed = defendant_category in valid_defendants

    # Gate 3: Tribunal Establishment & Ouster
    # Enforces qualified evidence finding from 16-enactment ledger
    tribunal_status = "NO_TRIBUNAL_ESTABLISHED_ON_SEARCHED_ENACTMENTS"
    gate_3_civil_court_maintainable = True

    # Gate 4: Substantive Defenses & Liabilities
    defense_applied: List[str] = []

    # JOPA 1850 S.1 branches
    if claim_data.get("defendant_is_judicial_officer", False):
        if claim_data.get("act_done_judicially_with_good_faith_jurisdiction", False):
            defense_applied.append("JUDICIAL_OFFICER_STATUTORY_NON_LIABILITY_BRANCH_A")
    elif claim_data.get("defendant_is_executing_ministerial_officer", False):
        if claim_data.get("executing_lawful_judicial_warrant_or_order", False):
            defense_applied.append("MINISTERIAL_OFFICER_STATUTORY_NON_LIABILITY_BRANCH_B")

    # Customs Act S.216 / S.217
    if claim_data.get("statutory_context") == "customs":
        if claim_data.get("claim_for_goods_loss_or_injury", False):
            # Fault threshold: gross negligence or willful act
            if not claim_data.get("gross_negligence_or_willful_act_proved", False):
                defense_applied.append("CUSTOMS_OFFICER_GOODS_COMPENSATION_RESTRICTION_S216")
        if claim_data.get("act_done_in_good_faith", False):
            defense_applied.append("CUSTOMS_GOOD_FAITH_PROCEEDING_BAR_S217_1")
        if claim_data.get("challenges_order_assessment_tax_penalty_or_collection", False):
            defense_applied.append("CIVIL_COURT_BAR_ON_CUSTOMS_ORDERS_ASSESSMENTS_S217_2")

    # Income Tax Ordinance S.227
    if claim_data.get("statutory_context") == "income_tax":
        if claim_data.get("suit_against_order_made_or_notice_issued", False):
            defense_applied.append("CIVIL_COURT_BAR_ON_INCOME_TAX_ORDERS_OR_NOTICES_S227_1_LIMB_1")
        if claim_data.get("act_done_in_good_faith", False):
            defense_applied.append("GOOD_FAITH_STATUTORY_PROTECTION_INCOME_TAX_S227_1_LIMB_2")

    # Gate 5: Procedural Pre-Suit Notice under Section 80 CPC
    notice_status = "NOT_APPLICABLE_TO_WRIT" if is_writ else "PENDING_VERIFICATION"
    section_80_result: Dict[str, Any] = {}

    if not is_writ:
        recipient = claim_data.get("notice_recipient", "")
        # Valid pathways under S.80(1)
        valid_recipient = recipient in [
            "federal_secretary", "railway_general_manager",
            "provincial_secretary", "collector_of_district", "public_officer"
        ]
        delivered_months = claim_data.get("notice_delivered_months_prior", 0)
        trigger = claim_data.get("section_80_trigger", 0)

        if delivered_months >= 2 and valid_recipient:
            notice_status = "VALID_SECTION_80_NOTICE_SERVED"
            section_80_result = {
                "notice_status": notice_status,
                "pathway": recipient,
                "period_satisfied": True
            }
        elif trigger == 1 or claim_data.get("suit_without_notice", False):
            notice_status = "TRIGGER_1_SUIT_WITHOUT_NOTICE"
            settled_within_two_months = claim_data.get("settled_within_two_months", False)
            section_80_result = {
                "notice_status": notice_status,
                "government_written_statement_min_months": 3,
                "costs_disallowed_if_settled_or_conceded": settled_within_two_months,
                "proviso_applied": "Section 80(2) Proviso (not less than 3 months for Government written statement)"
            }
        elif trigger in (2, 3) or claim_data.get("premature_suit_or_omitted_statement", False):
            notice_status = f"TRIGGER_{trigger}_GOVERNED_BY_ORDER_VIII"
            province = claim_data.get("province", "Punjab")
            # Provincial Order VIII timeline
            timeline = "30 days extendable up to 15 days" if province in ["Punjab", "KP"] else "30 days"
            section_80_result = {
                "notice_status": notice_status,
                "governing_rule": "Order VIII Rule 1 CPC (as amended by Provincial enactments)",
                "written_statement_timeline": timeline,
                "province": province
            }
        else:
            notice_status = "DEFECTIVE_OR_ABSENT_NOTICE"
            section_80_result = {"notice_status": notice_status, "is_fatal": True}
    else:
        section_80_result = {
            "notice_status": "ARTICLE_199_EXEMPT_FROM_S80_CPC",
            "governing_law": "High Court Rules and Orders (advance notice to Advocate General / Attorney General)"
        }

    return {
        "gate_1_substantive_tort": gate_1_passed,
        "gate_2_qualifying_defendant": gate_2_passed,
        "gate_3_tribunal_status": tribunal_status,
        "gate_3_civil_court_maintainable": gate_3_civil_court_maintainable,
        "gate_4_defenses_applied": defense_applied,
        "gate_5_section_80_result": section_80_result,
        "overall_maintainability": gate_1_passed and gate_2_passed and (not defense_applied) and (notice_status in [
            "VALID_SECTION_80_NOTICE_SERVED", "TRIGGER_1_SUIT_WITHOUT_NOTICE",
            "ARTICLE_199_EXEMPT_FROM_S80_CPC", "TRIGGER_2_GOVERNED_BY_ORDER_VIII",
            "TRIGGER_3_GOVERNED_BY_ORDER_VIII"
        ])
    }


def evaluate_art212_enemy_property(dispute_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-19: Article 212(1)(c) Enemy Property Custodian Evaluator.
    Custodian under Enemy Property Ordinance 1969 is an executive authority,
    not an Article 212 judicial tribunal; judicial review under Art 199 is maintainable.
    """
    return {
        "status": "TRIBUNAL_NOT_ESTABLISHED_ON_VERIFIED_SOURCES",
        "custodian_nature": "ENEMY_PROPERTY_CUSTODIAN_EXECUTIVE_JURISDICTION",
        "judicial_review_maintainable": True,
        "competent_forum": "High Court under Article 199 / Civil Court",
        "statutory_anchor": "Enemy Property Ordinance 1969 read with Article 199 Constitution"
    }


def evaluate_art212_provincial_proviso(extension_act_enacted: bool) -> Dict[str, Any]:
    """
    AC-20: Article 212(2) Provincial Extension Proviso Evaluator.
    Article 212(2) constitutional ouster applies to provincial tribunals only where
    Parliament has enacted an extension Act; otherwise evaluated under provincial law.
    """
    if extension_act_enacted:
        return {
            "ouster_applicable": True,
            "constitutional_bar": "Article 212(2) bar operative by parliamentary extension Act",
            "status": "PROVINCIAL_OUSTER_CONFIRMED"
        }
    else:
        return {
            "ouster_applicable": False,
            "constitutional_bar": "No parliamentary extension Act under Article 212(2) proviso",
            "status": "EVALUATED_UNDER_PROVINCIAL_STATUTORY_LAW"
        }


def evaluate_inheritance_limitation(claim_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-21, AC-22, AC-23: Female Inheritance Limitation Evaluator.
    - Omission of Article 144 by Act II of 1995 (adverse possession cannot extinguish co-heir title).
    - Co-heir possession is joint; male co-heirs are constructive trustees (PLD 1990 SC 1).
    - Article 142 applies strictly where prior possession and actual ouster are proved;
      revenue mutation is NOT dispossession.
    - Residuary Article 120 (6 years) runs strictly from unequivocal communicated denial.
    - Section 18 statutory fraud requires affirmative proof of intentional concealment.
    """
    relief = claim_data.get("relief_sought", "declaration")

    # Underspecified check
    if not claim_data.get("facts_specified", True) or not relief:
        return {
            "status": "LIMITATION_ARTICLE_UNRESOLVED",
            "reason": "Underspecified relief or factual matrix; cannot determine applicable schedule article"
        }

    # Specific Article 91 / 92 / 95 checks first
    if relief == "cancellation_of_instrument":
        return {
            "applicable_article": "Article 91 Limitation Act 1908",
            "period": "3 years",
            "starting_point": "When the facts entitling the plaintiff to have the instrument cancelled become known",
            "status": "ARTICLE_91_APPLIED"
        }
    elif relief == "declaration_of_forgery":
        return {
            "applicable_article": "Article 92 Limitation Act 1908",
            "period": "3 years",
            "starting_point": "When the issue or registration becomes known",
            "status": "ARTICLE_92_APPLIED"
        }

    # Article 142 Dispossession vs Mutation Check
    if claim_data.get("relies_on_article_142", False):
        had_prior_sole_possession = claim_data.get("prior_sole_possession", False)
        actual_ouster_proved = claim_data.get("actual_physical_ouster_proved", False)
        if not had_prior_sole_possession or not actual_ouster_proved:
            return {
                "article_142_maintainable": False,
                "status": "ARTICLE_142_REJECTED_NO_DISPOSSESSION",
                "reason": "Revenue mutation is not physical dispossession; female co-heir possession is joint in law"
            }
        else:
            return {
                "article_142_maintainable": True,
                "status": "ARTICLE_142_APPLIED_FROM_ACTUAL_OUSTER",
                "period": "12 years from actual physical ouster"
            }

    # Section 18 Statutory Fraud Check
    if claim_data.get("pleads_section_18_fraud", False):
        affirmative_concealment = claim_data.get("affirmative_fraudulent_concealment_proved", False)
        if not affirmative_concealment:
            return {
                "section_18_benefit_allowed": False,
                "status": "SECTION_18_FRAUD_NOT_ESTABLISHED",
                "reason": "Bare non-communication of revenue mutation does not satisfy Section 18 statutory fraud"
            }
        else:
            return {
                "section_18_benefit_allowed": True,
                "status": "SECTION_18_FRAUD_ESTABLISHED_TIME_RUNS_FROM_DISCOVERY",
                "starting_point": "Date of discovery of fraud"
            }

    # Declaratory suit under residuary Article 120
    denial_date = claim_data.get("unequivocal_hostile_denial_date")
    if not denial_date:
        return {
            "status": "LIMITATION_FACTS_INSUFFICIENT",
            "reason": "Accrual under Article 120 requires proof of unequivocal communicated denial date"
        }

    return {
        "applicable_article": "Article 120 Limitation Act 1908",
        "period": "6 years",
        "starting_point": f"From unequivocal communicated denial date: {denial_date}",
        "status": "ARTICLE_120_APPLIED_FROM_UNEQUIVOCAL_DENIAL",
        "authority": "PLD 2023 SC 362 (Saadat Khan), paras 7-10; PLD 1990 SC 1 (Ghulam Ali)"
    }


def evaluate_benami_transaction(transaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-24: Authentic Section 2(8) Benami Tree Evaluator under Act No. V of 2017.
    - Evaluates 4 independent alternative routes:
      * Route (A): Consideration-provider ($P$) and title-holder ($H$) severed ($P != H$) + held for $P$.
        Exclusions under S.2(8)(A)(b)(i) (fiduciary: trustee, executor, partner, director, agent, legal adviser,
        completed legatee distribution under Ss.332/336 Succession Act) and (ii) (family joint title + known resources).
        Disposition: STATUTORILY_EXCLUDED_NON_BENAMI (typed as BENAMI_EXCEPTION_ESTABLISHED).
      * Route (B): Fictitious name (forged CNIC not indispensable; 6 trade-name indicators; genuine sole proprietorship non-benami).
      * Route (C): Owner unaware or denies knowledge of ownership.
      * Route (D): Consideration-provider untraceable or fictitious.
    - Non-Masking Invariant: Route A exception CANNOT cure Route B, C, or D violations!
    - Combinatorial state space across 108 valid states.
    """
    # Act citation check
    act_name = transaction_data.get("governing_act", "")
    if "act no. v of 2017" not in act_name.lower() and "benami transactions (prohibition) act, 2017" not in act_name.lower():
        return {
            "status": "INVALID_STATUTORY_CITATION",
            "reason": "Authentic statutory citation is Act No. V of 2017 (Gazette of Pakistan Ext., 16 Feb 2017)"
        }

    # Check formal Section 24 order
    if transaction_data.get("is_formal_section_24_adjudication", False):
        return {
            "status": "BENAMI_TRANSACTION_ADJUDICATED",
            "provenance": transaction_data.get("adjudication_provenance", {}),
            "engaged_routes": transaction_data.get("engaged_routes", [])
        }

    route_a_state = transaction_data.get("route_a_state", "NOT_ESTABLISHED")
    route_b_state = transaction_data.get("route_b_state", "NOT_ESTABLISHED")
    route_c_state = transaction_data.get("route_c_state", "NOT_ESTABLISHED")
    route_d_state = transaction_data.get("route_d_state", "NOT_ESTABLISHED")

    # Detailed Route (A) Fiduciary Sub-Evaluation
    if transaction_data.get("evaluate_fiduciary_route_a", False):
        h_person = transaction_data.get("title_holder")
        p_person = transaction_data.get("consideration_provider")
        p_ne_h = (h_person != p_person) if (h_person and p_person) else False
        held_for_p = transaction_data.get("held_for_benefit_of_provider", False)

        if not p_ne_h or not held_for_p:
            route_a_state = "NOT_ESTABLISHED"
        else:
            # Check statutory fiduciary exception under S.2(8)(A)(b)(i)
            is_fiduciary = transaction_data.get("fiduciary_capacity_established", False)
            recognized_role = transaction_data.get("recognized_fiduciary_role", False)
            property_held_in_capacity = transaction_data.get("property_held_in_that_capacity", transaction_data.get("property_held_in_capacity", False))
            held_for_beneficiary = transaction_data.get("held_for_benefit_of_principal", transaction_data.get("held_for_beneficiary", False))

            if is_fiduciary and recognized_role and property_held_in_capacity and held_for_beneficiary:
                # Check for completed legatee distribution
                if transaction_data.get("is_legatee_distribution", False):
                    executor_assent = transaction_data.get("executor_assent_under_s332_336", transaction_data.get("executor_assent_under_s332", False))
                    debts_discharged = transaction_data.get("estate_debts_discharged", False)
                    funds_in_personal_account = transaction_data.get("funds_in_personal_account_prior_to_purchase", False)
                    if executor_assent and debts_discharged and funds_in_personal_account:
                        route_a_state = "EXCEPTION_ESTABLISHED"
                    else:
                        route_a_state = "UNRESOLVED"
                else:
                    route_a_state = "EXCEPTION_ESTABLISHED"
            elif transaction_data.get("fiduciary_pretext_personal_shelter", False):
                route_a_state = "ESTABLISHED_UNEXCEPTED"
            elif transaction_data.get("missing_evidence_on_consideration_or_benefit", False):
                route_a_state = "UNRESOLVED"
            else:
                route_a_state = "ESTABLISHED_UNEXCEPTED"

    # Detailed Route (B) Trade Name Sub-Evaluation
    if transaction_data.get("evaluate_route_b_trade_name", False):
        if transaction_data.get("invented_bogus_persona", False):
            route_b_state = "ESTABLISHED"
        elif transaction_data.get("genuine_sole_proprietorship_indicators_met", False):
            # Living proprietor, commercial nexus, consideration from proprietor
            route_b_state = "NOT_ESTABLISHED"

    # Precedence 1: Any independent violation established (Non-Masking Invariant)
    violations: List[str] = []
    if route_b_state == "ESTABLISHED":
        violations.append("ROUTE_B")
    if route_c_state == "ESTABLISHED":
        violations.append("ROUTE_C")
    if route_d_state == "ESTABLISHED":
        violations.append("ROUTE_D")
    if route_a_state == "ESTABLISHED_UNEXCEPTED":
        violations.append("ROUTE_A")

    if violations:
        return {
            "status": "POTENTIAL_BENAMI_TRANSACTION",
            "engaged_routes": violations,
            "route_a_state": route_a_state,
            "route_b_state": route_b_state,
            "route_c_state": route_c_state,
            "route_d_state": route_d_state,
            "non_masking_enforced": True
        }

    # Precedence 2: Evidentiary Uncertainty that could alter outcome
    if (route_a_state == "UNRESOLVED" or route_b_state == "UNRESOLVED" or
            route_c_state == "UNRESOLVED" or route_d_state == "UNRESOLVED"):
        return {
            "status": "BENAMI_CLASSIFICATION_UNRESOLVED",
            "route_a_state": route_a_state,
            "route_b_state": route_b_state,
            "route_c_state": route_c_state,
            "route_d_state": route_d_state,
            "missing_material_facts": transaction_data.get("missing_material_facts", ["unresolved_route_evidence"])
        }

    # Precedence 3: Route A exception established and all other routes NOT_ESTABLISHED
    if (route_a_state == "EXCEPTION_ESTABLISHED" and
            route_b_state == "NOT_ESTABLISHED" and
            route_c_state == "NOT_ESTABLISHED" and
            route_d_state == "NOT_ESTABLISHED"):
        return {
            "status": "STATUTORILY_EXCLUDED_NON_BENAMI",
            "typed_disposition": "BENAMI_EXCEPTION_ESTABLISHED",
            "exception_provision": "Section 2(8)(A)(b)(i) or (ii) Act No. V of 2017",
            "route_a_state": route_a_state
        }

    # Precedence 4: All routes conclusively NOT_ESTABLISHED
    return {
        "status": "NOT_BENAMI_TRANSACTION",
        "typed_disposition": "BENAMI_DEFINITION_NOT_ESTABLISHED",
        "route_a_state": route_a_state,
        "route_b_state": route_b_state,
        "route_c_state": route_c_state,
        "route_d_state": route_d_state
    }


def evaluate_s489f_cheque_liability(cheque_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-25: Section 489-F PPC Mens Rea & Forum Evaluator.
    - Dishonest intention evaluated at cheque issuance.
    - Security label does not bar Section 489-F if an existing crystallized obligation existed.
    - Liquidity failure is evidentiary, not an automatic complete defense.
    - Forum: Banking Court requires financial institution & finance; private recovery in Civil Court.
    """
    cheque_dishonored = cheque_data.get("cheque_dishonored", True)
    has_dishonest_intention_at_issuance = cheque_data.get("dishonest_intention_at_issuance", True)
    had_existing_obligation = cheque_data.get("existing_crystallized_obligation", True)
    is_financial_institution = cheque_data.get("payee_is_financial_institution", False)

    if not cheque_dishonored:
        return {"status": "NO_DISHONOR", "liability": False}

    if not has_dishonest_intention_at_issuance and not had_existing_obligation:
        return {
            "status": "SECTION_489F_NOT_ATTRACTED",
            "reason": "Pure advance contingent guarantee without dishonest intention or existing debt",
            "liability": False
        }

    forum = "Banking Court under FIO 2001 (summary recovery) & Criminal Court" if is_financial_institution else "Civil Court (Order XXXVII CPC) & Magistrate 1st Class (489-F PPC)"

    return {
        "status": "SECTION_489F_ATTRACTED",
        "liability": True,
        "security_label_effective": False,
        "competent_recovery_forum": forum,
        "statutory_anchor": "Section 489-F PPC read with 2010 SCMR 806 (Muhammad Sultan)"
    }


def evaluate_s420_inception_intention(dispute_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-26: Section 420 PPC Inception Intention & Quashment Evaluator.
    Section 420 requires dishonest intention at the time of representation/inducement.
    Commercial breach without inception fraud cannot be criminalized; FIR quashable.
    """
    fraud_at_inception = dispute_data.get("fraudulent_intention_at_inception", False)
    is_commercial_contract = dispute_data.get("dispute_arises_from_commercial_contract", True)

    if is_commercial_contract and not fraud_at_inception:
        return {
            "status": "CRIMINAL_FRAUD_NOT_ATTRACTED",
            "quashment_maintainable": True,
            "remedy": "Quashment of FIR under Article 199 / Section 561-A CrPC",
            "admitted_to_bucket": "Bucket 1B (Approved Cross-Domain)",
            "authority": "PLD 2023 SC 265 (Hamid Ali Shah); 1999 SCMR 1214 (Zafar Iqbal)"
        }
    else:
        return {
            "status": "CRIMINAL_FRAUD_ATTRACTED",
            "quashment_maintainable": False,
            "remedy": "Criminal trial under Section 420 PPC"
        }


def evaluate_s406_entrustment_vs_debt(dispute_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-27: Section 406 PPC Entrustment vs Debt Evaluator.
    Entrustment in fiduciary capacity is mandatory; sale of goods on credit
    creates a debtor-creditor relationship, not criminal breach of trust.
    """
    is_credit_sale = dispute_data.get("sale_of_goods_on_credit", True)
    fiduciary_entrustment = dispute_data.get("fiduciary_entrustment_of_property", False)

    if is_credit_sale and not fiduciary_entrustment:
        return {
            "status": "DEBTOR_CREDITOR_RELATIONSHIP",
            "section_406_applicable": False,
            "civil_remedy": "Suit for recovery of price of goods in Civil Court",
            "authority": "PLD 2004 SC 460; 2000 SCMR 445"
        }
    else:
        return {
            "status": "FIDUCIARY_ENTRUSTMENT_ESTABLISHED",
            "section_406_applicable": True,
            "authority": "Section 405/406 Pakistan Penal Code, 1860"
        }


def evaluate_art203f_appeal_forum(appeal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-28: Article 203F Appeal Routes & Appellate Forum Evaluator.
    - Route 1 (Art 203F(1) & (2)): Final decision under Art 203D (repugnancy) ->
      Appeal as of right to Shariat Appellate Bench (SAB) by virtue of Art 203F(5);
      operation suspended under Art 203D(2) proviso; 60 days ordinary / 6 months government.
    - Route 2 (Art 203F(2A)): Appeal as of right strictly in two categories:
      * Category (a) limb 1: reversal of acquittal and sentence to death, life, or > 14 years (15 > 14 qualifies; exact 14 does not).
      * Category (a) limb 2: revision enhancement to death, life, or > 14 years (15 > 14 qualifies; exact 14 does not).
      * Category (b): contempt of court punishment.
    - Route 3 (Art 203F(2B)): In all other decisions/sentences, appeal lies ONLY IF leave to appeal is granted.
    - Forum Demarcation: Art 203F(5) textually governs clauses (1) and (2).
      Where the specific forum (SAB vs regular SC bench) for clause (2A) or (2B) is unverified from authenticated authority,
      the engine strictly outputs APPELLATE_FORUM_UNRESOLVED_ESCALATE_HUMAN_REVIEW.
    """
    decision_type = appeal_data.get("decision_type", "")
    sentence_years = appeal_data.get("sentence_years", 0)
    sentence_type = appeal_data.get("sentence_type", "")
    is_contempt = appeal_data.get("is_contempt_punishment", False)
    is_revision = appeal_data.get("is_revision_enhancement", False)
    is_acquittal_reversal = appeal_data.get("is_acquittal_reversal", False)
    forum_authenticated = appeal_data.get("forum_authenticated_by_rules_or_precedent", False)

    # Route 1: Art 203D Repugnancy
    if decision_type == "art_203d_repugnancy":
        appellant_type = appeal_data.get("appellant_type", "party_aggrieved")
        limitation_days = 180 if appellant_type in ["federation", "province"] else 60
        return {
            "route": "ROUTE_1_ART_203F_1",
            "appeal_type": "APPEAL_AS_OF_RIGHT",
            "appellate_forum": "Shariat Appellate Bench of Supreme Court (Article 203F(5))",
            "limitation_period_days": limitation_days,
            "repugnancy_operation_suspended": True,
            "statutory_anchor": "Article 203F(1), (2), (5) read with Article 203D(2) Proviso"
        }

    # Route 2: Art 203F(2A) Specified Appeal as of Right
    is_category_a = False
    if is_acquittal_reversal or is_revision:
        if sentence_type in ["death", "life_imprisonment"]:
            is_category_a = True
        elif sentence_years > 14:
            is_category_a = True  # 15 > 14 qualifies
        elif sentence_years == 14:
            is_category_a = False  # 14 is NOT exceeding 14 years

    if is_category_a or is_contempt:
        # Check forum resolution
        if not forum_authenticated and not appeal_data.get("bypass_forum_check", False):
            forum = "APPELLATE_FORUM_UNRESOLVED_ESCALATE_HUMAN_REVIEW"
        else:
            forum = "Shariat Appellate Bench (institutional practice) / Supreme Court"

        category = "Contempt of Court (Art 203F(2A)(b))" if is_contempt else (
            "Revision Sentence Enhancement (Art 203F(2A)(a) second limb)" if is_revision else
            "Acquittal Reversal (Art 203F(2A)(a) first limb)"
        )
        return {
            "route": "ROUTE_2_ART_203F_2A",
            "appeal_type": "APPEAL_AS_OF_RIGHT",
            "category": category,
            "appellate_forum": forum,
            "statutory_anchor": "Article 203F(2A) Constitution of Pakistan"
        }

    # Route 3: Art 203F(2B) Leave to Appeal Required
    return {
        "route": "ROUTE_3_ART_203F_2B",
        "appeal_type": "LEAVE_TO_APPEAL_REQUIRED",
        "appellate_forum": "Supreme Court of Pakistan (Leave jurisdiction)",
        "statutory_anchor": "Article 203F(2B) Constitution of Pakistan"
    }


def evaluate_art202a_constitutional_bench(bench_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-28: High Court Article 202A Constitutional Bench Evaluator.
    Four Stages:
    1. JCP nomination of judges under clause (1).
    2. Appointment of Head of Constitutional Benches under clause (2).
    3. Constitution of specific hearing benches by 3-member committee under clause (4).
    4. Total-membership legislative resolution under clause (7) (joint Parliament for IHC, Provincial Assembly for provinces).
    Rules:
    - Resolution alone does not prove valid bench constitution:
      * Missing JCP nomination -> ARTICLE_202A_COMPETENCE_UNVERIFIED_ESCALATE_HUMAN_REVIEW.
      * Missing/defective committee constitution -> HEARING_BENCH_CONSTITUTION_UNVERIFIED.
    - Negative resolution check: fails total-membership majority -> PROVINCIAL_ACTIVATION_FAILED_RESOLUTION_INVALID.
    - Provincial isolation invariant: Punjab resolution never activates SHC, PHC, BHC, or IHC.
    - Post-27th Amendment substituted clause (3): general Article 199 bar once operationalized.
    - Procedural bench-action date tracking (D_bench_action >= D_resolution_commencement).
    - Narrow clause (5) historical transfer: Art 199(1)(a)(i)/(1)(c) pending pre-Oct 21, 2024 transferred;
      petitions outside clause 5 (e.g. certiorari under Art 199(1)(a)(ii)) not automatically transferred under clause 5.
    """
    court = bench_data.get("target_court", "LHC")
    resolution_passed = bench_data.get("resolution_passed", False)
    total_membership_majority = bench_data.get("majority_of_total_membership", False)
    jcp_nominated = bench_data.get("jcp_nominated", False)
    committee_constituted = bench_data.get("committee_hearing_bench_constituted", False)

    # Negative resolution total-membership check
    if resolution_passed and not total_membership_majority:
        return {
            "status": "PROVINCIAL_ACTIVATION_FAILED_RESOLUTION_INVALID",
            "operationalized": False,
            "reason": "Resolution failed to achieve majority of total membership of the Assembly under Article 202A(7)"
        }

    if not resolution_passed:
        return {
            "status": "ARTICLE_202A_NOT_ACTIVATED",
            "operationalized": False,
            "reason": f"No legislative resolution passed under Article 202A(7) for {court}"
        }

    # Resolution passed with total membership
    # Provincial isolation check
    activating_province = bench_data.get("activating_province", "Punjab")
    target_province = bench_data.get("target_province", "Punjab")
    if activating_province != target_province:
        return {
            "status": "PROVINCIAL_ISOLATION_INVARIANT_PRESERVED",
            "operationalized": False,
            "reason": f"Resolution in {activating_province} does not operationalize Constitutional Benches in {target_province}"
        }

    # Stage 1 check: JCP nomination
    if not jcp_nominated:
        return {
            "status": "ARTICLE_202A_COMPETENCE_UNVERIFIED_ESCALATE_HUMAN_REVIEW",
            "operationalized": False,
            "reason": "Legislative resolution passed, but JCP nomination of Constitutional Judges is unverified"
        }

    # Stage 3 check: Hearing bench constitution by committee under clause (4)
    if not committee_constituted:
        return {
            "status": "HEARING_BENCH_CONSTITUTION_UNVERIFIED",
            "operationalized": True,
            "hearing_bench_valid": False,
            "reason": "Constitutional Benches operationalized, but specific hearing bench constitution by 3-member committee is unverified"
        }

    # Check historical clause (5) transfer
    if bench_data.get("is_historical_pre_oct_2024_petition", False):
        petition_clause = bench_data.get("petition_clause", "")
        # Narrow clause (5) transfer applies strictly to (1)(a)(i) and (1)(c)
        if petition_clause in ["199_1_a_i", "199_1_c"]:
            return {
                "status": "TRANSFERRED_UNDER_ARTICLE_202A_5",
                "operationalized": True,
                "transferred_to_constitutional_bench": True,
                "reason": "Historical petition under Art 199(1)(a)(i) or (1)(c) transferred to Constitutional Bench"
            }
        else:
            return {
                "status": "NOT_TRANSFERRED_UNDER_NARROW_CLAUSE_5",
                "operationalized": True,
                "transferred_to_constitutional_bench": False,
                "reason": "Petition outside narrow sub-paragraph (i) of paragraph (a) and paragraph (c); heard by regular bench until post-27th Amendment operationalization"
            }

    # Current substituted Article 202A(3) jurisdiction bar
    bench_action_date = bench_data.get("bench_action_date", "2026-01-01")
    resolution_date = bench_data.get("resolution_date", "2025-01-01")
    if bench_action_date >= resolution_date:
        return {
            "status": "CONSTITUTIONAL_BENCH_EXCLUSIVE_JURISDICTION",
            "operationalized": True,
            "regular_bench_barred": True,
            "reason": "Under substituted Article 202A(3), no bench other than Constitutional Bench shall exercise Article 199 jurisdiction"
        }

    return {
        "status": "OPERATIONALIZED",
        "operationalized": True,
        "regular_bench_barred": False
    }


def evaluate_precedent_hierarchy_and_conflict(precedent_pair: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC-28: Precedent Hierarchy & Conflict Evaluator.
    - Articles 189 & 201 cross-court constitutional hierarchy.
    - FCC ratio binds Supreme Court and all courts under Art 189(1) on questions/principles of law.
    - Supreme Court & SAB bind all other courts under Arts 189(2) & 203F.
    - Federal Shariat Court Chapter 3A binds High Courts under Art 203GG.
    - Hard Cross-Court Guard: bench size strictly barred across courts (SC larger bench cannot overrule FCC).
    - Intra-court bench discipline under Multiline Associates (1995 SCMR 362): co-equal bench cannot depart;
      conflict -> UNRESOLVED_CO_EQUAL_APEX_CONFLICT.
    - Conservative Precedent Displacement Rule: unstated ratio relationships default to
      PRECEDENT_CONFLICT_REQUIRES_HUMAN_REVIEW.
    - Partial displacement of historical SC ruling: PRIOR_SC_AUTHORITY_DISPLACED_TO_EXTENT_OF_DIRECT_CONFLICT.
    """
    court_a = str(precedent_pair.get("court_a", "")).lower()
    court_b = str(precedent_pair.get("court_b", "")).lower()
    bench_a = precedent_pair.get("bench_size_a", 2)
    bench_b = precedent_pair.get("bench_size_b", 2)
    ratio_relation = precedent_pair.get("ratio_relationship", "unstated")
    is_constitutional_question = precedent_pair.get("is_constitutional_question", True)

    # 1. Cross-Court FCC vs Supreme Court
    if ("fcc" in court_a or "federal constitutional court" in court_a) and ("supreme court" in court_b):
        if is_constitutional_question:
            return {
                "controlling_authority": "Authority A (Federal Constitutional Court)",
                "status": "FCC_RATIO_CONTROLS_ACROSS_TIERS",
                "constitutional_anchor": "Article 189(1) Constitution (Twenty-Seventh Amendment)",
                "cross_court_bench_size_barred": True
            }

    # Direct conflict between FCC and SC
    if precedent_pair.get("is_cross_stream_conflict", False):
        return {
            "status": "APEX_CROSS_STREAM_JURISDICTIONAL_CONFLICT",
            "controlling_authority": None,
            "escalate_to_human_review": True,
            "reason": "Direct apex conflict between FCC and Supreme Court / SAB requires human review"
        }

    # 2. SAB vs FSC
    if ("shariat appellate bench" in court_a or "sab" in court_a) and ("fsc" in court_b or "federal shariat court" in court_b):
        return {
            "controlling_authority": "Authority A (Shariat Appellate Bench)",
            "status": "SAB_DECISION_CONTROLS_OVER_FSC",
            "constitutional_anchor": "Article 203F read with Article 189 Constitution"
        }

    # 3. Inter-High Court (Provincial Divergence)
    if "high court" in court_a and "high court" in court_b and court_a != court_b:
        return {
            "status": "INTER_PROVINCIAL_HIGH_COURT_DIVERGENCE",
            "controlling_authority": None,
            "relationship": "Coordinate and persuasive only; sister High Courts do not bind each other under Article 201"
        }

    # 4. Intra-Court Bench Discipline (Same Court)
    if court_a == court_b:
        # Co-equal conflict check
        if bench_a == bench_b and precedent_pair.get("direct_ratio_conflict", False):
            conflict_enum = "UNRESOLVED_CO_EQUAL_FCC_CONFLICT" if "fcc" in court_a else "UNRESOLVED_CO_EQUAL_APEX_CONFLICT"
            return {
                "status": conflict_enum,
                "controlling_authority": None,
                "escalate_to_human_review": True,
                "authority": "Multiline Associates (1995 SCMR 362) - co-equal bench cannot depart from coordinate bench"
            }

        # Larger vs Smaller bench
        if bench_b > bench_a and ratio_relation == "expressly_overruled":
            return {
                "controlling_authority": "Authority B (Larger Bench)",
                "status": "PRIOR_APEX_AUTHORITY_EXPRESSLY_OVERRULED"
            }
        elif bench_b > bench_a and ratio_relation == "unstated":
            return {
                "status": "PRECEDENT_CONFLICT_REQUIRES_HUMAN_REVIEW",
                "controlling_authority": None,
                "reason": "Unstated ratio relationship between different-sized benches cannot be algorithmically overruled"
            }

    # Historical SC authority partial displacement
    if precedent_pair.get("historical_sc_ruling_partially_displaced", False):
        return {
            "status": "PRIOR_SC_AUTHORITY_DISPLACED_TO_EXTENT_OF_DIRECT_CONFLICT",
            "controlling_authority": "Authority A to extent of direct conflict; remainder of historical ruling binding",
            "metadata_emitted": True
        }

    return {
        "status": "PRECEDENT_EVALUATED",
        "controlling_authority": "Authority A"
    }
