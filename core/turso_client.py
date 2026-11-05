"""
Turso / libSQL Database Client for Section AI Master Corpus
Provides low-latency access to 278k+ authentic case texts and FTS5 search index.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TURSO_URL = os.environ.get(
    "TURSO_DATABASE_URL_PIPELINE",
    "https://section-legal-db-lawyerbackend.aws-ap-south-1.turso.io/v2/pipeline"
)
TURSO_TOKEN = os.environ.get(
    "TURSO_AUTH_TOKEN",
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTM4OTc2NTQsImlkIjoiMDFhMWFjYTEtOTIwMS03OTE3LTlmMzctZjY0ZDg5NDM1NTFkIiwia2lkIjoianNXWWVWbGJYWlg2Yy1rSFNHVExWU3UwRWcxSnV3WGVvTWNuUGpPWERFNCIsInJpZCI6Ijg0MjQ1ODg0LTgzOGUtNDZlOC05YmNkLTcyMzZhNzdmNTljMCJ9.jvdO06iANK63zeYn8JAm6Iyjnz4RuLVQnvhPWoJ-OGlhzGNo70ehyH57cPKDUJBJU3xcNldel3KT_BwLqBCwCQ"
)

# In-memory LRU-like cache for hot case lookups
_CASE_CACHE: Dict[str, Dict[str, Any]] = {}

def execute_turso_pipeline(stmts: List[Dict[str, Any]], timeout: int = 15) -> List[Dict[str, Any]]:
    """
    Executes one or more SQL statements against the Turso libSQL pipeline.
    stmts format: [{"sql": "...", "args": [{"type": "text", "value": "..."}, ...]}]
    """
    if not TURSO_TOKEN or not TURSO_URL:
        logger.warning("Turso credentials not configured.")
        return []

    requests = []
    for s in stmts:
        stmt_obj = {"sql": s["sql"]}
        if "args" in s and s["args"]:
            stmt_obj["args"] = s["args"]
        requests.append({"type": "execute", "stmt": stmt_obj})

    payload = json.dumps({"requests": requests}).encode("utf-8")
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
    except Exception as e:
        logger.error(f"Turso pipeline execution error: {e}")
        return []

def get_case_by_identifier(case_id_or_cit: str) -> Optional[Dict[str, Any]]:
    """
    Looks up a single case by case_id (e.g. '2021_SCMR_1463') or neutral citation ('2021 SCMR 1463').
    """
    cleaned = case_id_or_cit.strip()
    norm_cit = " ".join(cleaned.replace("_", " ").split())
    norm_id = cleaned.replace(" ", "_").upper()

    if norm_id in _CASE_CACHE:
        return _CASE_CACHE[norm_id]

    sql = """
    SELECT case_id, neutral_citation, case_title, court_name, year, journal, page, content_level, full_text, headnote
    FROM case_texts
    WHERE case_id = ? OR UPPER(neutral_citation) = ? OR UPPER(neutral_citation) = ?
    LIMIT 1
    """
    args = [
        {"type": "text", "value": norm_id},
        {"type": "text", "value": norm_cit.upper()},
        {"type": "text", "value": cleaned.upper()}
    ]

    res = execute_turso_pipeline([{"sql": sql, "args": args}])
    if res and "rows" in res[0] and res[0]["rows"]:
        case_data = res[0]["rows"][0]
        _CASE_CACHE[norm_id] = case_data
        return case_data
    return None

def get_cases_batch(identifiers: List[str]) -> List[Dict[str, Any]]:
    """
    Fetches multiple cases in a single batch query.
    """
    if not identifiers:
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

    res = execute_turso_pipeline([{"sql": sql, "args": args}])
    if res and "rows" in res[0]:
        for row in res[0]["rows"]:
            c_norm = row.get("case_id", "").upper()
            _CASE_CACHE[c_norm] = row
            found.append(row)

    return found

def search_cases_fts(query_text: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Executes Okapi BM25 full-text search across the master judicial corpus in Turso.
    """
    clean_q = " ".join([w for w in query_text.replace('"', '').replace("'", "").split() if len(w) > 2])
    if not clean_q:
        return []

    sql = """
    SELECT c.case_id, c.neutral_citation, c.case_title, c.court_name, c.year, c.journal, c.content_level,
           snippet(case_texts_fts, 2, '<b>', '</b>', '...', 25) AS snippet,
           bm25(case_texts_fts) AS rank
    FROM case_texts_fts
    JOIN case_texts c ON case_texts_fts.rowid = c.rowid
    WHERE case_texts_fts MATCH ?
    ORDER BY rank
    LIMIT ?
    """
    args = [
        {"type": "text", "value": clean_q},
        {"type": "integer", "value": str(limit)}
    ]

    res = execute_turso_pipeline([{"sql": sql, "args": args}])
    if res and "rows" in res[0]:
        return res[0]["rows"]
    return []

def get_case_pdf_bytes(
    journal: str,
    year: Any,
    page: Optional[Any] = None,
    case_id: Optional[str] = None
) -> Optional[bytes]:
    """
    Fetches authentic PDF bytes from Turso case_pdfs table.
    Works anywhere including Railway container where local drive I: is unavailable.
    """
    import base64
    norm_jn = str(journal).upper().strip() if journal else ""
    norm_yr = int(year) if year and str(year).isdigit() else None
    norm_pg = int(page) if page and str(page).isdigit() else None

    sql = """
    SELECT pdf_base64 FROM case_pdfs
    WHERE (journal = ? AND year = ? AND page = ?) OR case_id = ?
    LIMIT 1
    """
    args = [
        {"type": "text", "value": norm_jn},
        {"type": "integer", "value": str(norm_yr) if norm_yr else None},
        {"type": "integer", "value": str(norm_pg) if norm_pg else None},
        {"type": "text", "value": case_id or ""}
    ]

    res = execute_turso_pipeline([{"sql": sql, "args": args}])
    if res and "rows" in res[0] and res[0]["rows"]:
        b64_str = res[0]["rows"][0].get("pdf_base64")
        if b64_str:
            try:
                raw_bytes = base64.b64decode(b64_str)
                if raw_bytes.startswith(b"%PDF"):
                    return raw_bytes
            except Exception as e:
                logger.warning(f"Failed to decode base64 PDF from Turso: {e}")
    return None

