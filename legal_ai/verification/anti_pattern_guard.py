"""
legal_ai/verification/anti_pattern_guard.py

Stage 5 Gate 2: Anti-Pattern Guardrail for Pakistani Legal AI Pipeline.
Enforces strict detection and prevention of hallucinated statutory citations, cross-statute collisions,
Indian-law imports, and structural impossibilities in Pakistani law reports:

1. Article vs Section Mismatches:
   - "Article X CrPC" -> CrPC 1898 has Sections, not Articles.
   - "Article X PPC" -> PPC 1860 has Sections, not Articles.
   - "Article X CPC" -> CPC 1908 has Sections and Orders/Rules, not Articles.
   - "Section X Constitution" -> Constitution 1973 has Articles, not Sections.
   - "Section X QSO" -> Qanun-e-Shahadat 1984 has Articles, not Sections.

2. Procedural & Substantive Cross-Statute Collisions:
   - "Section 497 PPC" / "Section 496 PPC" -> Bail is governed by CrPC 1898, not PPC 1860.
   - "Section 302 CrPC" / "Section 376 CrPC" -> Penal offenses are under PPC 1860, not CrPC 1898.
   - "Act 1882 for bail" / "TPA 1882 for bail" -> Transfer of Property Act 1882 has zero bail provisions.
   - "Section 138 NI Act" -> S. 138 is an Indian Negotiable Instruments Act provision; Pakistan repealed/omitted
     it, enacting Section 489-F PPC for dishonour of cheques.
   - "L[1973] Ineligible" or fake registry designations.

3. Guardian Intervention:
   - When anti-patterns are detected, provides deterministic correction mappings and
     injects standard disclosure notices rather than silently withholding valid analysis.
"""

import re
from typing import Dict, List, Any, Tuple, Optional


KNOWN_ANTI_PATTERNS = [
    {
        "id": "ARTICLE_CRPC",
        "pattern": r'\b(?:Articles?|Art\.?)\s*(\d+[A-Za-z]?)\s+(?:of\s+(?:the\s+)?)?(?:Code\s+of\s+Criminal\s+Procedure|Cr\.?P\.?C\.?)\b',
        "description": "CrPC 1898 consists of Sections, not Articles.",
        "replacement_template": "Section {num} of the Code of Criminal Procedure, 1898"
    },
    {
        "id": "ARTICLE_PPC",
        "pattern": r'\b(?:Articles?|Art\.?)\s*(\d+[A-Za-z]?(?:-[A-Za-z]+)?)\s+(?:of\s+(?:the\s+)?)?(?:Pakistan\s+Penal\s+Code|P\.?P\.?C\.?)\b',
        "description": "Pakistan Penal Code 1860 consists of Sections, not Articles.",
        "replacement_template": "Section {num} of the Pakistan Penal Code, 1860"
    },
    {
        "id": "ARTICLE_CPC",
        "pattern": r'\b(?:Articles?|Art\.?)\s*(\d+[A-Za-z]?)\s+(?:of\s+(?:the\s+)?)?(?:Code\s+of\s+Civil\s+Procedure|C\.?P\.?C\.?)\b',
        "description": "Code of Civil Procedure 1908 consists of Sections and Orders/Rules, not Articles.",
        "replacement_template": "Section {num} of the Code of Civil Procedure, 1908"
    },
    {
        "id": "SECTION_CONSTITUTION",
        "pattern": r'\b(?:Sections?|Sec\.?|s\.)\s*(\d+[A-Za-z]?)\s+(?:of\s+(?:the\s+)?)?(?:Constitution\s+(?:of\s+Pakistan)?(?:\s*,\s*1973)?)\b',
        "description": "The Constitution of Pakistan, 1973 consists of Articles, not Sections.",
        "replacement_template": "Article {num} of the Constitution of Pakistan, 1973"
    },
    {
        "id": "SECTION_QSO",
        "pattern": r'\b(?:Sections?|Sec\.?|s\.)\s*(\d+[A-Za-z]?)\s+(?:of\s+(?:the\s+)?)?(?:Qanun-e-Shahadat|QSO)(?:\s*,\s*1984)?\b',
        "description": "Qanun-e-Shahadat Order 1984 consists of Articles, not Sections.",
        "replacement_template": "Article {num} of the Qanun-e-Shahadat Order, 1984"
    },
    {
        "id": "BAIL_IN_PPC",
        "pattern": r'\b(?:Sections?|Sec\.?|s\.)\s*(496|497|498)\s+(?:of\s+(?:the\s+)?)?(?:Pakistan\s+Penal\s+Code|P\.?P\.?C\.?)\b',
        "description": "Bail is substantive procedure under CrPC 1898, not PPC 1860.",
        "replacement_template": "Section {num} of the Code of Criminal Procedure, 1898"
    },
    {
        "id": "PENAL_OFFENSE_IN_CRPC",
        "pattern": r'\b(?:Sections?|Sec\.?|s\.)\s*(302|376|380|392|406|409|420|468|471|489-F|489F)\s+(?:of\s+(?:the\s+)?)?(?:Code\s+of\s+Criminal\s+Procedure|Cr\.?P\.?C\.?)\b',
        "description": "Substantive criminal offenses are codified under Pakistan Penal Code 1860, not CrPC 1898.",
        "replacement_template": "Section {num} of the Pakistan Penal Code, 1860"
    },
    {
        "id": "BAIL_IN_TPA_1882",
        "pattern": r'\b(?:bail|pre-arrest\s+bail|post-arrest\s+bail)\b[^\.\n]*?\b(?:Transfer\s+of\s+Property\s+Act|TPA|Act\s+(?:IV\s+of\s+)?1882)\b',
        "description": "Transfer of Property Act, 1882 governs immoveable property conveyancing and has zero bail jurisdiction.",
        "replacement_template": "Code of Criminal Procedure, 1898 (Sections 496, 497, 498)"
    },
    {
        "id": "INDIAN_NI_ACT_138",
        "pattern": r'\b(?:Sections?|Sec\.?|s\.)\s*138\s+(?:of\s+(?:the\s+)?)?(?:Negotiable\s+Instruments\s+Act|NI\s+Act)(?:\s*,\s*1881)?\b',
        "description": "Section 138 of the NI Act 1881 does not exist in Pakistan; cheque dishonour is criminalized under Section 489-F PPC.",
        "replacement_template": "Section 489-F of the Pakistan Penal Code, 1860"
    },
    {
        "id": "L1973_INELIGIBLE",
        "pattern": r'\bL\[1973\]\s*Ineligible\b',
        "description": "Spurious law report registry annotation; invalid citation format in Pakistan.",
        "replacement_template": ""
    }
]


class AntiPatternGuard:
    """
    Stage 5 Gate 2: Validates text for known legal hallucination anti-patterns
    and applies deterministic Guardian Interventions.
    """

    def __init__(self, patterns: Optional[List[Dict[str, Any]]] = None):
        self.patterns = patterns or KNOWN_ANTI_PATTERNS

    def check_text(self, text: str) -> Dict[str, Any]:
        """
        Inspects text for anti-pattern violations.
        Returns:
            - is_clean: bool
            - violations: List[Dict[str, Any]]
            - guardian_interventions: List[Dict[str, str]]
            - sanitized_text: str (with corrected citations)
        """
        if not text:
            return {
                "is_clean": True,
                "violations": [],
                "guardian_interventions": [],
                "sanitized_text": text
            }

        violations = []
        guardian_interventions = []
        sanitized = text

        for p in self.patterns:
            matches = list(re.finditer(p["pattern"], sanitized, flags=re.IGNORECASE))
            for m in matches:
                matched_str = m.group(0)
                num = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
                
                replacement = p.get("replacement_template", "")
                if "{num}" in replacement and num:
                    replacement = replacement.format(num=num)
                
                violations.append({
                    "id": p["id"],
                    "matched_text": matched_str,
                    "description": p["description"],
                    "suggested_correction": replacement
                })

                if replacement:
                    guardian_interventions.append({
                        "original": matched_str,
                        "corrected": replacement,
                        "reason": p["description"]
                    })
                    # Replace in sanitized copy
                    sanitized = sanitized.replace(matched_str, replacement)

        is_clean = len(violations) == 0

        return {
            "is_clean": is_clean,
            "violations": violations,
            "guardian_interventions": guardian_interventions,
            "sanitized_text": sanitized
        }

    def format_guardian_notice(self, interventions: List[Dict[str, str]]) -> str:
        """
        Builds the standard Guardian Intervention disclosure box to prepend or append.
        """
        if not interventions:
            return ""

        lines = ["> [!NOTE] **Guardian Intervention Notice**"]
        lines.append("> The following statutory citations were automatically corrected against authentic Pakistani law registers:")
        for item in interventions:
            lines.append(f"> - Corrected `{item['original']}` to `{item['corrected']}` ({item['reason']}).")
        lines.append("")
        return "\n".join(lines)
