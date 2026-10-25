"""
legal_ai/statutes/statute_store.py

Structured section-addressable bare act index and verification store for Pakistan.
Single source of truth for:
1. Statute existence and provision bounds (positive existence, confirmed absence, unverified).
2. Cr.P.C. Schedule II lookup (cognizable, bailable, punishment, triable_by).
3. Query statute extraction and premise verification.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LookupResult(BaseModel):
    status: str = Field(..., description="'EXISTS', 'CONFIRMED_ABSENT', or 'UNVERIFIED'")
    exists: bool = Field(default=False)
    confirmed_absent: bool = Field(default=False)
    act_code: Optional[str] = None
    act_name: Optional[str] = None
    canonical_id: Optional[str] = None
    display_name: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    source: Optional[str] = None
    is_foreign_statute: bool = False
    schedule_ii: Optional[Dict[str, Any]] = None
    pakistani_equivalent: Optional[str] = None
    explanation: Optional[str] = None


# Canonical Pakistani statute aliases
PAKISTAN_STATUTE_ALIASES: Dict[str, str] = {
    "ppc": "PPC_1860",
    "pakistan penal code": "PPC_1860",
    "penal code": "PPC_1860",
    "crpc": "CRPC_1898",
    "code of criminal procedure": "CRPC_1898",
    "cpc": "CPC_1908",
    "code of civil procedure": "CPC_1908",
    "ni act": "NI_ACT_1881",
    "negotiable instruments": "NI_ACT_1881",
    "negotiable instruments act": "NI_ACT_1881",
    "limitation act": "LIMITATION_1908",
    "limitation": "LIMITATION_1908",
    "prpa": "PRPA_2009",
    "punjab rented premises act": "PRPA_2009",
    "srpo": "SRPO_1979",
    "sindh rented premises ordinance": "SRPO_1979",
    "constitution": "CONST_1973",
    "constitution of pakistan": "CONST_1973",
    "qso": "QSO_1984",
    "qanun-e-shahadat": "QSO_1984",
    "qanun-e-shahadat order": "QSO_1984",
    "mflo": "MFLO_1961",
    "muslim family laws ordinance": "MFLO_1961",
    "dmma": "DMMA_1939",
    "dissolution of muslim marriages act": "DMMA_1939",
    "family courts act": "FAMILY_COURTS_1964",
    "fio": "FIO_2001",
    "financial institutions ordinance": "FIO_2001",
    "cnsa": "CNSA_1997",
    "control of narcotic substances act": "CNSA_1997",
    "sra": "SRA_1877",
    "specific relief act": "SRA_1877",
    "contract act": "CONTRACT_1872",
}

# Known foreign/un-enacted statute names in Pakistan
FOREIGN_STATUTE_PATTERNS: Dict[str, Dict[str, str]] = {
    "ipc": {
        "name": "Indian Penal Code",
        "pakistani_equivalent": "Pakistan Penal Code, 1860 (PPC)",
        "explanation": "The Indian Penal Code (IPC) does not apply in Pakistan; the governing criminal code is the Pakistan Penal Code, 1860 (PPC)."
    },
    "indian penal code": {
        "name": "Indian Penal Code",
        "pakistani_equivalent": "Pakistan Penal Code, 1860 (PPC)",
        "explanation": "The Indian Penal Code (IPC) does not apply in Pakistan; the governing criminal code is the Pakistan Penal Code, 1860 (PPC)."
    },
    "indian evidence act": {
        "name": "Indian Evidence Act",
        "pakistani_equivalent": "Qanun-e-Shahadat Order, 1984 (QSO)",
        "explanation": "The Indian Evidence Act does not apply in Pakistan; the law of evidence is governed by the Qanun-e-Shahadat Order, 1984 (QSO)."
    },
    "indian crpc": {
        "name": "Code of Criminal Procedure (India)",
        "pakistani_equivalent": "Code of Criminal Procedure, 1898 (Cr.P.C.)",
        "explanation": "Indian criminal procedure does not apply in Pakistan; procedure is governed by the Code of Criminal Procedure, 1898 (Cr.P.C.)."
    }
}


class StatuteStore:
    """
    Section-addressable in-memory bare act index.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root:
            self.root = Path(workspace_root)
        else:
            self.root = Path(__file__).resolve().parent.parent.parent

        self.tables_dir = self.root / "data" / "statute_tables"
        self.versions_dir = self.root / "data" / "statute_versions"

        # In-memory indexes:
        # act_code -> list of records or dict of canonical_id -> record
        self._provisions_by_act: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Schedule II records: section_str -> dict
        self._schedule_ii: Dict[str, Dict[str, Any]] = {}
        # Version texts: canonical_id -> text
        self._version_texts: Dict[str, str] = {}

        self._load_all()

    def _load_all(self) -> None:
        """Loads tables, versions, and Schedule II into memory."""
        # 1. Load version texts
        if self.versions_dir.exists():
            for vfile in self.versions_dir.glob("*_versions.json"):
                try:
                    with open(vfile, "r", encoding="utf-8") as f:
                        vlist = json.load(f)
                    if isinstance(vlist, list):
                        for item in vlist:
                            cid = item.get("canonical_id")
                            txt = item.get("text")
                            if cid and txt:
                                self._version_texts[cid.upper()] = txt
                except Exception as e:
                    logger.warning(f"Error loading {vfile.name}: {e}")

        # 2. Load statute tables
        if self.tables_dir.exists():
            for tfile in self.tables_dir.glob("*.json"):
                if tfile.name == "CRPC_SCHEDULE_II.json":
                    continue
                act_code = tfile.stem
                try:
                    with open(tfile, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        by_cid: Dict[str, Dict[str, Any]] = {}
                        for item in data:
                            cid = item.get("canonical_id")
                            if cid:
                                by_cid[cid.upper()] = item
                        self._provisions_by_act[act_code] = by_cid
                except Exception as e:
                    logger.warning(f"Error loading table {tfile.name}: {e}")

        # 3. Load Cr.P.C. Schedule II
        sched_file = self.tables_dir / "CRPC_SCHEDULE_II.json"
        if sched_file.exists():
            try:
                with open(sched_file, "r", encoding="utf-8") as f:
                    self._schedule_ii = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading Schedule II: {e}")

    def is_statute_indexed(self, act_code: str) -> bool:
        """Returns True if the statute is actively loaded in the index."""
        return act_code in self._provisions_by_act

    def get_schedule_ii(self, section: str) -> Optional[Dict[str, Any]]:
        """Looks up Cr.P.C. Schedule II classification for a PPC section."""
        sec_clean = section.strip().upper().replace("SECTION", "").replace("SEC", "").replace("S.", "").strip()
        sec_clean = sec_clean.replace(" ", "")
        if sec_clean in self._schedule_ii:
            return self._schedule_ii[sec_clean]
        sec_dash = sec_clean.replace("-", "")
        if sec_dash in self._schedule_ii:
            return self._schedule_ii[sec_dash]
        return None

    def normalize_statute_name(self, statute_str: str) -> Tuple[Optional[str], bool, Optional[Dict[str, str]]]:
        """
        Normalizes statute string to (act_code, is_foreign, foreign_meta).
        """
        s_low = statute_str.strip().lower()

        # Check foreign statute patterns
        for fkey, fmeta in FOREIGN_STATUTE_PATTERNS.items():
            if fkey in s_low or s_low == fkey:
                return None, True, fmeta

        # Check Pakistani statute aliases
        for akey, acode in PAKISTAN_STATUTE_ALIASES.items():
            if akey in s_low or s_low == akey:
                return acode, False, None

        # Check raw code
        s_upper = statute_str.strip().upper()
        if s_upper in self._provisions_by_act:
            return s_upper, False, None

        return None, False, None

    def lookup(self, statute: str, provision: str) -> LookupResult:
        """
        Section-addressable lookup.
        Outcomes:
        - EXISTS: provision positively confirmed in Pakistani statute index.
        - CONFIRMED_ABSENT: statute is indexed, but provision is confirmed to NOT exist (e.g. s.138 NI Act),
          or statute itself is confirmed foreign (e.g. Indian Penal Code).
        - UNVERIFIED: statute or provision cannot be confirmed either way in the database.
        """
        stat_clean = statute.strip()
        prov_clean = provision.strip()

        act_code, is_foreign, foreign_meta = self.normalize_statute_name(stat_clean)

        # 1. Handle Foreign Statute
        if is_foreign and foreign_meta:
            m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', prov_clean, re.I)
            sec_num = m_sec.group(1).upper() if m_sec else prov_clean
            # Check if there is a Pakistani PPC equivalent for sentencing/Schedule II
            ppc_sched = self.get_schedule_ii(sec_num)
            ppc_rec = None
            if self.is_statute_indexed("PPC_1860"):
                sec_cid = f"PPC_1860_SEC_{sec_num.replace('-', '')}"
                ppc_rec = self._provisions_by_act["PPC_1860"].get(sec_cid)

            return LookupResult(
                status="CONFIRMED_ABSENT",
                exists=False,
                confirmed_absent=True,
                act_code="FOREIGN_IPC",
                act_name=foreign_meta["name"],
                display_name=f"Section {sec_num} ({foreign_meta['name']})",
                is_foreign_statute=True,
                pakistani_equivalent=f"Section {sec_num} PPC (Pakistan Penal Code, 1860)",
                explanation=foreign_meta["explanation"],
                schedule_ii=ppc_sched,
                source="Foreign statute (un-enacted in Pakistan)"
            )

        # 2. Handle Known Pakistani Statute
        if act_code and self.is_statute_indexed(act_code):
            provisions = self._provisions_by_act[act_code]

            # Specific rule for Negotiable Instruments Act 1881 (cheque dishonour context):
            if act_code == "NI_ACT_1881":
                m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?)\b', prov_clean, re.I)
                num = int(m_sec.group(1)) if m_sec and m_sec.group(1).isdigit() else None
                if num == 138:
                    # In Pakistan Code Act XXVI of 1881, Section 138 is 'Power to appoint notaries public'.
                    # The criminal offence of cheque dishonour (Indian Act 66 of 1988 s.138) does not exist in Pakistan's NI Act.
                    return LookupResult(
                        status="CONFIRMED_ABSENT",
                        exists=False,
                        confirmed_absent=True,
                        act_code="NI_ACT_1881",
                        act_name="Negotiable Instruments Act, 1881",
                        display_name="Section 138 (Cheque Dishonour Offence), Negotiable Instruments Act, 1881",
                        is_foreign_statute=True,
                        pakistani_equivalent="Section 489-F PPC (Pakistan Penal Code, 1860) and Order XXXVII CPC",
                        explanation=(
                            "The criminal offence of dishonouring a cheque under Section 138 of the Negotiable Instruments Act "
                            "is an Indian statutory provision (inserted in India by Act 66 of 1988) and does not exist in the "
                            "Pakistan Negotiable Instruments Act, 1881 (where Section 138 merely provides for the appointment "
                            "of Notaries Public). In Pakistan, criminal prosecution for dishonour of a cheque is governed exclusively "
                            "by Section 489-F of the Pakistan Penal Code, 1860, and summary civil recovery by Order XXXVII CPC."
                        ),
                        source="Pakistan Code (pakistancode.gov.pk), Act No. XXVI of 1881; https://pakistancode.gov.pk/pdffiles/administrator2bbb145adb573172ec68151f4e70dfb5.pdf"
                    )
                elif num and num > 139:
                    return LookupResult(
                        status="CONFIRMED_ABSENT",
                        exists=False,
                        confirmed_absent=True,
                        act_code="NI_ACT_1881",
                        act_name="Negotiable Instruments Act, 1881",
                        display_name=f"Section {num}, Negotiable Instruments Act, 1881",
                        is_foreign_statute=True,
                        pakistani_equivalent="Section 489-F PPC and Order XXXVII CPC",
                        explanation=(
                            f"Section {num} does not exist in the Negotiable Instruments Act, 1881 as enacted in Pakistan "
                            f"(which terminates at Section 139). Sections 140-142 are Indian amendments (Act 66 of 1988). "
                            f"In Pakistan, cheque dishonour is prosecuted under Section 489-F PPC."
                        ),
                        source="Pakistan Code (pakistancode.gov.pk), Act No. XXVI of 1881; https://pakistancode.gov.pk/pdffiles/administrator2bbb145adb573172ec68151f4e70dfb5.pdf"
                    )

            # Match provision against indexed records
            p_low = prov_clean.lower()
            matched_rec = None
            matched_cid = None

            # Handle Order & Rule for CPC
            if act_code == "CPC_1908":
                m_ord = re.search(r'\b(?:orders?|ord\.?|o\.)\s*([ivxlcdm\d]+)(?:[\s,]+(?:rules?|r\.?)\s*(\d+[a-z]?(?:\s*\([0-9a-z]+\))?))?', p_low)
                if not m_ord:
                    # check for bare "Rule 2A", "Rule 2B", "Rule 4A" in CPC context
                    m_bare_r = re.search(r'\b(?:rules?|r\.?)\s*(2-?[a-bA-B]|4-?[a-bA-B]|\d+[a-z]?)\b', prov_clean, re.I)
                    if m_bare_r and any(k in p_low for k in ["xxxix", "39", "injunction", "stay"]):
                        r_tok = m_bare_r.group(1).upper().replace("-", "")
                        cand_cids = [f"CPC_1908_ORD_XXXIX_R_{r_tok}"]
                        for c in cand_cids:
                            if c in provisions:
                                matched_rec = provisions[c]
                                matched_cid = c
                                break
                else:
                    ord_val = m_ord.group(1).upper()
                    r_val = m_ord.group(2)
                    if r_val:
                        r_clean = re.sub(r'[\(\)\s]', '', r_val).upper().replace("-", "")
                        m_base = re.match(r'(\d+[a-zA-Z]?)', r_val)
                        base_r = m_base.group(1).upper() if m_base else r_clean
                        cand_cids = [
                            f"CPC_1908_ORD_{ord_val}_R_{r_clean}",
                            f"CPC_1908_ORD_{ord_val}_R_{base_r}",
                            f"CPC_1908_ORD_{ord_val}_R_{r_clean[0]}_SR_{r_clean[1:]}" if len(r_clean) > 1 else "",
                            f"CPC_1908_ORD_{ord_val}_R_{r_clean.replace('A', '_A')}",
                        ]
                        for c in cand_cids:
                            if c and c in provisions:
                                matched_rec = provisions[c]
                                matched_cid = c
                                break
                    else:
                        cand_cid = f"CPC_1908_ORD_{ord_val}"
                        if cand_cid in provisions:
                            matched_rec = provisions[cand_cid]
                            matched_cid = cand_cid

            # Standard Section match
            if not matched_rec:
                m_sec = re.search(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-z]?(?:-[a-z])?)\b', prov_clean, re.I)
                if m_sec:
                    sec_clean = m_sec.group(1).upper().replace("-", "")
                    cand_cids = [
                        f"{act_code}_SEC_{sec_clean}",
                        f"{act_code}_SEC_{m_sec.group(1).upper()}"
                    ]
                    for c in cand_cids:
                        if c in provisions:
                            matched_rec = provisions[c]
                            matched_cid = c
                            break

            # Standard Article match
            if not matched_rec:
                m_art = re.search(r'\b(?:articles?|art\.?)\s*(\d+[a-z]?)\b', prov_clean, re.I)
                if m_art:
                    art_clean = m_art.group(1).upper()
                    cand_cid = f"{act_code}_ART_{art_clean}"
                    if cand_cid in provisions:
                        matched_rec = provisions[cand_cid]
                        matched_cid = cand_cid

            if matched_rec:
                # Retrieve verbatim text if loaded in versions
                text = self._version_texts.get(matched_cid) if matched_cid else None
                if not text:
                    text = matched_rec.get("text") or matched_rec.get("statutory_text")

                # Attach Schedule II if PPC
                sched_ii = None
                if act_code == "PPC_1860":
                    primary = str(matched_rec.get("primary_num", "")).upper()
                    sched_ii = self.get_schedule_ii(primary)

                explanation = None
                if matched_cid == "CPC_1908_ORD_XXXIX_R_2A" and any(k in prov_clean.lower() for k in ["breach", "disobey", "disobedience", "violation"]):
                    explanation = (
                        "In Pakistan CPC, Order XXXIX Rule 2A (inserted by Act XIV of 1994, s. 11) governs the "
                        "15-day maximum duration of ex-parte interim injunctions. Remedy for breach or disobedience "
                        "of an interim injunction in Pakistan is governed by Order XXXIX Rule 2(3) CPC "
                        "(providing for attachment of property and detention in civil prison up to 6 months; see 2006 YLR 2758)."
                    )

                return LookupResult(
                    status="EXISTS",
                    exists=True,
                    confirmed_absent=False,
                    act_code=act_code,
                    act_name=matched_rec.get("act_name"),
                    canonical_id=matched_cid,
                    display_name=matched_rec.get("display_name"),
                    title=matched_rec.get("title"),
                    text=text,
                    source=matched_rec.get("source_citation"),
                    schedule_ii=sched_ii,
                    explanation=explanation
                )
            else:
                # If statute is known to be fully indexed, check if number is out of bounds
                m_num = re.search(r'\b(\d+)\b', prov_clean)
                if m_num:
                    num_val = int(m_num.group(1))
                    # Check max section in this act
                    sec_nums = [
                        int(r["primary_num"]) for r in provisions.values()
                        if r.get("primary_num") and str(r.get("primary_num")).isdigit()
                    ]
                    if sec_nums and num_val > max(sec_nums):
                        return LookupResult(
                            status="CONFIRMED_ABSENT",
                            exists=False,
                            confirmed_absent=True,
                            act_code=act_code,
                            display_name=f"{prov_clean} ({act_code})",
                            explanation=f"Provision {prov_clean} exceeds the total number of provisions in {act_code} ({max(sec_nums)} provisions).",
                            source="Pakistan Code"
                        )

        # 3. Unverified outcome
        return LookupResult(
            status="UNVERIFIED",
            exists=False,
            confirmed_absent=False,
            display_name=prov_clean,
            explanation=f"Could not verify '{prov_clean}' in statute '{statute}' within the verified database.",
            source=None
        )

    def extract_provisions_from_query(self, query_text: str) -> List[Tuple[str, str]]:
        """
        Parses statute and provision references from query text.
        Returns list of (statute_hint, provision_str) pairs.
        """
        q = query_text.strip()
        results: List[Tuple[str, str]] = []

        # 1. Indian Penal Code / IPC
        m_ipc = re.search(r'(?:section\s*|s\.\s*)?(\d+[a-z]?(?:-[a-z])?)\s*(?:of\s+the\s+)?(?:indian\s+penal\s+code|ipc)', q, re.I)
        if m_ipc:
            results.append(("Indian Penal Code", f"Section {m_ipc.group(1)}"))

        # 2. Negotiable Instruments Act / NI Act
        m_ni = re.search(r'(?:section\s*|s\.\s*)?(\d+[a-z]?)\s*(?:of\s+the\s+)?(?:negotiable\s+instruments\s+act|ni\s+act)', q, re.I)
        if not m_ni:
            m_ni = re.search(r'(?:negotiable\s+instruments\s+act|ni\s+act)\s*(?:section\s*|s\.\s*)?(\d+[a-z]?)', q, re.I)
        if m_ni:
            results.append(("Negotiable Instruments Act", f"Section {m_ni.group(1)}"))

        # 3. CPC Orders & Rules
        m_cpc_ord = re.search(r'(?:order\s*|o\.\s*)([ivxlcdm\d]+)\s*(?:rule\s*|r\.\s*)(\d+[a-z]?)\s*(?:of\s+the\s+)?(?:cpc|code\s+of\s+civil\s+procedure)?', q, re.I)
        if m_cpc_ord:
            results.append(("CPC", f"Order {m_cpc_ord.group(1)} Rule {m_cpc_ord.group(2)}"))

        # 4. Standalone Section 489-F / 420 PPC
        m_489 = re.search(r'\b(?:489-f|489f)\b', q, re.I)
        if m_489:
            results.append(("PPC", "Section 489-F"))

        m_420 = re.search(r'\b(?:section\s*420|s\.\s*420)\b', q, re.I)
        if m_420 and not m_ipc:
            results.append(("PPC", "Section 420"))

        return results


# Global singleton
_GLOBAL_STORE: Optional[StatuteStore] = None


def get_statute_store() -> StatuteStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = StatuteStore()
    return _GLOBAL_STORE


def lookup(statute: str, provision: str) -> LookupResult:
    """Convenience lookup helper."""
    return get_statute_store().lookup(statute, provision)


def get_crpc_schedule_ii(section: str) -> Optional[Dict[str, Any]]:
    """Convenience Cr.P.C. Schedule II lookup helper."""
    return get_statute_store().get_schedule_ii(section)

