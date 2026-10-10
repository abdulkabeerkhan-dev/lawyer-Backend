"""
legal_ai/statutes/statute_injector.py

Statutory Provision Injection Module for Pakistani Legal AI Pipeline.
Ground-truth principle:
- Primary sources are strictly data/statute_tables/*.json and data/statute_versions/*.json.
- Verbatim bare-act text is injected into the prompt ONLY when loaded in primary stores.
- Missing text = [NOT_RETRIEVED: do not quote or describe], explicitly instructing the
  synthesis engine never to draft bare-act text from memory.
- Mandatory governing provisions are automatically included based on query doctrine.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

logger = logging.getLogger(__name__)

ENABLE_STATUTE_INJECTION: bool = os.environ.get("ENABLE_STATUTE_INJECTION", "true").lower() in ("true", "1", "yes")

ACT_PRETTY_NAMES: Dict[str, str] = {
    "PPC_1860": "Pakistan Penal Code, 1860",
    "CRPC_1898": "Code of Criminal Procedure, 1898",
    "CPC_1908": "Code of Civil Procedure, 1908",
    "LIMITATION_1908": "Limitation Act, 1908",
    "PRPA_2009": "Punjab Rented Premises Act, 2009",
    "SRPO_1979": "Sindh Rented Premises Ordinance, 1979",
    "CONST_1973": "Constitution of the Islamic Republic of Pakistan, 1973",
    "QSO_1984": "Qanun-e-Shahadat Order, 1984",
    "FIO_2001": "Financial Institutions (Recovery of Finances) Ordinance, 2001",
    "CNSA_1997": "Control of Narcotic Substances Act, 1997",
    "FAMILY_COURTS_1964": "Family Courts Act, 1964",
    "MFLO_1961": "Muslim Family Laws Ordinance, 1961",
    "DMMA_1939": "Dissolution of Muslim Marriages Act, 1939",
    "PREEMPTION_1991": "Punjab Pre-emption Act, 1991",
    "SRA_1877": "Specific Relief Act, 1877",
    "REGISTRATION_1908": "Registration Act, 1908",
    "TPA_1882": "Transfer of Property Act, 1882",
}


class StatuteInjector:
    """
    Loads verified bare-act provisions from disk and generates grounded statute injection blocks.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root:
            self.root = Path(workspace_root)
        else:
            self.root = Path(__file__).resolve().parent.parent.parent

        self.tables_dir = self.root / "data" / "statute_tables"
        self.versions_dir = self.root / "data" / "statute_versions"
        self._table_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._version_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._load_caches()

    def _load_caches(self) -> None:
        """Eagerly loads version maps for fast O(1) in-memory retrieval."""
        if self.versions_dir.exists():
            for vfile in self.versions_dir.glob("*_versions.json"):
                act_code = vfile.name.replace("_versions.json", "")
                try:
                    with open(vfile, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        by_cid: Dict[str, Dict[str, Any]] = {}
                        for item in data:
                            cid = item.get("canonical_id")
                            if cid:
                                by_cid[cid.upper()] = item
                        self._version_cache[act_code] = by_cid
                except Exception as e:
                    logger.warning(f"Error loading {vfile.name}: {e}")

        if self.tables_dir.exists():
            for tfile in self.tables_dir.glob("*.json"):
                act_code = tfile.stem
                try:
                    with open(tfile, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        self._table_cache[act_code] = data
                except Exception as e:
                    logger.warning(f"Error loading {tfile.name}: {e}")

    def resolve_canonical_id(self, prov_str: str) -> Tuple[str, str, str]:
        """
        Parses a provision string (e.g. 'Section 409 PPC', 'Order XXXIX Rule 1 CPC', 'Article 144 Limitation Act')
        into (act_code, canonical_id, display_name).
        """
        p_clean = prov_str.strip()
        p_low = p_clean.lower()

        # 1. Limitation Act (Sections & Articles)
        if "limitation" in p_low or "art 144" in p_low or "art 149" in p_low or "sec 28" in p_low:
            act_code = "LIMITATION_1908"
            m_art = re.search(r'\b(?:articles?|art\.?)\s*(\d+[a-z]?)\b', p_low)
            if m_art:
                art_num = m_art.group(1).upper()
                return act_code, f"{act_code}_ART_{art_num}", f"Article {art_num}, Limitation Act, 1908"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Limitation Act, 1908"

        # 2. CPC 1908 (Orders & Rules & Sections)
        if "cpc" in p_low or "order" in p_low or "o.xxxix" in p_low or "o.39" in p_low or "o.xliii" in p_low or "o.43" in p_low:
            act_code = "CPC_1908"
            m_ord = re.search(r'\b(?:orders?|ord\.?|o\.)\s*([ivxlcdm\d]+)(?:[\s,]+(?:rules?|r\.?)\s*(\d+[a-z]?(?:\([0-9a-z]+\))?))?\b', p_low)
            if m_ord:
                ord_val = m_ord.group(1).upper()
                r_val = m_ord.group(2)
                if r_val:
                    r_clean = re.sub(r'[\(\)]', '', r_val).upper()
                    return act_code, f"{act_code}_ORD_{ord_val}_R_{r_clean}", f"Order {ord_val} Rule {r_val}, Code of Civil Procedure, 1908"
                return act_code, f"{act_code}_ORD_{ord_val}", f"Order {ord_val}, Code of Civil Procedure, 1908"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Code of Civil Procedure, 1908"

        # 3. Punjab Rented Premises Act (PRPA)
        if "prpa" in p_low or "punjab rented" in p_low:
            act_code = "PRPA_2009"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Punjab Rented Premises Act, 2009"

        # 4. Sindh Rented Premises Ordinance (SRPO)
        if "srpo" in p_low or "sindh rented" in p_low:
            act_code = "SRPO_1979"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Sindh Rented Premises Ordinance, 1979"

        # 5. Pakistan Penal Code (PPC)
        if "ppc" in p_low or any(k in p_low for k in ["409", "420", "406", "489-f", "489f", "302", "376"]):
            act_code = "PPC_1860"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                sec_clean = sec_num.replace("-", "")
                return act_code, f"{act_code}_SEC_{sec_clean}", f"Section {sec_num}, Pakistan Penal Code, 1860"

        # 6. Code of Criminal Procedure (CrPC)
        if "crpc" in p_low or any(k in p_low for k in ["497", "498", "561-a", "561a", "154", "249-a"]):
            act_code = "CRPC_1898"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                sec_clean = sec_num.replace("-", "")
                return act_code, f"{act_code}_SEC_{sec_clean}", f"Section {sec_num}, Code of Criminal Procedure, 1898"

        # 7. Specific Relief Act (SRA)
        if "sra" in p_low or "specific relief" in p_low:
            act_code = "SRA_1877"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Specific Relief Act, 1877"

        # 8. Registration Act
        if "registration" in p_low:
            act_code = "REGISTRATION_1908"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Registration Act, 1908"

        # 9. Constitution 1973
        if "constitution" in p_low or "const" in p_low or "article 199" in p_low or "article 184" in p_low:
            act_code = "CONST_1973"
            m_art = re.search(r'\b(?:articles?|art\.?)\s*(\d+[a-z]?)\b', p_low)
            if m_art:
                art_num = m_art.group(1).upper()
                return act_code, f"{act_code}_ART_{art_num}", f"Article {art_num}, Constitution of Pakistan, 1973"

        # Default fallback
        m_num = re.search(r'\b(\d+[a-z]?)\b', p_clean)
        num_str = m_num.group(1).upper() if m_num else "UNKNOWN"
        return "UNKNOWN_ACT", f"UNKNOWN_SEC_{num_str}", p_clean

    def get_provision_record(self, act_code: str, canonical_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves provision record from versions cache or tables cache."""
        cid_upper = canonical_id.upper()
        # 1. Check version cache
        if act_code in self._version_cache:
            if cid_upper in self._version_cache[act_code]:
                return self._version_cache[act_code][cid_upper]

        # 2. Check table cache
        if act_code in self._table_cache:
            for item in self._table_cache[act_code]:
                if str(item.get("canonical_id", "")).upper() == cid_upper:
                    return item
        return None

    def inject_statutory_framework(
        self,
        query_plan: Any,
        query_text: str = ""
    ) -> Dict[str, Any]:
        """
        Builds the grounded statutory framework block for the synthesis prompt.
        """
        if not ENABLE_STATUTE_INJECTION:
            return {
                "statute_block": "",
                "injected_provisions": [],
                "provisions_with_text": [],
                "provisions_not_retrieved": [],
                "token_estimate": 0
            }

        # Gather target provisions
        target_provisions: List[str] = []
        if query_plan:
            if hasattr(query_plan, "provisions") and query_plan.provisions:
                target_provisions.extend([str(p) for p in query_plan.provisions])
            elif isinstance(query_plan, dict) and query_plan.get("provisions"):
                target_provisions.extend([str(p) for p in query_plan["provisions"]])

        q_comb = f"{query_text} {' '.join(target_provisions)}".lower()

        # Automatic mandatory inclusions based on doctrine
        if any(k in q_comb for k in ["adverse possession", "animus possidendi", "limitation act", "art 144", "art 149", "sec 28"]):
            mandatory_ap = [
                "Section 28 Limitation Act",
                "Article 144 Limitation Act",
                "Article 149 Limitation Act"
            ]
            for m in mandatory_ap:
                if not any(m.split()[1] in p for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["injunction", "order xxxix", "o.xxxix", "o.39"]):
            mandatory_inj = [
                "Order XXXIX Rule 1 CPC",
                "Order XXXIX Rule 2 CPC",
                "Order XLIII Rule 1(r) CPC",
                "Section 115 CPC"
            ]
            for m in mandatory_inj:
                if not any(m.split()[1] in p for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["rent", "tenant", "landlord", "eviction", "prpa"]):
            if "lahore" in q_comb or "punjab" in q_comb or "prpa" in q_comb:
                mandatory_rent = [
                    "Section 4 PRPA 2009",
                    "Section 15 PRPA 2009",
                    "Section 34 PRPA 2009"
                ]
                for m in mandatory_rent:
                    if not any(m.split()[1] in p for p in target_provisions):
                        target_provisions.append(m)

        if any(k in q_comb for k in ["cheque", "bounced", "dishonour", "dishonored", "489-f", "489f"]):
            mandatory_cheque = [
                "Section 489-F PPC"
            ]
            for m in mandatory_cheque:
                if not any("489" in p for p in target_provisions):
                    target_provisions.append(m)

        lines: List[str] = [
            "### STATUTORY FRAMEWORK & VERIFIED BARE-ACT PROVISIONS ON RECORD:\n",
            "CRITICAL INSTRUCTION: You may quote bare-act statutory language ONLY for provisions containing verbatim text below.",
            "If a provision displays '[NOT_RETRIEVED: do not quote or describe]', you MUST NOT fabricate, quote, or paraphrase statutory text from memory.\n"
        ]

        seen_cids: Set[str] = set()
        injected: List[str] = []
        with_text: List[str] = []
        not_retrieved: List[str] = []

        for prov_str in target_provisions:
            act_code, cid, display_name = self.resolve_canonical_id(prov_str)
            if cid in seen_cids or cid.startswith("UNKNOWN"):
                continue
            seen_cids.add(cid)
            injected.append(display_name)

            rec = self.get_provision_record(act_code, cid)
            raw_text = ""
            title = ""
            status = "in_force"
            if rec:
                raw_text = str(rec.get("text") or rec.get("statutory_text") or "").strip()
                title = str(rec.get("title") or rec.get("display_name") or "").strip()
                stat_dict = rec.get("status")
                if isinstance(stat_dict, dict):
                    status = stat_dict.get("punjab") or stat_dict.get("federal") or "in_force"
                elif isinstance(stat_dict, str):
                    status = stat_dict

            lines.append(f"--- PROVISION: {display_name} ---")
            lines.append(f"Status in Force: {status.replace('_', ' ').title()}")
            if title:
                lines.append(f"Subject / Title: {title}")

            if raw_text and len(raw_text) > 10:
                with_text.append(display_name)
                lines.append("Verbatim Bare-Act Text in Force:")
                lines.append(f'"{raw_text}"\n')
            else:
                not_retrieved.append(display_name)
                lines.append("Verbatim Bare-Act Text: [NOT_RETRIEVED: do not quote or describe]")
                lines.append("Note: Official bare-act text is not loaded in primary local stores. Do not draft, quote, or invent statutory language from memory.\n")

        full_block = "\n".join(lines)
        token_est = len(full_block) // 4

        return {
            "statute_block": full_block,
            "injected_provisions": injected,
            "provisions_with_text": with_text,
            "provisions_not_retrieved": not_retrieved,
            "token_estimate": token_est
        }


# Global singleton instance
_GLOBAL_INJECTOR: Optional[StatuteInjector] = None


def get_statute_injector() -> StatuteInjector:
    global _GLOBAL_INJECTOR
    if _GLOBAL_INJECTOR is None:
        _GLOBAL_INJECTOR = StatuteInjector()
    return _GLOBAL_INJECTOR


def inject_statutory_framework(query_plan: Any, query_text: str = "") -> Dict[str, Any]:
    """Convenience helper accessing the singleton injector."""
    return get_statute_injector().inject_statutory_framework(query_plan, query_text)
