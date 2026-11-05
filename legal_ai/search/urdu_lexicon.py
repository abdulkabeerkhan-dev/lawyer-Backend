"""
legal_ai/search/urdu_lexicon.py

Bilingual Roman Urdu & Phonetic Legal Lexicon for Pakistani Trial & High Courts.
Translates advocate vernacular, FIR terminology, and police/revenue jargon into
exact statutory provisions, orders, and rules.
"""

import re
from typing import Dict, Any, List, Tuple

# Comprehensive mapping of Pakistani advocate colloquialisms & trial court terms
URDU_LEGAL_LEXICON: List[Dict[str, Any]] = [
    {
        "patterns": [r"zamanat\s*qabal\s*az\s*giraftari", r"qabal\s*az\s*giraftari", r"pre\s*arrest\s*bail", r"advance\s*bail"],
        "statute": "Code of Criminal Procedure 1898",
        "section": "Section 498 CrPC",
        "formal_concept": "Pre-arrest Bail",
        "keywords": ["CrPC 498", "mala fide arrest", "ulterior motives", "pre-arrest bail"],
        "jurisdiction": "Sessions Court / High Court"
    },
    {
        "patterns": [r"zamanat\s*baad\s*az\s*giraftari", r"baad\s*az\s*giraftari", r"post\s*arrest\s*bail", r"paka\s*bail"],
        "statute": "Code of Criminal Procedure 1898",
        "section": "Section 497 CrPC",
        "formal_concept": "Post-arrest Bail",
        "keywords": ["CrPC 497", "further inquiry", "prohibitory clause", "post-arrest bail"],
        "jurisdiction": "Magistrate / Sessions Court / High Court"
    },
    {
        "patterns": [r"biyan[- ]e[- ]halfi", r"bayan[- ]e[- ]halfi", r"halfan\s*bayan", r"affidavit"],
        "statute": "Code of Civil Procedure 1908",
        "section": "Order XIX CPC",
        "formal_concept": "Affidavit / Evidence on Affidavit",
        "keywords": ["Order 19 CPC", "affidavit verification", "oath commissioner"],
        "jurisdiction": "Civil Court / High Court"
    },
    {
        "patterns": [r"tamleek", r"hiba", r"hibba", r"hiba\s*bil\s*ewaz"],
        "statute": "Transfer of Property Act 1882 / Islamic Law",
        "section": "Section 122 TPA / Mohammedan Law",
        "formal_concept": "Gift / Tamleek among legal heirs",
        "keywords": ["Gift deed", "Hiba", "delivery of possession", "offer and acceptance"],
        "jurisdiction": "Civil Court / Revenue Court"
    },
    {
        "patterns": [r"fard[- ]e[- ]jurm", r"fard\s*jurm", r"charge\s*sheet"],
        "statute": "Code of Criminal Procedure 1898",
        "section": "Section 242 and 265-D CrPC",
        "formal_concept": "Framing of Formal Charge",
        "keywords": ["Framing of charge", "plea of guilty", "CrPC 242", "CrPC 265-D"],
        "jurisdiction": "Magistrate / Sessions Court"
    },
    {
        "patterns": [r"istighasa", r"istighasah", r"private\s*complaint"],
        "statute": "Code of Criminal Procedure 1898",
        "section": "Section 200 CrPC",
        "formal_concept": "Direct / Private Criminal Complaint",
        "keywords": ["Private complaint", "Section 200 CrPC", "preliminary inquiry"],
        "jurisdiction": "Magistrate Court"
    },
    {
        "patterns": [r"hukm[- ]e[- ]imtanai", r"stay\s*order", r"stay\s*application"],
        "statute": "Code of Civil Procedure 1908",
        "section": "Order XXXIX Rules 1 and 2 CPC",
        "formal_concept": "Temporary Injunction / Stay Order",
        "keywords": ["Order 39 Rule 1 and 2", "prima facie case", "irreparable loss", "balance of convenience"],
        "jurisdiction": "Civil Court / High Court"
    },
    {
        "patterns": [r"dar[- ]khast\s*bar[- ]e[- ]kharji", r"dawa\s*kharij", r"rejection\s*of\s*plaint", r"7[- ]11"],
        "statute": "Code of Civil Procedure 1908",
        "section": "Order VII Rule 11 CPC",
        "formal_concept": "Rejection of Plaint for Want of Cause of Action",
        "keywords": ["Order 7 Rule 11", "rejection of plaint", "cause of action", "barred by law"],
        "jurisdiction": "Civil Court"
    },
    {
        "patterns": [r"cheque\s*dishonour", r"cheque\s*bounce", r"bad\s*cheque", r"489[- ]f"],
        "statute": "Pakistan Penal Code 1860",
        "section": "Section 489-F PPC",
        "formal_concept": "Dishonestly Issuing a Cheque",
        "keywords": ["PPC 489-F", "dishonestly issuing a cheque", "repayment of loan", "fulfillment of obligation"],
        "jurisdiction": "Criminal Court"
    },
    {
        "patterns": [r"khula", r"khulah", r"dissolution\s*of\s*marriage"],
        "statute": "Dissolution of Muslim Marriages Act 1939",
        "section": "Section 2 DMMA 1939 / Family Courts Act 1964",
        "formal_concept": "Dissolution of Marriage on Ground of Khula",
        "keywords": ["Khula", "Family Courts Act 1964", "return of dower", "zar-e-khula"],
        "jurisdiction": "Family Court"
    },
    {
        "patterns": [r"haq\s*shufa", r"shufa", r"pre[- ]emption"],
        "statute": "Punjab Pre-emption Act 1991 / Khyber Pakhtunkhwa Pre-emption Act 1987",
        "section": "Section 13 Pre-emption Act",
        "formal_concept": "Right of Pre-emption (Talab-i-Mowasibat, Talab-i-Ishhad)",
        "keywords": ["Talab-i-Mowasibat", "Talab-i-Ishhad", "jumping demand", "notice of talab"],
        "jurisdiction": "Civil Court"
    },
    {
        "patterns": [r"nazar\s*sani", r"review\s*application"],
        "statute": "Code of Civil Procedure 1908",
        "section": "Section 114 and Order XLVII CPC",
        "formal_concept": "Review of Judgment / Decree",
        "keywords": ["Order 47 CPC", "Section 114 CPC", "error apparent on face of record"],
        "jurisdiction": "Same Court that passed order"
    },
    {
        "patterns": [r"tauheen[- ]e[- ]adalat", r"contempt\s*of\s*court"],
        "statute": "Contempt of Court Ordinance 2003 / Constitution 1973",
        "section": "Article 204 Constitution of Pakistan",
        "formal_concept": "Contempt of Court",
        "keywords": ["Article 204", "Contempt of Court Ordinance 2003", "willful disobedience"],
        "jurisdiction": "High Court / Supreme Court"
    },
    {
        "patterns": [r"bar[- ]e[- ]saboot", r"burden\s*of\s*proof"],
        "statute": "Qanun-e-Shahadat Order 1984",
        "section": "Articles 117-129 QSO 1984",
        "formal_concept": "Burden of Proof and Onus Probandi",
        "keywords": ["Article 117 QSO", "Article 118 QSO", "onus of proof"],
        "jurisdiction": "All Courts"
    },
    {
        "patterns": [r"iqrar[- ]nama", r"biana", r"bayana", r"agreement\s*to\s*sell"],
        "statute": "Specific Relief Act 1877",
        "section": "Section 12 Specific Relief Act 1877",
        "formal_concept": "Specific Performance of Contract to Sell",
        "keywords": ["Specific performance", "earnest money", "readiness and willingness"],
        "jurisdiction": "Civil Court"
    },
    {
        "patterns": [r"mukhtar[- ]nama", r"power\s*of\s*attorney", r"mukhtar\s*aam", r"mukhtar\s*khas"],
        "statute": "Powers of Attorney Act 1882",
        "section": "Powers of Attorney Act 1882 / Article 17 QSO",
        "formal_concept": "General / Special Power of Attorney",
        "keywords": ["General Power of Attorney", "attestation", "principal and agent"],
        "jurisdiction": "Civil Court / Sub-Registrar"
    }
]

def expand_urdu_legal_query(query: str) -> Dict[str, Any]:
    """
    Expands a user's query containing Roman Urdu / trial court vernacular
    with statutory sections, formal legal terms, and targeted keywords.
    """
    q_norm = query.lower().strip()
    matched_entries = []
    expansion_tokens = []
    statutory_anchors = []

    for entry in URDU_LEGAL_LEXICON:
        matched = False
        for pat in entry["patterns"]:
            if re.search(r'\b' + pat + r'\b', q_norm, re.IGNORECASE):
                matched = True
                break
        if matched:
            matched_entries.append({
                "statute": entry["statute"],
                "section": entry["section"],
                "formal_concept": entry["formal_concept"],
                "jurisdiction": entry["jurisdiction"]
            })
            expansion_tokens.extend(entry["keywords"])
            statutory_anchors.append(entry["section"])

    if not matched_entries:
        return {
            "has_urdu_terms": False,
            "original_query": query,
            "expanded_query": query,
            "matched_entries": [],
            "statutory_anchors": []
        }

    unique_tokens = list(dict.fromkeys(expansion_tokens))
    expanded_str = f"{query} [Statutory Context: {' '.join(unique_tokens)}]"

    return {
        "has_urdu_terms": True,
        "original_query": query,
        "expanded_query": expanded_str,
        "matched_entries": matched_entries,
        "statutory_anchors": list(set(statutory_anchors))
    }
