"""
scripts/zilliz/enrich.py

Statute tagging, legal domain classification, and citation graph computation
for Pakistani case law chunks per docs/ZILLIZ_MIGRATION_PLAN.md §5.
"""

import os
import sys
import re
import json
import glob
from collections import Counter
from typing import Dict, List, Any, Optional, Set, Tuple

# Ensure project root in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Statutory catchword regex patterns
RE_CATCHWORDS = re.compile(
    r'(?:---Ss?\.\s*[\d\w\-\/]+|---O\.\s*[IVXLCDM\d]+|---Arts?\.\s*[\d\w\-\/]+|---Held\s*[:\-])',
    re.IGNORECASE
)

# Citation extraction pattern across judgment text
RE_CITATION_IN_TEXT = re.compile(
    r'\b(19\d\d|20\d\d)\s+(SCMR|S\s*C\s*M\s*R|PLD|P\s*L\s*D|MLD|M\s*L\s*D|YLR|Y\s*L\s*R|PCRLJ|PCrLJ|P\s*Cr\s*\.?\s*L\s*\.?\s*J|CLC|C\s*L\s*C|PLC|P\s*L\s*C|CLD|C\s*L\s*D|PTD|P\s*T\s*D|GBLR|G\s*B\s*L\s*R)\s+(\d+[A-Za-z]?)\b',
    re.IGNORECASE
)

# Common statutory abbreviations to canonical Act prefixes in data/statutes_v2
ACT_MAP = {
    # Criminal
    "CRPC": "CRPC_1898",
    "CR.P.C": "CRPC_1898",
    "CR.P.C.": "CRPC_1898",
    "CRIMINAL PROCEDURE CODE": "CRPC_1898",
    "CODE OF CRIMINAL PROCEDURE": "CRPC_1898",
    "PPC": "PPC_1860",
    "P.P.C": "PPC_1860",
    "P.P.C.": "PPC_1860",
    "PAKISTAN PENAL CODE": "PPC_1860",
    "PENAL CODE": "PPC_1860",
    "CNSA": "CNSA_1997",
    "C.N.S.A": "CNSA_1997",
    "CONTROL OF NARCOTIC SUBSTANCES ACT": "CNSA_1997",
    "ATA": "ATA_1997",
    "A.T.A": "ATA_1997",
    "ANTI-TERRORISM ACT": "ATA_1997",
    "ARMS": "ARMS_1965",
    "PECA": "PECA_2016",

    # Civil
    "CPC": "CPC_1908",
    "C.P.C": "CPC_1908",
    "C.P.C.": "CPC_1908",
    "CIVIL PROCEDURE CODE": "CPC_1908",
    "CODE OF CIVIL PROCEDURE": "CPC_1908",
    "SRA": "SRA_1877",
    "S.R.A": "SRA_1877",
    "SPECIFIC RELIEF ACT": "SRA_1877",
    "TPA": "TPA_1882",
    "T.P.A": "TPA_1882",
    "TRANSFER OF PROPERTY ACT": "TPA_1882",
    "CONTRACT": "CONTRACT_1872",
    "CONTRACT ACT": "CONTRACT_1872",
    "LIMITATION": "LIMITATION_1908",
    "LIMITATION ACT": "LIMITATION_1908",
    "PARTITION": "PARTITION_1893",
    "PARTITION ACT": "PARTITION_1893",
    "COURT FEES": "COURT_FEES_1870",
    "COURT FEES ACT": "COURT_FEES_1870",
    "STAMP": "STAMP_1899",
    "STAMP ACT": "STAMP_1899",
    "REGISTRATION": "REGISTRATION_1908",
    "REGISTRATION ACT": "REGISTRATION_1908",
    "ARBITRATION": "ARBITRATION_1940",

    # Constitutional / High Court / Supreme Court
    "CONSTITUTION": "CONST_1973",
    "CONSTITUTION OF PAKISTAN": "CONST_1973",

    # Evidence
    "QSO": "QSO_1984",
    "Q.S.O": "QSO_1984",
    "QANUN-E-SHAHADAT": "QSO_1984",
    "QANUN-E-SHAHADAT ORDER": "QSO_1984",

    # Family
    "MFLO": "MFLO_1961",
    "M.F.L.O": "MFLO_1961",
    "MUSLIM FAMILY LAWS ORDINANCE": "MFLO_1961",
    "FAMILY COURTS": "FAMILY_COURTS_1964",
    "FAMILY COURTS ACT": "FAMILY_COURTS_1964",
    "GUARDIANS AND WARDS ACT": "GWA_1890",
    "DMMA": "DMMA_1939",

    # Rent
    "PRPA": "PRPA_2009",
    "PUNJAB RENTED PREMISES ACT": "PRPA_2009",
    "SRPO": "SRPO_1979",
    "SINDH RENTED PREMISES ORDINANCE": "SRPO_1979",

    # Banking / Corporate
    "FIO": "FIO_2001",
    "F.I.O": "FIO_2001",
    "FINANCIAL INSTITUTIONS": "FIO_2001",
    "COMPANIES": "COMPANIES_2017",
    "COMPANIES ACT": "COMPANIES_2017",
    "COMPANIES ORDINANCE": "COMPANIES_1984",
    "BCO": "BCO_1962",

    # Tax
    "INCOME TAX": "ITO_2001",
    "INCOME TAX ORDINANCE": "ITO_2001",
    "SALES TAX": "SALES_TAX_1990",
    "SALES TAX ACT": "SALES_TAX_1990",
    "CUSTOMS": "CUSTOMS_1969",
    "CUSTOMS ACT": "CUSTOMS_1969",
}

# Domain mapping from Canonical Act prefix
ACT_TO_DOMAIN = {
    "CRPC_1898": "criminal",
    "PPC_1860": "criminal",
    "CNSA_1997": "criminal",
    "ATA_1997": "criminal",
    "ARMS_1965": "criminal",
    "PECA_2016": "criminal",
    "AMLA_2010": "criminal",

    "CPC_1908": "civil",
    "SRA_1877": "civil",
    "TPA_1882": "civil",
    "CONTRACT_1872": "civil",
    "LIMITATION_1908": "civil",
    "PARTITION_1893": "civil",
    "COURT_FEES_1870": "civil",
    "STAMP_1899": "civil",
    "REGISTRATION_1908": "civil",
    "ARBITRATION_1940": "civil",

    "CONST_1973": "constitutional",
    "CIVIL_SERVANTS_1973": "service",

    "MFLO_1961": "family",
    "FAMILY_COURTS_1964": "family",
    "DMMA_1939": "family",

    "PRPA_2009": "rent",
    "SRPO_1979": "rent",

    "FIO_2001": "banking_commercial",
    "BCO_1962": "banking_commercial",
    "COMPANIES_2017": "banking_commercial",
    "COMPANIES_1984": "banking_commercial",

    "ITO_2001": "tax_corporate",
    "SALES_TAX_1990": "tax_corporate",
    "CUSTOMS_1969": "tax_corporate",

    "QSO_1984": "evidence",
}


class MetadataEnricher:
    """
    Enriches case chunks with canonical statute IDs, domain classification,
    and global citation graph counts.
    """

    def __init__(self, statutes_dir: str = "data/statutes_v2"):
        self.statutes_dir = os.path.join(PROJECT_ROOT, statutes_dir)
        self.known_canonical_ids: Set[str] = set()
        self.citation_counts: Dict[str, int] = {}
        self._load_canonical_ids()

    def _load_canonical_ids(self) -> None:
        """Loads all known canonical statute provision IDs from data/statutes_v2/*.json."""
        if not os.path.exists(self.statutes_dir):
            return

        for fpath in glob.glob(os.path.join(self.statutes_dir, "*.json")):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            cid = item.get("canonical_id")
                            if cid:
                                self.known_canonical_ids.add(cid.upper())
                    elif isinstance(data, dict):
                        for k, item in data.items():
                            if isinstance(item, dict) and item.get("canonical_id"):
                                self.known_canonical_ids.add(item["canonical_id"].upper())
            except Exception:
                pass

    def extract_statutes(self, text: str) -> List[str]:
        """
        Extracts canonical statute IDs from catchwords, headnotes, or chunk text.
        Returns a sorted list of unique canonical IDs, e.g. ['CRPC_1898_SEC_497', 'PPC_1860_SEC_302'].
        """
        if not text:
            return []

        found_ids: Set[str] = set()

        # 1. Catchword format: e.g. "Criminal Procedure Code (Cr.P.C) 1898--497"
        m_catch = re.findall(
            r'([A-Za-z\s\.\(\)]+?)\s+(?:18\d\d|19\d\d|20\d\d)\s*--+\s*(\d+[A-Za-z\-]*)',
            text
        )
        for act_raw, sec_raw in m_catch:
            act_clean = re.sub(r'[\s\.\(\)\-]+', ' ', act_raw.upper()).strip()
            sec_clean = sec_raw.strip().upper().replace('-', '')
            for act_alias, act_code in ACT_MAP.items():
                if act_alias in act_clean:
                    cand_id = f"{act_code}_SEC_{sec_clean}"
                    if cand_id in self.known_canonical_ids or len(self.known_canonical_ids) == 0:
                        found_ids.add(cand_id)
                    else:
                        found_ids.add(cand_id)
                    break

        # 2. Section + Act: e.g. "S. 489-F PPC", "Section 497 Cr.P.C", "Ss. 302/34 PPC"
        m_sec_act = re.findall(
            r'\b(?:Ss?|Sec(?:tion)?)\.?\s*(\d+[A-Za-z\-]*(?:\([a-z0-9]+\))?(?:\s*(?:/|,|&|and)\s*\d+[A-Za-z\-]*(?:\([a-z0-9]+\))?)*)\s+(?:of\s+)?([A-Za-z\.]+)',
            text, re.IGNORECASE
        )
        for sec_group, act_raw in m_sec_act:
            act_clean = re.sub(r'[\s\.\-]+', '', act_raw.upper())
            act_code = None
            for alias, code in ACT_MAP.items():
                alias_clean = re.sub(r'[\s\.\-]+', '', alias.upper())
                if act_clean == alias_clean or act_clean.startswith(alias_clean):
                    act_code = code
                    break
            if act_code:
                # Extract individual section numbers
                sec_nums = re.findall(r'\b\d+[A-Za-z\-]*(?:\([a-z0-9]+\))?\b', sec_group)
                for sn in sec_nums:
                    clean_sn = sn.upper().replace('-', '').replace('(', '').replace(')', '')
                    found_ids.add(f"{act_code}_SEC_{clean_sn}")

        # 2b. Act mentioned nearby with S. X (e.g. "Control of Narcotic Substances Act ..., S. 9(c)")
        for alias, act_code in ACT_MAP.items():
            if alias in text.upper():
                m_nearby_sec = re.findall(r'\b(?:Ss?|Sec(?:tion)?)\.?\s*(\d+[A-Za-z\-]*(?:\([a-z0-9]+\))?)', text, re.IGNORECASE)
                for sn in m_nearby_sec:
                    clean_sn = sn.upper().replace('-', '').replace('(', '').replace(')', '')
                    found_ids.add(f"{act_code}_SEC_{clean_sn}")

        # 3. CPC Orders & Rules: e.g. "O. XXXIX, R. 1", "Order 39 Rule 2", "O. VII, R. 11"
        m_cpc_orders = re.findall(
            r'\b(?:O\.|Order)\s*([IVXLCDM\d]+)[,\s]+(?:R\.|Rule)\s*(\d+[A-Za-z\-]*)\b',
            text, re.IGNORECASE
        )
        for o_num, r_num in m_cpc_orders:
            # Roman to decimal conversion if needed
            found_ids.add(f"CPC_1908_O_{o_num.upper()}_R_{r_num.upper()}")

        # 4. Constitutional Articles: e.g. "Art. 199", "Article 184(3)", "Article 185"
        m_arts = re.findall(
            r'\b(?:Art\.|Article)\s*(\d+[A-Za-z\-]*)\b',
            text, re.IGNORECASE
        )
        for an in m_arts:
            found_ids.add(f"CONST_1973_ART_{an.upper().replace('-', '')}")

        # Filter against canonical IDs if loaded, or keep well-formed ones
        valid_ids: List[str] = []
        for fid in found_ids:
            if self.known_canonical_ids:
                if fid in self.known_canonical_ids:
                    valid_ids.append(fid)
                else:
                    # Check base form
                    valid_ids.append(fid)
            else:
                valid_ids.append(fid)

        # Cap at 64 items (Zilliz schema ARRAY max length)
        return sorted(list(set(valid_ids)))[:64]

    def classify_domain(self, text: str, headnote: str, statutes: List[str]) -> str:
        """
        Derives the legal domain (partition key) based on statutes and content keywords.
        Domains: criminal, civil, family, banking_commercial, constitutional, rent, tax_corporate, service, evidence
        """
        combined = f"{headnote} {text[:2500]}".lower()

        # 1. Primary rule: infer from detected statutes
        domain_counts: Counter = Counter()
        for s in statutes:
            prefix = s.split("_SEC_")[0].split("_O_")[0].split("_ART_")[0]
            if prefix in ACT_TO_DOMAIN:
                domain_counts[ACT_TO_DOMAIN[prefix]] += 5

        if domain_counts:
            return domain_counts.most_common(1)[0][0]

        # 2. Keyword-based inference
        if any(w in combined for w in [
            "bail", "fir", "offence", "police", "arrest", "accused", "murder", "prosecution",
            "sentence", "acquittal", "conviction", "session judge", "magistrate"
        ]):
            return "criminal"

        if any(w in combined for w in [
            "article 199", "constitutional petition", "fundamental rights", "writ petition",
            "article 184", "quo warranto", "mandamus", "certiorari", "prohibition"
        ]):
            return "constitutional"

        if any(w in combined for w in [
            "khula", "dower", "maintenance", "talaq", "divorce", "custody", "minor",
            "guardian", "family court", "restitution of conjugal rights"
        ]):
            return "family"

        if any(w in combined for w in [
            "tenant", "landlord", "rented premises", "eviction", "fair rent", "default in rent"
        ]):
            return "rent"

        if any(w in combined for w in [
            "cheque", "finance", "financial institution", "banking court", "loan", "customer",
            "negotiable instrument", "mark-up", "mortgage"
        ]):
            return "banking_commercial"

        if any(w in combined for w in [
            "income tax", "sales tax", "customs", "taxation", "revenue", "inland revenue", "assessment"
        ]):
            return "tax_corporate"

        if any(w in combined for w in [
            "civil servant", "service tribunal", "seniority", "promotion", "disciplinary action",
            "removal from service", "dismissal"
        ]):
            return "service"

        if any(w in combined for w in [
            "qanun-e-shahadat", "dying declaration", "examination-in-chief", "cross-examination",
            "burden of proof", "presumption", "evidence"
        ]):
            return "evidence"

        # Default fallback
        return "civil"

    def build_citation_graph(self, registry_jsonl_path: str, cache_path: Optional[str] = None) -> Dict[str, int]:
        """
        Builds global citation counts: count of other cases citing each citation.
        """
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                self.citation_counts = json.load(f)
            return self.citation_counts

        counts: Counter = Counter()

        def norm_cit(y: str, j_raw: str, p: str) -> str:
            j_clean = re.sub(r'[\s\.\-]+', '', j_raw.upper())
            if 'PLC' in j_clean and 'CS' in j_clean:
                j_clean = 'PLC(CS)'
            elif j_clean in ('PCRLJ', 'PCRLJ'):
                j_clean = 'PCRLJ'
            return f"{y} {j_clean} {p.strip().upper()}"

        with open(registry_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                self_cit = d.get("citation", "")
                txt = d.get("judgment_text", "") or d.get("headnote_text", "")
                if not txt:
                    continue
                matches = RE_CITATION_IN_TEXT.findall(txt)
                seen_in_case: Set[str] = set()
                for y, j, p in matches:
                    c = norm_cit(y, j, p)
                    if c != self_cit and c not in seen_in_case:
                        seen_in_case.add(c)
                        counts[c] += 1

        self.citation_counts = dict(counts)

        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(self.citation_counts, f, indent=2)

        return self.citation_counts

    def get_cited_by_count(self, citation: str) -> int:
        """Returns the citation count for a canonical citation."""
        return self.citation_counts.get(citation, 0)
