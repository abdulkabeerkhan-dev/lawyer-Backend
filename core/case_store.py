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
_CASE_CACHE_MAX = 128  # full case texts are large; keep the hot set only (1 GB container)
_case_cache: "OrderedDict[str, Optional[Dict[str, Any]]]" = OrderedDict()
_cache_lock = threading.Lock()
_CID_RE = re.compile(r"^((?:19|20)\d\d)_([A-Z()]+)_(\d+)$")
# Zilliz case_key carries a court code ("2020_PCRLJ_LHC_1445"); most full_judgments.case_id do not.
_COURT_KEY_RE = re.compile(r"^((?:19|20)\d\d_[A-Z()]+)_(?:SC|FSC|LHC|SHC|PHC|BHC|IHC|AJKHC|AJKSC|GBSAC|GBCC)_(\d+)$")

CASE_TEXT_PREFIX = "case_texts/v1"
_CT_CACHE_MAX = 6
_ct_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
PDF_PREFIX = "pdfs/v1"
PDF_BUNDLE_PAGES = 250
_BUNDLE_CACHE_MAX = 2
_bundle_cache: "OrderedDict[str, bytes]" = OrderedDict()
LEGACY_STATUTES_KEY = "statutes/legacy_app_provisions.json.gz"
_statutes: Optional[Dict[str, Dict[str, Any]]] = None
_statutes_by_act_sec: Dict[str, Dict[str, Any]] = {}
_statutes_lock = threading.Lock()


# ------------------------------------------------------------------ cases
def normalize_case_id(ident: str) -> str:
    """'2021 SCMR 1463' / '2021_scmr_1463' -> '2021_SCMR_1463' (the full_judgments.case_id form)."""
    return "_".join(str(ident or "").replace("_", " ").split()).upper()


# Zilliz court code -> (full_judgments PLD case_id court, PLD citation court abbreviation)
_PLD_COURTS = {"SC": ("SC", "SC"), "LHC": ("LAH", "Lah"), "SHC": ("KAR", "Kar"), "PHC": ("PESH", "Pesh"),
               "BHC": ("QTA", "Quetta"), "IHC": ("ISL", "Isl"), "FSC": ("FSC", "FSC"),
               "AJKSC": ("SCAJK", "AJ&K SC"), "AJKHC": ("HCAJK", "AJ&K HC")}


def _variants(key: str) -> List[str]:
    m = _COURT_KEY_RE.match(key)
    if not m:
        return [key]
    out = [key, f"{m.group(1)}_{m.group(2)}"]
    parts = key.split("_")
    if len(parts) == 4 and parts[1] == "PLD" and parts[2] in _PLD_COURTS:
        out.append(f"{parts[0]}_PLD_{_PLD_COURTS[parts[2]][0]}_{parts[3]}")
    return list(dict.fromkeys(out))


def _pld_citation_form(key: str) -> Optional[str]:
    """2024_PLD_LHC_1 -> 'PLD 2024 Lah 1' (how full_judgments writes PLD citations)."""
    parts = (key or "").split("_")
    if len(parts) == 4 and parts[1] == "PLD" and parts[2] in _PLD_COURTS:
        return f"PLD {parts[0]} {_PLD_COURTS[parts[2]][1]} {parts[3]}"
    return None


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


def _court_hint(key: str) -> Optional[str]:
    """'2020_PCRLJ_LHC_1445' -> 'LHC' (the court code a Zilliz case_key carries)."""
    m = re.match(r"^(?:18|19|20)\d\d_[A-Z()]+_([A-Z]+)_\d+$", key or "")
    return m.group(1) if m else None


def _pick(key: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The row that really is `key`. In ~18% of full_judgments rows the case_id page is a
    serial number, not the citation page (1978_SCMR_31 is really 1978 SCMR 81), so a bare
    case_id match can be a different judgment. Match on neutral_citation first, use the
    court as a tie-breaker, and never return a row whose own citation says otherwise."""
    from legal_ai.verification.citation_keys import citation_key
    from legal_ai.storage.text_hydration import court_code
    ck = citation_key(key)
    if not ck:
        return next((r for r in rows if str(r.get("case_id") or "").upper() == key), None)
    same_cit = [r for r in rows if citation_key(str(r.get("neutral_citation") or "")) == ck]
    if same_cit:
        hint = _court_hint(key)
        if hint:
            by_court = [r for r in same_cit if court_code(r.get("court_name")) == hint]
            if by_court:
                return by_court[0]
        exact = [r for r in same_cit if str(r.get("case_id") or "").upper() in _variants(key)]
        return (exact or same_cit)[0]
    # No row carries this citation: accept a case_id match only if the row has no
    # parseable citation of its own (otherwise it is a different judgment).
    for r in rows:
        if str(r.get("case_id") or "").upper() in _variants(key) and not citation_key(str(r.get("neutral_citation") or "")):
            return r
    return None


def _supabase_rows(keys: List[str], columns: str = _CASE_COLUMNS, shape: bool = True) -> Dict[str, Optional[Dict[str, Any]]]:
    """key -> shaped row or None, for keys not in the Turso copy. Raises on DB errors."""
    from legal_ai.verification.citation_keys import citation_key
    sb = _supabase()
    if sb is None:
        raise RuntimeError("Supabase unavailable")
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for i in range(0, len(keys), 40):
        chunk = keys[i:i + 40]
        ids = list(dict.fromkeys(v for k in chunk for v in _variants(k)))
        forms: List[str] = []
        for k in chunk:
            ck = citation_key(k)
            if ck:
                y, j, p = ck
                forms += [f"{y} {j} {p}", f"{j} {y} {p}"]
                pf = _pld_citation_form(k)
                if pf:
                    forms.append(pf)
        rows: Dict[str, Dict[str, Any]] = {}
        res = sb.table("full_judgments").select(columns).in_("case_id", ids).execute()
        for r in res.data or []:
            rows[str(r.get("id"))] = r
        if forms:
            res = sb.table("full_judgments").select(columns).in_("neutral_citation", list(dict.fromkeys(forms))).execute()
            for r in res.data or []:
                rows[str(r.get("id"))] = r
        pool = list(rows.values())
        for k in chunk:
            hit = _pick(k, pool)
            out[k] = (_shape(dict(hit)) if shape else dict(hit)) if hit else None
    return out


def retrieval_statuses(keys: List[str]) -> Dict[str, Optional[str]]:
    """Zilliz case_key (or any case id) -> full_judgments.retrieval_status ('' when the row
    has none, None when no row is this case). Zilliz keys carry a court code
    (2005_CLC_SHC_1241) that full_judgments.case_id does not (2005_CLC_1241), so a plain
    case_id lookup misses most cases; match on the real citation instead. Raises on DB errors."""
    keys = [k for k in dict.fromkeys(str(k or "").strip().upper() for k in keys) if k]
    rows = _supabase_rows(keys, columns="id, case_id, neutral_citation, court_name, retrieval_status", shape=False)
    return {k: (None if r is None else str(r.get("retrieval_status") or "").lower()) for k, r in rows.items()}


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
    # 2. Supabase full_judgments (text hydrated from R2), matched on the real citation
    try:
        row = _supabase_rows([key]).get(key)
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
    try:
        got = _supabase_rows(missing)
    except Exception as err:
        logger.warning(f"[CaseStore] batch lookup failed: {err}")
        return found
    for k in missing:
        row = got.get(k)
        _cache_put(k, row)
        if row and all(row.get("id") != f.get("id") or row.get("id") is None for f in found):
            found.append(row)
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
        # Handles every citation/key form, including Zilliz keys with a court code
        # (2003_PLD_SC_102), which the old year_journal_page pattern could not parse.
        from legal_ai.verification.citation_keys import citation_key
        ck = citation_key(case_id)
        if ck:
            year, journal, page = int(ck[0]), ck[1], int(ck[2])
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
    if not (data and data.startswith(b"%PDF")):
        return None
    if journal in _SHARED_SERIES_JOURNALS and not _pdf_matches_case(data, case_id or f"{year}_{journal}_{page}"):
        logger.warning(f"[CaseStore] PDF {journal} {year} {page} does not match the requested case; not served")
        return None
    return data


# PLD and YLR number each court's series separately, but the PDF archive is keyed only by
# journal/year/page, so one PDF can stand for several judgments (4,694 such PDFs).
_SHARED_SERIES_JOURNALS = {"PLD", "YLR"}
_TITLE_STOP = {"THE", "AND", "VS", "VERSUS", "STATE", "OTHERS", "OTHER", "THROUGH", "GOVERNMENT", "PAKISTAN",
               "MST", "MUHAMMAD", "MOHAMMAD", "SECRETARY", "PROVINCE", "FEDERATION", "LTD", "LIMITED", "ANOTHER", "AHMAD",
               "AHMED", "KHAN", "ALI", "SHAH", "CHAIRMAN", "COMMISSIONER", "PUNJAB", "SINDH"}


def _pdf_matches_case(pdf: bytes, case_id: str) -> bool:
    """True when the PDF's first page names a distinctive party of the requested case.
    Unknown title or unreadable PDF -> True (do not block on missing information)."""
    try:
        rec = get_case_by_identifier(case_id)
        title = str((rec or {}).get("case_title") or "")
        words = {w for w in re.findall(r"[A-Z][A-Z]{3,}", title.upper()) if w not in _TITLE_STOP}
        if not words:
            return True
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        head = doc[0].get_text().upper() if doc.page_count else ""
        if not head.strip():
            return True
        return any(w in head for w in words)
    except Exception as err:
        logger.warning(f"[CaseStore] PDF/case match check skipped: {err}")
        return True


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
