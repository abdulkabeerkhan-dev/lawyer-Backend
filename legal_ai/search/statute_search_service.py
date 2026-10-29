"""
legal_ai/search/statute_search_service.py

High-performance in-memory and database search service for Pakistani Statutes,
Acts, Codes, and Ordinances.
"""

import re
from typing import Dict, List, Any, Optional
from core.unified_statute_store import get_unified_statute_store

ACT_DESCRIPTIONS: Dict[str, Dict[str, Any]] = {
    "PPC_1860": {
        "code": "PPC_1860",
        "title": "Pakistan Penal Code, 1860",
        "short_name": "Pakistan Penal Code",
        "aliases": ["penal code", "ppc", "pakistan penal code"],
        "year": 1860,
        "category": "Criminal Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "CRPC_1898": {
        "code": "CRPC_1898",
        "title": "Code of Criminal Procedure, 1898",
        "short_name": "Code of Criminal Procedure",
        "aliases": ["criminal procedure", "crpc", "cr.p.c"],
        "year": 1898,
        "category": "Criminal Procedure",
        "jurisdiction": "Pakistan (Federal)"
    },
    "CPC_1908": {
        "code": "CPC_1908",
        "title": "Code of Civil Procedure, 1908",
        "short_name": "Code of Civil Procedure",
        "aliases": ["civil procedure", "cpc", "c.p.c"],
        "year": 1908,
        "category": "Civil Procedure",
        "jurisdiction": "Pakistan (Federal)"
    },
    "CONST_1973": {
        "code": "CONST_1973",
        "title": "Constitution of the Islamic Republic of Pakistan, 1973",
        "short_name": "Constitution of Pakistan",
        "aliases": ["constitution", "const", "pakistan constitution", "article"],
        "year": 1973,
        "category": "Constitutional Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "QSO_1984": {
        "code": "QSO_1984",
        "title": "Qanun-e-Shahadat Order, 1984",
        "short_name": "Qanun-e-Shahadat Order",
        "aliases": ["qanun-e-shahadat", "qso", "evidence"],
        "year": 1984,
        "category": "Evidence Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "PRPA_2009": {
        "code": "PRPA_2009",
        "title": "Punjab Rented Premises Act, 2009",
        "short_name": "Punjab Rented Premises Act",
        "aliases": ["punjab rented premises", "prpa", "rented premises", "rent act"],
        "year": 2009,
        "category": "Tenancy & Rent Law",
        "jurisdiction": "Punjab"
    },
    "COMPANIES_2017": {
        "code": "COMPANIES_2017",
        "title": "Companies Act, 2017",
        "short_name": "Companies Act, 2017",
        "aliases": ["companies act", "company law"],
        "year": 2017,
        "category": "Corporate Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "CNSA_1997": {
        "code": "CNSA_1997",
        "title": "Control of Narcotic Substances Act, 1997",
        "short_name": "Control of Narcotic Substances Act",
        "aliases": ["narcotic", "cnsa", "narcotics"],
        "year": 1997,
        "category": "Criminal Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "FIO_2001": {
        "code": "FIO_2001",
        "title": "Financial Institutions (Recovery of Finances) Ordinance, 2001",
        "short_name": "Financial Institutions Ordinance",
        "aliases": ["financial institutions", "fio", "banking recovery"],
        "year": 2001,
        "category": "Banking Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "BCO_1962": {
        "code": "BCO_1962",
        "title": "Banking Companies Ordinance, 1962",
        "short_name": "Banking Companies Ordinance",
        "aliases": ["banking companies", "bco"],
        "year": 1962,
        "category": "Banking Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "ITO_2001": {
        "code": "ITO_2001",
        "title": "Income Tax Ordinance, 2001",
        "short_name": "Income Tax Ordinance",
        "aliases": ["income tax", "ito"],
        "year": 2001,
        "category": "Tax Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "CONTRACT_1872": {
        "code": "CONTRACT_1872",
        "title": "Contract Act, 1872",
        "short_name": "Contract Act, 1872",
        "aliases": ["contract act", "contracts"],
        "year": 1872,
        "category": "Commercial Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "SRA_1877": {
        "code": "SRA_1877",
        "title": "Specific Relief Act, 1877",
        "short_name": "Specific Relief Act, 1877",
        "aliases": ["specific relief", "sra"],
        "year": 1877,
        "category": "Civil Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "TPA_1882": {
        "code": "TPA_1882",
        "title": "Transfer of Property Act, 1882",
        "short_name": "Transfer of Property Act, 1882",
        "aliases": ["transfer of property", "tpa"],
        "year": 1882,
        "category": "Property Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "LIMITATION_1908": {
        "code": "LIMITATION_1908",
        "title": "Limitation Act, 1908",
        "short_name": "Limitation Act, 1908",
        "aliases": ["limitation act", "limitation"],
        "year": 1908,
        "category": "Procedural Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "REGISTRATION_1908": {
        "code": "REGISTRATION_1908",
        "title": "Registration Act, 1908",
        "short_name": "Registration Act, 1908",
        "aliases": ["registration act", "registration"],
        "year": 1908,
        "category": "Property Law",
        "jurisdiction": "Pakistan (Federal)"
    },
    "STAMP_1899": {
        "code": "STAMP_1899",
        "title": "Stamp Act, 1899",
        "short_name": "Stamp Act, 1899",
        "aliases": ["stamp act"],
        "year": 1899,
        "category": "Revenue Law",
        "jurisdiction": "Pakistan (Federal)"
    }
}


def get_all_statute_acts() -> List[Dict[str, Any]]:
    """Returns directory of all available legal codes and acts."""
    store = get_unified_statute_store()
    acts_counts: Dict[str, int] = {}
    for prov in store._by_cid.values():
        ac = prov.get("act_code")
        if ac:
            acts_counts[ac] = acts_counts.get(ac, 0) + 1

    results = []
    for code, count in acts_counts.items():
        info = ACT_DESCRIPTIONS.get(code, {
            "code": code,
            "title": code.replace("_", " "),
            "short_name": code,
            "year": 2000,
            "category": "General Law",
            "jurisdiction": "Pakistan",
            "aliases": []
        })
        results.append({
            "act_code": code,
            "title": info["title"],
            "short_name": info["short_name"],
            "category": info["category"],
            "jurisdiction": info["jurisdiction"],
            "provisions_count": count
        })
    results.sort(key=lambda x: x["title"])
    return results


def search_statute_provisions(
    query: str,
    act_code: Optional[str] = None,
    limit: int = 25
) -> Dict[str, Any]:
    """
    Searches across Pakistani statutory provisions by keyword, section number, or act title.
    """
    store = get_unified_statute_store()
    q_raw = query.strip()
    q_lower = q_raw.lower()

    # Find any standalone section numbers or alphanumeric section tokens (e.g. "489-f", "19", "561-a")
    raw_tokens = re.findall(r'\b[0-9]+(?:-[a-z0-9]+|[a-z0-9]+)?\b', q_lower)
    target_nums = {re.sub(r'[^a-z0-9]', '', t) for t in raw_tokens}

    m_sec = re.search(r'\b(?:section|sec|article|art|rule|order|s\.)\s*([0-9]+(?:-[a-z0-9]+|[a-z0-9]+)?)\b', q_lower)
    if m_sec:
        target_nums.add(re.sub(r'[^a-z0-9]', '', m_sec.group(1)))

    candidates = []
    seen_cids = set()

    for cid, prov in store._by_cid.items():
        p_act = prov.get("act_code") or ""
        if act_code and p_act.upper() != act_code.upper():
            continue

        act_info = ACT_DESCRIPTIONS.get(p_act, {})
        act_name = str(prov.get("act_name") or act_info.get("title") or p_act)
        act_lower = act_name.lower()
        act_aliases = act_info.get("aliases", [])

        # Check if query matches this act
        act_matches_query = (
            p_act.lower() in q_lower or
            any(alias in q_lower for alias in act_aliases) or
            any(w in q_lower for w in act_lower.split() if len(w) > 4)
        )

        p_num = str(prov.get("primary_num") or "")
        p_num_norm = re.sub(r'[^a-z0-9]', '', p_num.lower())
        p_title = str(prov.get("title") or "")
        p_title_lower = p_title.lower()
        p_text = str(prov.get("text") or "")
        p_text_lower = p_text.lower()

        score = 0

        # Exact section number match
        if p_num_norm in target_nums:
            score += 300
            if act_matches_query:
                score += 500  # Dominant boost for exact section inside matching act

        # Act match bonus
        if act_matches_query:
            score += 80

        # Title match
        if q_lower in p_title_lower:
            score += 150
        elif any(w in p_title_lower for w in q_lower.split() if len(w) > 3 and w not in ["under", "section", "article"]):
            score += 40

        # Text body match
        if q_lower in p_text_lower:
            score += 50
        else:
            text_word_hits = sum(1 for w in q_lower.split() if len(w) > 4 and w in p_text_lower)
            score += text_word_hits * 10

        if score > 0:
            if cid not in seen_cids:
                seen_cids.add(cid)
                # Form clean excerpt
                excerpt = ""
                if q_lower in p_text_lower:
                    idx = p_text_lower.find(q_lower)
                    start = max(0, idx - 80)
                    end = min(len(p_text), idx + 200)
                    excerpt = "..." + p_text[start:end].replace("\n", " ").strip() + "..."
                elif p_text:
                    excerpt = p_text[:220].replace("\n", " ").strip() + "..."

                prov_type = prov.get("provision_type") or ("article" if "CONST" in p_act else "section")
                disp = f"{prov_type.title()} {p_num}, {act_info.get('short_name') or act_name}"

                candidates.append({
                    "score": score,
                    "canonical_id": cid,
                    "act_code": p_act,
                    "act_name": act_name,
                    "short_act_name": act_info.get("short_name") or act_name,
                    "provision_type": prov_type,
                    "primary_num": p_num,
                    "title": p_title,
                    "display_name": disp,
                    "snippet": excerpt,
                    "has_text": bool(p_text and "no text available" not in p_text.lower()),
                    "in_force": prov.get("in_force", True),
                    "tier": prov.get("tier", "text_layer_extracted")
                })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    results = candidates[:limit]

    return {
        "query": query,
        "total_matches": len(candidates),
        "results": results
    }


def get_provision_full_text(canonical_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the authentic verbatim text and details of a single provision."""
    store = get_unified_statute_store()
    prov = store.get_by_canonical_id(canonical_id)
    if not prov:
        return None

    act_code = prov.get("act_code") or ""
    act_info = ACT_DESCRIPTIONS.get(act_code, {})
    act_name = prov.get("act_name") or act_info.get("title") or act_code

    prov_type = prov.get("provision_type") or ("article" if "CONST" in act_code else "section")
    num = str(prov.get("primary_num") or "")

    return {
        "canonical_id": prov.get("canonical_id") or canonical_id,
        "act_code": act_code,
        "act_name": act_name,
        "short_act_name": act_info.get("short_name") or act_name,
        "provision_type": prov_type,
        "primary_num": num,
        "title": prov.get("title") or "",
        "text": prov.get("text") or "",
        "tier": prov.get("tier", "text_layer_extracted"),
        "in_force": prov.get("in_force", True),
        "footnotes": prov.get("footnotes", [])
    }
