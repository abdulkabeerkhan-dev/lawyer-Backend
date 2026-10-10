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
    "constitution": [r"constitution", r"constitutional", r"\bconst\b"],
    "service_tribunals_act": [r"service tribunals?\s+act", r"\bsta\b"],
    "peeda": [r"peeda", r"punjab employees efficiency discipline and accountability", r"efficiency and discipline"],
}

# Negation and distinction patterns to prevent false-positive flags
NEGATION_AND_DISTINCTION_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"\b(?:does\s+not|do\s+not|did\s+not|cannot|shall\s+not|is\s+not|are\s+not|not)\s+"
        r"(?:apply|applicable|grant|provide|deal\s+with|prescribe|contain|create|confer|extend\s+to|constitute|available|maintainable|the\s+route|exclusive|the\s+exclusive)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"\b(?:unlike|rather\s+than|cannot\s+be\s+invoked|has\s+no\s+application|is\s+not\s+available|"
        r"not\s+the\s+route|is\s+not\s+maintainable|never\s+applies|does\s+not\s+extend\s+to|"
        r"distinguished\s+from|inapposite|inapplicable|no\s+application\s+to|no\s+relevance\s+to|no\s+preferential\s+treatment|"
        r"contains?\s+no|has\s+no|not\s+grant|not\s+contain|not\s+prescribe|not\s+the\s+exclusive)\b",
        re.IGNORECASE
    ),
]

PATTERN_RULES: List[Dict[str, Any]] = [
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "LA_S28_IMMUNITY",
        "severity": "warn",
        "status": "disputed_pending_primary_source",
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
        "message": "Limitation Act 1908 s.28 is the extinguishment provision, not a Government-immunity provision. Note: The constitutional status of s.28 under 1991 SCMR 2063 is marked disputed_pending_primary_source pending unquarantined full-text verification. Distinguish Art. 144 vs Art. 149 (60 years for Government suits).",
        "fix": "Do not assert Government immunity under s.28. Maintain claim under disputed_pending_primary_source and distinguish Art. 144 vs Art. 149.",
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
        "none_of": [
            r"section\s*49\s+(?:of\s+(?:the\s+)?)?registration\s+act",
            r"registration\s+act[^.]{0,30}section\s*49",
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
        "none_of": [
            r"jurisdiction\s+under\s+(?:section|s\.|order|c\.?p\.?c|code\s+of\s+civil\s+procedure|art\.?\s*(?:185|199))",
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
        "id": "O39_R2A_INDIAN_IMPORT",
        "severity": "error",
        "status": "pending_review",
        "topics": ["injunction"],
        "all_of": [
            r"(?:order\s*xxxix|o\.?\s*xxxix|o\s*39|order\s*39)[^.]{0,30}rule\s*2-?[aA]\b|rule\s*2-?[aA]\b[^.]{0,30}(?:order\s*xxxix|o\.?\s*xxxix|o\s*39|order\s*39)"
        ],
        "message": "Order XXXIX Rule 2A is an Indian CPC amendment (Act 104 of 1976) that does not exist in the Pakistan Code. In Pakistan, disobedience or breach of an injunction is governed strictly by Order XXXIX Rule 2(3) CPC 1908.",
        "fix": "Replace citation of Order XXXIX Rule 2A with Order XXXIX Rule 2(3) CPC 1908.",
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
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "ART4_LIFE_LIBERTY",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [
            r"(?:article\s*4\b|art\.?\s*4\b)"
        ],
        "any_of": [
            r"right\s+to\s+life",
            r"life\s+and\s+liberty",
            r"liberty\s+and\s+security",
            r"life\s+or\s+liberty",
        ],
        "none_of": [
            r"article\s*9\b|art\.?\s*9\b",
            r"in\s+accordance\s+with\s+law",
            r"protection\s+of\s+law",
            r"4\(2\)\(a\)",
            r"detrimental\s+to\s+(?:the\s+)?life",
        ],
        "message": "Article 4 guarantees the inalienable right of individuals to be dealt with in accordance with law; although Article 4(2)(a) prohibits action detrimental to life or liberty save in accordance with law, the primary substantive constitutional guarantee of security of person / right to life is Article 9.",
        "fix": "Cite Article 9 as the primary substantive provision for life and liberty, and Article 4 for treatment in accordance with law.",
    },
    {
        "code": "TEMPLATE_RESIDUE",
        "id": "SERVICE_CUSTODIAL_RESIDUE",
        "severity": "error",
        "status": "pending_review",
        "topics": ["service_dismissal"],
        "any_of": [
            r"custodial\s+interrogation",
            r"police\s+custody",
            r"physical\s+remand",
            r"pre-?arrest\s+bail",
            r"section\s*498\b",
            r"custodial\s+investigation",
        ],
        "none_of": [],
        "message": "Criminal bail template terminology ('custodial interrogation / police custody / bail') detected in a service dismissal matter.",
        "fix": "Remove criminal bail residue and focus on administrative and service tribunal remedies.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "VOID_AB_INITIO_NO_CURE",
        "severity": "warn",
        "status": "pending_review",
        "topics": ["service_dismissal"],
        "all_of": [
            r"void\s+ab\s+initio"
        ],
        "any_of": [
            r"cannot\s+be\s+cured",
            r"incurable",
            r"no\s+remand",
            r"absolute\s+nullity",
            r"per\s+se\s+void",
            r"without\s+(?:showing\s+)?prejudice",
            r"no\s+requirement\s+to\s+(?:show|demonstrate)\s+prejudice",
        ],
        "none_of": [
            r"(?:remand(?:ed)?\s+(?:for|to)|fresh\s+inquiry)",
            r"(?:can|may)\s+be\s+cured",
            r"\bcurable\b",
            r"unless\s+prejudice\s+(?:is\s+)?shown",
            r"prejudice\s+must\s+be\s+shown",
        ],
        "message": "Procedural defects in a show-cause or inquiry do not automatically make dismissal void ab initio without cure; superior courts routinely remand for de novo inquiry unless substantial prejudice is shown.",
        "fix": "Acknowledge that procedural defects permit departmental remand from the stage the defect occurred.",
    },
    {
        "code": "FORUM_PROVISION_MISMATCH",
        "id": "O39_IN_WRIT",
        "severity": "warn",
        "status": "pending_review",
        "topics": ["service_dismissal"],
        "all_of": [
            r"(?:order\s*xxxix|o\.?\s*xxxix|order\s*39\b|o\s*39\b)"
        ],
        "any_of": [
            r"(?:article\s*199\b|art\.?\s*199\b|writ\s+petition|constitutional\s+petition)"
        ],
        "none_of": [
            r"does\s+not\s+apply",
            r"not\s+applicable",
            r"inapplicable",
            r"distinguish",
            r"civil\s+suit",
        ],
        "message": "Order XXXIX CPC applies to ordinary civil suits, not Article 199 writ petitions. Note: Article 199(4) is a constitutional restriction prohibiting interim orders that prejudice public works, State property, or revenue without notice to the law officer, not an affirmative source of interim relief. Interim stay in writ jurisdiction is governed by the High Court's constitutional powers and High Court Rules.",
        "fix": "Do not invoke Order XXXIX CPC in Article 199 writ petitions; address interim stay under constitutional writ jurisdiction subject to Article 199(4) restrictions.",
    },
    {
        "code": "PRECEDENT_MISATTRIBUTION",
        "id": "DIRECTLY_ON_POINT",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "any_of": [
            r"directly\s+on\s+point",
            r"on\s+all\s+fours",
            r"squarely\s+governs",
            r"directly\s+controlling",
        ],
        "none_of": [
            r"not\s+directly\s+on\s+point",
            r"distinguishable",
            r"analogous",
            r"by\s+analogy",
            r"tentative",
        ],
        "message": "A precedent is described as 'directly on point' or 'on all fours'. Under Pakistan jurisprudence, precedents should only be characterized as directly controlling where all material facts, statutory provisions, and questions of law coincide; otherwise, characterization should be 'applies by analogy' or 'tangential'.",
        "fix": "Verify that the precedent directly decided the identical legal question under the identical statutory framework, or characterize as persuasive by analogy.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "NI_ACT_S138_IMPORT",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [
            r"(?:negotiable\s+instruments\s+act|n\.?i\.?\s+act)[^.]{0,40}section\s*138|section\s*138[^.]{0,40}(?:negotiable\s+instruments\s+act|n\.?i\.?\s+act)"
        ],
        "none_of": [
            r"indian", r"india", r"foreign", r"comparative", r"unlike", r"does\s+not\s+apply",
            r"not\s+applicable", r"inapplicable", r"not\s+exist", r"not\s+enacted", r"does\s+not\s+contain"
        ],
        "message": "Section 138 of the Negotiable Instruments Act is an Indian statutory amendment (Act 66 of 1988) that does not exist in the Pakistan Code. In Pakistan, criminal prosecution for dishonour of a cheque is governed by Section 489-F PPC.",
        "fix": "Cite Section 489-F PPC for criminal cheque dishonour in Pakistan; cite Negotiable Instruments Act only if discussing civil liability or distinguishing Indian law.",
    },
    {
        "code": "FORUM_PROVISION_MISMATCH",
        "id": "LIMITATION_ACT_CRIMINAL",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"limitation\s+act"],
        "any_of": [
            r"limitation\s+period[^.]{0,40}(?:for\s+lodging\s+an?\s+fir|to\s+lodge\s+an?\s+fir|for\s+criminal\s+prosecution|for\s+criminal\s+complaint|under\s+section\s*489-?f)",
            r"period\s+of\s+limitation[^.]{0,40}(?:for\s+criminal|to\s+lodge\s+fir|for\s+section\s*489)",
            r"article\s*105[^.]{0,40}(?:cheque|489|criminal|fir|bounced)"
        ],
        "none_of": [
            r"does\s+not\s+apply", r"not\s+applicable", r"no\s+limitation", r"inapplicable",
            r"no\s+period\s+of\s+limitation", r"civil\s+only", r"civil\s+suit"
        ],
        "message": "The Limitation Act 1908 governs civil suits, appeals, and applications (First Schedule); it does not prescribe limitation periods for lodging an FIR or initiating criminal prosecution under the Cr.P.C. (Article 105 Limitation Act is for a mortgagor's suit for surplus collections).",
        "fix": "Clarify that no general statutory limitation period is prescribed under the Limitation Act 1908 or Cr.P.C. for lodging an FIR or criminal complaint under Section 489-F PPC, though unexplained inordinate delay is evaluated at trial.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "PUNJAB_TENANCY_ACT_FOR_RENT",
        "severity": "warn",
        "status": "pending_review",
        "topics": ["rent_eviction"],
        "all_of": [r"punjab\s+tenancy\s+act"],
        "any_of": [
            r"commercial", r"urban", r"shop", r"building", r"house", r"rented\s+premises"
        ],
        "none_of": [
            r"agricultural", r"distinguish", r"unlike", r"not\s+applicable", r"does\s+not\s+apply", r"inapplicable"
        ],
        "message": "The Punjab Tenancy Act 1887 applies exclusively to agricultural land tenancies. Urban commercial and residential buildings in Punjab are governed exclusively by the Punjab Rented Premises Act 2009 (PRPA).",
        "fix": "Cite the Punjab Rented Premises Act 2009 for urban building and commercial shop tenancies in Punjab.",
    },
    {
        "code": "FORUM_PROVISION_MISMATCH",
        "id": "O42_R1_JURISDICTION",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"(?:order\s*xlii|order\s*42|o\.?\s*xlii|o\.?\s*42)\s*rule\s*1"],
        "any_of": [
            r"original\s+jurisdiction", r"forum\s+for", r"remedy\s+for\s+eviction", r"institute\s+a\s+suit", r"rent\s+tribunal"
        ],
        "none_of": [
            r"second\s+appeal", r"procedural", r"section\s*100"
        ],
        "message": "Order XLII Rule 1 CPC prescribes procedure for Second Appeals under Section 100 CPC in the High Court; it is not an original forum or jurisdiction for eviction or civil disputes.",
        "fix": "Cite the Rent Tribunal under PRPA 2009 / SRPO 1979 for eviction, or Section 9 CPC for original civil suits.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "S34_CPC_MULTIPLE_REMEDIES",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"(?:section\s*34|s\.\s*34)\s+(?:of\s+(?:the\s+)?)?c\.?p\.?c\b"],
        "any_of": [
            r"multiple\s+remedies", r"concurrent\s+(?:remedies|proceedings)", r"dual\s+remedies", r"both\s+proceed\s+at\s+the\s+same\s+time"
        ],
        "none_of": [
            r"interest", r"cost\s+of\s+funds", r"decree", r"payment\s+of\s+money"
        ],
        "message": "Section 34 CPC empowers civil courts to award interest/markup in money decrees; it does not authorize or regulate concurrent civil and criminal remedies.",
        "fix": "Cite general procedural jurisprudence confirming that civil remedies (Rent Tribunal / civil suit) and criminal proceedings (Section 489-F PPC) are distinct and can proceed concurrently.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "S200_COGNIZANCE",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"(?:section\s*200|s\.\s*200)\s+(?:of\s+(?:the\s+)?)?cr\.?p\.?c\b"],
        "any_of": [
            r"takes\s+cognizance\s+under\s+section\s*200", r"cognizance\s+is\s+taken\s+under\s+section\s*200", r"cognizance\s+under\s+section\s*200"
        ],
        "none_of": [
            r"section\s*190", r"examination\s+of\s+complainant", r"upon\s+taking\s+cognizance"
        ],
        "message": "Section 200 Cr.P.C. provides for examination of the complainant on oath upon a direct complaint; judicial cognizance of offences is taken under Section 190 Cr.P.C.",
        "fix": "Cite Section 190 Cr.P.C. for taking cognizance and Section 200 Cr.P.C. for recording the complainant's statement.",
    },
    {
        "code": "STATUTE_MISSTATEMENT",
        "id": "S228_CHARGE",
        "severity": "warn",
        "status": "pending_review",
        "topics": [],
        "all_of": [r"(?:section\s*228|s\.\s*228)\s+(?:of\s+(?:the\s+)?)?cr\.?p\.?c\b"],
        "any_of": [
            r"framing\s+of\s+charge\s+under\s+section\s*228", r"charges?\s+(?:are|is)\s+framed\s+under\s+section\s*228"
        ],
        "none_of": [
            r"alteration", r"alter\s+the\s+charge", r"indian", r"amendment\s+of\s+charge"
        ],
        "message": "In Pakistani Cr.P.C. 1898, Section 228 concerns procedure when a charge is altered. Framing of formal charge in Magisterial trials is under Section 242 Cr.P.C. (or Section 265-D in Sessions trials). (Section 228 Indian CrPC is framing of charge).",
        "fix": "Cite Section 242 Cr.P.C. for framing of charge in Magisterial trials.",
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
    {"act": "constitution", "kind": "article", "id": "4", "subject": "Right of individuals to be dealt with in accordance with law, etc.", "not_about": ["life and liberty", "custodial interrogation"], "required_if_correct": ["accordance with law"], "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "constitution", "kind": "article", "id": "9", "subject": "Security of person (no person shall be deprived of life or liberty save in accordance with law)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "constitution", "kind": "article", "id": "10A", "subject": "Right to fair trial (determination of civil rights and obligations or criminal charge)", "pattern": r"(?:articles?|arts?\.?)\s*10\-?A\b", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "constitution", "kind": "article", "id": "199", "subject": "Jurisdiction of High Court (no other adequate remedy; without lawful authority and of no legal effect)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "constitution", "kind": "article", "id": "212", "subject": "Administrative Courts and Tribunals (exclusive jurisdiction; ouster of other courts)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "service_tribunals_act", "kind": "section", "id": "4", "subject": "Appeals to Tribunals (appeal by civil servant; departmental review/appeal 90-day requirement)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "peeda", "kind": "section", "id": "3", "subject": "Grounds for proceedings and penalties", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "peeda", "kind": "section", "id": "4", "subject": "Penalties (minor and major penalties including dismissal from service)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
    {"act": "peeda", "kind": "section", "id": "7", "subject": "Procedure where inquiry is dispensed with (show cause notice and opportunity of personal hearing)", "text": None, "as_at": None, "source": None, "reviewed_by": None},
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
        "landmark_authorities": [
            "1991 SCMR 2063",
        ],
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
        "query_only": True,
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
        "landmark_authorities": [
            "2002 SCMR 1298",
        ],
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
    "rent_eviction": {
        "detect": [
            r"rent",
            r"tenant",
            r"landlord",
            r"eviction",
            r"ejectment",
            r"prpa",
            r"srpo",
        ],
        "mandatory_groups": [
            {
                "label": "Punjab Rented Premises Act 2009 s.15 (eviction grounds)",
                "any": [r"section\s*15", r"s\.\s*15"],
            },
            {
                "label": "PRPA 2009 s.34 (bar on civil courts)",
                "any": [r"section\s*34", r"s\.\s*34"],
            },
        ],
        "mandatory_keys": [
            "prpa_2009:section:15",
            "prpa_2009:section:34",
        ],
        "relevance": {
            "strong": [
                r"rent\s*(?:tribunal|controller|restriction)",
                r"ejectment",
                r"eviction",
                r"tenant",
                r"landlord",
                r"non-payment of rent",
                r"default in payment of rent",
            ],
        },
        "landmark_authorities": [
            "2000 MLD 1345",
        ],
        "extra_queries": [
            "eviction of tenant non-payment of rent Punjab Rented Premises Act 2009",
            "bar on civil court suit Section 34 PRPA Rent Tribunal",
        ],
        "template_forbid": [
            r"pre-?arrest bail",
            r"bail strategy",
        ],
        "template_headings": [
            "Question and short answer",
            "Governing provisions",
            "Authorities",
            "Analysis",
            "Procedure",
            "Research gaps",
        ],
    },
    "service_dismissal": {
        "detect": [
            r"\bdismiss(?:al|ed|ing|s)?\b",
            r"\b(?:government|civil|public)\s+(?:servant|employee)s?\b|\bcivil\s+service\b",
            r"\bshow[\s\-]cause\b",
            r"\baudi\s+alteram\s+partem\b",
            r"\b(?:art(?:icle)?\.?\s*212)\b",
            r"\bservice\s+tribunal(?:s)?\b",
            r"\b(?:natural\s+justice|opportunity\s+of\s+hearing|without\s+(?:a\s+)?hearing)\b",
        ],
        "min_signals": 3,
        "query_only": False,
        "mandatory_groups": [
            {
                "label": "Article 212 (Constitutional bar on courts regarding civil servant terms/conditions)",
                "any": [r"article\s*212", r"\bart\.?\s*212\b"],
            },
            {
                "label": "Service Tribunals Act 1973 s.4 or departmental appeal requirement",
                "any": [
                    r"service\s+tribunals?\s+act",
                    r"\bdepartmental\s+appeal\b",
                    r"\bsection\s*4\b[^.]{0,40}service\s+tribunals?",
                ],
            },
            {
                "label": "Article 199(1) requirement of no other adequate alternative remedy",
                "any": [
                    r"(?:adequate\s+(?:alternative\s+)?remedy|no\s+other\s+adequate\s+remedy|alternative\s+remedy)",
                ],
            },
            {
                "label": "Employee status and governing statutory service rules",
                "any": [
                    r"civil\s+servants?\s+act",
                    r"efficiency\s+and\s+discipline",
                    r"\be\s*&\s*d\b",
                    r"\bpeeda\b",
                    r"police\s+rules",
                    r"statutory\s+service\s+rules",
                    r"governing\s+service\s+rules",
                    r"master\s+and\s+servant",
                ],
            },
        ],
        "mandatory_keys": [
            "constitution:article:212",
            "service_tribunals_act:section:4",
            "constitution:article:199",
        ],
        "relevance": {
            "strong": [
                r"\bdismiss(?:al|ed|ing)?\b",
                r"\bremoval\s+from\s+service\b",
                r"\btermination\s+of\s+service\b",
                r"\bcompulsory\s+retirement\b",
            ],
        },
        "landmark_authorities": [
            "2024 SCMR 1155",
            "2023 SCMR 1135",
            "PLD 2025 SC 737",
        ],
        "extra_queries": [
            "Article 212 bar High Court service matters civil servant Article 199",
            "non-statutory rules master and servant writ maintainability",
            "dismissal without inquiry civil servant Service Tribunal",
            "show cause notice proposed penalty efficiency and discipline",
        ],
        "template_forbid": [
            r"pre-?arrest bail",
            r"bail strategy",
            r"custodial interrogation",
            r"physical remand",
        ],
        "template_headings": [
            "Question and short answer",
            "Issues",
            "Governing provisions (statute text as loaded)",
            "Maintainability and jurisdictional threshold (Article 212 vs Article 199)",
            "Authorities (relevant only)",
            "Analysis",
            "Remedies and departmental appeal route",
            "Research gaps",
        ],
    },
    "cheque_dishonour": {
        "detect": [
            r"cheque",
            r"dishonour",
            r"dishonored",
            r"bounced",
            r"489-?f\b",
        ],
        "mandatory_groups": [
            {
                "label": "Pakistan Penal Code s.489-F (dishonestly issuing a cheque)",
                "any": [r"section\s*489-?f\b", r"489-?f\b", r"s\.\s*489-?f\b"],
            },
        ],
        "mandatory_keys": [
            "ppc_1860:section:489F",
        ],
        "relevance": {
            "strong": [
                r"489-?f",
                r"dishonour\s+of\s+cheque",
                r"bounced\s+cheque",
                r"dishonestly\s+issuing\s+a\s+cheque",
                r"repayment\s+of\s+loan",
                r"fulfilment\s+of\s+an\s+obligation",
            ],
        },
        "landmark_authorities": [
            "2019 SCMR 1083",
            "PLD 2018 SC 645",
        ],
        "extra_queries": [
            "Section 489-F PPC dishonestly issuing cheque ingredients loan obligation Supreme Court",
            "cheque dishonour concurrent civil suit and criminal prosecution Section 489-F PPC",
            "quashment FIR Section 489-F PPC civil dispute repayment of loan",
        ],
        "template_forbid": [],
        "template_headings": [
            "Question and short answer",
            "Governing provisions",
            "Authorities",
            "Analysis",
            "Procedure and concurrent remedies",
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

    # 4. Constitutional / Service
    if any(k in comb for k in [
        "article 199", "article 184(3)", "writ petition", "quo warranto", "habeas corpus",
        "service tribunal", "civil servant", "service dismissal", "efficiency and discipline"
    ]):
        return "constitutional"

    return "civil"


def detect_topics(text: str, query_only_text: Optional[str] = None) -> List[str]:
    """
    Detects active legal verification topics in text.
    Topics flagged query_only (e.g. injunction) must be detected from the USER QUESTION ONLY,
    never from the memo body.
    """
    t_full = text.lower()
    t_query = query_only_text.lower() if query_only_text is not None else None
    active = []

    for name, spec in TOPICS_SPEC.items():
        is_query_only = spec.get("query_only", False)
        if is_query_only:
            target = t_query if t_query is not None else t_full
        else:
            target = t_full

        min_signals = spec.get("min_signals", 1)
        detect_patterns = spec.get("detect", [])

        if min_signals > 1:
            matched_count = sum(1 for p in detect_patterns if re.search(p, target, re.IGNORECASE))
            if matched_count >= min_signals:
                active.append(name)
        else:
            if any(re.search(p, target, re.IGNORECASE) for p in detect_patterns):
                active.append(name)

    return active


import functools

@functools.lru_cache(maxsize=2048)
def _compile_rule_pattern(p_str: str) -> re.Pattern:
    return re.compile(p_str, re.IGNORECASE)


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

    # Phase 4 Guardrail: Skip civil-only rules when matter_type is ambiguous, mixed, or criminal
    civil_only_rules = {
        "CRPC_561A_CIVIL", "LA_S28_IMMUNITY", "ART_184_3_PRIVATE",
        "O39_R1_FINAL_DECLARATORY", "O39_R2_FINAL_EXECUTION",
        "O39_R3_DISOBEDIENCE", "O39_R4_EXPARTE", "O39_EXCLUSIVE"
    }
    m_type = str(matter_type or "").lower().strip()
    is_criminal_or_ambiguous = (
        ("criminal" in m_type)
        or ("mixed" in m_type)
        or (m_type in ("", "none", "ambiguous", "mixed", "unknown", "general"))
    )
    if rule_id in civil_only_rules and is_criminal_or_ambiguous:
        return False

    # False-positive guard: SERVICE_CUSTODIAL_RESIDUE must NOT fire in criminal matters
    if rule_id == "SERVICE_CUSTODIAL_RESIDUE" and "criminal" in m_type:
        return False

    # False-positive guard: ART4_LIFE_LIBERTY must NOT fire if sentence mentions Art 9
    if rule_id == "ART4_LIFE_LIBERTY":
        if re.search(r"\b(?:art(?:icle)?\.?\s*9)\b", sentence, re.IGNORECASE):
            return False

    # Check all_of
    if not all(_compile_rule_pattern(p).search(sentence) for p in rule.get("all_of", [])):
        return False

    # Check any_of
    any_of = rule.get("any_of")
    if any_of and not any(_compile_rule_pattern(p).search(sentence) for p in any_of):
        return False

    # Check none_of
    none_of = rule.get("none_of")
    if none_of and any(_compile_rule_pattern(p).search(sentence) for p in none_of):
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
    Includes explicit negative directives for the verified doctrinal rules from Phase 1.1.
    """
    lines: List[str] = [
        "CRITICAL DOCTRINAL & VERIFICATION DIRECTIVES (Zero Exceptions):",
        "1. Never cite non-retrieved or unverified authorities from memory. Cite ONLY the supplied superior court precedents.",
        "2. Exact citation formatting required: 'PLD 2025 SC 502' or '2026 SCMR 190'.",
        "3. Verbatim statutory text: Quote bare-act text ONLY if provided in the STATUTORY FRAMEWORK block. If not provided (marked [NOT_RETRIEVED]), state that bare-act text was not retrieved rather than paraphrasing into quotes.",
        "4. Never invent statutory connections: Section 49 regarding effect of unregistered documents is in the Registration Act 1908, NEVER Transfer of Property Act.",
        "5. Avoid forum mismatch: Section 561-A Cr.P.C. is strictly criminal inherent jurisdiction; do NOT cite it for civil appeals, revisions, or injunctions.",
        "6. Limitation Act Articles (e.g. Art. 144, 149, 181) are periods of limitation in the First Schedule, NOT sources of court jurisdiction.",
        "7. Limitation Act Section 5 has NO express proviso excluding Government; Government has no preferential treatment on condonation.",
        "8. Injunctions Framework: Order XXXIX Rule 1 governs temporary injunction grounds; Rule 2 covers breach restraint. "
        "Rule 2A does NOT exist in Pakistan CPC; penalty for disobedience is Order XXXIX Rule 2(3) (detention/attachment). "
        "Order XXXIX Rule 1 does NOT create categories of final or declaratory injunctions (which fall under Specific Relief Act). "
        "Injunctions are not exclusive to Order XXXIX (s.94(c), s.151 CPC and SRA ss.52-57 also apply). "
        "Appeals lie under Order XLIII Rule 1(r) C.P.C.",
        "9. Adverse Possession Doctrine: Section 28 Limitation Act 1908 extinguishes right to property at the expiry of limitation; "
        "it is NOT a government-immunity doctrine. Distinguish Article 144 (private suits, 12 years) from Article 149 (Government suits, 60 years).",
        "10. Rent Jurisdiction: Under Punjab Rented Premises Act 2009 (PRPA), Section 34 bars the jurisdiction of civil courts under CPC. "
        "All eviction and tenancy disputes must be instituted before the Rent Tribunal under PRPA, NOT as civil suits under Section 9 CPC.",
        "11. Cheque Dishonour & Criminal Law: Under Pakistani law, dishonour of a cheque is prosecuted under Section 489-F PPC (inserted in 2002). "
        "Section 138 of the Negotiable Instruments Act is Indian law and does not exist in the Pakistan Code. "
        "The Limitation Act 1908 applies only to civil proceedings; there is no statutory limitation period for lodging an FIR or criminal complaint under Cr.P.C. 1898. "
        "Section 200 Cr.P.C. is for examining a complainant; cognizance is taken under Section 190 Cr.P.C. "
        "Framing of charge in Magisterial trials is under Section 242 Cr.P.C., not Section 228 (which governs alteration of charge).",
        "12. Tenancy, Rent & Concurrent Remedies: In Punjab, urban shop and residential building tenancies are governed by the Punjab Rented Premises Act 2009 (PRPA). "
        "The Punjab Tenancy Act 1887 applies only to agricultural land tenancies. "
        "Under Section 34 PRPA, civil courts are strictly barred. Civil eviction petitions lie before the Special Judge (Rent) / Rent Tribunal, while Section 489-F PPC proceedings are criminal and can proceed concurrently without legal impediment. "
        "Section 34 CPC relates to interest/cost of funds in money decrees, not concurrent remedies."
    ]

    if "criminal" not in matter_type:
        lines.append(
            "13. SECTION 6 HEADING: Title Section 6 strictly '### 6. ### PROCEDURAL REMEDY & APPELLATE STRATEGY'. "
            "Do NOT discuss pre-arrest bail, FIR, or criminal procedures in purely civil, property, or rent matters."
        )
    else:
        lines.append(
            "13. SECTION 6 HEADING: Title Section 6 '### 6. ### PRE-ARREST BAIL STRATEGY (OR PROCEDURAL REMEDY)'. "
            "Focus on statutory pre-arrest bail under Section 498 Cr.P.C. or concurrent procedural remedy for dual civil/criminal matters."
        )

    if abstain_topics:
        lines.append(
            f"12. UNRETRIEVED DOCTRINES: No controlling precedent retrieved for: {', '.join(abstain_topics)}. "
            "Explicitly disclose this limitation and withhold an unqualified conclusion."
        )

    return "\n".join(lines)
