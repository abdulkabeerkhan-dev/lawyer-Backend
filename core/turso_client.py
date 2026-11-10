"""
Turso / libSQL Database Client for Section AI Master Corpus
Provides low-latency access to 278k+ authentic case texts and FTS5 search index.
"""

import os
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_raw_turso_url = os.environ.get(
    "TURSO_DATABASE_URL_PIPELINE",
    os.environ.get("TURSO_DATABASE_URL", os.environ.get("TURSO_URL", ""))
)
if _raw_turso_url.startswith("libsql://"):
    _raw_turso_url = _raw_turso_url.replace("libsql://", "https://")
if _raw_turso_url and not _raw_turso_url.endswith("/v2/pipeline"):
    _raw_turso_url = _raw_turso_url.rstrip("/") + "/v2/pipeline"

TURSO_URL = _raw_turso_url or "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
TURSO_TOKEN = os.environ.get(
    "TURSO_AUTH_TOKEN",
    os.environ.get(
        "TURSO_TOKEN",
        "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"
    )
)

# In-memory LRU-like cache for hot case lookups
_CASE_CACHE: Dict[str, Dict[str, Any]] = {}
_STATUTE_CACHE: Dict[str, Dict[str, Any]] = {}

# Fast Circuit Breaker for Turso network timeouts
_TURSO_CIRCUIT_OPEN_UNTIL: float = 0.0

def is_turso_circuit_open() -> bool:
    global _TURSO_CIRCUIT_OPEN_UNTIL
    return time.time() < _TURSO_CIRCUIT_OPEN_UNTIL

def trip_turso_circuit(duration: float = 5.0):
    global _TURSO_CIRCUIT_OPEN_UNTIL
    _TURSO_CIRCUIT_OPEN_UNTIL = time.time() + duration

def execute_turso_pipeline(stmts: List[Dict[str, Any]], timeout: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """
    Executes one or more SQL statements against the Turso libSQL pipeline.
    Features strict 3s timeout and circuit breaker to prevent cascading worker hangs.
    """
    if not TURSO_TOKEN or not TURSO_URL:
        return []
    if is_turso_circuit_open():
        return []

    requests = []
    for s in stmts:
        stmt_obj = {"sql": s["sql"]}
        if "args" in s and s["args"]:
            clean_args = []
            for a in s["args"]:
                arg_copy = dict(a)
                # libSQL pipeline requires integer values to be serialized as string
                if arg_copy.get("type") == "integer" and not isinstance(arg_copy.get("value"), str) and arg_copy.get("value") is not None:
                    arg_copy["value"] = str(arg_copy["value"])
                clean_args.append(arg_copy)
            stmt_obj["args"] = clean_args
        requests.append({"type": "execute", "stmt": stmt_obj})

    payload = json.dumps({"requests": requests}).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            TURSO_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {TURSO_TOKEN}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for res_item in data.get("results", []):
                    if res_item.get("type") == "ok":
                        exec_res = res_item.get("response", {}).get("result", {})
                        cols = [c["name"] for c in exec_res.get("cols", [])]
                        rows = []
                        for row in exec_res.get("rows", []):
                            row_dict = {}
                            for i, cell in enumerate(row):
                                val = cell.get("value")
                                if cell.get("type") == "integer" and val is not None:
                                    val = int(val)
                                row_dict[cols[i]] = val
                            rows.append(row_dict)
                        results.append({"cols": cols, "rows": rows, "affected": exec_res.get("affected_row_count", 0)})
                    else:
                        results.append({"error": res_item.get("error")})
                return results
        except urllib.error.HTTPError as he:
            err_body = ""
            try:
                err_body = he.read().decode("utf-8")
            except Exception:
                pass
            logger.warning(f"Turso HTTP {he.code} client error: {err_body or he}")
            return []
        except Exception as e:
            if attempt == max_retries:
                trip_turso_circuit(5.0)
                logger.warning(f"Turso pipeline timeout/failure ({e}). Circuit breaker tripped for 5s.")
            else:
                time.sleep(0.2)
    return []

def get_case_by_identifier(case_id_or_cit: str) -> Optional[Dict[str, Any]]:
    """
    Looks up a single case by case_id (e.g. '2021_SCMR_1463') or neutral citation ('2021 SCMR 1463').
    Uses fast exact index lookups (< 0.5s) instead of unindexed table scan.
    """
    if is_turso_circuit_open():
        return None

    cleaned = case_id_or_cit.strip()
    norm_cit = " ".join(cleaned.replace("_", " ").split())
    norm_id = cleaned.replace(" ", "_").upper()

    if norm_id in _CASE_CACHE:
        return _CASE_CACHE[norm_id]
    if norm_cit in _CASE_CACHE:
        return _CASE_CACHE[norm_cit]

    # 1. Primary Key lookup by case_id (< 0.2s)
    sql_id = """
    SELECT case_id, neutral_citation, case_title, court_name, year, journal, page, content_level, full_text, headnote
    FROM case_texts
    WHERE case_id = ?
    LIMIT 1
    """
    res = execute_turso_pipeline([{"sql": sql_id, "args": [{"type": "text", "value": norm_id}]}], timeout=3, max_retries=1)
    if res and "rows" in res[0] and res[0]["rows"]:
        case_data = res[0]["rows"][0]
        case_data["text_type"] = case_data.get("content_level") or ("headnote" if case_data.get("headnote") and not case_data.get("full_text") else "full_judgment")
        _CASE_CACHE[norm_id] = case_data
        _CASE_CACHE[norm_cit] = case_data
        return case_data

    # 2. Indexed lookup by neutral_citation (< 0.5s)
    sql_cit = """
    SELECT case_id, neutral_citation, case_title, court_name, year, journal, page, content_level, full_text, headnote
    FROM case_texts
    WHERE neutral_citation = ? OR neutral_citation = ?
    LIMIT 1
    """
    args_cit = [
        {"type": "text", "value": norm_cit},
        {"type": "text", "value": cleaned}
    ]
    res2 = execute_turso_pipeline([{"sql": sql_cit, "args": args_cit}], timeout=3, max_retries=1)
    if res2 and "rows" in res2[0] and res2[0]["rows"]:
        case_data = res2[0]["rows"][0]
        case_data["text_type"] = case_data.get("content_level") or ("headnote" if case_data.get("headnote") and not case_data.get("full_text") else "full_judgment")
        _CASE_CACHE[norm_id] = case_data
        _CASE_CACHE[norm_cit] = case_data
        return case_data
    return None

def get_cases_batch(identifiers: List[str]) -> List[Dict[str, Any]]:
    """
    Fetches multiple cases in a single batch query.
    """
    if not identifiers or is_turso_circuit_open():
        return []

    found = []
    missing_ids = []
    for ident in identifiers:
        c_norm = ident.strip().replace(" ", "_").upper()
        if c_norm in _CASE_CACHE:
            found.append(_CASE_CACHE[c_norm])
        else:
            missing_ids.append(ident.strip())

    if not missing_ids:
        return found

    placeholders = ", ".join(["?"] * len(missing_ids))
    sql = f"""
    SELECT case_id, neutral_citation, case_title, court_name, year, journal, page, content_level, full_text, headnote
    FROM case_texts
    WHERE case_id IN ({placeholders}) OR neutral_citation IN ({placeholders})
    """
    args = [{"type": "text", "value": m} for m in missing_ids] + [{"type": "text", "value": m} for m in missing_ids]

    res = execute_turso_pipeline([{"sql": sql, "args": args}], timeout=3, max_retries=1)
    if res and "rows" in res[0]:
        for row in res[0]["rows"]:
            row["text_type"] = row.get("content_level") or ("headnote" if row.get("headnote") and not row.get("full_text") else "full_judgment")
            c_norm = row.get("case_id", "").upper()
            _CASE_CACHE[c_norm] = row
            found.append(row)

    return found

def search_cases_fts(query_text: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Executes Okapi BM25 full-text search across the master judicial corpus in Turso.
    """
    if is_turso_circuit_open():
        return []
    clean_q = " ".join([w for w in query_text.replace('"', '').replace("'", "").split() if len(w) > 2])
    if not clean_q:
        return []

    sql = """
    SELECT c.case_id, c.neutral_citation, c.case_title, c.court_name, c.year, c.journal, c.content_level,
           snippet(case_texts_fts, 2, '<b>', '</b>', '...', 25) AS snippet,
           bm25(case_texts_fts) AS rank_score
    FROM case_texts_fts f
    JOIN case_texts c ON c.case_id = f.case_id
    WHERE case_texts_fts MATCH ?
    ORDER BY rank_score ASC
    LIMIT ?
    """
    args = [
        {"type": "text", "value": clean_q},
        {"type": "integer", "value": limit}
    ]

    res = execute_turso_pipeline([{"sql": sql, "args": args}], timeout=3, max_retries=1)
    if res and "rows" in res[0]:
        return res[0]["rows"]
    return []

def get_case_pdf_bytes(
    case_id: str,
    target_year: Optional[int] = None,
    target_journal: Optional[str] = None,
    target_page: Optional[int] = None
) -> Optional[bytes]:
    """
    Retrieves compressed/base64 original scanned judgment PDF bytes from Turso case_pdfs table.
    """
    if is_turso_circuit_open():
        return None
    import base64
    sql = """
    SELECT pdf_base64
    FROM case_pdfs
    WHERE case_id = ?
    LIMIT 1
    """
    args = [{"type": "text", "value": case_id.strip()}]
    res = execute_turso_pipeline([{"sql": sql, "args": args}], timeout=3, max_retries=1)
    if res and "rows" in res[0] and res[0]["rows"]:
        b64_str = res[0]["rows"][0].get("pdf_base64")
        if b64_str:
            try:
                return base64.b64decode(b64_str)
            except Exception as e:
                logger.warning(f"Failed to decode base64 PDF from Turso: {e}")
    return None

def get_statute_provision(canonical_id_or_sec: str, act_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Looks up a statutory provision from Turso statute_provisions table by canonical_id
    using fast exact indexed lookups (< 0.2s) with caching and circuit breaker protection.
    """
    if is_turso_circuit_open():
        return None

    ident = canonical_id_or_sec.strip().upper()
    act = act_code.strip().upper() if act_code else None

    cache_key = f"{act}_{ident}" if act else ident
    if cache_key in _STATUTE_CACHE:
        return _STATUTE_CACHE[cache_key]

    # 1. Check by exact canonical_id (Primary Key index < 0.2s)
    sql = """
    SELECT canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force
    FROM statute_provisions
    WHERE canonical_id = ?
    LIMIT 1
    """
    args = [{"type": "text", "value": ident}]
    res = execute_turso_pipeline([{"sql": sql, "args": args}], timeout=3, max_retries=1)
    if res and "rows" in res[0] and res[0]["rows"]:
        prov = res[0]["rows"][0]
        _STATUTE_CACHE[cache_key] = prov
        return prov

    # 2. If act_code provided, check by exact (act_code, section_num) index (< 0.3s)
    if act:
        sec_clean = ident.replace(f"{act}_SEC_", "").replace(f"{act}_ART_", "").replace(f"{act}_ORD_", "").strip()
        sql2 = """
        SELECT canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force
        FROM statute_provisions
        WHERE act_code = ? AND section_num = ?
        LIMIT 1
        """
        args2 = [
            {"type": "text", "value": act},
            {"type": "text", "value": sec_clean}
        ]
        res2 = execute_turso_pipeline([{"sql": sql2, "args": args2}], timeout=3, max_retries=1)
        if res2 and "rows" in res2[0] and res2[0]["rows"]:
            prov = res2[0]["rows"][0]
            _STATUTE_CACHE[cache_key] = prov
            return prov

    return None

def search_statutes(query_text: str, act_code: Optional[str] = None, domain: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Searches statutory provisions in Turso by text or title match.
    """
    if is_turso_circuit_open():
        return []

    words = [w for w in query_text.replace("'", "").replace('"', '').split() if len(w) > 2]
    if not words:
        return []

    word_clauses = []
    args = []
    for w in words[:4]:
        word_clauses.append("(verbatim_text LIKE ? OR title LIKE ?)")
        args.extend([{"type": "text", "value": f"%{w}%"}, {"type": "text", "value": f"%{w}%"}])

    clauses = ["(" + " OR ".join(word_clauses) + ")"]

    if act_code:
        clauses.append("act_code = ?")
        args.append({"type": "text", "value": act_code.strip().upper()})
    if domain:
        clauses.append("domain = ?")
        args.append({"type": "text", "value": domain.strip().lower()})

    sql = f"""
    SELECT canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force
    FROM statute_provisions
    WHERE {' AND '.join(clauses)}
    LIMIT ?
    """
    args.append({"type": "integer", "value": limit})

    res = execute_turso_pipeline([{"sql": sql, "args": args}], timeout=3, max_retries=1)
    if res and "rows" in res[0]:
        return res[0]["rows"]
    return []
