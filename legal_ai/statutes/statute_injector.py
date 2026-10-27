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
    "FIO_2001": "Financial Institutions (Recovery of Finances) Ordinance, 2001",
    "REGISTRATION_1908": "Registration Act, 1908",
    "TPA_1882": "Transfer of Property Act, 1882",
    "CONTRACT_1872": "Contract Act, 1872",
    "BCO_1962": "Banking Companies Ordinance, 1962",
    "STAMP_1899": "Stamp Act, 1899",
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

        self.unified_dir = self.root / "data" / "statutes_v2"
        self.tables_dir = self.root / "data" / "statute_tables"
        self.versions_dir = self.root / "data" / "statute_versions"
        self._unified_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._table_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._version_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._load_caches()

    def _load_caches(self) -> None:
        """Eagerly loads unified statutes and version maps for fast O(1) in-memory retrieval."""
        if self.unified_dir.exists():
            for ufile in self.unified_dir.glob("*.json"):
                act_code = ufile.stem
                try:
                    with open(ufile, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    records = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
                    by_cid: Dict[str, Dict[str, Any]] = {}
                    for item in records:
                        if isinstance(item, dict) and item.get("canonical_id"):
                            by_cid[str(item["canonical_id"]).upper()] = item
                    self._unified_cache[act_code] = by_cid
                except Exception as e:
                    logger.warning(f"Error loading {ufile.name}: {e}")

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

        # 0. Direct canonical ID format e.g. 'CPC_1908_ORD_XXXIX_R_2' or 'FIO_2001_SEC_22'
        m_cid = re.match(r'^([A-Z0-9]+(?:_[A-Z0-9]+)*)_(SEC|ORD|ART)_(.*)$', p_clean)
        if m_cid:
            act_code, typ, rest = m_cid.groups()
            pretty_act = ACT_PRETTY_NAMES.get(act_code, act_code)
            if typ == "SEC":
                return act_code, p_clean, f"Section {rest}, {pretty_act}"
            elif typ == "ART":
                return act_code, p_clean, f"Article {rest}, {pretty_act}"
            elif typ == "ORD":
                parts = rest.split("_R_")
                disp = f"Order {parts[0]} Rule {parts[1]}, {pretty_act}" if len(parts) == 2 else f"Order {rest}, {pretty_act}"
                return act_code, p_clean, disp
            return act_code, p_clean, f"{p_clean} ({pretty_act})"

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
                    r_clean = r_val.upper().replace("-", "")
                    if ord_val == "XXXIX":
                        if r_clean in ("2A", "2-A"):
                            return act_code, "CPC_1908_ORD_XXXIX_R_2A", "Order XXXIX Rule 2A, Code of Civil Procedure, 1908 (15-day limit on ex-parte injunction)"
                        if r_clean in ("2B", "2-B"):
                            return act_code, "CPC_1908_ORD_XXXIX_R_2B", "Order XXXIX Rule 2B, Code of Civil Procedure, 1908"
                        if r_clean in ("4A", "4-A"):
                            return act_code, "CPC_1908_ORD_XXXIX_R_4A", "Order XXXIX Rule 4A, Code of Civil Procedure, 1908"
                        if "2(3)" in r_clean or "2(1)" in r_clean or "2(2)" in r_clean or r_clean == "23":
                            return act_code, "CPC_1908_ORD_XXXIX_R_2", "Order XXXIX Rule 2(3), Code of Civil Procedure, 1908 (disobedience / breach of injunction)"

                    m_sub = re.match(r'(\d+[a-z]?)\s*\(([0-9a-z]+)\)', r_val, re.I)
                    if m_sub:
                        r_main = m_sub.group(1).upper()
                        r_sub = m_sub.group(2).upper()
                        cid_sub = f"{act_code}_ORD_{ord_val}_R_{r_main}_SR_{r_sub}"
                        if self.get_provision_record(act_code, cid_sub):
                            return act_code, cid_sub, f"Order {ord_val} Rule {r_val}, Code of Civil Procedure, 1908"
                        return act_code, f"{act_code}_ORD_{ord_val}_R_{r_main}", f"Order {ord_val} Rule {r_val}, Code of Civil Procedure, 1908"

                    r_clean_val = re.sub(r'[\(\)]', '', r_val).upper()
                    return act_code, f"{act_code}_ORD_{ord_val}_R_{r_clean_val}", f"Order {ord_val} Rule {r_val.upper()}, Code of Civil Procedure, 1908"
                return act_code, f"{act_code}_ORD_{ord_val}", f"Order {ord_val}, Code of Civil Procedure, 1908"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Code of Civil Procedure, 1908"

        # 3. FIO 2001
        if "fio" in p_low or "financial institutions" in p_low or "recovery of finances" in p_low or "banking court" in p_low:
            act_code = "FIO_2001"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Financial Institutions (Recovery of Finances) Ordinance, 2001"

        # 4. ITO 2001
        if "ito" in p_low or "income tax" in p_low:
            act_code = "ITO_2001"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Income Tax Ordinance, 2001"

        # 5. MFLO 1961
        if "mflo" in p_low or "muslim family laws" in p_low:
            act_code = "MFLO_1961"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Muslim Family Laws Ordinance, 1961"

        # 6. Family Courts Act 1964
        if "family courts" in p_low or "family court act" in p_low:
            act_code = "FAMILY_COURTS_1964"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Family Courts Act, 1964"

        # 7. Arbitration Act 1940
        if "arbitration" in p_low:
            act_code = "ARBITRATION_1940"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Arbitration Act, 1940"

        # 8. CNSA 1997
        if "cnsa" in p_low or "narcotic" in p_low:
            act_code = "CNSA_1997"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Control of Narcotic Substances Act, 1997"

        # 9. Contract Act 1872
        if "contract act" in p_low or ("contract" in p_low and "1872" in p_low):
            act_code = "CONTRACT_1872"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Contract Act, 1872"

        # 10. Transfer of Property Act 1882
        if "transfer of property" in p_low or "tpa" in p_low:
            act_code = "TPA_1882"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Transfer of Property Act, 1882"

        # 11. Companies Act 2017
        if "companies" in p_low:
            act_code = "COMPANIES_2017"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Companies Act, 2017"

        # 12. Punjab Pre-emption Act 1991
        if "preemption" in p_low or "pre-emption" in p_low:
            act_code = "PREEMPTION_1991"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Punjab Pre-emption Act, 1991"

        # 13. Punjab Rented Premises Act (PRPA)
        if "prpa" in p_low or "punjab rented" in p_low:
            act_code = "PRPA_2009"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Punjab Rented Premises Act, 2009"

        # 14. Sindh Rented Premises Ordinance (SRPO)
        if "srpo" in p_low or "sindh rented" in p_low:
            act_code = "SRPO_1979"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Sindh Rented Premises Ordinance, 1979"

        # 15. Pakistan Penal Code (PPC)
        if "ppc" in p_low or any(k in p_low for k in ["409", "420", "406", "489-f", "489f", "302", "376"]):
            act_code = "PPC_1860"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                sec_clean = sec_num.replace("-", "")
                sec_disp = f"{sec_num[:-1]}-{sec_num[-1]}" if re.match(r'^\d+[A-Z]$', sec_num) else sec_num
                return act_code, f"{act_code}_SEC_{sec_clean}", f"Section {sec_disp}, Pakistan Penal Code, 1860"

        # 16. Code of Criminal Procedure (CrPC)
        if "crpc" in p_low or "criminal procedure" in p_low or any(k in p_low for k in ["496", "497", "498", "561-a", "561a", "154", "249-a", "249a", "265-k", "265k", "22-a", "22a", "54", "61"]):
            act_code = "CRPC_1898"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                sec_clean = sec_num.replace("-", "")
                return act_code, f"{act_code}_SEC_{sec_clean}", f"Section {sec_num}, Code of Criminal Procedure, 1898"

        # 17. Specific Relief Act (SRA)
        if "sra" in p_low or "specific relief" in p_low:
            act_code = "SRA_1877"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Specific Relief Act, 1877"

        # 18. Registration Act
        if "registration" in p_low:
            act_code = "REGISTRATION_1908"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Registration Act, 1908"

        # 19. Constitution 1973
        if "constitution" in p_low or "const" in p_low or "article 199" in p_low or "article 184" in p_low:
            act_code = "CONST_1973"
            m_art = re.search(r'\b(?:articles?|art\.?)\s*(\d+[a-z]?)\b', p_low)
            if m_art:
                art_num = m_art.group(1).upper()
                return act_code, f"{act_code}_ART_{art_num}", f"Article {art_num}, Constitution of Pakistan, 1973"

        # 20. Negotiable Instruments Act 1881
        if "negotiable" in p_low or "ni act" in p_low:
            act_code = "NI_ACT_1881"
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                return act_code, f"{act_code}_SEC_{sec_num}", f"Section {sec_num}, Negotiable Instruments Act, 1881"

        # Default fallback
        m_num = re.search(r'\b(\d+[a-z]?)\b', p_clean)
        num_str = m_num.group(1).upper() if m_num else "UNKNOWN"
        return "UNKNOWN_ACT", f"UNKNOWN_SEC_{num_str}", p_clean

    def get_provision_record(self, act_code: str, canonical_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves provision record from unified cache, versions cache, or tables cache."""
        cid_upper = canonical_id.upper()
        # 0. Check primary authoritative unified cache
        if act_code in self._unified_cache:
            if cid_upper in self._unified_cache[act_code]:
                return self._unified_cache[act_code][cid_upper]
            if "_SR_" in cid_upper:
                parent_cid = cid_upper.split("_SR_")[0]
                if parent_cid in self._unified_cache[act_code]:
                    return self._unified_cache[act_code][parent_cid]

        # 1. Check version cache
        if act_code in self._version_cache:
            if cid_upper in self._version_cache[act_code]:
                return self._version_cache[act_code][cid_upper]
            if "_SR_" in cid_upper:
                parent_cid = cid_upper.split("_SR_")[0]
                if parent_cid in self._version_cache[act_code]:
                    return self._version_cache[act_code][parent_cid]

        # 2. Check table cache
        if act_code in self._table_cache:
            for item in self._table_cache[act_code]:
                if str(item.get("canonical_id", "")).upper() == cid_upper:
                    return item
            if "_SR_" in cid_upper:
                parent_cid = cid_upper.split("_SR_")[0]
                for item in self._table_cache[act_code]:
                    if str(item.get("canonical_id", "")).upper() == parent_cid:
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

        from legal_ai.statutes.statute_store import get_statute_store
        store = get_statute_store()

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

        if any(k in q_comb for k in ["injunction", "order xxxix", "o.xxxix", "o.39", "stay order", "disobedience", "breach of injunction"]):
            mandatory_inj = [
                "Order XXXIX Rule 1 CPC",
                "Order XXXIX Rule 2 CPC",
                "Order XXXIX Rule 2(3) CPC",
                "Order XLIII Rule 1(r) CPC",
                "Section 115 CPC"
            ]
            if any(k in q_comb for k in ["rule 2a", "2a", "15 days", "fifteen days", "ex parte", "ex-parte"]):
                mandatory_inj.append("Order XXXIX Rule 2A CPC")
            for m in mandatory_inj:
                m_short = m.split()[-2] + " " + m.split()[-1] if len(m.split()) >= 3 else m
                if not any(m_short.lower() in p.lower() for p in target_provisions):
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

        if any(k in q_comb for k in ["cheque", "bounced", "dishonour", "dishonored", "489-f", "489f", "138"]):
            mandatory_cheque = [
                "Section 489-F PPC",
                "Order XXXVII Rule 2 CPC",
                "Section 118 Negotiable Instruments Act, 1881"
            ]
            for m in mandatory_cheque:
                if not any(m.split()[1].lower() in p.lower() for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["cheating", "fraud", "420"]):
            mandatory_fraud = [
                "Section 420 PPC",
                "Section 497 CrPC"
            ]
            for m in mandatory_fraud:
                if not any(m.split()[1].lower() in p.lower() for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["breach of trust", "406", "criminal breach"]):
            mandatory_cbt = [
                "Section 405 PPC",
                "Section 406 PPC",
                "Section 497 CrPC",
                "Section 498 CrPC"
            ]
            for m in mandatory_cbt:
                if not any(m.split()[1].lower() in p.lower() for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["bail", "bailable", "non-bailable", "non bailable", "pre-arrest bail", "post-arrest bail", "arrest without"]):
            mandatory_bail = [
                "Section 496 CrPC",
                "Section 497 CrPC",
                "Section 498 CrPC"
            ]
            if any(k in q_comb for k in ["without warrant", "without a warrant", "arrest without", "arrested without"]):
                mandatory_bail.extend(["Section 54 CrPC", "Section 61 CrPC"])
            for m in mandatory_bail:
                m_num = m.split()[1].lower()
                if not any(m_num in p.lower() for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["specific performance", "specific relief", "agreement to sell"]):
            mandatory_sra = [
                "Section 12 Specific Relief Act",
                "Section 22 Specific Relief Act",
                "Section 24 Specific Relief Act",
                "Section 27 Specific Relief Act",
                "Article 113 Limitation Act"
            ]
            for m in mandatory_sra:
                if not any(m.split()[1].lower() in p.lower() for p in target_provisions):
                    target_provisions.append(m)

        if any(k in q_comb for k in ["promissory note", "promissory", "negotiable instrument"]) and any(k in q_comb for k in ["limitation", "period", "suit"]):
            mandatory_pn = [
                "Article 73 Limitation Act",
                "Article 80 Limitation Act",
                "Article 64A Limitation Act",
                "Section 4 Negotiable Instruments Act, 1881",
                "Section 19 Negotiable Instruments Act, 1881"
            ]
            for m in mandatory_pn:
                if not any(m.split()[1].lower() in p.lower() for p in target_provisions):
                    target_provisions.append(m)

        lines: List[str] = [
            "### STATUTORY FRAMEWORK & VERIFIED BARE-ACT PROVISIONS ON RECORD:\n",
            "CRITICAL INSTRUCTION: You may quote bare-act statutory language ONLY for provisions containing verbatim text below.",
            "If a provision displays '[Statutory text not found in verified database]', you MUST NOT fabricate, quote, or paraphrase statutory text from memory.",
            "You MUST output '[Statutory text not found in verified database]' under Section 2 instead.\n"
        ]

        # Check for premise corrections from query plan
        premise_corrections = getattr(query_plan, "premise_corrections", []) if query_plan else []
        if premise_corrections:
            lines.append("### MANDATORY QUERY PREMISE CORRECTIONS:")
            for pc in premise_corrections:
                lines.append(f"- Query Premise Correction: {pc.get('mandatory_opening_thesis')}")
                if pc.get('explanation'):
                    lines.append(f"  Explanation: {pc.get('explanation')}")
                if pc.get('schedule_ii'):
                    sch = pc['schedule_ii']
                    lines.append(f"  Cr.P.C. Schedule II: Cognizable={sch.get('cognizable')}, Bail={sch.get('bailable_status')}, Punishment={sch.get('punishment')}")
            lines.append("CRITICAL: You MUST open the Executive Summary / Legal Issue section with this explicit premise correction.\n")

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
            tier = ""
            in_force = True
            if rec:
                raw_text = str(rec.get("text") or rec.get("statutory_text") or "").strip()
                title = str(rec.get("title") or rec.get("display_name") or "").strip()
                tier = str(rec.get("tier") or "").lower().strip()
                in_force = rec.get("in_force", True)
                stat_dict = rec.get("status")
                if isinstance(stat_dict, dict):
                    status = stat_dict.get("punjab") or stat_dict.get("federal") or "in_force"
                elif isinstance(stat_dict, str):
                    status = stat_dict

            lines.append(f"--- PROVISION: {display_name} ---")
            lines.append(f"Status in Force: {status.replace('_', ' ').title()}")
            if title:
                lines.append(f"Subject / Title: {title}")

            # Check in_force status gating (Item 6)
            if in_force is False:
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL REFUSAL: {display_name} IS NOT IN FORCE (REPEALED / OMITTED).")
                lines.append("The engine strictly refuses to quote repealed or omitted provisions as operative law.")
                lines.append("You MUST open your response with:")
                lines.append(f"> [!CAUTION]")
                lines.append(f"> **PROVISION NOT IN FORCE**: {display_name} is omitted or repealed from the statute book and cannot be quoted or applied as operative law.")
                lines.append("********************************************************************************")
                raw_text = "[REPEALED / OMITTED - NOT IN FORCE: The engine refuses to quote this provision as operative law]"

            # Check unsourced tier / quoting blocked gating (Order 1.4 Item 1)
            elif tier == "unsourced" or in_force == "unknown" or (rec and rec.get("quoting_allowed") is False):
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL REFUSAL: {display_name} HAS NO SOURCED OFFICIAL PDF IN REPOSITORY (TIER: UNSOURCED).")
                lines.append("The engine strictly blocks quoting or applying unverified/unsourced statutory text.")
                lines.append("You MUST output '[Statutory text unverified / unsourced: quoting strictly blocked]' under Section 2 instead.")
                lines.append("********************************************************************************")
                raw_text = ""

            # Check disputed tier warning gating (Item 8 & Item 10)
            elif tier == "disputed":
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL WARNING: {display_name} IS TAGGED AS DISPUTED IN OFFICIAL STORE.")
                lines.append("Reason: Text not yet checked against page images by a human.")
                lines.append("Do NOT print any '> [!' banner yourself. System banners are attached automatically after verification.")
                lines.append("Human advocate verification against official Gazette page images is required before relying on this text.")
                lines.append("********************************************************************************")

            # Schedule II injection for PPC offences
            if act_code == "PPC_1860":
                m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', display_name, re.I)
                sec_token = m_sec.group(1).upper() if m_sec else ""
                sched = store.get_schedule_ii(sec_token)
                if sched:
                    lines.append("Cr.P.C. Schedule II Classification:")
                    lines.append(f"- Offence: {sched.get('offence')}")
                    lines.append(f"- Police Powers: {sched.get('police_arrest')} ({'Cognizable' if sched.get('cognizable') else 'Non-cognizable'})")
                    if sched.get('bailable'):
                        bail_expl = "Bailable as of right under Section 496 Cr.P.C."
                    elif sched.get('max_imprisonment_years', 0) >= 10:
                        bail_expl = "Non-bailable (within prohibitory clause of Section 497 Cr.P.C.: bail may not be granted except under statutory provisos)"
                    else:
                        bail_expl = "Non-bailable (falls outside prohibitory clause of Section 497 Cr.P.C.: grant of bail is rule and refusal exception per Hakeem v. State 2026 SCMR 792 and Tariq Bashir PLD 1995 SC 34)"
                    lines.append(f"- Bailable Status: {sched.get('bailable_status')} [Cr.P.C. Schedule II Column 5: {sched.get('schedule_ii_column_5', sched.get('bailable_status'))}] ({bail_expl})")
                    lines.append(f"- Compoundable: {sched.get('compoundable')}")
                    lines.append(f"- Punishment: {sched.get('punishment')}")
                    lines.append(f"- Trial Forum: {sched.get('triable_by')}")

            if raw_text and len(raw_text) > 10:
                with_text.append(display_name)
                lines.append("Verbatim Bare-Act Text in Force:")
                lines.append(f'"{raw_text}"\n')
            else:
                not_retrieved.append(display_name)
                lines.append("Verbatim Bare-Act Text: [Statutory text not found in verified database]")
                lines.append("Note: Official bare-act text is not loaded in primary local stores. You must output '[Statutory text not found in verified database]' under Section 2 instead of drafting, quoting, or inventing statutory language from memory.\n")

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
