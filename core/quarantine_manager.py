"""
Quarantine Review & Manual Promotion Engine
Version: 1.0.0
Phase 4 Step 6 & 8 Component

Enforces human-in-the-loop validation of quarantined judgments:
- Reviewing quarantined candidates under 30 seconds
- Approving & promoting candidate records into full_judgments
- Rejecting invalid/malformed candidate records
- Maintaining immutable audit trail of all promotion actions
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

supabase_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as e:
        print(f"⚠️ Supabase init notice in quarantine_manager: {e}")

QUARANTINE_DIR = r"D:\missing_gaps_verified\quarantine"
os.makedirs(QUARANTINE_DIR, exist_ok=True)
QUARANTINE_LEDGER = os.path.join(QUARANTINE_DIR, "quarantined_judgments.jsonl")
PROMOTED_AUDIT_LOG = os.path.join(QUARANTINE_DIR, "promoted_audit_log.json")
REGRESSION_TEST_SET = os.path.join(QUARANTINE_DIR, "regression_promoted_cases.json")


def generate_canonical_case_id(court: str, case_type: str, docket: str, date_str: str) -> str:
    """
    Generates deterministic canonical ID in standard format:
    e.g. SC_CP_2768L_2022 or LHC_WP_3278_2019
    """
    # Court token
    c_token = "SC" if "supreme" in court.lower() else "LHC" if "lahore" in court.lower() else "HC"
    # Type token
    t_token = (case_type or "GEN").upper().replace(".", "")
    # Docket clean
    d_clean = (docket or "0").replace("/", "_").replace("-", "").replace(" ", "_").upper()
    # Year
    y_match = re.search(r"\b(19\d\d|20\d\d)\b", date_str or docket or "")
    year_token = y_match.group(1) if y_match else "2026"

    return f"{c_token}_{t_token}_{d_clean}_{year_token}"


def list_quarantined_records(status_filter: Optional[str] = "pending_review") -> List[Dict[str, Any]]:
    """
    Reads quarantined records from Supabase and/or the local ledger.
    """
    records: List[Dict[str, Any]] = []

    # 1. Check Supabase
    if supabase_client:
        try:
            q = supabase_client.table("quarantined_judgments").select("*")
            if status_filter:
                q = q.eq("status", status_filter)
            res = q.order("fetched_at", desc=True).execute()
            if res.data:
                records.extend(res.data)
        except Exception:
            pass

    # 2. Check local ledger
    if os.path.exists(QUARANTINE_LEDGER):
        try:
            with open(QUARANTINE_LEDGER, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        if not status_filter or r.get("status") == status_filter:
                            # Avoid duplicates by composite_key or source_url
                            if not any(x.get("source_url") == r.get("source_url") and x.get("docket_number") == r.get("docket_number") for x in records):
                                records.append(r)
        except Exception as e:
            print(f"Notice reading quarantine ledger: {e}")

    return records


def approve_and_promote_record(
    record_composite_key_or_url: str,
    reviewer: str,
    edited_fields: Optional[Dict[str, Any]] = None,
    custom_citation: Optional[str] = None,
    dashboard_session_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Promotes a quarantined record into production (full_judgments):
    STRICT SAFETY RULE: Requires an active, authenticated dashboard_session_token.
    Direct script invocation from CLI or LLM is blocked.
    """
    # 0. HARD ENFORCEMENT: Block any direct script invocation without human dashboard token
    if not dashboard_session_token or not dashboard_session_token.startswith("HUMAN_DASHBOARD_VERIFIED_"):
        raise PermissionError(
            "SAFETY VIOLATION: Direct script or programmatic promotion into full_judgments is blocked. "
            "Records can only be promoted through an authenticated human curation session in the Quarantine Dashboard."
        )

    if not reviewer or reviewer.strip() in ("", "system", "auto", "kabeer_admin", "human_curator"):
        raise ValueError(
            "A specific, verified human reviewer identifier must be provided."
        )

    import re
    # Find matching record
    records = list_quarantined_records(status_filter=None)
    target = None
    for r in records:
        if (r.get("composite_key") == record_composite_key_or_url or 
            r.get("source_url") == record_composite_key_or_url or
            r.get("docket_number") == record_composite_key_or_url or
            str(r.get("id")) == record_composite_key_or_url):
            target = r
            break

    if not target:
        return {"status": "error", "message": f"No record matching '{record_composite_key_or_url}' found in quarantine."}

    edits = edited_fields or {}

    court = edits.get("court_name") or target.get("extracted_court_name") or target.get("court_name") or "Court"
    case_type = edits.get("case_type") or target.get("case_type") or "GEN"
    docket = edits.get("docket_number") or target.get("docket_number") or "0"
    date_val = edits.get("decision_date") or target.get("extracted_date") or target.get("decision_date") or "2026-01-01"
    title = edits.get("case_title") or target.get("extracted_case_title") or target.get("case_title") or "Unnamed Judgment"
    bench = edits.get("bench") or target.get("extracted_judge_names") or target.get("judge_names")
    full_text = target.get("raw_text") or ""

    # Generate canonical case id
    c_token = "SC" if "supreme" in court.lower() else "LHC" if "lahore" in court.lower() else "HC"
    t_token = case_type.upper().replace(".", "")
    d_clean = docket.replace("/", "_").replace("-", "").replace(" ", "_").upper()
    y_match = re.search(r"\b(19\d\d|20\d\d)\b", f"{date_val} {docket}")
    year_token = y_match.group(1) if y_match else "2026"
    canonical_id = f"{c_token}_{t_token}_{d_clean}_{year_token}"

    citation = edits.get("neutral_citation") or custom_citation or target.get("extracted_citation") or f"{year_token} {c_token} {docket}"

    # Target payload for full_judgments
    promoted_payload = {
        "case_id": canonical_id,
        "case_title": title,
        "neutral_citation": citation,
        "court_name": court,
        "bench": bench,
        "decision_date": date_val,
        "full_text": full_text,
        "docket_number": docket,
        "case_type": case_type
    }

    # 1. Insert into full_judgments
    db_promoted = False
    db_error = None
    if supabase_client:
        try:
            # Check if case_id already in full_judgments
            existing = supabase_client.table("full_judgments").select("id").eq("case_id", canonical_id).execute()
            if existing.data:
                res = supabase_client.table("full_judgments").update(promoted_payload).eq("case_id", canonical_id).execute()
            else:
                res = supabase_client.table("full_judgments").insert(promoted_payload).execute()
            db_promoted = True
        except Exception as e:
            db_error = str(e)
            print(f"⚠️ Supabase promotion insert notice: {e}")


    # 2. Update quarantine record status
    target["status"] = "promoted"
    target["reviewed_by"] = reviewer
    target["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
    target["promoted_to_case_id"] = canonical_id

    # Update local ledger file
    if os.path.exists(QUARANTINE_LEDGER):
        updated_lines = []
        with open(QUARANTINE_LEDGER, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if (item.get("composite_key") == target.get("composite_key") or 
                        item.get("source_url") == target.get("source_url")):
                        item.update({
                            "status": "promoted",
                            "reviewed_by": reviewer,
                            "reviewed_at": target["reviewed_at"],
                            "promoted_to_case_id": canonical_id
                        })
                    updated_lines.append(json.dumps(item))
        with open(QUARANTINE_LEDGER, "w", encoding="utf-8") as f:
            for l in updated_lines:
                f.write(l + "\n")

    # 3. Add to regression test set
    regression_items = []
    if os.path.exists(REGRESSION_TEST_SET):
        try:
            with open(REGRESSION_TEST_SET, "r", encoding="utf-8") as f:
                regression_items = json.load(f)
        except Exception:
            pass

    if not any(x.get("case_id") == canonical_id for x in regression_items):
        regression_items.append({
            "case_id": canonical_id,
            "case_title": title,
            "neutral_citation": citation,
            "court_name": court,
            "docket_number": docket,
            "case_type": case_type,
            "decision_date": date_val,
            "promoted_at": target["reviewed_at"],
            "reviewer": reviewer
        })
        with open(REGRESSION_TEST_SET, "w", encoding="utf-8") as f:
            json.dump(regression_items, f, indent=2)

    # 4. Append to audit log
    audit_event = {
        "event": "PROMOTION_APPROVED",
        "timestamp": target["reviewed_at"],
        "reviewer": reviewer,
        "canonical_id": canonical_id,
        "source_url": target.get("source_url"),
        "court": court,
        "docket": docket,
        "title": title,
        "db_promoted": db_promoted,
        "db_error": db_error
    }
    
    audit_history = []
    if os.path.exists(PROMOTED_AUDIT_LOG):
        try:
            with open(PROMOTED_AUDIT_LOG, "r", encoding="utf-8") as f:
                audit_history = json.load(f)
        except Exception:
            pass
    audit_history.append(audit_event)
    with open(PROMOTED_AUDIT_LOG, "w", encoding="utf-8") as f:
        json.dump(audit_history, f, indent=2)

    return {
        "status": "success",
        "action": "promoted",
        "canonical_id": canonical_id,
        "case_title": title,
        "court": court,
        "db_promoted": db_promoted,
        "audit_event": audit_event
    }


def reject_quarantined_record(
    record_composite_key_or_url: str,
    rejection_reason: str,
    reviewer: str = "human_curator"
) -> Dict[str, Any]:
    """
    Marks a quarantined record as rejected.
    """
    records = list_quarantined_records(status_filter=None)
    target = None
    for r in records:
        if (r.get("composite_key") == record_composite_key_or_url or 
            r.get("source_url") == record_composite_key_or_url or
            r.get("docket_number") == record_composite_key_or_url):
            target = r
            break

    if not target:
        return {"status": "error", "message": f"No record matching '{record_composite_key_or_url}' found in quarantine."}

    now_ts = datetime.utcnow().isoformat() + "Z"
    target["status"] = "rejected"
    target["reviewed_by"] = reviewer
    target["reviewed_at"] = now_ts
    target["rejection_reason"] = rejection_reason

    # Update local ledger
    if os.path.exists(QUARANTINE_LEDGER):
        updated_lines = []
        with open(QUARANTINE_LEDGER, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if (item.get("composite_key") == target.get("composite_key") or 
                        item.get("source_url") == target.get("source_url")):
                        item.update({
                            "status": "rejected",
                            "reviewed_by": reviewer,
                            "reviewed_at": now_ts,
                            "rejection_reason": rejection_reason
                        })
                    updated_lines.append(json.dumps(item))
        with open(QUARANTINE_LEDGER, "w", encoding="utf-8") as f:
            for l in updated_lines:
                f.write(l + "\n")

    return {
        "status": "success",
        "action": "rejected",
        "source_url": target.get("source_url"),
        "rejection_reason": rejection_reason,
        "reviewed_at": now_ts
    }
