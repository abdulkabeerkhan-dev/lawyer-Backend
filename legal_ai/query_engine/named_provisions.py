"""
legal_ai/query_engine/named_provisions.py

Deterministic statute anchoring for the evidence pack.

The 100-question evaluation (Nov 2026) showed answers refusing or reasoning from the
wrong law because the governing provision never reached the evidence pack, even when
the question named it ("Article 199", "s.310 PPC", "S.4 MFLO") or the topic made it
obvious (khula, second marriage, badal-i-sulh). This module turns both into exact
canonical ids from the unified statute store:

    provisions_named_in(query)   -> ids for provisions the question names
    provisions_for_topics(query) -> ids for the governing provisions of known topics

Only ids that exist in the store are returned (the caller checks with the store).
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

# act alias regex -> (act code, default unit for a bare number)
ACT_ALIASES: List[Tuple[str, str, str]] = [
    (r"\bconstitution\b|\bconst\.?\b", "CONST_1973", "ART"),
    (r"\bppc\b|\bp\.p\.c\b|pakistan\s+penal\s+code|\bpenal\s+code\b", "PPC_1860", "SEC"),
    (r"\bcr\.?\s?p\.?\s?c\b|criminal\s+procedure", "CRPC_1898", "SEC"),
    (r"\bc\.?p\.?c\b|civil\s+procedure", "CPC_1908", "SEC"),
    (r"\bqso\b|qanun[\s-]*e[\s-]*shahadat|qanoon[\s-]*e[\s-]*shahadat", "QSO_1984", "ART"),
    (r"limitation\s+act|\blimitation\b", "LIMITATION_1908", "ART"),
    (r"\bmflo\b|muslim\s+family\s+laws?", "MFLO_1961", "SEC"),
    (r"family\s+courts?\s+act|\bfca\b", "FAMILY_COURTS_1964", "SEC"),
    (r"guardians?\s+(?:and|&)\s+wards|\bgwa\b", "GWA_1890", "SEC"),
    (r"dissolution\s+of\s+muslim\s+marriages|\bdmma\b", "DMMA_1939", "SEC"),
    (r"contract\s+act", "CONTRACT_1872", "SEC"),
    (r"specific\s+relief|\bsra\b", "SRA_1877", "SEC"),
    (r"transfer\s+of\s+property|\btpa\b", "TPA_1882", "SEC"),
    (r"companies\s+act(?:,?\s*2017)?", "COMPANIES_2017", "SEC"),
    (r"financial\s+institutions|\bfio\b", "FIO_2001", "SEC"),
    (r"anti[\s-]*terrorism|\bata\b", "ATA_1997", "SEC"),
    (r"control\s+of\s+narcotic|\bcnsa\b", "CNSA_1997", "SEC"),
    (r"electronic\s+crimes|\bpeca\b", "PECA_2016", "SEC"),
    (r"arbitration\s+act(?:,?\s*1940)?", "ARBITRATION_1940", "SEC"),
    (r"partition\s+act", "PARTITION_1893", "SEC"),
    (r"benami", "BENAMI_2017", "SEC"),
    (r"land\s+revenue", "LAND_REVENUE_1967", "SEC"),
    (r"pre[\s-]?emption", "PREEMPTION_1991", "SEC"),
    (r"succession\s+act", "SUCCESSION_1925", "SEC"),
    (r"service\s+tribunals?\s+act", "SERVICE_TRIBUNALS_1973", "SEC"),
]

_ROMAN = r"[IVXL]+"
_UNIT = re.compile(
    rf"(?P<order>\b(?:order|o)\.?\s*(?P<ord>{_ROMAN})\s*,?\s*(?:rule|r)\.?\s*(?P<rule>\d+[A-Z]?))"
    rf"|(?P<kind>\barticles?|\barts?\.?|\bsections?|\bss?\.)\s*(?P<num>\d+(?:-?[A-Z])?(?:\s*\(\s*[0-9a-z]+\s*\))*)"
    rf"(?P<more>(?:\s*(?:,|and|&|/|or)\s*\d+(?:-?[A-Z])?(?:\s*\(\s*[0-9a-z]+\s*\))*)*)",
    re.IGNORECASE,
)

# Topic -> governing provisions. Each entry: (trigger regex on the question, ids).
TOPIC_PROVISIONS: List[Tuple[str, List[str]]] = [
    (r"\bqatl\b|\bmurder\b|\b302\b", ["PPC_1860_SEC_302"]),
    (r"\bcheque\b|\b489-?f\b", ["PPC_1860_SEC_489F"]),
    (r"pre-?arrest\s+bail|anticipatory\s+bail|\bbail\s+before\s+arrest", ["CRPC_1898_SEC_498"]),
    (r"\bbail\b", ["CRPC_1898_SEC_497"]),
    (r"breach\s+of\s+trust|\bentrust", ["PPC_1860_SEC_405", "PPC_1860_SEC_406", "PPC_1860_SEC_409"]),
    (r"\bcheating\b|\bfraud(?:ulent)?ly\s+induc", ["PPC_1860_SEC_415", "PPC_1860_SEC_420"]),
    (r"defamation|defamatory", ["PPC_1860_SEC_499", "PPC_1860_SEC_500"]),
    (r"breach\s+of\s+contract|\bdamages\b", ["CONTRACT_1872_SEC_73", "CONTRACT_1872_SEC_74"]),
    (r"narcotic|\bcharas\b|\bheroin\b|\bopium\b|\bice\b\s+drug", ["CNSA_1997_SEC_9"]),
    (r"reject(?:ion)?\s+(?:of\s+)?(?:the\s+|a\s+)?plaint|plaint\s+be\s+rejected", ["CPC_1908_ORD_VII_R_11"]),
    (r"\bpartition\b", ["PARTITION_1893_SEC_4", "CPC_1908_ORD_XX_R_18"]),
    (r"mesne\s+profits?", ["CPC_1908_ORD_XX_R_12"]),
    (r"\bbenami\b", ["BENAMI_2017_SEC_3", "BENAMI_2017_SEC_4", "QSO_1984_ART_117"]),
    (r"burden\s+of\s+proof", ["QSO_1984_ART_117"]),
    (r"power\s+of\s+attorney|general\s+attorney|\battorney\b.*\bsold\b", ["CONTRACT_1872_SEC_211", "CONTRACT_1872_SEC_214", "CONTRACT_1872_SEC_215"]),
    (r"objection\s+petition|third[\s-]party\s+(?:objector|claim)|resist\w*\s+(?:in|to)\s+execution|obstruction\s+in\s+execution",
     ["CPC_1908_ORD_XXI_R_58", "CPC_1908_ORD_XXI_R_97", "CPC_1908_ORD_XXI_R_99", "CPC_1908_ORD_XXI_R_103"]),
    (r"\bdeclaration\b|declaratory", ["SRA_1877_SEC_42"]),
    (r"forg(?:ery|ed)|fabricat", ["PPC_1860_SEC_463", "PPC_1860_SEC_468", "PPC_1860_SEC_471"]),
    (r"handwriting|forensic\s+expert|expert\s+(?:opinion|evidence)", ["QSO_1984_ART_59"]),
    (r"appointment\s+of\s+judges|judicial\s+commission", ["CONST_1973_ART_175A"]),
    (r"transfer\s+(?:of\s+)?(?:high\s+court\s+)?judges?|\bjudges?\b.*\btransfer", ["CONST_1973_ART_200"]),
    (r"(?s)(?=.*banking\s+court)(?=.*\bappeal)", ["FIO_2001_SEC_22"]),
    (r"\bkhula\b", ["DMMA_1939_SEC_2", "FAMILY_COURTS_1964_SEC_10"]),
    (r"\btalaq\b|\bdivorce\b", ["MFLO_1961_SEC_7", "MFLO_1961_SEC_8"]),
    (r"second\s+marriage|polygam|another\s+wife|permission\s+of\s+(?:the\s+)?arbitration\s+council", ["MFLO_1961_SEC_6"]),
    (r"\bdower\b|\bmehr\b|\bmahr\b|\bhaq\s*mehr\b", ["MFLO_1961_SEC_10"]),
    (r"maintenance", ["MFLO_1961_SEC_9", "FAMILY_COURTS_1964_SEC_5"]),
    (r"orphaned\s+grand|grand(?:children|son|daughter|child)|pre-?deceased\s+(?:son|daughter|father)|father\s+died\s+before",
     ["MFLO_1961_SEC_4"]),
    (r"badal[\s-]*i[\s-]*sulh|compound(?:ing|ed)?\s+(?:of\s+)?(?:qatl|murder|offence)|\bdiyat\b|\bqisas\b",
     ["PPC_1860_SEC_309", "PPC_1860_SEC_310", "CRPC_1898_SEC_345"]),
    (r"arbitration\s+award|objections?\s+to\s+(?:an?\s+|the\s+)?award", ["ARBITRATION_1940_SEC_17", "ARBITRATION_1940_SEC_30", "ARBITRATION_1940_SEC_33"]),
    (r"\bcustody\b|\bhizanat\b|guardian", ["GWA_1890_SEC_17", "GWA_1890_SEC_25"]),
    (r"\bhiba\b|\bgift\b", ["TPA_1882_SEC_122", "TPA_1882_SEC_129"]),
    (r"pre[\s-]?emption|\btalb", ["PREEMPTION_1991_SEC_13"]),
    (r"lis\s+pendens|pendency\s+of\s+(?:a\s+|the\s+)?suit|during\s+(?:the\s+)?pendency", ["TPA_1882_SEC_52"]),
    (r"ostensible\s+owner|bona\s+fide\s+purchaser", ["TPA_1882_SEC_41"]),
    (r"part\s+performance", ["TPA_1882_SEC_53A"]),
    (r"confession", ["QSO_1984_ART_37", "QSO_1984_ART_38", "QSO_1984_ART_39", "QSO_1984_ART_40"]),
    (r"dying\s+declaration", ["QSO_1984_ART_46"]),
    (r"recovery\s+on\s+(?:the\s+)?disclosure|discovery\s+of\s+fact", ["QSO_1984_ART_40"]),
    (r"amend(?:ment)?\s+(?:of\s+)?(?:the\s+)?(?:plaint|pleading)|amend\s+the\s+plaint", ["CPC_1908_ORD_VI_R_17"]),
    (r"ex[\s-]?parte\s+decree", ["CPC_1908_ORD_IX_R_13", "LIMITATION_1908_ART_164"]),
    (r"res\s+judicata", ["CPC_1908_SEC_11"]),
    (r"\brevision\b", ["CPC_1908_SEC_115"]),
    (r"\bexecution\b|executing\s+court", ["CPC_1908_SEC_47"]),
    (r"12\s*\(\s*2\s*\)|fraud(?:ulent)?\s+decree|decree\s+obtained\s+(?:through|by)\s+fraud", ["CPC_1908_SEC_12"]),
    (r"possession\s+(?:of\s+immovable\s+property\s+)?based\s+on\s+title|suit\s+for\s+possession", ["LIMITATION_1908_ART_142", "LIMITATION_1908_ART_144"]),
    (r"(?s)(?=.*(?:inherit|legal\s+heir|co-?heir|\bmutation\b))(?=.*(?:limitation|time[\s-]*barred|\bperiod\b|\bdelay\b))",
     ["LIMITATION_1908_ART_120", "LIMITATION_1908_ART_144"]),
    (r"minority\s+shareholder|oppress(?:ion|ive)\s+(?:and|or)\s+mismanagement", ["COMPANIES_2017_SEC_286"]),
    (r"\bwrit\b|constitutional\s+petition|\bmandamus\b|\bcertiorari\b", ["CONST_1973_ART_199"]),
    (r"suo\s+motu|public\s+importance|public\s+interest\s+litigation", ["CONST_1973_ART_175E"]),
    (r"fair\s+trial|due\s+process", ["CONST_1973_ART_10A"]),
    (r"civil\s+servant|terms\s+and\s+conditions\s+of\s+service|service\s+tribunal", ["CONST_1973_ART_212", "SERVICE_TRIBUNALS_1973_SEC_4"]),
    (r"cyber\s+terror", ["PECA_2016_SEC_10"]),
    (r"register(?:ing|ed|ation)?\s+(?:of\s+)?(?:an?\s+|the\s+)?fir|refus\w*\s+to\s+register|justice\s+of\s+(?:the\s+)?peace",
     ["CRPC_1898_SEC_154", "CRPC_1898_SEC_22A"]),
    (r"quash(?:ing|ment|ed)?", ["CRPC_1898_SEC_561A"]),
    (r"leave\s+to\s+defend|banking\s+court|recovery\s+of\s+finance", ["FIO_2001_SEC_9", "FIO_2001_SEC_10"]),
    (r"anti[\s-]*terrorism\s+court|\batc\b|(?<!cyber\s)(?<!cyber-)\bterrorism", ["ATA_1997_SEC_6", "ATA_1997_SEC_7"]),
    (r"\bauction\b|sale\s+proclamation|proclamation\s+of\s+sale|reserve\s+price|set(?:ting)?\s+aside\s+(?:the\s+|an?\s+)?(?:execution\s+|auction\s+)?sale",
     ["CPC_1908_ORD_XXI_R_90", "CPC_1908_ORD_XXI_R_66", "FIO_2001_SEC_19"]),
]


def _norm_num(raw: str) -> List[str]:
    """'184(3)' -> ['184_3', '184']; '489-F' -> ['489F']; '10A' -> ['10A']."""
    raw = re.sub(r"\s+", "", raw.upper())
    subs = re.findall(r"\(([0-9A-Z]+)\)", raw)
    base = re.sub(r"\(.*", "", raw).replace("-", "")
    out = []
    if subs:
        out.append(base + "_" + "_".join(s.lower() if s.isalpha() else s for s in subs))
        out.append(base + "_" + subs[0])
    out.append(base)
    return list(dict.fromkeys(out))


def _acts_in(text: str) -> List[Tuple[int, int, str, str]]:
    out = []
    for rx, code, unit in ACT_ALIASES:
        for m in re.finditer(rx, text, re.IGNORECASE):
            out.append((m.start(), m.end(), code, unit))
    return out


def provisions_named_in(query: str, exists: Optional[Callable[[str], bool]] = None) -> List[str]:
    """Canonical ids for provisions the question names, in the order mentioned."""
    text = query or ""
    acts = _acts_in(text)
    distinct = list(dict.fromkeys(a[2] for a in acts))
    ids: List[str] = []
    for m in _UNIT.finditer(text):
        # nearest act mention (prefer one after the unit, within 80 chars, then before)
        after = sorted((a for a in acts if 0 <= a[0] - m.end() <= 80), key=lambda a: a[0] - m.end())
        before = sorted((a for a in acts if 0 <= m.start() - a[1] <= 80), key=lambda a: m.start() - a[1])
        act = (after[0] if after else (before[0] if before else None))
        if m.group("order"):
            # Orders and Rules exist only in the CPC
            cands = [f"CPC_1908_ORD_{m.group('ord').upper()}_R_{m.group('rule').upper()}"]
        else:
            kind = m.group("kind").lower()
            unit = "ART" if kind.startswith("art") else "SEC"
            if act:
                code = act[2]
            elif len(distinct) == 1:
                code = distinct[0]
            elif unit == "ART":
                code = "CONST_1973"  # a bare "Article N" in Pakistani legal usage is the Constitution
            else:
                continue
            units = [unit] + (["ART" if unit == "SEC" else "SEC"] if code == "LIMITATION_1908" else [])
            raw_nums = [m.group("num")] + re.findall(r"\d+(?:-?[A-Z])?(?:\s*\(\s*[0-9a-z]+\s*\))*", m.group("more") or "", re.IGNORECASE)
            groups = [[f"{code}_{u}_{n}" for u in units for n in _norm_num(r)] for r in raw_nums]
            for cands in groups:
                for cid in cands:
                    if exists is None or exists(cid):
                        ids.append(cid)
                        break
            continue
        for cid in cands:
            if exists is None or exists(cid):
                ids.append(cid)
                break
    # The Constitution (Twenty-seventh Amendment) Act, 2025 omitted Art. 184 and moved original and
    # public-importance jurisdiction to the Federal Constitutional Court (Art. 175E). Keep the cited
    # article, so the answer can say it is omitted, and add the provision that now governs.
    for old, new in SUCCESSORS.items():
        if old in ids and new not in ids and (exists is None or exists(new)):
            ids.insert(ids.index(old) + 1, new)
    return list(dict.fromkeys(ids))


SUCCESSORS = {"CONST_1973_ART_184_3": "CONST_1973_ART_175E", "CONST_1973_ART_184": "CONST_1973_ART_175E",
              "CONST_1973_ART_186": "CONST_1973_ART_175E"}


def provisions_for_topics(query: str, exists: Optional[Callable[[str], bool]] = None) -> List[str]:
    text = query or ""
    ids: List[str] = []
    for rx, cids in TOPIC_PROVISIONS:
        if re.search(rx, text, re.IGNORECASE):
            ids += [c for c in cids if exists is None or exists(c)]
    return list(dict.fromkeys(ids))


GENERIC_PLANNER_DEFAULT = {"CPC_1908_SEC_9", "CPC_1908_SEC_151"}


def useful_planned(planned: Optional[Iterable[str]]) -> List[str]:
    """Planner ids, minus the generic CPC 9/151 pair it falls back to when it knows nothing."""
    ids = [str(p).strip().upper() for p in (planned or []) if str(p).strip()]
    if not ids or set(ids) <= GENERIC_PLANNER_DEFAULT:
        return []
    return list(dict.fromkeys(ids))


def act_of(cid: str) -> str:
    return re.sub(r"_(?:SEC|ART|ORD|RULE|SCHED|SCH|PARA|REG|CH)_.*$", "", str(cid or "").upper())


def anchored_ids(query: str, planned: Optional[Sequence[str]], exists: Callable[[str], bool]) -> List[str]:
    """Named provisions first, then the planner's, then topic anchors. Existing ids only."""
    out = provisions_named_in(query, exists)
    out += [p for p in useful_planned(planned) if exists(p)]
    out += provisions_for_topics(query, exists)
    return list(dict.fromkeys(out))
