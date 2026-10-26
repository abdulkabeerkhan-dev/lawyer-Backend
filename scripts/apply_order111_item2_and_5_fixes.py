"""
scripts/apply_order111_item2_and_5_fixes.py

Applies the fixes for Item 2 and Item 5 of ORDER 1.11:
1. memo_verifier.py: Add blocked_payload support to MemorandumVerificationBlockedError.
2. query_processor.py: Add automatic regeneration loop (max 2 attempts) with verification feedback,
   populate error_category, safe_reason, retry_guidance, verified_statute_fallback (with disputed banner).
3. main.py:
   - Exception handler populates all error fields into jobs_store[job_id].
   - Add check_query_jobs_table_exists() startup self-check.
   - Guard persist_in_flight_job_state and reap_interrupted_jobs_on_startup with table check.
   - Prevent safe_supabase_query from retrying PGRST205 schema cache errors.
"""

import os
import re

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)

# ==============================================================================
# 1. legal_ai/verification/memo_verifier.py
# ==============================================================================
mv_path = os.path.join(REPO_DIR, "legal_ai", "verification", "memo_verifier.py")
with open(mv_path, "r", encoding="utf-8") as f:
    mv_content = f.read()

mv_target = """class MemorandumVerificationBlockedError(Exception):
    \"\"\"Raised when a research memorandum fails ground-truth verification.\"\"\"
    def __init__(self, verification_report: Dict[str, Any]):
        self.verification_report = verification_report
        total = verification_report.get("total_failures", 0)
        super().__init__(f"Memorandum failed ground-truth verification with {total} violations.")"""

mv_replacement = """class MemorandumVerificationBlockedError(Exception):
    \"\"\"Raised when a research memorandum fails ground-truth verification.\"\"\"
    def __init__(self, verification_report: Dict[str, Any], blocked_payload: Optional[Dict[str, Any]] = None):
        self.verification_report = verification_report
        self.blocked_payload = blocked_payload
        total = verification_report.get("total_failures", 0)
        super().__init__(f"Memorandum failed ground-truth verification with {total} violations.")"""

if mv_target in mv_content:
    mv_content = mv_content.replace(mv_target, mv_replacement, 1)
    with open(mv_path, "w", encoding="utf-8") as f:
        f.write(mv_content)
    print("SUCCESS: Updated legal_ai/verification/memo_verifier.py")
else:
    print("SKIPPED/ALREADY_PATCHED: legal_ai/verification/memo_verifier.py")


# ==============================================================================
# 2. legal_ai/query_engine/query_processor.py
# ==============================================================================
qp_path = os.path.join(REPO_DIR, "legal_ai", "query_engine", "query_processor.py")
with open(qp_path, "r", encoding="utf-8") as f:
    qp_content = f.read()

qp_target = """    # ORDER 1.7 & 1.10: MEMORANDUM VERIFIER GATE & SYSTEM DISPUTED BANNER FLOW
    # Fail-closed gate: if verification fails, check if the ONLY failure is a cited disputed provision lacking banner.
    # Model cannot set is_system_rendered; only the backend runtime attaches the system banner and passes is_system_rendered=True.
    from legal_ai.verification.memo_verifier import (
        verify_memorandum_text,
        MemorandumVerificationBlockedError,
        attach_system_disputed_banner
    )
    verification_gate = verify_memorandum_text(clean_answer, is_system_rendered=False)
    if not verification_gate.get('passed', False):
        disputed_notices = verification_gate.get('disputed_notices', [])
        failures = verification_gate.get('failures', [])
        if disputed_notices and all(f.get('category') == 'DISPUTED_TEXT_UNNOTICED' for f in failures):
            bannered_answer = attach_system_disputed_banner(clean_answer, disputed_notices)
            re_gate = verify_memorandum_text(bannered_answer, is_system_rendered=True)
            if re_gate.get('passed', False):
                clean_answer = bannered_answer
                verification_gate = re_gate

    if not verification_gate.get('passed', False):
        print(
            f'[JOB {job_id}] MEMORANDUM VERIFICATION BLOCKED: {len(verification_gate.get("failures", []))} violations detected.',
            file=sys.stderr,
            flush=True,
        )
        if job_id in jobs_store:
            jobs_store[job_id].update({
                'status': 'error',
                'stage': 'verification_blocked',
                'error': 'MEMORANDUM_VERIFICATION_FAILED',
                'result': None,
                'verification_report': verification_gate,
                'completed_at': datetime.now(timezone.utc),
            })
        raise MemorandumVerificationBlockedError(verification_gate)"""

qp_replacement = """    # ORDER 1.7 & 1.10 & 1.11: MEMORANDUM VERIFIER GATE, REGENERATION & SYSTEM DISPUTED BANNER FLOW
    from legal_ai.verification.memo_verifier import (
        verify_memorandum_text,
        MemorandumVerificationBlockedError,
        attach_system_disputed_banner
    )

    # Initial verification attempt (Attempt 1)
    verification_gate = verify_memorandum_text(clean_answer, is_system_rendered=False)
    if not verification_gate.get('passed', False):
        disputed_notices = verification_gate.get('disputed_notices', [])
        failures = verification_gate.get('failures', [])
        if disputed_notices and all(f.get('category') == 'DISPUTED_TEXT_UNNOTICED' for f in failures):
            bannered_answer = attach_system_disputed_banner(clean_answer, disputed_notices)
            re_gate = verify_memorandum_text(bannered_answer, is_system_rendered=True)
            if re_gate.get('passed', False):
                clean_answer = bannered_answer
                verification_gate = re_gate

    # ORDER 1.11 - ITEM 2: Automatic Regeneration Loop (Max 2 Attempts)
    attempts_history = [{
        "attempt": 1,
        "passed": bool(verification_gate.get("passed", False)),
        "total_failures": verification_gate.get("total_failures", 0),
        "failures_sample": [f.get("issue") or f.get("reason") for f in verification_gate.get("failures", [])[:5]]
    }]

    if not verification_gate.get('passed', False):
        print(f"[JOB {job_id}] Attempt 1 blocked with {verification_gate.get('total_failures', 0)} failures. Triggering Attempt 2 regeneration with feedback constraints...", file=sys.stderr, flush=True)
        # Formulate feedback constraints from Attempt 1 failures
        feedback_constraints = "\\n\\nCRITICAL REMEDIATION CONSTRAINTS (PRIOR DRAFT VIOLATIONS):\\n"
        for f in verification_gate.get("failures", [])[:8]:
            feedback_constraints += f"- [{f.get('rule', '')} {f.get('category', '')}] {f.get('issue') or f.get('reason')}\\n"
        feedback_constraints += "Enforce: Quote official statutory texts verbatim; cite verified section/subsections only; eliminate unsourced analytical commentary.\\n"

        try:
            regen_content = user_synthesis_content + "\\n\\n" + feedback_constraints
            regen_message = await anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": regen_content}]
            )
            regen_raw = ""
            for block in getattr(regen_message, "content", []):
                if getattr(block, "type", None) == "text":
                    regen_raw += block.text

            if regen_raw.strip():
                regen_clean = purge_debug_warnings(regen_raw)
                regen_gate = verify_memorandum_text(regen_clean, is_system_rendered=False)
                if not regen_gate.get('passed', False):
                    r_disputed = regen_gate.get('disputed_notices', [])
                    r_failures = regen_gate.get('failures', [])
                    if r_disputed and all(f.get('category') == 'DISPUTED_TEXT_UNNOTICED' for f in r_failures):
                        bannered_regen = attach_system_disputed_banner(regen_clean, r_disputed)
                        re_re_gate = verify_memorandum_text(bannered_regen, is_system_rendered=True)
                        if re_re_gate.get('passed', False):
                            regen_clean = bannered_regen
                            regen_gate = re_re_gate

                attempts_history.append({
                    "attempt": 2,
                    "passed": bool(regen_gate.get("passed", False)),
                    "total_failures": regen_gate.get("total_failures", 0),
                    "failures_sample": [f.get("issue") or f.get("reason") for f in regen_gate.get("failures", [])[:5]]
                })

                if regen_gate.get('passed', False):
                    clean_answer = regen_clean
                    verification_gate = regen_gate
        except Exception as regen_ex:
            print(f"[JOB {job_id}] Regeneration attempt error: {regen_ex}", file=sys.stderr, flush=True)

    if not verification_gate.get('passed', False):
        print(
            f'[JOB {job_id}] MEMORANDUM VERIFICATION BLOCKED: {len(verification_gate.get("failures", []))} violations detected after {len(attempts_history)} attempt(s).',
            file=sys.stderr,
            flush=True,
        )
        # Classify specific error category
        failures = verification_gate.get("failures", [])
        categories = {f.get("category") for f in failures}
        if "MISATTRIBUTED_QUOTE" in categories or "UNMATCHED_QUOTE" in categories:
            err_cat = "STATUTORY_MISQUOTATION"
        elif "UNVERIFIED_AUTHORITY" in categories:
            err_cat = "FABRICATED_CITATION"
        elif "UNSOURCED_ANALYSIS" in categories:
            err_cat = "UNSOURCED_ANALYSIS"
        elif "CITED_PROVISION_NOT_IN_VERIFIED_STORE" in categories:
            err_cat = "UNSOURCED_PROVISION_CITATION"
        elif "DISPUTED_TEXT_UNNOTICED" in categories:
            err_cat = "DISPUTED_TEXT_UNNOTICED"
        else:
            err_cat = "VERIFICATION_GATE_REJECTION"

        safe_reason = (
            "The generated memorandum could not be verified against official statutory gazettes and "
            "the verified judicial precedent index. Output withheld to protect legal accuracy."
        )
        retry_guidance = (
            "Ensure all statutory quotes verbatim match authentic gazettes, cite only in-force provisions from "
            "verified acts, and omit uncited speculative factual assertions."
        )

        # Build verified_statute_fallback with tier labels and disputed banner
        verified_fallback = []
        for p in verified_statutory_provisions:
            cid = p.get("canonical_id") or p.get("act_code") or "PROVISION"
            tier = p.get("tier", "tier_1")
            disp_name = p.get("display_name") or p.get("act_name") or cid
            txt = p.get("text_cleaned") or p.get("text") or ""
            if isinstance(txt, dict):
                txt = " ".join(str(v) for v in txt.values())

            # Check if disputed
            is_disputed = (p.get("verification_status") == "disputed_boundary_repaired" or 
                           p.get("status") == "disputed" or 
                           "FIO_2001_SEC_22" in str(cid))
            banner_prefix = ""
            if is_disputed:
                banner_prefix = "> [!WARNING] DISPUTED STATUTORY TEXT — HUMAN CHECK REQUIRED\\n> Official prints of this provision contain contested variations.\\n\\n"

            verified_fallback.append({
                "canonical_id": cid,
                "display_name": disp_name,
                "tier": tier,
                "is_disputed": is_disputed,
                "text": banner_prefix + f"[{tier.upper()}] {disp_name}:\\n{txt}"
            })

        blocked_payload = {
            'status': 'error',
            'stage': 'verification_blocked',
            'error': 'MEMORANDUM_VERIFICATION_FAILED',
            'error_category': err_cat,
            'safe_reason': safe_reason,
            'retry_guidance': retry_guidance,
            'verified_statute_fallback': verified_fallback,
            'attempts': attempts_history,
            'early_display': None,
            'result': None,
            'verification_report': verification_gate,
            'completed_at': datetime.now(timezone.utc),
        }
        if job_id in jobs_store:
            jobs_store[job_id].update(blocked_payload)
        raise MemorandumVerificationBlockedError(verification_gate, blocked_payload=blocked_payload)"""

if qp_target in qp_content:
    qp_content = qp_content.replace(qp_target, qp_replacement, 1)
    with open(qp_path, "w", encoding="utf-8") as f:
        f.write(qp_content)
    print("SUCCESS: Updated legal_ai/query_engine/query_processor.py")
else:
    print("SKIPPED/ALREADY_PATCHED: legal_ai/query_engine/query_processor.py")


# ==============================================================================
# 3. main.py
# ==============================================================================
main_path = os.path.join(REPO_DIR, "main.py")
with open(main_path, "r", encoding="utf-8") as f:
    main_content = f.read()

# 3.1: safe_supabase_query PGRST205 check
sq_target = """        except Exception as e:

            err_str = str(e)

            if "ConnectionTerminated" in err_str or "connection" in err_str.lower() or attempt < retries - 1:"""

sq_replacement = """        except Exception as e:

            err_str = str(e)
            if "PGRST205" in err_str or "schema cache" in err_str or "could not find" in err_str.lower():
                raise e

            if "ConnectionTerminated" in err_str or "connection" in err_str.lower() or attempt < retries - 1:"""

if sq_target in main_content:
    main_content = main_content.replace(sq_target, sq_replacement, 1)
    print("SUCCESS: Updated safe_supabase_query in main.py")

# 3.2: startup self-check function and table guarding
jobs_def_target = """jobs_store: Dict[str, Dict[str, Any]] = {}

_IN_FLIGHT_JOBS_CACHE: Dict[str, Dict[str, Any]] = {}
_IN_FLIGHT_JOBS_LOCK = threading.Lock()

def _load_in_flight_jobs() -> Dict[str, Dict[str, Any]]:"""

jobs_def_replacement = """jobs_store: Dict[str, Dict[str, Any]] = {}

_IN_FLIGHT_JOBS_CACHE: Dict[str, Dict[str, Any]] = {}
_IN_FLIGHT_JOBS_LOCK = threading.Lock()
_QUERY_JOBS_TABLE_EXISTS: Optional[bool] = None

def check_query_jobs_table_exists() -> bool:
    \"\"\"
    Startup self-check for the PostgreSQL `query_jobs` table.
    Logs a warning (without failing) if the table is missing from Supabase schema cache.
    Zero retries; evaluates table presence immediately.
    \"\"\"
    global _QUERY_JOBS_TABLE_EXISTS
    if _QUERY_JOBS_TABLE_EXISTS is not None:
        return _QUERY_JOBS_TABLE_EXISTS

    if not supabase:
        _QUERY_JOBS_TABLE_EXISTS = False
        return False

    try:
        supabase.table("query_jobs").select("job_id").limit(1).execute()
        _QUERY_JOBS_TABLE_EXISTS = True
        logger.info("[STARTUP SELF-CHECK] Table 'public.query_jobs' verified in Supabase.")
    except Exception as e:
        err_msg = str(e)
        _QUERY_JOBS_TABLE_EXISTS = False
        if "PGRST205" in err_msg or "schema cache" in err_msg or "not find" in err_msg:
            print(f"⚠️ [STARTUP SELF-CHECK] Notice: 'public.query_jobs' table is missing in Supabase (PGRST205). In-flight persistence will use memory store. To enable database persistence, apply migrations/query_jobs.sql.", file=sys.stderr, flush=True)
            logger.warning(f"[STARTUP SELF-CHECK] Table 'public.query_jobs' missing: {err_msg}")
        else:
            logger.debug(f"[STARTUP SELF-CHECK] query_jobs check encountered: {err_msg}")

    return _QUERY_JOBS_TABLE_EXISTS

def _load_in_flight_jobs() -> Dict[str, Dict[str, Any]]:"""

if jobs_def_target in main_content:
    main_content = main_content.replace(jobs_def_target, jobs_def_replacement, 1)
    print("SUCCESS: Added check_query_jobs_table_exists to main.py")

# 3.3: Guard _load_in_flight_jobs and persist_in_flight_job_state
persist_target = """    if supabase:
        try:
            payload = {
                "job_id": job_id,
                "stage": stage,
                "status": status,
                "updated_at": now_iso,
                "metadata": sanitized_metadata
            }
            if user_id:
                payload["user_id"] = user_id
            safe_supabase_query(lambda: supabase.table("query_jobs").upsert(payload).execute())
        except Exception as e:
            logger.debug(f"Failed to upsert job {job_id} to query_jobs table: {e}")"""

persist_replacement = """    if supabase and check_query_jobs_table_exists():
        try:
            payload = {
                "job_id": job_id,
                "stage": stage,
                "status": status,
                "updated_at": now_iso,
                "metadata": sanitized_metadata
            }
            if user_id:
                payload["user_id"] = user_id
            safe_supabase_query(lambda: supabase.table("query_jobs").upsert(payload).execute())
        except Exception as e:
            logger.debug(f"Failed to upsert job {job_id} to query_jobs table: {e}")"""

if persist_target in main_content:
    main_content = main_content.replace(persist_target, persist_replacement, 1)
    print("SUCCESS: Guarded persist_in_flight_job_state with check_query_jobs_table_exists")

# 3.4: Guard startup reaper
reap_target = """@app.on_event("startup")
async def on_startup_reap_jobs():
    try:
        reap_interrupted_jobs_on_startup()
    except Exception as e:
        print(f"Startup job reaper notice: {e}")"""

reap_replacement = """@app.on_event("startup")
async def on_startup_reap_jobs():
    try:
        if check_query_jobs_table_exists():
            reap_interrupted_jobs_on_startup()
    except Exception as e:
        print(f"Startup job reaper notice: {e}")"""

if reap_target in main_content:
    main_content = main_content.replace(reap_target, reap_replacement, 1)
    print("SUCCESS: Guarded on_startup_reap_jobs in main.py")

# 3.5: Update MemorandumVerificationBlockedError handler in main.py
handler_target = """        except MemorandumVerificationBlockedError as ve:
            print(f"[JOB {job_id}] MEMORANDUM BLOCKED BY VERIFIER: {ve}", file=sys.stderr, flush=True)
            if job_id in jobs_store:
                jobs_store[job_id].update({
                    'status': 'error',
                    'stage': 'verification_blocked',
                    'error': 'MEMORANDUM_VERIFICATION_FAILED',
                    'result': None,
                    'verification_report': ve.verification_report,
                    'completed_at': datetime.now(timezone.utc),
                })
            return"""

handler_replacement = """        except MemorandumVerificationBlockedError as ve:
            print(f"[JOB {job_id}] MEMORANDUM BLOCKED BY VERIFIER: {ve}", file=sys.stderr, flush=True)
            if job_id in jobs_store:
                blocked_data = getattr(ve, "blocked_payload", None)
                if blocked_data:
                    jobs_store[job_id].update(blocked_data)
                else:
                    jobs_store[job_id].update({
                        'status': 'error',
                        'stage': 'verification_blocked',
                        'error': 'MEMORANDUM_VERIFICATION_FAILED',
                        'error_category': 'VERIFICATION_GATE_REJECTION',
                        'safe_reason': 'The research memorandum failed strict ground-truth verification against official statute gazettes and verified precedent indexes.',
                        'retry_guidance': 'Ensure all statutory quotes verbatim match authentic gazettes and all case citations exist in verified index.',
                        'verified_statute_fallback': [],
                        'result': None,
                        'verification_report': ve.verification_report,
                        'completed_at': datetime.now(timezone.utc),
                    })
            return"""

if handler_target in main_content:
    main_content = main_content.replace(handler_target, handler_replacement, 1)
    print("SUCCESS: Updated MemorandumVerificationBlockedError handler in main.py")

# 3.6: Update GET /query/{job_id} endpoint in main.py
get_endpoint_target = """    if job.get("status") == "error":
        return {
            "status": "error",
            "stage": job.get("stage", "verification_blocked"),
            "error": job.get("error"),
            "error_category": job.get("error_category"),
            "safe_reason": job.get("safe_reason"),
            "retry_guidance": job.get("retry_guidance"),
            "verified_statute_fallback": job.get("verified_statute_fallback"),
            "early_display": None,
            "result": None
        }"""

get_endpoint_replacement = """    if job.get("status") == "error":
        return {
            "status": "error",
            "stage": job.get("stage", "verification_blocked"),
            "error": job.get("error"),
            "error_category": job.get("error_category"),
            "safe_reason": job.get("safe_reason"),
            "retry_guidance": job.get("retry_guidance"),
            "verified_statute_fallback": job.get("verified_statute_fallback"),
            "attempts": job.get("attempts", []),
            "early_display": None,
            "result": None
        }"""

if get_endpoint_target in main_content:
    main_content = main_content.replace(get_endpoint_target, get_endpoint_replacement, 1)
    print("SUCCESS: Updated GET /query/{job_id} in main.py")

with open(main_path, "w", encoding="utf-8") as f:
    f.write(main_content)
print("SUCCESS: main.py saved.")
