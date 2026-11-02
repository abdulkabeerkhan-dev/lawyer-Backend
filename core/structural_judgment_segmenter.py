"""
core/structural_judgment_segmenter.py

Structural Legal Judgment Segmenter & Domain Classifier for Pakistani Jurisprudence.
Transforms raw court judgment records into clean, structurally segregated segments:
1. Headnote Segment (Editorial digest, statutory anchors, legal issue)
2. Ratio Decidendi Segment (Binding judicial holding, tests, and operative reasoning)
3. Procedural Facts & Outcome Segment (Parties, trial history, and final order)

Also performs automated statutory provision extraction, legal domain classification,
and Pinecone/Supabase multi-field payload generation.
"""

import re
import hashlib
from typing import Dict, List, Any, Optional, Set, Tuple


# =====================================================================
# 1. Authoritative Pakistani Statute Registry & Pattern Matchers
# =====================================================================

STATUTE_PATTERNS: List[Tuple[str, str, str]] = [
    # (regex_pattern, canonical_act_name, default_domain)
    (r'\b(?:Civil\s+Procedure\s+Code|C\.?P\.?C\.?)\b', "Code of Civil Procedure, 1908", "civil"),
    (r'\b(?:Partition\s+Act|Partition\s+Act\s*\(IV\s+of\s+1893\))\b', "Partition Act, 1893", "civil"),
    (r'\b(?:Benami\s+Transactions?\s*(?:\(Prohibition\)\s*)?Act|Benami\s+Act)\b', "Benami Transactions (Prohibition) Act, 2017", "civil"),
    (r'\b(?:Specific\s+Relief\s+Act|S\.?R\.?A\.?)\b', "Specific Relief Act, 1877", "civil"),
    (r'\b(?:Limitation\s+Act)\b', "Limitation Act, 1908", "civil"),
    (r'\b(?:Transfer\s+of\s+Property\s+Act|T\.?P\.?A\.?)\b', "Transfer of Property Act, 1882", "civil"),
    (r'\b(?:Registration\s+Act)\b', "Registration Act, 1908", "civil"),
    (r'\b(?:Stamp\s+Act)\b', "Stamp Act, 1899", "civil"),
    (r'\b(?:Contract\s+Act)\b', "Contract Act, 1872", "civil"),
    (r'\b(?:Punjab\s+Pre-?emption\s+Act)\b', "Punjab Pre-emption Act, 1991", "civil"),
    (r'\b(?:Khyber\s+Pakhtunkhwa\s+Pre-?emption\s+Act|KPK\s+Pre-?emption\s+Act)\b', "KPK Pre-emption Act, 1987", "civil"),
    (r'\b(?:Punjab\s+Rented\s+Premises\s+Act)\b', "Punjab Rented Premises Act, 2009", "civil"),
    (r'\b(?:Sindh\s+Rented\s+Premises\s+Ordinance)\b', "Sindh Rented Premises Ordinance, 1979", "civil"),
    (r'\b(?:Court\s+Fees\s+Act)\b', "Court Fees Act, 1870", "civil"),
    (r'\b(?:Suits\s+Valuation\s+Act)\b', "Suits Valuation Act, 1887", "civil"),
    (r'\b(?:Arbitration\s+Act)\b', "Arbitration Act, 1940", "civil"),
    (r'\b(?:Succession\s+Act)\b', "Succession Act, 1925", "civil"),
    (r'\b(?:Judicial\s+Officers\s*(?:Protection|Protections)\s*Act)\b', "Judicial Officers Protection Act, 1850", "civil"),

    # Criminal Statutes
    (r'\b(?:Pakistan\s+Penal\s+Code|P\.?P\.?C\.?)\b', "Pakistan Penal Code, 1860", "criminal"),
    (r'\b(?:Code\s+of\s+Criminal\s+Procedure|Cr\.?P\.?C\.?)\b', "Code of Criminal Procedure, 1898", "criminal"),
    (r'\b(?:Control\s+of\s+Narcotic\s+Substances\s+Act|C\.?N\.?S\.?A\.?)\b', "Control of Narcotic Substances Act, 1997", "criminal"),
    (r'\b(?:Anti-?Terrorism\s+Act|A\.?T\.?A\.?)\b', "Anti-Terrorism Act, 1997", "criminal"),
    (r'\b(?:National\s+Accountability\s+Ordinance|N\.?A\.?O\.?)\b', "National Accountability Ordinance, 1999", "criminal"),
    (r'\b(?:Prevention\s+of\s+Electronic\s+Crimes\s+Act|P\.?E\.?C\.?A\.?)\b', "Prevention of Electronic Crimes Act, 2016", "criminal"),
    (r'\b(?:Anti-?Money\s+Laundering\s+Act|A\.?M\.?L\.?A\.?)\b', "Anti-Money Laundering Act, 2010", "criminal"),
    (r'\b(?:Offence\s+of\s+Zina|Zina\s*\(Enforcement\s+of\s+Hudood\)\s*Ordinance)\b', "Offence of Zina (Enforcement of Hudood) Ordinance, 1979", "criminal"),
    (r'\b(?:Offences\s+Against\s+Property\s*\(Enforcement\s+of\s+Hudood\))\b', "Offences Against Property (Enforcement of Hudood) Ordinance, 1979", "criminal"),
    (r'\b(?:Arms\s+Ordinance|Arms\s+Act)\b', "Arms Ordinance, 1965", "criminal"),

    # Family & Succession
    (r'\b(?:Family\s+Courts\s+Act)\b', "Family Courts Act, 1964", "family"),
    (r'\b(?:Muslim\s+Family\s+Laws\s+Ordinance|M\.?F\.?L\.?O\.?)\b', "Muslim Family Laws Ordinance, 1961", "family"),
    (r'\b(?:Guardians\s+and\s+Wards\s+Act)\b', "Guardians and Wards Act, 1890", "family"),
    (r'\b(?:Dissolution\s+of\s+Muslim\s+Marriages\s+Act)\b', "Dissolution of Muslim Marriages Act, 1939", "family"),
    (r'\b(?:Child\s+Marriage\s+Restraint\s+Act)\b', "Child Marriage Restraint Act, 1929", "family"),

    # Banking & Commercial
    (r'\b(?:Financial\s+Institutions\s*\(Recovery\s+of\s+Finances\)\s*Ordinance|F\.?I\.?O\.?)\b', "Financial Institutions (Recovery of Finances) Ordinance, 2001", "banking_commercial"),
    (r'\b(?:Banking\s+Companies\s+Ordinance|B\.?C\.?O\.?)\b', "Banking Companies Ordinance, 1962", "banking_commercial"),
    (r'\b(?:Negotiable\s+Instruments\s+Act|N\.?I\.?\s+Act)\b', "Negotiable Instruments Act, 1881", "banking_commercial"),
    (r'\b(?:Companies\s+Act)\b', "Companies Act, 2017", "banking_commercial"),
    (r'\b(?:Companies\s+Ordinance)\b', "Companies Ordinance, 1984", "banking_commercial"),
    (r'\b(?:Partnership\s+Act)\b', "Partnership Act, 1932", "banking_commercial"),

    # Constitutional & Administrative
    (r'\b(?:Constitution\s+of\s+Pakistan|Constitution\s+of\s+the\s+Islamic\s+Republic\s+of\s+Pakistan)\b', "Constitution of Pakistan, 1973", "constitutional"),
    (r'\b(?:Federal\s+Service\s+Tribunals?\s+Act|F\.?S\.?T\.?\s+Act)\b', "Service Tribunals Act, 1973", "constitutional"),

    # Tax & Fiscal
    (r'\b(?:Income\s+Tax\s+Ordinance|I\.?T\.?O\.?)\b', "Income Tax Ordinance, 2001", "tax_corporate"),
    (r'\b(?:Sales\s+Tax\s+Act)\b', "Sales Tax Act, 1990", "tax_corporate"),
    (r'\b(?:Customs\s+Act)\b', "Customs Act, 1969", "tax_corporate"),

    # Evidence & Procedure
    (r'\b(?:Qanun-?e-?Shahadat\s*(?:Order)?|Q\.?S\.?O\.?)\b', "Qanun-e-Shahadat Order, 1984", "evidence"),
]


# =====================================================================
# 2. Subdomain Mapping Rules
# =====================================================================

SUBDOMAIN_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "civil": {
        "partition": ["partition", "order xx rule 18", "partial partition", "ancestral estate", "preliminary decree", "partition act", "co-sharer", "joint holding"],
        "benami": ["benami", "benamidar", "ostensible owner", "benami transactions", "fictitious name", "consideration paid by"],
        "specific_performance": ["specific performance", "agreement to sell", "section 12", "article 113", "readiness and willingness"],
        "injunction": ["order xxxix", "temporary injunction", "interim injunction", "prima facie case", "balance of convenience", "irreparable loss"],
        "pre_emption": ["pre-emption", "talb-i-mowasibat", "talb-i-ishhad", "talb-i-khusumat", "zaroorat", "pre-emptor", "informer"],
        "limitation": ["limitation act", "section 5", "condonation of delay", "barred by time", "article 142", "article 144"],
        "tort_and_damages": ["damages", "tort", "malicious prosecution", "defamation", "negligence", "fatal accidents"],
        "rent_eviction": ["rented premises", "eviction", "default in rent", "personal bona fide need", "tenant", "landlord"]
    },
    "criminal": {
        "bail_pre_arrest": ["pre-arrest bail", "anticipatory bail", "section 498", "mala fide", "ulterior motive", "harassment"],
        "bail_post_arrest": ["post-arrest bail", "section 497", "further inquiry", "statutory delay", "prohibitory clause"],
        "fraud_and_cheating": ["section 420", "section 406", "criminal breach of trust", "cheating", "commercial dispute", "civil liability"],
        "cheque_bounce": ["section 489-f", "dishonestly issuing a cheque", "repayment of loan", "fulfillment of obligation"],
        "quashment": ["section 561-a", "quashment of fir", "abuse of process", "criminal proceedings"],
        "narcotics": ["cnsa", "section 9", "charas", "heroin", "recovery memo", "safe custody"],
        "murder": ["section 302", "qatl-i-amd", "eye-witness", "ocular account", "medical evidence", "dying declaration"]
    },
    "family": {
        "khula": ["khula", "dissolution of marriage", "zar-i-khula", "hatred", "aversion", "section 10(4)"],
        "dower_and_mahr": ["dower", "mahr", "prompt dower", "deferred dower", "dower deed"],
        "maintenance": ["maintenance", "wife maintenance", "child maintenance", "section 9 mflo", "pauper"],
        "custody_and_guardianship": ["custody", "hizanat", "welfare of minor", "guardian", "guardians and wards act", "visitation schedule"]
    },
    "banking_commercial": {
        "fio_recovery": ["financial institutions", "fio 2001", "section 9", "section 10", "leave to defend", "banking court", "statement of account"],
        "mortgage_and_charge": ["mortgage", "redemption", "foreclosure", "hypothecation", "pledged shares"],
        "arbitration": ["arbitration act", "arbitrator", "award", "rule of court", "misconduct of arbitrator"]
    },
    "constitutional": {
        "writ_art_199": ["article 199", "writ of certiorari", "writ of mandamus", "writ of prohibition", "aggrieved person", "alternate remedy"],
        "service_ouster_art_212": ["article 212", "service tribunal", "civil servant", "terms and conditions of service", "ouster of jurisdiction"],
        "constitutional_bench_art_202a": ["article 202a", "constitutional bench", "twentieth-seventh amendment", "twenty-sixth amendment", "judicial commission"],
        "shariat_repugnancy": ["article 203d", "article 203f", "article 203gg", "federal shariat court", "shariat appellate bench", "repugnant to injunctions"]
    },
    "tax_corporate": {
        "income_tax": ["income tax", "ito 2001", "commissioner inland revenue", "assessment order", "show cause notice"],
        "customs": ["customs act", "section 216", "section 217", "smuggling", "confiscation of goods", "customs appellate tribunal"],
        "corporate_governance": ["companies act", "oppression and mismanagement", "winding up", "director disqualification", "secp"]
    }
}


# =====================================================================
# 3. Core Structural Segmenter
# =====================================================================

class StructuralJudgmentSegmenter:
    """
    High-precision segmenter for Pakistani superior court judgments.
    Extracts structural components:
    - Headnote (editorial markers, catchwords, held summary)
    - Judicial Judgment (verbatim proceedings)
    - Ratio Decidendi (core legal tests and conclusions)
    - Statutory provisions & sections cited
    - Domain & subdomain classification
    """

    @classmethod
    def segment_judgment(cls, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Segments a judgment text into its constituent legal parts.
        """
        if not text or not isinstance(text, str):
            return cls._empty_result()

        meta = dict(metadata or {})
        raw_text = text.strip()
        word_count = len(raw_text.split())

        # 1. Clean scraper artifacts & portal navigation
        clean_text = cls._clean_portal_debris(raw_text)

        # 2. Identify structural split between editorial headnote and judicial order
        split_res = cls._split_headnote_and_order(clean_text)
        detected_type = split_res["detected_type"]
        headnote_text = split_res["headnote_text"]
        order_text = split_res["order_text"]

        # 3. Extract Ratio Decidendi
        ratio_text = cls._extract_ratio_decidendi(order_text if order_text else headnote_text)

        # 4. Extract Procedural Facts & Outcome
        facts_text = cls._extract_facts_and_outcome(order_text if order_text else headnote_text)

        # 5. Extract all referenced statutes and specific provisions
        statutes_found, provisions_found = cls._extract_statutes_and_provisions(clean_text)

        # 6. Classify Domain, Subdomain, and Key Topics
        domain, subdomain, topics = cls._classify_domain_and_topics(
            text=clean_text,
            headnote=headnote_text,
            statutes=statutes_found,
            provisions=provisions_found
        )

        # 7. Construct Pinecone & Supabase payloads
        pinecone_segments = cls._build_pinecone_segments(
            meta=meta,
            domain=domain,
            subdomain=subdomain,
            statutes=list(statutes_found),
            provisions=list(provisions_found),
            headnote=headnote_text,
            ratio=ratio_text,
            facts=facts_text,
            detected_type=detected_type
        )

        return {
            "case_id": meta.get("case_id"),
            "citation": meta.get("neutral_citation") or meta.get("citation"),
            "detected_type": detected_type,
            "word_count": word_count,
            "domain": domain,
            "subdomain": subdomain,
            "topics": topics,
            "statutes_cited": sorted(list(statutes_found)),
            "provisions_cited": sorted(list(provisions_found)),
            "headnote_segment": headnote_text,
            "ratio_decidendi_segment": ratio_text,
            "facts_and_order_segment": facts_text,
            "pinecone_segments": pinecone_segments,
            "has_full_text": bool(order_text and len(order_text.split()) >= 150),
            "parsed_outcome": split_res.get("parsed_outcome")
        }

    @classmethod
    def _clean_portal_debris(cls, text: str) -> str:
        """Strips HTML tags, portal navigation, and scraping headers."""
        t = re.sub(r'<[^>]+>', ' ', text)
        t = re.sub(r'(?i)(?:Citation Name:\s*[^\n]+|Bookmark this Case|Copyrights?\s*©?[^\n]+|Help\s+FAQ\'?s\s+Sitemap)', '', t)
        t = re.sub(r'(?i)(?:page \d+ of \d+|all rights reserved)', '', t)
        t = re.sub(r'[\r\t]+', ' ', t)
        t = re.sub(r'\n{3,}', '\n\n', t)
        return t.strip()

    @classmethod
    def _split_headnote_and_order(cls, text: str) -> Dict[str, Any]:
        """
        Splits text into editorial headnote and judicial order based on Pakistani reporting conventions.
        """
        t = text.strip()
        words = len(t.split())

        # Split markers
        split_offset = None
        order_match = re.search(r'\n{2,}\s*(?:JUDGMENT|ORDER|SHORT ORDER)\s*\n+', t, re.IGNORECASE)
        byline_match = re.search(r'\n{2,}\s*(?:[A-Z\s\.]+(?:,?\s*J\.|,?\s*CJ\.|,?\s*JJ\.)---|Before\s+[A-Za-z\s\.]+,?\s*(?:J|CJ|JJ))', t)

        candidate_offsets = []
        if order_match and order_match.start() > 100:
            candidate_offsets.append(order_match.start())
        if byline_match and byline_match.start() > 100:
            candidate_offsets.append(byline_match.start())

        if candidate_offsets:
            split_offset = min(candidate_offsets)

        head_500 = t[:500]
        has_catchwords = bool(re.search(r'(?:---Ss?\.\s*\d+|---O\.\s*[IVXLCDM\d]+|---Arts?\.\s*\d+|---Held:|---Validity)', t))
        has_dash_markers = len(re.findall(r'-{3,}', t[:1500])) >= 2
        has_held_marker = bool(re.search(r'\b(?:Held|Validity)\s*[:\-]', t, re.IGNORECASE))
        has_order_start = bool(re.match(r'^\s*(?:ORDER|JUDGMENT|SHORT ORDER)\b', head_500, re.IGNORECASE))

        is_headnote_dominant = has_catchwords or has_dash_markers or has_held_marker

        headnote_text = None
        order_text = None

        if split_offset and is_headnote_dominant:
            detected_type = "mixed"
            headnote_text = t[:split_offset].strip()
            order_text = t[split_offset:].strip()
        elif is_headnote_dominant and not has_order_start and words < 1200:
            detected_type = "headnote_only"
            headnote_text = t
            order_text = ""
        elif has_order_start or not is_headnote_dominant:
            detected_type = "full_judgment" if words >= 800 else "order_text"
            headnote_text = ""
            order_text = t
        else:
            detected_type = "mixed" if split_offset else "full_judgment"
            if split_offset:
                headnote_text = t[:split_offset].strip()
                order_text = t[split_offset:].strip()
            else:
                headnote_text = ""
                order_text = t

        # Outcome detection from order tail
        parsed_outcome = cls._parse_outcome(order_text if order_text else headnote_text)

        return {
            "detected_type": detected_type,
            "split_offset": split_offset,
            "headnote_text": headnote_text or "",
            "order_text": order_text or "",
            "parsed_outcome": parsed_outcome
        }

    @classmethod
    def _extract_ratio_decidendi(cls, text: str) -> str:
        """
        Extracts the core judicial ratio decidendi / legal principle from text.
        """
        if not text:
            return ""

        # 1. Check for explicit "Held:" blocks
        m_held = re.search(r'\bHeld\s*[:\-]\s*(.+?)(?:\n\n|\Z)', text, re.IGNORECASE | re.DOTALL)
        if m_held:
            held_text = m_held.group(1).strip()
            if len(held_text.split()) >= 20:
                return held_text[:1200]

        # 2. Check for numbered analysis paragraphs
        paragraphs = [p.strip() for p in re.split(r'\n{2,}|\n(?=\d+\.\s+)', text) if len(p.strip()) > 80]
        
        ratio_candidates = []
        ratio_signals = [
            r'\b(?:we\s+hold\s+that|i\s+hold\s+that|it\s+is\s+(?:a\s+)?settled\s+(?:proposition|principle|law)|in\s+our\s+considered\s+view|is\s+not\s+legally\s+sustainable|the\s+learned\s+court\s+below\s+erred|entitled\s+to\s+confine|the\s+question\s+before\s+us|for\s+the\s+reasons\s+recorded|the\s+principle\s+that\s+emerges)\b'
        ]

        for p in paragraphs:
            for sig in ratio_signals:
                if re.search(sig, p, re.IGNORECASE):
                    ratio_candidates.append(p)
                    break

        if ratio_candidates:
            # Combine up to 2 strongest analytical paragraphs
            combined = "\n\n".join(ratio_candidates[:2])
            return combined[:1500]

        # 3. Fallback: Concluding paragraphs before operative tail
        if len(paragraphs) >= 3:
            return "\n\n".join(paragraphs[-3:-1])[:1200]
        elif paragraphs:
            return paragraphs[-1][:1000]

        return text[:1000]

    @classmethod
    def _extract_facts_and_outcome(cls, text: str) -> str:
        """
        Extracts factual background and trial court outcome from the opening and tail.
        """
        if not text:
            return ""
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) > 60]
        if not paragraphs:
            return text[:600]

        opening = paragraphs[0][:600]
        tail = paragraphs[-1][:400] if len(paragraphs) > 1 else ""
        if tail and tail != opening:
            return f"Facts Summary:\n{opening}\n\nDisposition:\n{tail}"
        return opening

    @classmethod
    def _extract_statutes_and_provisions(cls, text: str) -> Tuple[Set[str], Set[str]]:
        """
        Extracts both primary acts and specific section/order provisions cited.
        """
        statutes: Set[str] = set()
        provisions: Set[str] = set()

        if not text:
            return statutes, provisions

        # 1. Match Acts
        for pattern, canonical_name, _ in STATUTE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                statutes.add(canonical_name)

        # 2. Match Orders & Rules (e.g. Order XX Rule 18, O.39 R.1)
        for m in re.finditer(r'\b(?:Order|O\.)\s*([IVXLCDM\d]+)[,\s]+(?:Rule|R\.)\s*(\d+[A-Za-z\-]*)\b', text, re.IGNORECASE):
            order_num = m.group(1).upper()
            rule_num = m.group(2).upper()
            provisions.add(f"Order {order_num} Rule {rule_num} CPC")
            statutes.add("Code of Civil Procedure, 1908")

        # 3. Match Sections (e.g. Section 420, S. 4, Sec. 12)
        for m in re.finditer(r'\b(?:Section|Sec\.|Ss?\.)\s*(\d+[A-Za-z\-]*)\b', text, re.IGNORECASE):
            sec_num = m.group(1)
            provisions.add(f"Section {sec_num}")

        # 4. Match Articles (e.g. Article 199, Art. 189)
        for m in re.finditer(r'\b(?:Article|Art\.)\s*(\d+[A-Za-z\-]*(?:\(\d+\)[A-Za-z]*)?)\b', text, re.IGNORECASE):
            art_num = m.group(1)
            provisions.add(f"Article {art_num}")

        return statutes, provisions

    @classmethod
    def _classify_domain_and_topics(
        cls,
        text: str,
        headnote: str,
        statutes: Set[str],
        provisions: Set[str]
    ) -> Tuple[str, str, List[str]]:
        """
        Authoritative Pakistani legal domain and subdomain classifier.
        """
        combined = f"{headnote} {text[:2000]}".lower()

        # Score domains
        domain_scores: Dict[str, int] = {
            "civil": 0,
            "criminal": 0,
            "family": 0,
            "banking_commercial": 0,
            "constitutional": 0,
            "tax_corporate": 0
        }

        # Weight from explicit statutes
        for pattern, name, dom in STATUTE_PATTERNS:
            if name in statutes:
                if dom in domain_scores:
                    domain_scores[dom] += 5

        # Weight from keywords
        matched_topics: List[str] = []
        subdomain_candidates: List[Tuple[str, str, int]] = []

        for dom, sub_dict in SUBDOMAIN_KEYWORDS.items():
            for sub, kws in sub_dict.items():
                match_count = 0
                for kw in kws:
                    if kw in combined:
                        match_count += 1
                        matched_topics.append(kw)
                if match_count > 0:
                    domain_scores[dom] += (match_count * 2)
                    subdomain_candidates.append((dom, sub, match_count))

        # Select top domain
        best_domain = max(domain_scores, key=domain_scores.get)
        if domain_scores[best_domain] == 0:
            best_domain = "civil"  # Default fallback

        # Select top subdomain within best_domain
        dom_subs = [s for d, s, cnt in subdomain_candidates if d == best_domain]
        best_subdomain = dom_subs[0] if dom_subs else "general"

        return best_domain, best_subdomain, sorted(list(set(matched_topics)))[:10]

    @classmethod
    def _parse_outcome(cls, text: str) -> str:
        """Parses the judicial outcome from the tail of the order."""
        if not text:
            return "unknown"
        tail = text[-600:].lower()
        if re.search(r'\b(?:revision\s+is\s+accepted|revision\s+accepted|petition\s+is\s+accepted|appeal\s+is\s+accepted|suit\s+is\s+decreed)\b', tail):
            return "accepted"
        if re.search(r'\b(?:appeal\s+is\s+allowed|appeal\s+allowed|petition\s+is\s+allowed|petition\s+allowed)\b', tail):
            return "allowed"
        if re.search(r'\b(?:revision\s+is\s+dismissed|revision\s+dismissed|petition\s+is\s+dismissed|appeal\s+is\s+dismissed|suit\s+is\s+dismissed)\b', tail):
            return "dismissed"
        if re.search(r'\b(?:bail\s+is\s+granted|bail\s+granted|ad-interim\s+bail\s+is\s+confirmed)\b', tail):
            return "bail_granted"
        if re.search(r'\b(?:bail\s+is\s+refused|bail\s+refused|bail\s+is\s+recalled)\b', tail):
            return "bail_refused"
        return "adjudicated"

    @classmethod
    def _build_pinecone_segments(
        cls,
        meta: Dict[str, Any],
        domain: str,
        subdomain: str,
        statutes: List[str],
        provisions: List[str],
        headnote: str,
        ratio: str,
        facts: str,
        detected_type: str
    ) -> List[Dict[str, Any]]:
        """
        Builds the 3 segment vectors with structured metadata for Pinecone ingestion.
        """
        cid = str(meta.get("case_id") or "UNKNOWN")
        # Pinecone ID max length is 512 chars; safeguard against long or aberrant case identifiers
        safe_cid = cid if len(cid) <= 120 else f"{cid[:100]}_{hashlib.md5(cid.encode('utf-8')).hexdigest()[:12]}"
        cit = meta.get("neutral_citation") or meta.get("citation") or cid
        title = meta.get("case_title") or meta.get("title") or "Precedent on Record"
        court = meta.get("court_name") or meta.get("court") or "Supreme Court of Pakistan"
        year = meta.get("decision_date", "")[:4] if meta.get("decision_date") else meta.get("year", 2024)

        header = f"[{cit} | {title} | {court} | {year} | Domain: {domain.upper()} | Subdomain: {subdomain.upper()}]"
        segments = []

        # Segment A: Headnote (The Legal Doctrine)
        if headnote and len(headnote.split()) >= 20:
            segments.append({
                "segment_id": f"{safe_cid}_seg_headnote",
                "segment_type": "headnote",
                "text": f"{header}\n\nHEADNOTE & STATUTORY ANCHORS:\n{headnote}",
                "metadata": {
                    "case_id": cid[:256],
                    "citation": cit[:256],
                    "case_title": title[:256],
                    "court": court[:128],
                    "year": int(year) if str(year).isdigit() else 2024,
                    "domain": domain,
                    "legal_domain": domain,
                    "subdomain": subdomain,
                    "statutes": statutes[:8],
                    "provisions": provisions[:10],
                    "statutory_provisions": provisions[:10],
                    "segment_type": "headnote",
                    "metadata_schema_version": "1.0",
                    "detected_type": detected_type
                }
            })

        # Segment B: Ratio Decidendi (The Judicial Holding)
        if ratio and len(ratio.split()) >= 20:
            segments.append({
                "segment_id": f"{safe_cid}_seg_ratio",
                "segment_type": "ratio_decidendi",
                "text": f"{header}\n\nRATIO DECIDENDI & JUDICIAL HOLDING:\n{ratio}",
                "metadata": {
                    "case_id": cid[:256],
                    "citation": cit[:256],
                    "case_title": title[:256],
                    "court": court[:128],
                    "year": int(year) if str(year).isdigit() else 2024,
                    "domain": domain,
                    "legal_domain": domain,
                    "subdomain": subdomain,
                    "statutes": statutes[:8],
                    "provisions": provisions[:10],
                    "statutory_provisions": provisions[:10],
                    "segment_type": "ratio_decidendi",
                    "metadata_schema_version": "1.0",
                    "detected_type": detected_type
                }
            })

        # Segment C: Facts & Outcome (Procedural Context)
        if facts and len(facts.split()) >= 20:
            segments.append({
                "segment_id": f"{safe_cid}_seg_facts",
                "segment_type": "facts_and_order",
                "text": f"{header}\n\nFACTS & PROCEDURAL OUTCOME:\n{facts}",
                "metadata": {
                    "case_id": cid[:256],
                    "citation": cit[:256],
                    "case_title": title[:256],
                    "court": court[:128],
                    "year": int(year) if str(year).isdigit() else 2024,
                    "domain": domain,
                    "legal_domain": domain,
                    "subdomain": subdomain,
                    "statutes": statutes[:8],
                    "provisions": provisions[:10],
                    "statutory_provisions": provisions[:10],
                    "segment_type": "facts_and_order",
                    "metadata_schema_version": "1.0",
                    "detected_type": detected_type
                }
            })

        return segments

    @classmethod
    def _empty_result(cls) -> Dict[str, Any]:
        return {
            "case_id": None,
            "citation": None,
            "detected_type": "unknown",
            "word_count": 0,
            "domain": "civil",
            "subdomain": "general",
            "topics": [],
            "statutes_cited": [],
            "provisions_cited": [],
            "headnote_segment": "",
            "ratio_decidendi_segment": "",
            "facts_and_order_segment": "",
            "pinecone_segments": [],
            "has_full_text": False,
            "parsed_outcome": "unknown"
        }
