"""
core/case_store.py

Case, PDF and legacy-statute lookups that used to go to Turso (core/turso_client.py).

    cases     -> R2 copy of Turso case_texts (case_texts/v1, verbatim), then
                 Supabase full_judgments (text hydrated from R2 by the wrapped client)
    PDFs      -> Cloudflare R2  pdfs/v1/{JOURNAL}/{YEAR}/{PAGE // 250}.zip  (member "{PAGE}.pdf")
    statutes  -> Cloudflare R2  statutes/legacy_app_provisions.json.gz (the 3,888
                 app-format rows Turso held; the curated store and Zilliz come first)

Function names and return shapes match the old Turso client so callers only
change their import. Every function returns None / [] on failure and never raises.
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_CASE_COLUMNS = "id, case_id, neutral_citation, case_title, court_name, full_text, headnote"
_CASE_CACHE_MAX = 2048
_case_cache: "OrderedDict[str, Optional[Dict[str, Any]]]" = OrderedDict()
_cache_lock = threading.Lock()
_CID_RE = re.compile(r"^((?:19|20)\d\d)_([A-Z()]+)_(\d+)$")
# Zilliz case_key carries a court code ("2020_PCRLJ_LHC_1445"); most full_judgments.case_id do not.
_COURT_KEY_RE = re.compile(r"^((?:19|20)\d\d_[A-Z()]+)_(?:SC|FSC|LHC|SHC|PHC|BHC|IHC|AJKHC|AJKSC|GBSAC|GBCC)_(\d+)$")

CASE_TEXT_PREFIX = "case_texts/v1"
_CT_CACHE_MAX = 64
_ct_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
PDF_PREFIX = "pdfs/v1"
PDF_BUNDLE_PAGES = 250
_BUNDLE_CACHE_MAX = 8
_bundle_cache: "OrderedDict[str, bytes]" = OrderedDict()
LEGACY_STATUTES_KEY = "statutes/legacy_app_provisions.json.gz"
_statutes: Optional[Dict[str, Dict[str, Any]]] = None
_statutes_by_act_sec: Dict[str, Dict[str, Any]] = {}
_statutes_lock = threading.Lock()


# ------------------------------------------------------------------ cases
def normalize_case_id(ident: str) -> str:
    """'2021 SCMR 1463' / '2021_scmr_1463' -> '2021_SCMR_1463' (the full_judgments.case_id form)."""
    return "_".join(str(ident or "").replace("_", " ").split()).upper()


def _variants(key: str) -> List[str]:
    m = _COURT_KEY_RE.match(key)
    return [key, f"{m.group(1)}_{m.group(2)}"] if m else [key]


def _split_case_id(case_id: str) -> Dict[str, Any]:
    m = _CID_RE.match(case_id or "")
    if not m:
        return {"year": None, "journal": None, "page": None}
    return {"year": int(m.group(1)), "journal": m.group(2), "page": int(m.group(3))}


def _normalize_case_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Same Type A / Type B split the Turso client applied."""
    if not row:
        return row
    from core.content_classification import classify_judgment_content
    c_lvl = classify_judgment_content(row)
    row["content_level"] = c_lvl
    row["text_type"] = c_lvl
    if c_lvl in ("headnote", "headnote_only"):
        raw_ft = row.get("full_text") or ""
        raw_hn = row.get("headnote") or ""
        if len(raw_ft) > len(raw_hn):
            row["headnote"] = raw_ft
        row["full_text"] = None
    elif c_lvl == "full_judgment" and row.get("full_text"):
        from core.structural_judgment_segmenter import parse_pakistan_law_site_document
        p = parse_pakistan_law_site_document(row["full_text"])
        if p.get("full_text"):
            row["full_text"] = p["full_text"]
            if not row.get("headnote") and p.get("headnote_text"):
                row["headnote"] = p.get("headnote_text")
    return row


def _shape(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k, v in _split_case_id(str(out.get("case_id") or "").upper()).items():
        if out.get(k) in (None, ""):
            out[k] = v
    return _normalize_case_record(out)


def _from_turso_copy(key: str) -> Optional[Dict[str, Any]]:
    """The verbatim Turso case_texts row (R2 copy) for any id variant, shaped like before."""
    for v in _variants(key):
        rec = get_case_text_record(v)
        if rec:
            return _shape(rec)
    return None


def _cache_get(key: str):
    with _cache_lock:
        if key in _case_cache:
            _case_cache.move_to_end(key)
            return True, _case_cache[key]
    return False, None


def _cache_put(key: str, val: Optional[Dict[str, Any]]) -> None:
    with _cache_lock:
        _case_cache[key] = val
        while len(_case_cache) > _CASE_CACHE_MAX:
            _case_cache.popitem(last=False)


def _supabase():
    try:
        from legal_ai.config import get_supabase_client
        return get_supabase_client()
    except Exception as err:  # pragma: no cover
        logger.warning(f"[CaseStore] Supabase unavailable: {err}")
        return None


def get_case_by_identifier(case_id_or_cit: str) -> Optional[Dict[str, Any]]:
    """One case by case_id ('2021_SCMR_1463') or citation ('2021 SCMR 1463')."""
    key = normalize_case_id(case_id_or_cit)
    if not key:
        return None
    hit, val = _cache_get(key)
    if hit:
        return val
    # 1. Turso's case_texts (now an R2 copy) was the primary store and often holds the
    #    full reported judgment where Supabase only has the portal summary.
    row = _from_turso_copy(key)
    if row:
        _cache_put(key, row)
        return row
    # 2. Supabase full_judgments (text hydrated from R2)
    sb = _supabase()
    if sb is None:
        return None
    try:
        variants = _variants(key)
        q = sb.table("full_judgments").select(_CASE_COLUMNS)
        q = q.eq("case_id", key) if len(variants) == 1 else q.in_("case_id", variants)
        res = q.limit(len(variants)).execute()
        got = {str(r.get("case_id") or "").upper(): r for r in (res.data or [])}
        hit = next((got[v] for v in variants if v in got), None)
        row = _shape(hit) if hit else None
    except Exception as err:
        logger.warning(f"[CaseStore] case lookup failed for {key}: {err}")
        return None
    _cache_put(key, row)
    return row


def get_cases_batch(identifiers: List[str]) -> List[Dict[str, Any]]:
    """Several cases in one query. Unknown identifiers are skipped."""
    keys = list(dict.fromkeys(normalize_case_id(i) for i in identifiers or [] if i))
    found: List[Dict[str, Any]] = []
    missing: List[str] = []
    for k in keys:
        hit, val = _cache_get(k)
        if not hit:
            val = _from_turso_copy(k)
            if val:
                _cache_put(k, val)
                hit = True
        if hit:
            if val and all(val is not f for f in found):
                found.append(val)
        else:
            missing.append(k)
    if not missing:
        return found
    sb = _supabase()
    if sb is None:
        return found
    try:
        for i in range(0, len(missing), 50):
            chunk = missing[i:i + 50]
            ask = list(dict.fromkeys(v for k in chunk for v in _variants(k)))
            res = sb.table("full_judgments").select(_CASE_COLUMNS).in_("case_id", ask).execute()
            got = {str(r.get("case_id") or "").upper(): r for r in (res.data or [])}
            shaped: Dict[str, Dict[str, Any]] = {}
            for k in chunk:
                v = next((v for v in _variants(k) if v in got), None)
                row = None
                if v:
                    row = shaped.get(v) or _shape(got[v])
                    shaped[v] = row
                _cache_put(k, row)
                if row and all(row is not f for f in found):
                    found.append(row)
    except Exception as err:
        logger.warning(f"[CaseStore] batch lookup failed: {err}")
    return found


# ------------------------------------------------------------------ Turso case_texts copy (R2)
def case_text_key(case_id: str) -> str:
    """Key of a case in the R2 copy of Turso case_texts: the case_id, upper-cased, as Turso stored it."""
    return str(case_id or "").strip().upper()


def case_text_shard_key(key: str, prefix: str = CASE_TEXT_PREFIX) -> str:
    import hashlib
    shard = hashlib.sha1(key.encode("utf-8")).hexdigest()[:3]
    return f"{prefix.strip('/')}/{shard}.json.gz" if prefix else f"{shard}.json.gz"


def get_case_text_record(case_id: str) -> Optional[Dict[str, Any]]:
    """Verbatim Turso case_texts row (all columns) from R2, or None."""
    key = case_text_key(case_id)
    if not key:
        return None
    obj = case_text_shard_key(key)
    with _cache_lock:
        shard = _ct_cache.get(obj)
        if shard is not None:
            _ct_cache.move_to_end(obj)
    if shard is None:
        try:
            from legal_ai.storage.r2_text_store import r2_configured, _signed_get
            if not r2_configured():
                return None
            raw = _signed_get(obj, timeout_s=6.0)
            shard = json.loads(gzip.decompress(raw).decode("utf-8")) if raw else {}
        except Exception as err:
            logger.warning(f"[CaseStore] case text shard {obj} unavailable: {err}")
            return None
        with _cache_lock:
            _ct_cache[obj] = shard
            while len(_ct_cache) > _CT_CACHE_MAX:
                _ct_cache.popitem(last=False)
    rec = shard.get(key)
    return dict(rec) if rec else None


# ------------------------------------------------------------------ PDFs
def pdf_bundle_key(journal: str, year: Union[int, str], page: Union[int, str], prefix: str = PDF_PREFIX) -> str:
    """R2 object holding the PDF for (journal, year, page): one ZIP per 250 pages of a journal-year."""
    return f"{prefix.strip('/')}/{str(journal).strip().upper()}/{int(year)}/{int(page) // PDF_BUNDLE_PAGES}.zip"


def _read_bundle(key: str) -> Optional[bytes]:
    with _cache_lock:
        if key in _bundle_cache:
            _bundle_cache.move_to_end(key)
            return _bundle_cache[key]
    from legal_ai.storage.r2_text_store import _signed_get
    data = _signed_get(key, timeout_s=10.0)
    if data:
        with _cache_lock:
            _bundle_cache[key] = data
            while len(_bundle_cache) > _BUNDLE_CACHE_MAX:
                _bundle_cache.popitem(last=False)
    return data


def get_case_pdf_bytes(
    case_id: str,
    target_year: Optional[Union[int, str]] = None,
    target_journal: Optional[str] = None,
    target_page: Optional[Union[int, str]] = None,
) -> Optional[bytes]:
    """Original scanned judgment PDF from R2, located by (journal, year, page)."""
    journal = (target_journal or "").strip().upper()
    try:
        year = int(target_year) if target_year is not None else None
    except (TypeError, ValueError):
        year = None
    try:
        page = int(target_page) if target_page is not None else None
    except (TypeError, ValueError):
        page = None
    if not (journal and year and page) and case_id:
        m1 = re.search(r'\b(19\d\d|20\d\d)[_\s]+([a-zA-Z\(\)]+)[_\s]+(\d+)\b', case_id)
        m2 = None if m1 else re.search(r'\b([a-zA-Z\(\)]+)[_\s]+(19\d\d|20\d\d)[_\s]+(\d+)\b', case_id)
        if m1:
            year, journal, page = int(m1.group(1)), m1.group(2).upper(), int(m1.group(3))
        elif m2:
            journal, year, page = m2.group(1).upper(), int(m2.group(2)), int(m2.group(3))
    if not (journal and year and page):
        return None
    try:
        import io
        import zipfile
        from legal_ai.storage.r2_text_store import r2_configured
        if not r2_configured():
            return None
        bundle = _read_bundle(pdf_bundle_key(journal, year, page))
        if not bundle:
            return None
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            data = zf.read(f"{int(page)}.pdf")
    except KeyError:
        return None  # that page has no PDF in its bundle
    except Exception as err:
        logger.warning(f"[CaseStore] PDF fetch failed for {journal} {year} {page}: {err}")
        return None
    return data if data and data.startswith(b"%PDF") else None


# ------------------------------------------------------------------ legacy statutes
def _load_statutes() -> Dict[str, Dict[str, Any]]:
    global _statutes
    if _statutes is not None:
        return _statutes
    with _statutes_lock:
        if _statutes is not None:
            return _statutes
        data: Dict[str, Dict[str, Any]] = {}
        try:
            from legal_ai.storage.r2_text_store import r2_configured, _signed_get
            if r2_configured():
                raw = _signed_get(LEGACY_STATUTES_KEY, timeout_s=8.0)
                if raw:
                    for rec in json.loads(gzip.decompress(raw).decode("utf-8")):
                        cid = str(rec.get("canonical_id") or "").upper()
                        if cid:
                            data[cid] = rec
                            act = str(rec.get("act_code") or "").upper()
                            sec = str(rec.get("section_num") or "").upper()
                            if act and sec:
                                _statutes_by_act_sec.setdefault(f"{act}|{sec}", rec)
        except Exception as err:
            logger.warning(f"[CaseStore] legacy statutes unavailable: {err}")
            return {}  # retry on the next call
        _statutes = data
        return _statutes


def get_statute_provision(canonical_id_or_sec: str, act_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Last-resort provision lookup by canonical_id, or by (act_code, section)."""
    ident = str(canonical_id_or_sec or "").strip().upper()
    if not ident:
        return None
    store = _load_statutes()
    rec = store.get(ident)
    if rec:
        return rec
    act = (act_code or "").strip().upper()
    if act:
        sec = ident.replace(f"{act}_SEC_", "").replace(f"{act}_ART_", "").replace(f"{act}_ORD_", "").strip()
        return _statutes_by_act_sec.get(f"{act}|{sec}")
    return None
