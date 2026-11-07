"""
legal_ai/query_engine/statute_router.py

Stage 1: Dual Track Intent & Statute Router for Pakistani Legal AI Pipeline.
Orchestrates:
- Track A: Conceptual & Factual Mapper (e.g. 'bounced cheque' -> 489-F PPC; 'without warrant bail' -> 496 & 497 CrPC)
- Track B: Exact Regex & Shorthand (e.g. '489-F PPC', '7(2) CPC', '12(2) CPC', 'Art 199', 'S.12 SRA')
- Disambiguation & Hierarchy Engine (Resolving Section 12 SRA vs CPC 12; Section 22 FIO vs CPC 22; SRA + CrPC)
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple


CONCEPTUAL_FACTUAL_PATTERNS = [
    {
        "id": "BENAMI_PROHIBITION",
        "keywords": ["benami", "benamidar", "real owner", "ostensible owner"],
        "primary_provisions": [
            "Section 4 Benami Transactions (Prohibition) Act, 2017",
            "Section 3 Benami Transactions (Prohibition) Act, 2017"
        ],
        "act_codes": ["BENAMI_2017"],
        "forum": "Federal Adjudicating Authority / Special Court",
        "domain": "Civil Law / Benami Transactions"
    },
    {
        "id": "MONEY_RECOVERY_LIMITATION",
        "keywords": ["money lent", "debt", "loan", "recovery of money", "suit for money", "money payable", "price of goods", "borrowed money"],
        "primary_provisions": [
            "Article 57 Limitation Act, 1908",
            "Article 64 Limitation Act, 1908",
            "Article 64-A Limitation Act, 1908",
            "Article 115 Limitation Act, 1908",
            "Section 3 Limitation Act, 1908"
        ],
        "act_codes": ["LIMITATION_1908"],
        "forum": "Civil Court (Senior Civil Judge)",
        "domain": "Civil Law / Money Suits & Limitation"
    },
    {
        "id": "CHEQUE_DISHONOUR",
        "keywords": ["cheque", "check", "dishonour", "dishonored", "bounced", "lack of funds", "insufficient funds"],
        "primary_provisions": ["Section 489-F PPC", "Order XXXVII Rule 2 CPC", "Section 118 Negotiable Instruments Act, 1881"],
        "act_codes": ["PPC_1860", "CPC_1908", "NI_ACT_1881"],
        "forum": "Judicial Magistrate 1st Class (Criminal) / District Judge (Civil Summary Suit)",
        "domain": "Criminal Law / Negotiable Instruments"
    },
    {
        "id": "WITHOUT_WARRANT_ARREST_BAIL",
        "keywords": ["without warrant", "arrest without a warrant", "police custody", "illegal detention", "24 hours magistrate"],
        "primary_provisions": ["Section 54 CrPC", "Section 61 CrPC", "Section 496 CrPC", "Section 497 CrPC"],
        "act_codes": ["CRPC_1898"],
        "forum": "Area Judicial Magistrate / Sessions Court",
        "domain": "Criminal Procedure & Fundamental Rights"
    },
    {
        "id": "BAIL_GENERAL",
        "keywords": ["bail", "pre-arrest", "post-arrest", "pre arrest", "post arrest", "anticipatory bail", "protective bail"],
        "primary_provisions": ["Section 496 CrPC", "Section 497 CrPC", "Section 498 CrPC"],
        "act_codes": ["CRPC_1898"],
        "forum": "Court of Session / High Court",
        "domain": "Criminal Procedure / Bail"
    },
    {
        "id": "SALE_DEED_SPECIFIC_PERFORMANCE",
        "keywords": ["sale deed", "advance money", "earnest money", "agreement to sell", "token money", "refused to execute", "refused to register"],
        "primary_provisions": [
            "Section 12 Specific Relief Act, 1877",
            "Section 73 Contract Act, 1872",
            "Article 113 Limitation Act, 1908",
            "Section 53A Transfer of Property Act, 1882",
            "Section 55 Transfer of Property Act, 1882"
        ],
        "act_codes": ["SRA_1877", "CONTRACT_1872", "LIMITATION_1908", "TPA_1882"],
        "forum": "Civil Court (Senior Civil Judge)",
        "domain": "Civil Law / Property & Specific Performance"
    },
    {
        "id": "INJUNCTION_AND_STAY",
        "keywords": ["injunction", "stay order", "restraining order", "disobedience", "breach of injunction", "status quo"],
        "primary_provisions": [
            "Order XXXIX Rule 1 CPC",
            "Order XXXIX Rule 2 CPC",
            "Order XXXIX Rule 2(3) CPC",
            "Order XLIII Rule 1(r) CPC"
        ],
        "act_codes": ["CPC_1908"],
        "forum": "Civil Court granting injunction / Appellate District Court",
        "domain": "Civil Procedure / Interlocutory Remedies"
    },
    {
        "id": "FRAUDULENT_DECREE",
        "keywords": ["fraud decree", "decree by fraud", "misrepresentation", "set aside decree", "want of jurisdiction", "12(2)"],
        "primary_provisions": ["Section 12(2) Code of Civil Procedure, 1908"],
        "act_codes": ["CPC_1908"],
        "forum": "Court which passed the final decree",
        "domain": "Civil Procedure / Challenging Decrees"
    },
    {
        "id": "BANKING_DECREE_AND_APPEAL",
        "keywords": ["banking court", "banking decree", "leave to defend", "fio", "financial institutions", "decretal amount deposit"],
        "primary_provisions": [
            "Section 10 Financial Institutions (Recovery of Finances) Ordinance, 2001",
            "Section 22 Financial Institutions (Recovery of Finances) Ordinance, 2001"
        ],
        "act_codes": ["FIO_2001"],
        "forum": "High Court (Division Bench)",
        "domain": "Banking Law / Finance Recovery"
    },
    {
        "id": "ADVERSE_POSSESSION",
        "keywords": ["adverse possession", "prescriptive title", "hostile possession", "extinguishment of right", "12 years possession"],
        "primary_provisions": [
            "Section 28 Limitation Act, 1908",
            "Article 144 Limitation Act, 1908",
            "Article 149 Limitation Act, 1908"
        ],
        "act_codes": ["LIMITATION_1908"],
        "forum": "Civil Court",
        "domain": "Property Law / Limitation"
    },
    {
        "id": "QUASHMENT_OF_FIR",
        "keywords": ["quash fir", "quashing of fir", "quashment", "false fir", "malicious prosecution"],
        "primary_provisions": [
            "Section 561-A Code of Criminal Procedure, 1898",
            "Article 199 Constitution of Pakistan, 1973"
        ],
        "act_codes": ["CRPC_1898", "CONST_1973"],
        "forum": "High Court",
        "domain": "Criminal Procedure / Constitutional Inherent Jurisdiction"
    }
]

EXACT_REGEX_PATTERNS = [
    # 1. PPC sections: 489-F PPC, Section 409 PPC
    (r'\b(?:Sections?|Sec\.?|s\.)?\s*(489-?[A-Za-z]|409|420|302|376|406|468|471)\s*(?:of\s+the\s+)?(?:PPC|Pakistan\s+Penal\s+Code)\b', "Section {0} Pakistan Penal Code, 1860", "PPC_1860"),
    # 2. CrPC sections: 496 CrPC, Section 497 CrPC, 561-A
    (r'\b(?:Sections?|Sec\.?|s\.)?\s*(496|497|498|561-?[A-Za-z]|54|61|154|249-?[A-Za-z]|265-?[A-Za-z]|22-?[A-Za-z])\s*(?:of\s+the\s+)?(?:CrPC|Code\s+of\s+Criminal\s+Procedure)\b', "Section {0} Code of Criminal Procedure, 1898", "CRPC_1898"),
    # 3. CPC Orders & Rules: Order XXXIX Rule 1 CPC, O.39 R.1, O.VII R.11
    (r'\b(?:Order|O\.)\s*([IVXLCDM]+|\d+)\s*(?:Rule|R\.)\s*(\d+[A-Za-z]?(?:\(\d+\))*)\s*(?:of\s+the\s+)?(?:CPC|Code\s+of\s+Civil\s+Procedure)\b', "Order {0} Rule {1} Code of Civil Procedure, 1908", "CPC_1908"),
    # 4. CPC Sections: Section 12(2) CPC, Section 115 CPC, Section 9 CPC
    (r'\b(?:Sections?|Sec\.?|s\.)\s*(12\s*\(\s*2\s*\)|115|9|10|11|100|151)\s*(?:of\s+the\s+)?(?:CPC|Code\s+of\s+Civil\s+Procedure)\b', "Section {0} Code of Civil Procedure, 1908", "CPC_1908"),
    # 5. SRA sections: Section 12 SRA, Section 8, 9, 42 SRA
    (r'\b(?:Sections?|Sec\.?|s\.)\s*(12|8|9|27|42|54|55)\s*(?:of\s+the\s+)?(?:SRA|Specific\s+Relief\s+Act)\b', "Section {0} Specific Relief Act, 1877", "SRA_1877"),
    # 6. Contract Act: Section 73 Contract Act, Section 56
    (r'\b(?:Sections?|Sec\.?|s\.)\s*(73|74|56|65|2|10)\s*(?:of\s+the\s+)?(?:Contract\s+Act)\b', "Section {0} Contract Act, 1872", "CONTRACT_1872"),
    # 7. Limitation Act: Article 113 Limitation Act, Article 144, Section 28
    (r'\b(?:Articles?|Art\.?)\s*(113|144|149|181|182)\s*(?:of\s+the\s+)?(?:Limitation\s+Act)\b', "Article {0} Limitation Act, 1908", "LIMITATION_1908"),
    (r'\b(?:Sections?|Sec\.?|s\.)\s*(3|5|12|14|28)\s*(?:of\s+the\s+)?(?:Limitation\s+Act)\b', "Section {0} Limitation Act, 1908", "LIMITATION_1908"),
    # 8. Constitution: Article 199, Article 184(3)
    (r'\b(?:Articles?|Art\.?)\s*(199(?:\([1-5]\))?|184\s*\(\s*3\s*\)|185(?:\([1-3]\))?|212)\s*(?:of\s+the\s+)?(?:Constitution)\b', "Article {0} Constitution of Pakistan, 1973", "CONST_1973"),
    # 9. FIO 2001: Section 22 FIO, Section 10 FIO
    (r'\b(?:Sections?|Sec\.?|s\.)\s*(22(?:\([1-7]\))?|10(?:\([1-9]\))?|9|15)\s*(?:of\s+the\s+)?(?:FIO|FIFO|Financial\s+Institutions)\b', "Section {0} Financial Institutions (Recovery of Finances) Ordinance, 2001", "FIO_2001")
]


class DualTrackStatuteRouter:
    """
    Stage 1: Dispatches user queries through both Track A (Conceptual & Factual)
    and Track B (Exact Regex & Shorthand), applying disambiguation rules.
    """

    def route_query(self, query: str) -> Dict[str, Any]:
        q_clean = query.strip()
        q_low = q_clean.lower()

        # Track A: Conceptual & Factual Mapping
        track_a_matches = []
        track_a_provisions = []
        track_a_acts = set()
        matched_domains = []
        target_forum = "Civil Court / High Court"

        for entry in CONCEPTUAL_FACTUAL_PATTERNS:
            if any(kw in q_low for kw in entry["keywords"]):
                track_a_matches.append(entry["id"])
                track_a_provisions.extend(entry["primary_provisions"])
                track_a_acts.update(entry["act_codes"])
                matched_domains.append(entry["domain"])
                if entry.get("forum"):
                    target_forum = entry["forum"]

        # Track B: Exact Regex & Shorthand Matching
        track_b_matches = []
        track_b_provisions = []
        track_b_acts = set()

        for pattern, tmpl, act_code in EXACT_REGEX_PATTERNS:
            for m in re.finditer(pattern, q_clean, flags=re.IGNORECASE):
                matched_span = m.group(0)
                primary_val = m.group(1).strip()
                sec_val = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                
                formatted = tmpl.format(primary_val, sec_val).strip()
                track_b_matches.append(matched_span)
                track_b_provisions.append(formatted)
                track_b_acts.add(act_code)

        # Disambiguation & Hierarchy Engine
        disambiguated_provisions, disambiguated_acts = self._disambiguate_collisions(
            q_low, track_a_provisions, track_b_provisions, track_a_acts, track_b_acts
        )

        return {
            "track_a_matched_intents": track_a_matches,
            "track_b_matched_citations": track_b_matches,
            "candidate_provisions": disambiguated_provisions,
            "governing_act_codes": list(disambiguated_acts),
            "suggested_forum": target_forum,
            "domains": list(set(matched_domains))
        }

    def _disambiguate_collisions(
        self,
        q_low: str,
        provisions_a: List[str],
        provisions_b: List[str],
        acts_a: Set[str],
        acts_b: Set[str]
    ) -> Tuple[List[str], Set[str]]:
        """
        Disambiguates classic Pakistani cross-statute numerical collisions.
        """
        all_provisions = list(dict.fromkeys(provisions_b + provisions_a))
        all_acts = set(acts_b | acts_a)

        # 1. Section 12 Ambiguity: SRA 1877 (Specific Performance) vs CPC 1908 (Fraud decree challenge)
        has_property_or_sale = any(k in q_low for k in ["sale deed", "property", "advance", "contract", "buyer", "seller", "earnest"])
        has_fraud_or_decree = any(k in q_low for k in ["fraud", "misrepresentation", "decree", "set aside", "12(2)"])

        if has_property_or_sale and not has_fraud_or_decree:
            # Exclude Section 12 CPC in pure property sale disputes
            all_provisions = [p for p in all_provisions if not ("cpc" in p.lower() and "12" in p.lower())]
            if not any("specific relief" in p.lower() and "12" in p.lower() for p in all_provisions):
                all_provisions.insert(0, "Section 12 Specific Relief Act, 1877")
            all_acts.add("SRA_1877")
        elif has_fraud_or_decree:
            all_provisions = [p for p in all_provisions if not ("specific relief" in p.lower() and "12" in p.lower())]
            if not any("12(2)" in p for p in all_provisions):
                all_provisions.insert(0, "Section 12(2) Code of Civil Procedure, 1908")
            all_acts.add("CPC_1908")

        # 2. Section 22 Ambiguity: FIO 2001 (Banking Appeal) vs CPC 1908 (Transfer of suits)
        if any(k in q_low for k in ["banking", "bank", "borrower", "finance", "fio"]):
            all_provisions = [p for p in all_provisions if not ("cpc" in p.lower() and "22" in p.lower())]
            if not any("fio" in p.lower() or "financial institutions" in p.lower() for p in all_provisions):
                all_provisions.insert(0, "Section 22 Financial Institutions (Recovery of Finances) Ordinance, 2001")
            all_acts.add("FIO_2001")

        # 3. Bail & Act 1882 Anti-Collision: If bail query, scrub TPA 1882
        if "bail" in q_low:
            all_provisions = [p for p in all_provisions if not ("transfer of property" in p.lower() or "tpa" in p.lower())]
            all_acts.discard("TPA_1882")
            all_acts.add("CRPC_1898")

        return all_provisions, all_acts


# ==============================================================================
# Layers 3 & 4: Query Understanding, High-Precision Retrieval & Pack Assembly
# ==============================================================================

from pydantic import BaseModel, Field
from legal_ai.statutes.legal_unit_record import LegalUnitRecord
from legal_ai.evidence.bounded_evidence_pack import BoundedEvidencePack
from core.unified_statute_store import get_unified_statute_store

CANONICAL_ACT_MAP = {
    "LIMITATION_1908": ("limitation-act-1908", "Limitation Act, 1908", "civil"),
    "PPC_1860": ("pakistan-penal-code-1860", "Pakistan Penal Code, 1860", "criminal"),
    "CRPC_1898": ("code-of-criminal-procedure-1898", "Code of Criminal Procedure, 1898", "criminal"),
    "CPC_1908": ("code-of-civil-procedure-1908", "Code of Civil Procedure, 1908", "civil"),
    "SRA_1877": ("specific-relief-act-1877", "Specific Relief Act, 1877", "civil"),
    "CONTRACT_1872": ("contract-act-1872", "Contract Act, 1872", "civil"),
    "BENAMI_2017": ("benami-transactions-act-2017", "Benami Transactions (Prohibition) Act, 2017", "civil"),
    "CONST_1973": ("constitution-1973", "Constitution of the Islamic Republic of Pakistan, 1973", "constitutional"),
    "FIO_2001": ("financial-institutions-ordinance-2001", "Financial Institutions (Recovery of Finances) Ordinance, 2001", "banking")
}


class StatuteQueryIntent(BaseModel):
    query_text: str
    domain: str = "civil"
    jurisdiction: str = "federal"
    likely_statutes: List[str] = Field(default_factory=list)
    query_type: str = "general_rule"  # "specific_provision" or "general_rule"
    named_provisions: List[str] = Field(default_factory=list)
    sub_topic: str = ""


def analyze_statute_query_intent(query_text: str) -> StatuteQueryIntent:
    """
    Layer 3: Query Understanding.
    Classifies domain, jurisdiction, likely statutes, and whether a specific
    provision is named or a general rule is sought.
    """
    router = DualTrackStatuteRouter()
    routing = router.route_query(query_text)

    q_lower = query_text.lower()
    jurisdiction = "federal"
    if "punjab" in q_lower or "lahore" in q_lower:
        jurisdiction = "punjab"
    elif "sindh" in q_lower or "karachi" in q_lower:
        jurisdiction = "sindh"
    elif "khyber" in q_lower or "kpk" in q_lower or "peshawar" in q_lower:
        jurisdiction = "kpk"
    elif "balochistan" in q_lower or "quetta" in q_lower:
        jurisdiction = "balochistan"

    acts = routing.get("governing_act_codes", [])
    domains = routing.get("domains", [])

    primary_domain = "civil"
    if any(a in ["PPC_1860", "CRPC_1898"] for a in acts) or any("criminal" in str(d).lower() for d in domains):
        primary_domain = "criminal"
    elif any(a in ["CONST_1973"] for a in acts):
        primary_domain = "constitutional"
    elif any(a in ["FIO_2001"] for a in acts):
        primary_domain = "business"

    # Direct benami keyword support
    if "benami" in q_lower and "BENAMI_2017" not in acts:
        acts.append("BENAMI_2017")

    named = routing.get("track_b_matched_citations", [])
    q_type = "specific_provision" if named else "general_rule"

    return StatuteQueryIntent(
        query_text=query_text,
        domain=primary_domain,
        jurisdiction=jurisdiction,
        likely_statutes=acts,
        query_type=q_type,
        named_provisions=routing.get("candidate_provisions", []),
        sub_topic=query_text[:60]
    )


def retrieve_statute_provisions(
    intent: StatuteQueryIntent,
    max_results: int = 5
) -> List[LegalUnitRecord]:
    """
    Layer 4: High-Precision Statute Retrieval.
    1. Direct lookup when specific provisions are named.
    2. Hybrid / Anchor lookup otherwise.
    3. Caps at top 3-5 provisions and converts to atomic LegalUnitRecords.
    """
    store = get_unified_statute_store()
    results: List[LegalUnitRecord] = []
    seen_cids = set()

    # Direct / Candidate Provision Lookup
    for cand in intent.named_provisions:
        m_art = re.search(r'Article\s*([0-9]+[A-Za-z]?(?:-[A-Za-z])?)\s+([A-Za-z\s,0-9]+)', cand, re.IGNORECASE)
        m_sec = re.search(r'Section\s*([0-9IVXLCDM]+[A-Za-z]?(?:-[A-Za-z])?(?:\([0-9]+\))?)\s+([A-Za-z\s,0-9]+)', cand, re.IGNORECASE)
        m_ord = re.search(r'Order\s*([IVXLCDM]+)\s*Rule\s*([0-9]+[A-Za-z]?)', cand, re.IGNORECASE)

        act_code = "LIMITATION_1908" if "limitation" in cand.lower() else (
            "CPC_1908" if "civil procedure" in cand.lower() or "cpc" in cand.lower() else (
                "PPC_1860" if "penal code" in cand.lower() or "ppc" in cand.lower() else (
                    "CRPC_1898" if "criminal procedure" in cand.lower() or "crpc" in cand.lower() else (
                        "SRA_1877" if "specific relief" in cand.lower() or "sra" in cand.lower() else (
                            "BENAMI_2017" if "benami" in cand.lower() else ""
                        )
                    )
                )
            )
        )

        cids_to_try = []
        if m_art and act_code:
            clean_num = m_art.group(1).upper().replace('-', '')
            cids_to_try.append(f"{act_code}_ART_{clean_num}")
        elif m_ord and act_code:
            cids_to_try.append(f"{act_code}_ORD_{m_ord.group(1).upper()}_R_{m_ord.group(2).upper()}")
        elif m_sec and act_code:
            raw_s = m_sec.group(1).upper()
            clean_s = re.sub(r'[^A-Z0-9]', '', raw_s)
            cids_to_try.extend([f"{act_code}_SEC_{clean_s}", f"{act_code}_SEC_{raw_s}"])

        for cid in cids_to_try:
            if cid not in seen_cids:
                rec = store.get_by_canonical_id(cid)
                if rec and (rec.get("text") or rec.get("title")):
                    seen_cids.add(cid)
                    results.append(_convert_to_legal_unit_record(rec, cid))
                    break

    # Topic-specific anchors if fewer than 2 results found
    if len(results) < 2:
        q_low = intent.query_text.lower()
        if "limitation" in q_low or any(k in q_low for k in ["money lent", "loan", "debt", "recovery"]):
            for l_cid in ["LIMITATION_1908_ART_57", "LIMITATION_1908_ART_64", "LIMITATION_1908_ART_64A", "LIMITATION_1908_SEC_3"]:
                if l_cid not in seen_cids:
                    rec = store.get_by_canonical_id(l_cid)
                    if rec and rec.get("text"):
                        seen_cids.add(l_cid)
                        results.append(_convert_to_legal_unit_record(rec, l_cid))
        elif any(k in q_low for k in ["cheque", "dishonour", "489"]):
            for c_cid in ["PPC_1860_SEC_489F", "PPC_1860_SEC_420"]:
                if c_cid not in seen_cids:
                    rec = store.get_by_canonical_id(c_cid)
                    if rec and rec.get("text"):
                        seen_cids.add(c_cid)
                        results.append(_convert_to_legal_unit_record(rec, c_cid))
        elif any(k in q_low for k in ["bail", "non-bailable"]):
            for b_cid in ["CRPC_1898_SEC_497", "CRPC_1898_SEC_498"]:
                if b_cid not in seen_cids:
                    rec = store.get_by_canonical_id(b_cid)
                    if rec and rec.get("text"):
                        seen_cids.add(b_cid)
                        results.append(_convert_to_legal_unit_record(rec, b_cid))
        elif "benami" in q_low:
            for b_cid in ["BENAMI_2017_SEC_4", "BENAMI_2017_SEC_3"]:
                if b_cid not in seen_cids:
                    rec = store.get_by_canonical_id(b_cid)
                    if rec and rec.get("text"):
                        seen_cids.add(b_cid)
                        results.append(_convert_to_legal_unit_record(rec, b_cid))

    return results[:max_results]


def build_evidence_pack_for_query(
    query_text: str,
    precedent_cards: Optional[List[Dict[str, Any]]] = None,
    max_statutes: int = 5
) -> Tuple[BoundedEvidencePack, StatuteQueryIntent]:
    """
    Layers 3, 4, 5 Orchestrator:
    Produces a populated BoundedEvidencePack with [E1], [E2], ...
    and automatically pulls linked caveats (e.g. Punjab Loans Limitation Act, 1904).
    """
    intent = analyze_statute_query_intent(query_text)
    statute_units = retrieve_statute_provisions(intent, max_results=max_statutes)

    pack = BoundedEvidencePack()
    for u in statute_units:
        pack.add_legal_unit(u, pull_linked_caveats=True)

    for card in (precedent_cards or []):
        cit = card.get("citation") or card.get("case_id") or ""
        ratio = card.get("ratio_decidendi") or card.get("holding") or card.get("preview") or ""
        if cit and ratio:
            pack.add_case_precedent(
                citation=cit,
                case_title=card.get("case_name") or card.get("title") or "Precedent",
                court=card.get("court") or card.get("court_name") or "Supreme Court of Pakistan",
                ratio=ratio,
                year=card.get("year"),
                statutes_invoked=[s.get("name", "") if isinstance(s, dict) else str(s) for s in (card.get("statutes_invoked") or [])],
                pdf_url=card.get("pdf_url")
            )

    return pack, intent


def _convert_to_legal_unit_record(rec: Dict[str, Any], canonical_id: str) -> LegalUnitRecord:
    import hashlib
    act_code = (rec.get("act_code") or "").upper()
    if not act_code and "_" in canonical_id:
        act_code = canonical_id.split("_")[0].upper()

    meta = CANONICAL_ACT_MAP.get(act_code, (act_code.lower().replace("_", "-"), rec.get("act_name") or act_code, "civil"))
    statute_id, default_title, _ = meta
    act_name = rec.get("act_name") or rec.get("act") or default_title

    u_type = rec.get("provision_type") or ("article" if "_ART_" in canonical_id else ("order" if "_ORD_" in canonical_id else "section"))
    num = str(rec.get("primary_num") or rec.get("section") or canonical_id.split("_")[-1])

    heading = rec.get("heading") or rec.get("title") or f"{u_type.capitalize()} {num}"
    raw_txt = str(rec.get("text") or rec.get("text_raw") or "").strip()
    # Normalize soft-hyphens
    clean_txt = raw_txt.replace('­', '')

    chk = hashlib.sha256(clean_txt.encode("utf-8")).hexdigest()

    return LegalUnitRecord(
        unit_id=f"{statute_id}:{u_type}:{num}".lower(),
        statute_id=statute_id,
        statute_title=act_name,
        jurisdiction=rec.get("jurisdiction") or "federal",
        unit_type=u_type,
        number=num,
        parent=rec.get("parent"),
        heading_description=heading,
        period=rec.get("period"),
        trigger=rec.get("trigger"),
        text=clean_txt,
        footnotes=rec.get("footnotes") or [],
        caveats=rec.get("caveats") or [],
        cross_references=rec.get("cross_references") or [],
        checksum=chk,
        source_url=rec.get("source_url") or ""
    )
