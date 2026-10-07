"""
legal_ai/verification/doctrinal_rules.py

Doctrinal trap detection, governing provisions specification, and pattern rules
for Pakistani superior court legal opinion verification.
All pattern rules are strictly flagged with rule_status='pending_review'
until reviewed and signed off by a licensed advocate.
"""

from __future__ import annotations
import re
from typing import Dict, List, Optional, Any, Set

CORE_CODES: Set[str] = {
    "MISSING_GOVERNING_PROVISION",
    "STATUTE_MISSTATEMENT",
    "STATUTE_QUOTE_UNVERIFIED",
    "NO_AUTHORITY_FOR_TOPIC",
    "OVERCONFIDENT_VS_GAPS",
    "PROVISION_WRONG_ACT",
}

ACT_ALIASES: Dict[str, List[str]] = {
    "limitation_act": [r"limitation act"],
    "tpa": [r"transfer of property act", r"\btpa\b"],
    "cpc": [r"(?<![a-z])c\.?p\.?c\b", r"code of civil procedure", r"civil procedure code"],
    "crpc": [r"cr\.?\s?p\.?\s?c\b", r"code of criminal procedure"],
    "sra": [r"specific relief act"],
    "registration_act": [r"registration act"],
}

# Negation and distinction patterns to prevent false-positive flags
NEGATION_AND_DISTINCTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(?:does\s+not\s+apply|not\s+applicable|inapplicable|unlike|rather\s+than|cannot\s+be\s+invoked|has\s+no\s+application|is\s+not\s+available|not\s+the\s+route|is\s+not\s+maintainable|never\s+applies|does\s+not\s+extend\s+to)\b", re.IGNORECASE),
    re.compile(r"\b(?:distinguished\s+from|inapposite|no\s+application\s+to|no\s+relevance\s+to|no\s+preferential\s+treatment)\b", re.IGNORECASE),
]

PATTERN_RULES: List[Dict[str, Any]] = [
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "LA_S28_IMMUNITY",
        "severity": "error",
        "status": "pending_review",
        "topics": ["adverse_possession"],
        "all_of": [r"section\s*28|\bs\.\s*28"],
        "any_of": [
            r"no period of limitation[^.]{0,80}run",
            r"government immunity",
            r"absolute (statutory )?bar",
            r"\bgovernment\b[^.]{0,60}disabilit",
        ],
        "none_of": [
            r"consumer",
            r"act,? 2005",
            r"sub-?section \(4\)",
        ],
        "message": "Limitation Act 1908 s.28 is the extinguishment provision (right to property extinguished when the period for a possession suit ends). It is not a Government-immunity provision.",
        "fix": "Remove the immunity thesis. Analyse Art. 144 vs Art. 149 (Government suits) and s.28 extinguishment; quote only text loaded in the statute store.",
    },
    {
        "code": "PROVISION_WRONG_ACT",
        "id": "TPA_S49",
        "severity": "error",
        "status": "pending_review",
        "topics": [],
        "all_of": [
            r"transfer of property act[^.]{0,40}section\s*49|section\s*49[^.]{0,30}transfer of property act"
        ],
        "message": "Section 49 concerning effect of non-registration is in the Registration Act 1908, not the Transfer of Property Act.",
        "fix": "Cite Registration Act 1908 s.49.",
    },
    {
        "code": "FORUM_PROVISION_MISMATCH",
        "id": "CRPC_561A_CIVIL",
        "severity": "error",
        "status": "pending_review",
        "topics": ["adverse_possession", "injunction"],
        "all_of": [r"561-?\s?a"],
        "any_of": [
            r"c\.?p\.?c",
            r"civil",
            r"injunction",
            r"order xxxix",
            r"revision",
        ],
        "none_of": [
            r"criminal",
        ],
        "message": "s.561-A is a Cr.P.C. inherent-powers provision. It is not the route for civil revision or injunction orders.",
        "fix": "Civil: appeal under O.XLIII R.1(r) CPC, s.151 CPC, or revision under s.115 CPC where available.",
    },
    {
        "code": "ARTICLE_TYPE_CONFUSION",
        "id": "LA_ARTICLES_AS_JURISDICTION",
        "severity": "error",
        "status": "pending_review",
        "topics": [],
        "all_of": [
            r"articles?\s*\d+[^.]{0,60}limitation act"
        ],
        "any_of": [
            r"jurisdiction",
            r"revisional",
            r"appellate",
        ],
        "message": "Articles of the Limitation Act First Schedule are limitation entries, not sources of court jurisdiction.",
        "fix": "Cite the jurisdictional provision (e.g. s.115 CPC, Art. 199/185 Constitution) and the limitation Article separately.",
    },
    {
        "code": "FORUM_PROVISION_MISMATCH",
        "id": "ART_184_3_PRIVATE",
        "severity": "warn",
        "status": "pending_review",
        "topics": ["adverse_possession", "injunction"],
        "all_of": [r"184\s*\(3\)"],
        "any_of": [
            r"adverse possession",
            r"injunction",
            r"interim relief",
            r"private",
            r"civil",
        ],
        "message": "Art. 184(3) is original jurisdiction on questions of public importance re fundamental rights. Private civil disputes reach the Supreme Court by leave/appeal (Art. 185); interim directions are usually Art. 187.",
        "fix": "Use Art. 185 for civil appeals; consider Art. 187 for interim orders.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "O39_R4_EXPARTE",
        "severity": "error",
        "status": "pending_review",
        "topics": ["injunction"],
        "all_of": [r"rule\s*4\b"],
        "any_of": [
            r"ex parte",
            r"lapse",
        ],
        "message": "O.XXXIX R.4 concerns discharge, variation or setting aside of injunction orders. Notice before grant (and ex parte exception) is R.3. A 'lapse unless inter partes' mechanism is not the text of R.4.",
        "fix": "Rewrite using R.3 (notice) and R.4 (discharge/vary/set aside); quote only loaded text.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "O39_R3_DISOBEDIENCE",
        "severity": "error",
        "status": "pending_review",
        "topics": ["injunction"],
        "all_of": [r"rule\s*3\b"],
        "any_of": [
            r"disobedience",
            r"contempt",
            r"attach",
        ],
        "message": "Consequences of disobedience/breach of an injunction are under O.XXXIX R.2(3), not R.3.",
        "fix": "Cite O.XXXIX R.2(3).",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "O39_R2_FINAL_EXECUTION",
        "severity": "error",
        "status": "pending_review",
        "topics": ["injunction"],
        "all_of": [r"rule\s*2\b"],
        "any_of": [
            r"final injunction",
            r"in aid of (an )?(existing )?judgment",
            r"judgment-debtor",
            r"executing court",
        ],
        "message": "O.XXXIX concerns temporary injunctions. Protecting assets before judgment is attachment before judgment (O.XXXVIII); no 'final injunction in aid of execution' exists under R.2.",
        "fix": "Remove, or re-base on O.XXXVIII / execution provisions.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "O39_R1_FINAL_DECLARATORY",
        "severity": "error",
        "status": "pending_review",
        "topics": ["injunction"],
        "all_of": [r"rule\s*1\b"],
        "any_of": [
            r"final injunctions",
            r"declaratory injunctions",
            r"three categories",
        ],
        "message": "O.XXXIX R.1 lists the situations for a temporary injunction (waste, alienation, dispossession, other injury). It does not create categories of final or declaratory injunction.",
        "fix": "Describe R.1 as the temporary-injunction grounds; final injunctions fall under the Specific Relief Act.",
    },
    {
        "code": "OVERSTATEMENT",
        "id": "O39_EXCLUSIVE",
        "severity": "warn",
        "status": "pending_review",
        "topics": ["injunction"],
        "all_of": [r"order xxxix|o\.?\s*xxxix"],
        "any_of": [
            r"exclusive (procedural )?mechanism",
            r"exclusive and controlling",
        ],
        "message": "Injunctions are also available via s.94(c) and s.151 CPC and under the Specific Relief Act ss.52-57; 'exclusive' is an overstatement.",
        "fix": "Soften, and cite the other routes.",
    },
    {
        "code": "UNVERIFIED_STATUTE_REFERENCE",
        "id": "CONTEMPT_ORD_2003",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"contempt of court ordinance"],
        "message": "Current status of the cited Ordinance is unchecked. First remedy for breach of a civil injunction is O.XXXIX R.2(3).",
        "fix": "Verify the instrument is in force; lead with O.XXXIX R.2(3).",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "LA_S5_GOVT_PROVISO",
        "severity": "error",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"section\s*5\b"],
        "any_of": [
            r"proviso excluding government",
            r"express proviso excluding",
        ],
        "message": "Limitation Act s.5 has no Government-exclusion proviso. Sindh Irrigation (2026 SCMR 190) only says no preferential treatment for Government on condonation.",
        "fix": "Describe the case holding only.",
    },
    {
        "code": "UNSOURCED_PERIOD",
        "id": "PERIOD_30_DAYS",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"within\s*30\s*days"],
        "any_of": [
            r"revision",
            r"appeal",
            r"petition",
        ],
        "message": "A limitation period is asserted without a source. Periods come from the Limitation Act First Schedule.",
        "fix": "Cite the Article or drop the number.",
    },
]

PROVISIONS_SPEC: List[Dict[str, Any]] = [
    {"act": "limitation_act", "kind": "section", "id": "3", "subject": "Dismissal of suits, appeals and applications instituted after the period of limitation", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "section", "id": "5", "subject": "Extension of prescribed period in certain cases (condonation of delay)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "section", "id": "28", "subject": "Extinguishment of right to property at determination of period limited to institute a suit for possession", "not_about": [], "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "section", "id": "29", "subject": "Savings (special or local laws)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "article", "id": "144", "subject": "Suit for possession of immovable property (private person): twelve years from when possession becomes adverse", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "article", "id": "149", "subject": "Suit by or on behalf of Government for possession of immovable property (longer period; verify against bare Act)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "article", "id": "178", "subject": "Filing of award in court under Arbitration Act 1940", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "limitation_act", "kind": "article", "id": "181", "subject": "Residuary: applications for which no period is provided", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "tpa", "kind": "section", "id": "110", "subject": "Exclusion of day on which term commences (computation of time)", "not_about": ["adverse possession", "good faith"], "required_if_correct": [], "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "tpa", "kind": "section", "id": "123", "subject": "Transfer by gift of immovable property (registered instrument; delivery for movables)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "registration_act", "kind": "section", "id": "49", "subject": "Effect of non-registration of documents required to be registered", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "sra", "kind": "section", "id": "42", "subject": "Discretion of court as to declaration of status or right", "not_about": ["injunction"], "required_if_correct": ["declar"], "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "sra", "kind": "section", "id": "53", "subject": "Temporary injunctions", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "sra", "kind": "section", "id": "54", "subject": "Perpetual injunctions", "not_about": ["shall not be granted", "is refused", "grounds on which an injunction"], "required_if_correct": [], "severity": "warn", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "sra", "kind": "section", "id": "55", "subject": "Mandatory injunctions", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "sra", "kind": "section", "id": "56", "subject": "Injunction when refused", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "section", "id": "94", "subject": "Supplemental proceedings (incl. temporary injunctions, cl. (c))", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "section", "id": "115", "subject": "Revision", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "section", "id": "151", "subject": "Saving of inherent powers of court", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "crpc", "kind": "section", "id": "561-A", "subject": "Saving of inherent powers of High Court (criminal)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "rule", "id": "O39R1", "subject": "Cases in which temporary injunction may be granted", "pattern": r"(order\s*xxxix|o\.?\s*xxxix)[^.]{0,40}rule\s*1", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "rule", "id": "O39R2", "subject": "Injunction to restrain repetition or continuance of breach", "pattern": r"(order\s*xxxix|o\.?\s*xxxix)[^.]{0,40}rule\s*2", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "rule", "id": "O39R2(3)", "subject": "Consequence of disobedience or breach of injunction (attachment, detention)", "pattern": r"rule\s*2\s*\(3\)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "rule", "id": "O39R3", "subject": "Before granting injunction, court to direct notice to opposite party (exception where delay defeats object)", "pattern": r"(order\s*xxxix|o\.?\s*xxxix)[^.]{0,40}rule\s*3", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "rule", "id": "O39R4", "subject": "Order for injunction may be discharged, varied or set aside", "pattern": r"(order\s*xxxix|o\.?\s*xxxix)[^.]{0,40}rule\s*4", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "cpc", "kind": "rule", "id": "O43R1(r)", "subject": "Appeal from order granting, refusing, discharging or varying injunction", "pattern": r"(order\s*xliii|o\.?\s*xliii)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
]

TOPICS_SPEC: Dict[str, Any] = {
    "adverse_possession": {
        "detect": [
            r"adverse possession",
            r"animus possidendi",
        ],
        "mandatory_groups": [
            {
                "label": "Limitation Act Art. 144 (private suit for possession)",
                "any": [r"article\s*144"],
            },
            {
                "label": "Limitation Act Art. 149 (suit by Government for possession)",
                "any": [r"article\s*149"],
            },
            {
                "label": "Limitation Act s.28 (extinguishment)",
                "any": [r"section\s*28|s\.\s*28"],
            },
        ],
        "mandatory_keys": [
            "limitation_act:article:144",
            "limitation_act:article:149",
            "limitation_act:section:28",
        ],
        "relevance": {
            "strong": [
                r"adverse possession",
                r"animus possidendi",
                r"article\s*14[49]",
                r"hostile possession",
            ],
        },
        "extra_queries": [
            "adverse possession Article 144 Limitation Act Supreme Court",
            "suit by Government for possession Article 149 Limitation Act",
            "animus possidendi adverse possession hostile title Supreme Court",
            "adverse possession against state land Pakistan",
        ],
        "template_forbid": [
            r"pre-?arrest bail",
            r"bail strategy",
        ],
        "template_headings": [
            "Question and short answer",
            "Issues",
            "Governing provisions (statute text as loaded)",
            "Authorities (relevant only)",
            "Analysis",
            "Practical routes (practice notes, not authority)",
            "Research gaps",
        ],
    },
    "injunction": {
        "detect": [
            r"order xxxix",
            r"o\.?\s*xxxix",
            r"injunction",
        ],
        "mandatory_groups": [
            {
                "label": "Order XXXIX (CPC)",
                "any": [r"order\s*xxxix", r"o\.?\s*xxxix"],
            },
            {
                "label": "Specific Relief Act ss.52-57 (injunctions)",
                "any": [
                    r"specific relief act[^.]{0,120}5[2-7]",
                    r"sections?\s*(?:\d+\s*(?:,|&|and)\s*)*5[2-7][^.]{0,60}specific relief",
                ],
            },
            {
                "label": "Appeal from injunction order, O.XLIII R.1(r) CPC",
                "any": [r"order\s*xliii", r"o\.?\s*xliii", r"o\.?\s*43"],
            },
        ],
        "mandatory_keys": [
            "cpc:rule:O39R1",
            "cpc:rule:O39R2",
            "cpc:rule:O39R2(3)",
            "cpc:rule:O39R3",
            "cpc:rule:O39R4",
            "cpc:rule:O43R1(r)",
            "sra:section:53",
            "sra:section:54",
            "sra:section:56",
        ],
        "relevance": {
            "strong": [
                r"order\s*xxxix",
                r"o\.?\s*xxxix",
                r"temporary injunction",
                r"interim injunction",
                r"balance of convenience",
                r"irreparable (?:loss|injury|harm)",
                r"prima facie case",
            ],
        },
        "extra_queries": [
            "temporary injunction prima facie case irreparable loss balance of convenience Supreme Court",
            "Order XXXIX Rule 1 Rule 2 temporary injunction",
            "Order XLIII Rule 1 appeal order refusing injunction",
            "breach of injunction Order XXXIX Rule 2(3) attachment detention",
        ],
        "template_forbid": [
            r"pre-?arrest bail",
            r"bail strategy",
        ],
        "template_headings": [
            "Question and short answer",
            "Governing provisions (statute text as loaded)",
            "Test applied by the courts (with authority)",
            "Authorities (relevant only)",
            "Procedure: filing, notice, ex parte, discharge/variation",
            "Remedies after refusal/grant (appeal/revision)",
            "Practice notes (not authority)",
            "Research gaps",
        ],
    },
}

GAP_PHRASES: List[str] = [
    r"not (?:been )?(?:retrieved|located|substantiated)",
    r"remain(?:s)? beyond the scope",
    r"no reported cases?[^.]{0,80}retrieved",
    r"did not retrieve",
    r"unlocated (?:statutory )?authorit",
    r"requir\w+ deeper investigation",
    r"not extensively addressed",
]

STRONG_PHRASES: List[str] = [
    r"direct opinion:",
    r"absolute(?:ly)? (?:statutory )?bar",
    r"zero realistic prospect",
    r"insurmountable",
    r"exclusive and controlling",
    r"exclusive mechanism",
    r"mandatory and conjunctive",
    r"categorical bar",
    r"invariably",
]

OVERCLAIM_PHRASES: List[str] = [
    r"verified against official records",
    r"retrieved from official (?:court|supreme court) records",
    r"drawn directly from the retrieved",
    r"verified statutory text",
    r"confirmed from provided case matrix",
]


def classify_matter_type(query: str, plan_domains: Optional[List[str]] = None) -> str:
    """
    Deterministically classifies legal matter type into:
    'tax', 'criminal', 'corporate', 'constitutional', or 'civil'.
    """
    q_low = query.lower()
    domains_str = " ".join([d.lower() for d in (plan_domains or [])])
    comb = f"{q_low} {domains_str}"

    # 1. Tax
    if any(k in comb for k in [
        "income tax", "sales tax", "fbr", "tax assessment", "ptd", "customs",
        "section 127", "section 131", "appellate tribunal inland revenue", "commissioner (appeals)"
    ]):
        return "tax"

    # 2. Criminal
    if any(k in comb for k in [
        "pre-arrest", "post-arrest", "bail", "fir", "497", "498", "420", "406",
        "409", "302", "ppc", "crpc", "cr.p.c", "cnsa", "nab", "anti-terrorism", "culpable homicide"
    ]):
        if any(civ in comb for civ in ["injunction", "order xxxix", "specific relief", "adverse possession"]):
            if "bail" not in q_low and "fir" not in q_low:
                return "civil"
        return "criminal"

    # 3. Corporate / Banking
    if any(k in comb for k in [
        "companies act", "secp", "winding up", "banking court", "fio 2001",
        "financial institutions", "recovery of finance"
    ]):
        return "corporate"

    # 4. Constitutional
    if any(k in comb for k in [
        "article 199", "article 184(3)", "writ petition", "quo warranto", "habeas corpus"
    ]):
        return "constitutional"

    return "civil"


def detect_topics(text: str) -> List[str]:
    """Detects active legal verification topics in text."""
    t = text.lower()
    return [
        name for name, spec in TOPICS_SPEC.items()
        if any(re.search(p, t, re.IGNORECASE) for p in spec["detect"])
    ]


def rule_matches_sentence(
    rule: Dict[str, Any],
    sentence: str,
    matter_type: str = "civil"
) -> bool:
    """
    Evaluates whether a pattern rule triggers on a specific sentence.
    Includes false-positive immunity:
    1. Gated by matter_type (e.g. CRPC_561A_CIVIL ignored in criminal matters).
    2. Gated by negation and distinction patterns (e.g. 'does not apply', 'unlike').
    """
    rule_id = rule.get("id", "")

    # Criminal matter immunity for CrPC civil mismatch
    if rule_id == "CRPC_561A_CIVIL" and matter_type == "criminal":
        return False

    # Check all_of
    if not all(re.search(p, sentence, re.IGNORECASE) for p in rule.get("all_of", [])):
        return False

    # Check any_of
    any_of = rule.get("any_of")
    if any_of and not any(re.search(p, sentence, re.IGNORECASE) for p in any_of):
        return False

    # Check none_of
    none_of = rule.get("none_of")
    if none_of and any(re.search(p, sentence, re.IGNORECASE) for p in none_of):
        return False

    # Check negation / distinction immunity:
    # If the sentence explicitly negates or distinguishes the improper thesis, do not flag.
    # Note: for LA_S5_GOVT_PROVISO, we only negate if the sentence specifically mentions that there is no proviso
    if any(neg.search(sentence) for neg in NEGATION_AND_DISTINCTION_PATTERNS):
        return False

    return True


def build_pre_synthesis_trap_instructions(
    matter_type: str,
    topics: List[str],
    abstain_topics: Optional[List[str]] = None
) -> str:
    """
    Generates concise pre-synthesis instructions detailing known traps to avoid,
    grounding rules, and mandatory section headings without adding LLM latency.
    """
    lines: List[str] = [
        "CRITICAL DOCTRINAL & VERIFICATION DIRECTIVES (Zero Exceptions):",
        "1. Never cite non-retrieved or unverified authorities from memory. Cite ONLY the supplied superior court precedents.",
        "2. Exact citation formatting required: 'PLD 2025 SC 502' or '2026 SCMR 190'.",
        "3. Verbatim statutory text: Quote bare-act text ONLY if provided in the STATUTORY FRAMEWORK block. If not provided, state that text was not retrieved rather than paraphrasing into quotes.",
        "4. Never invent statutory connections: Section 49 regarding effect of unregistered documents is in the Registration Act 1908, NEVER Transfer of Property Act.",
        "5. Avoid forum mismatch: Section 561-A Cr.P.C. is strictly criminal inherent jurisdiction; do NOT cite it for civil appeals, revisions, or injunctions.",
        "6. Limitation Act Articles (e.g. Art. 144, 181, 182) are periods of limitation in the First Schedule, NOT sources of court jurisdiction.",
    ]

    if "adverse_possession" in topics or "property" in matter_type:
        lines.append(
            "7. Adverse Possession Doctrine: Section 28 Limitation Act 1908 extinguishes right to property at the expiry of limitation; "
            "it is NOT a government-immunity doctrine. Distinguish Article 144 (private, 12 yrs) from Article 149 (Government, 60 yrs)."
        )

    if "injunction" in topics or matter_type in ("civil", "commercial"):
        lines.append(
            "8. Injunctions Framework: Order XXXIX Rule 1 governs temporary injunction grounds; Rule 2 covers breach restraint; "
            "Rule 2(3) covers disobedience/contempt penalties; Rule 3 covers pre-grant notice; Rule 4 covers discharge/variation/setting aside. "
            "Appeals lie under Order XLIII Rule 1(r) C.P.C."
        )

    if abstain_topics:
        lines.append(
            f"9. UNRETRIEVED DOCTRINES: No controlling precedent retrieved for: {', '.join(abstain_topics)}. "
            "Explicitly disclose this limitation and withhold an unqualified conclusion."
        )

    return "\n".join(lines)
