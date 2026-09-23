"""
Precedent Currency & Overruling-Status Tracking Engine (Phase 5 Pilot)
Tracks negative judicial history (overruled, criticized_not_followed, distinguished, superseded_by_statute)
for Pakistani superior court precedents via Supabase precedent_status table with local seed fallback.
"""

import json
import os
import re
import sys
from typing import Dict, Any, List, Optional

ANNOTATIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "precedent_annotations.json"
)

_LOCAL_ANNOTATIONS: Optional[List[Dict[str, Any]]] = None
_LOOKUP_MAP: Dict[str, Dict[str, Any]] = {}


COLLISION_WHITELIST = {
    "2006_YLR_1206",
    "2006 YLR 1206",
    "2007_YLR_2827",
    "2007 YLR 2827",
    "2006_YLR_3278",
    "2006 YLR 3278",
    "2006_YLR_96",
    "2006 YLR 96",
}


def _normalize_key(s: str) -> str:
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def is_whitelisted_citation(identifier: str) -> bool:
    if not identifier:
        return False
    norm = _normalize_key(identifier)
    return norm in {_normalize_key(x) for x in COLLISION_WHITELIST} or any(k in norm for k in ["2006ylr1206", "2007ylr2827", "2006ylr3278", "2006ylr96"])



def load_local_annotations(force_reload: bool = False) -> List[Dict[str, Any]]:
    global _LOCAL_ANNOTATIONS, _LOOKUP_MAP
    if _LOCAL_ANNOTATIONS is not None and not force_reload:
        return _LOCAL_ANNOTATIONS

    _LOCAL_ANNOTATIONS = []
    _LOOKUP_MAP = {}

    if not os.path.exists(ANNOTATIONS_PATH):
        return _LOCAL_ANNOTATIONS

    try:
        with open(ANNOTATIONS_PATH, "r", encoding="utf-8") as f:
            _LOCAL_ANNOTATIONS = json.load(f)

        for entry in _LOCAL_ANNOTATIONS:
            for field in ["case_id", "stored_case_id", "citation", "normalized_citation"]:
                val = entry.get(field)
                if val:
                    _LOOKUP_MAP[_normalize_key(val)] = entry
                    _LOOKUP_MAP[str(val).strip().upper()] = entry
                    _LOOKUP_MAP[str(val).strip().lower()] = entry

            case_name = entry.get("case_name")
            if case_name:
                _LOOKUP_MAP[_normalize_key(case_name)] = entry
                _LOOKUP_MAP[str(case_name).strip().lower()] = entry

    except Exception as e:
        print(f"[WARN] Error loading local precedent annotations: {e}")

    return _LOCAL_ANNOTATIONS


def check_precedent_currency(case_id: str) -> Optional[Dict[str, Any]]:
    """
    Checks Supabase `precedent_status` table for a given case_id or citation.
    Falls back gracefully to local curated seed data if the table is unavailable.
    """
    if not case_id:
        return None

    norm_id = str(case_id).strip()
    norm_u = norm_id.upper()

    # 1. Attempt Supabase query
    try:
        from main import supabase, init_supabase_client
        sb = supabase or init_supabase_client()
        if sb:
            # Query by case_id
            res = sb.table("precedent_status").select("*").eq("case_id", norm_id).limit(1).execute()
            if res.data:
                return res.data[0]
            if norm_u != norm_id:
                res = sb.table("precedent_status").select("*").eq("case_id", norm_u).limit(1).execute()
                if res.data:
                    return res.data[0]
            # Query by citation
            res = sb.table("precedent_status").select("*").eq("citation", norm_id).limit(1).execute()
            if res.data:
                return res.data[0]
    except Exception:
        # Graceful fallback to local annotations
        pass

    # 2. Local fallback
    load_local_annotations()
    if norm_u in _LOOKUP_MAP:
        return _LOOKUP_MAP[norm_u]
    if norm_id.lower() in _LOOKUP_MAP:
        return _LOOKUP_MAP[norm_id.lower()]

    norm_clean = _normalize_key(norm_id)
    if norm_clean in _LOOKUP_MAP:
        return _LOOKUP_MAP[norm_clean]

    for entry in _LOCAL_ANNOTATIONS or []:
        e_norm = _normalize_key(entry.get("normalized_citation", ""))
        e_raw_norm = _normalize_key(entry.get("citation", ""))
        e_stored = _normalize_key(entry.get("stored_case_id", ""))
        e_cid = _normalize_key(entry.get("case_id", ""))
        if (e_norm and e_norm in norm_clean) or (e_raw_norm and e_raw_norm in norm_clean) or (e_stored and e_stored in norm_clean) or (e_cid and e_cid in norm_clean):
            return entry

    return None


def get_precedent_annotation(identifier: str) -> Optional[Dict[str, Any]]:
    return check_precedent_currency(identifier)


def format_precedent_status_banner(status_info: Dict[str, Any]) -> str:
    """
    Constructs the mandatory deterministic warning banner matching the Phase 5 specification:
    '⚠️ Precedent Status Warning: [case_name] has been [status] by [superseding_case_name] ([superseding_citation]). [doctrinal_note]'
    """
    case_name = status_info.get("case_name", "This precedent")
    citation = status_info.get("citation", "")
    status = status_info.get("status", "overruled").replace("_", " ")
    superseding_case = status_info.get("superseding_case_name", "a later Supreme Court bench")
    superseding_cit = status_info.get("superseding_citation", "")
    doctrinal_note = status_info.get("doctrinal_note", "")

    super_part = f"{superseding_case}"
    if superseding_cit:
        super_part += f" ({superseding_cit})"

    note_part = f" {doctrinal_note}" if doctrinal_note else ""

    banner = f"> ⚠️ **Precedent Status Warning**: {case_name} has been {status} by {super_part}.{note_part}"
    return banner


def find_precedent_status_annotation(
    query_text: str = "",
    citations: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Evaluates whether the user query or any retrieved precedent card in `citations`
    refers to a precedent with negative currency status.
    Returns the annotation record if triggered, else None.
    
    CONTROL GUARD: Never fires for the superseding authority (e.g. Asma Jilani).
    """
    # 1. Check retrieved citations in payload
    for c in (citations or []):
        for field in ["case_id", "supabase_id", "citation", "neutral_citation", "title", "case_name"]:
            val = c.get(field)
            if val:
                annot = check_precedent_currency(str(val))
                if annot:
                    return annot

    # 2. Check query text specifically for the superseded case
    q_norm = _normalize_key(query_text)
    # Check known keys for State v. Dosso
    local_data = load_local_annotations()
    for entry in local_data:
        target_keys = [
            _normalize_key(entry.get("citation", "")),
            _normalize_key(entry.get("normalized_citation", "")),
            _normalize_key(entry.get("stored_case_id", "")),
            _normalize_key(entry.get("case_id", ""))
        ]
        case_name = entry.get("case_name", "")
        if "dosso" in case_name.lower():
            target_keys.append("dosso")

        for tk in target_keys:
            if tk and tk in q_norm:
                return entry

    # 3. Check for specific natural-language doctrine queries regarding revolutionary legality
    if any(k in query_text.lower() for k in ["revolutionary legality", "doctrine of revolutionary legality"]):
        dosso_annot = check_precedent_currency("1958_PLD_SC_533") or check_precedent_currency("PLD 1958 SC 533")
        if dosso_annot:
            return dosso_annot

    return None


def check_citations_and_query_for_precedent_status(
    query_text: str = "",
    citations: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """
    Evaluates whether the user query or any retrieved precedent card in `citations`
    refers to a precedent with negative currency status.
    Returns the formatted banner if triggered, else None.
    """
    annot = find_precedent_status_annotation(query_text=query_text, citations=citations)
    if annot:
        return format_precedent_status_banner(annot)
    return None

