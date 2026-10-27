"""
core/case_law_quotes.py

ORDER 2.0 — STEP 7: CASE-LAW QUOTES GUARDRAIL
Rule:
- A quotation from a judgment must appear byte-for-byte in that judgment's stored `full_text`.
- Sindh High Court (SHC) material stays link-and-cite only: system may print citation and link, NEVER a block quote.
- Local fixture interface: zero database/Supabase access.
"""

from typing import Dict, Any, Optional, Tuple, List
import re

# Local fixture judgments for offline verification
LOCAL_CASE_LAW_FIXTURES: Dict[str, Dict[str, Any]] = {
    "2023_SCMR_380": {
        "citation": "2023 SCMR 380",
        "court": "Supreme Court of Pakistan",
        "title": "Mst. Sakina Bibi v. Federation of Pakistan",
        "jurisdiction": "federal",
        "is_shc": False,
        "full_text": (
            "It is well settled that the jurisdiction of the Banking Court under the Financial Institutions "
            "(Recovery of Finances) Ordinance, 2001 is exclusive and overriding. A suit filed before the "
            "ordinary civil court in respect of matters falling within section 9 of the Ordinance is barred by law."
        )
    },
    "PLD_2022_SC_561": {
        "citation": "PLD 2022 SC 561",
        "court": "Supreme Court of Pakistan",
        "title": "Tariq Mahmood v. The State",
        "jurisdiction": "federal",
        "is_shc": False,
        "full_text": (
            "Grant of bail in offences not falling within the prohibitory clause of section 497 Cr.P.C. is a rule "
            "and refusal is an exception. Liberty of a citizen cannot be curtailed on mere vague allegations."
        )
    },
    "2021_CLD_1420": {
        "citation": "2021 CLD 1420",
        "court": "High Court of Sindh",
        "title": "ABC Bank Limited v. XYZ Spinning Mills",
        "jurisdiction": "sindh",
        "is_shc": True,
        "full_text": (
            "Under section 10 of the Financial Institutions Ordinance, 2001, leave to defend must disclose "
            "substantial questions of law and fact. Summary adjudication is mandated where no triable issue is raised."
        )
    },
    "2020_PCrLJ_154": {
        "citation": "2020 PCrLJ 154",
        "court": "High Court of Sindh",
        "title": "Muhammad Aslam v. The State",
        "jurisdiction": "sindh",
        "is_shc": True,
        "full_text": (
            "Dishonest issuance of cheque under section 489-F PPC requires strict proof of mens rea at the time of issuance."
        )
    }
}

class CaseLawQuoteVerifier:
    def __init__(self, fixtures: Optional[Dict[str, Dict[str, Any]]] = None):
        self.fixtures = fixtures if fixtures is not None else LOCAL_CASE_LAW_FIXTURES

    def verify_case_quote(
        self,
        citation_key: str,
        quoted_text: str,
        is_block_quote: bool = True
    ) -> Tuple[bool, str]:
        """
        Verifies a case-law quote against stored full_text.
        Returns (is_valid, reason).
        """
        norm_key = re.sub(r'[^A-Z0-9]', '_', citation_key.strip().upper())
        judgment = None
        for k, v in self.fixtures.items():
            if k.upper() == norm_key or v.get("citation", "").replace(" ", "_").upper() == norm_key:
                judgment = v
                break

        if not judgment:
            return False, f"JUDGMENT_NOT_IN_INDEX: Citation '{citation_key}' not found in case-law index."

        # SHC material rule: link-and-cite only, never a block quote
        is_shc = judgment.get("is_shc") or "SINDH" in judgment.get("court", "").upper()
        if is_shc and is_block_quote:
            return False, (
                f"SHC_BLOCK_QUOTE_DENIED: Material from High Court of Sindh ({judgment['citation']}) "
                "is restricted to link-and-cite only. Verbatim block quoting is blocked."
            )

        full_text = judgment.get("full_text", "")
        clean_quote = quoted_text.strip()
        if not clean_quote:
            return False, "EMPTY_QUOTE: Quoted text cannot be empty."

        # Byte-for-byte exact check
        if clean_quote not in full_text:
            return False, f"QUOTE_MISMATCH: Quoted text does not appear byte-for-byte in {judgment['citation']}."

        return True, "QUOTE_VERIFIED"
