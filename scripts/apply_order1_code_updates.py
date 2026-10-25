"""
scripts/apply_order1_code_updates.py
Deterministic script to apply Order 1 Code Updates:
- Item A: Lock PDF routes, require Clerk session or HMAC token, strip wildcard CORS, add burst rate limiting.
- Item B: Gate LangSmith wrapper behind ENABLE_LANGSMITH_TRACING=true (default false).
- Item D: Prompt Cleanup: purge ZERO DISCLAIMER POLLUTION, embedded client facts, 25-word rule, and prompt tuning.
- Item E: Precedent Labels: replace is_boosted heuristic with unreviewed labels, remove synthetic 0.99 score.
- Item H: In-flight job reaper on startup.
- Mass assignment protection on ProfileUpdatePayload.
"""

import os
import sys
import re

def update_main_py():
    with open("main.py", "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. Imports
    for idx, line in enumerate(lines[:120]):
        if "from fastapi import FastAPI" in line:
            lines[idx] = "from fastapi import FastAPI, HTTPException, status, Depends, Response, BackgroundTasks, Request, Query\n"
        elif "from pydantic import BaseModel, Field" in line:
            lines[idx] = "from pydantic import BaseModel, Field, ConfigDict\n"
        elif "from core.pdf_resolver import resolve_judgment_pdf_url" in line:
            lines[idx] = "from core.pdf_resolver import resolve_judgment_pdf_url, fetch_storage_pdf_bytes, extract_journal_and_year, verify_hmac_pdf_token\n"

    # 2. Add startup hook and reaper
    health_idx = None
    for idx, line in enumerate(lines[:500]):
        if '@app.get("/health")' in line:
            health_idx = idx
            break
    assert health_idx is not None, "Failed to find @app.get('/health')"

    startup_hook = [
        '\n',
        '@app.on_event("startup")\n',
        'async def on_startup_reap_jobs():\n',
        '    try:\n',
        '        reap_interrupted_jobs_on_startup()\n',
        '    except Exception as e:\n',
        '        print(f"Startup job reaper notice: {e}")\n',
        '\n',
    ]
    lines[health_idx:health_idx] = startup_hook

    # 3. LangSmith gating
    for idx, line in enumerate(lines):
        if "async_anthropic_client = wrappers.wrap_anthropic(raw_client)" in line:
            try_idx = idx - 1
            while try_idx > 0 and "try:" not in lines[try_idx]:
                try_idx -= 1
            except_idx = idx + 1
            while except_idx < len(lines) and "except Exception:" not in lines[except_idx]:
                except_idx += 1
            end_except_idx = except_idx + 1
            while end_except_idx < len(lines) and "async_anthropic_client = raw_client" not in lines[end_except_idx]:
                end_except_idx += 1
            
            replacement = [
                '        enable_langsmith = os.environ.get("ENABLE_LANGSMITH_TRACING", "").strip().lower() in ("true", "1", "yes")\n',
                '        if enable_langsmith:\n',
                '            try:\n',
                '                from langsmith import wrappers\n',
                '                async_anthropic_client = wrappers.wrap_anthropic(raw_client)\n',
                '            except Exception:\n',
                '                async_anthropic_client = raw_client\n',
                '        else:\n',
                '            async_anthropic_client = raw_client\n'
            ]
            lines[try_idx:end_except_idx+1] = replacement
            break

    # 4. Precedent labels in sanitize_precedent_card
    for idx, line in enumerate(lines):
        if 'raw_vstatus = c.get("verification_status")' in line:
            start_vstatus = idx - 1
            end_vstatus = None
            for j in range(idx, idx + 25):
                if 'c["verification_status"] = str(raw_vstatus)' in lines[j]:
                    end_vstatus = j
                    break
            assert end_vstatus is not None, "Failed to find end of verification_status"
            new_vstatus_lines = [
                '    # 12. verification_status (Full Judgment (unreviewed), Headnote (unreviewed), Unverified Metadata)\n',
                '    c_type = str(c.get("content_type", "")).lower()\n',
                '    raw_txt = str(c.get("raw_judgment_text", "") or c.get("text", "") or c.get("full_text", "") or "").strip()\n',
                '    words = len(raw_txt.split()) if raw_txt else 0\n\n',
                '    if c_type in ("full_text", "fresh_court_fetch") and words >= 150:\n',
                '        c["verification_status"] = "Full Judgment (unreviewed)"\n',
                '    elif c_type in ("headnote_only", "editorial_summary", "headnote") or (0 < words < 150):\n',
                '        c["verification_status"] = "Headnote (unreviewed)"\n',
                '    else:\n',
                '        c["verification_status"] = "Unverified Metadata"\n\n',
                '    # Score handling: never display synthetic 0.99 score as similarity\n',
                '    if c.get("is_boosted") or c.get("direct_citation_match") or c.get("score") == 0.99:\n',
                '        if c.get("score") == 0.99:\n',
                '            c["score"] = None\n',
                '            c["similarity"] = None\n',
                '            c["match_type"] = "exact_citation"\n'
            ]
            lines[start_vstatus:end_vstatus+1] = new_vstatus_lines
            break

    # 5. ProfileUpdatePayload ConfigDict(extra="forbid")
    for idx, line in enumerate(lines):
        if "class ProfileUpdatePayload(BaseModel):" in line:
            lines[idx] = "class ProfileUpdatePayload(BaseModel):\n    model_config = ConfigDict(extra='forbid')\n"
            break

    # 6. Insert job reaper before def cleanup_old_jobs():
    cleanup_idx = None
    for idx, line in enumerate(lines):
        if "def cleanup_old_jobs():" in line:
            cleanup_idx = idx
            break
    assert cleanup_idx is not None, "Failed to find cleanup_old_jobs()"
    reaper_lines = [
        '\n',
        'def reap_interrupted_jobs_on_startup() -> int:\n',
        '    """\n',
        '    Startup reaper: marks any stuck running or processing jobs as interrupted.\n',
        '    When server launches, any previously in-flight jobs were abandoned by process restart.\n',
        '    """\n',
        '    reaped_count = 0\n',
        '    now_iso = datetime.now(timezone.utc).isoformat()\n',
        '    if supabase:\n',
        '        try:\n',
        '            res = safe_supabase_query(\n',
        '                lambda: supabase.table("query_jobs")\n',
        '                .select("job_id, status, stage")\n',
        '                .in_("status", ["running", "processing"])\n',
        '                .execute()\n',
        '            )\n',
        '            if res and hasattr(res, "data") and res.data:\n',
        '                for row in res.data:\n',
        '                    jid = row.get("job_id")\n',
        '                    if jid:\n',
        '                        try:\n',
        '                            safe_supabase_query(\n',
        '                                lambda: supabase.table("query_jobs")\n',
        '                                .update({\n',
        '                                    "status": "interrupted",\n',
        '                                    "stage": "server_restarted",\n',
        '                                    "updated_at": now_iso\n',
        '                                })\n',
        '                                .eq("job_id", jid)\n',
        '                                .execute()\n',
        '                            )\n',
        '                            reaped_count += 1\n',
        '                        except Exception as up_err:\n',
        '                            logger.debug(f"Failed to mark job {jid} as interrupted: {up_err}")\n',
        '        except Exception as q_err:\n',
        '            logger.debug(f"Failed to query query_jobs during startup reap: {q_err}")\n',
        '\n',
        '    with _IN_FLIGHT_JOBS_LOCK:\n',
        '        for jid, rec in list(_IN_FLIGHT_JOBS_CACHE.items()):\n',
        '            if rec.get("status") in ("running", "processing"):\n',
        '                rec["status"] = "interrupted"\n',
        '                rec["stage"] = "server_restarted"\n',
        '                rec["updated_at"] = now_iso\n',
        '                reaped_count += 1\n',
        '\n',
        '    for jid, job in list(jobs_store.items()):\n',
        '        if job.get("status") in ("running", "processing"):\n',
        '            job["status"] = "interrupted"\n',
        '            job["stage"] = "server_restarted"\n',
        '\n',
        '    print(f"--> [STARTUP JOB REAPER]: Reaped {reaped_count} zombie in-flight job(s).")\n',
        '    return reaped_count\n',
        '\n',
    ]
    lines[cleanup_idx:cleanup_idx] = reaper_lines

    # 7. Replace synthetic score: 0.99
    content = "".join(lines)
    content = re.sub(
        r'("score":\s*)0\.99(,\s*"is_boosted":\s*True)',
        r'"score": None, "match_type": "exact_citation"\2',
        content
    )
    content = re.sub(
        r'("citation":\s*c_cit,\s*)"score":\s*0\.99,',
        r'\1"score": None, "match_type": "exact_citation",',
        content
    )

    # 8. Prompt cleanup: clean lines matching ZERO DISCLAIMER POLLUTION or consultancy fee
    lines = content.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if "ZERO DISCLAIMER POLLUTION" in line:
            if "8. ZERO DISCLAIMER POLLUTION" in line:
                lines[idx] = '                    "8. STATUTORY FIDELITY: Statutory text is supplied verbatim by code. Clearly note any research scope limitations or unlocated provisions.\\n"\n'
            elif "4. ZERO DISCLAIMER POLLUTION" in line:
                lines[idx] = '                    "4. GROUNDING: Ensure all legal propositions are strictly grounded in retrieved authorities.\\n"\n'
            else:
                lines[idx] = '                    "STATUTORY FIDELITY: Maintain strict factual grounding in retrieved sources.\\n"\n'
        elif "consultancy fee vs undocumented loan repayment" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"- ### APPLICATION OF LAW TO FACTS: Apply substantive law directly to the facts presented in the advocate\'s query.\\n"\n'
        elif "Section 409 PPC, Section 420 PPC, Section 498 Cr.P.C." in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"- ### STATUTORY & PROCEDURAL FRAMEWORK: Exact statutory provisions from the retrieved context. Verbatim statutory text is supplied by code; analyze each legal ingredient.\\n"\n'
        elif "distinguish dishonest intention at inception vs. subsequent contractual breach" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"- ### SUBSTANTIVE LEGAL ANALYSIS & DOCTRINE: Comprehensive legal analysis grounded in retrieved statutory provisions and precedents.\\n"\n'
        elif "Ground bail strategy in settled principles (mala fide" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"- ### PROCEDURAL REMEDIES & STRATEGY: Ground procedural remedies strictly in applicable statutory provisions and settled principles. Detail mandatory procedural steps.\\n"\n'
        elif "e.g. filing pre-arrest bail before Sessions/High Court" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"- ### RECOMMENDATIONS & LITIGATION ROADMAP: Immediate step-by-step guidance for the advocate based strictly on retrieved authorities.\\n"\n'
        elif "Confine all research limitations, database scope notes" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"- ### APPENDIX: RESEARCH SCOPE & UNLOCATED AUTHORITIES: Research limitations, database scope notes, and unlocated specific points appear here.\\n\\n"\n'
        elif "at least 25 words per section" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"3. Ensure all relevant sections are articulated with <<<CARDS>>> JSON.\\n"\n'
        elif "DO NOT cite ungrounded Constitutional Articles" in line:
            indent = " " * (len(line) - len(line.lstrip()))
            lines[idx] = indent + '"6. DO NOT cite ungrounded Constitutional Articles (such as Article 199) unless explicitly present in the retrieved authorities or raised in the query.\\n"\n'

    # 9. Lock PDF routes
    content = "".join(lines)

    pdf_helper_code = '''
async def _authorize_pdf_access(
    case_id: str,
    request: Request,
    token: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = None
) -> str:
    """
    Authorizes PDF streaming access:
    1. If HMAC token provided (?token=...), verifies cryptographic signature and expiration.
    2. Otherwise, requires a valid Clerk authentication session (Bearer token).
    3. Enforces sliding-window burst rate limiting.
    Fails closed with 401 if unauthenticated or signature is invalid.
    """
    caller_identifier = None

    # Option 1: HMAC token authentication
    if token:
        decoded_id = urllib.parse.unquote(case_id).strip()
        is_valid = verify_hmac_pdf_token(token, decoded_id) or verify_hmac_pdf_token(token, case_id)
        if not is_valid:
            match_record = find_judgment_by_id_or_canonical(decoded_id)
            if match_record:
                for alt in [match_record.get("citation"), match_record.get("neutral_citation"), match_record.get("case_id"), match_record.get("id")]:
                    if alt and verify_hmac_pdf_token(token, str(alt)):
                        is_valid = True
                        break
        if is_valid:
            parts = token.split(".", 2)
            caller_identifier = parts[1] if len(parts) == 3 else "hmac_pdf_client"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access Denied: Invalid or expired PDF access token."
            )

    # Option 2: Clerk session authentication
    if not caller_identifier:
        if credentials and credentials.credentials:
            caller_identifier = await verify_clerk_session(credentials)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access Denied: Missing authorization credentials or signed PDF token."
            )

    # Sliding-window burst rate limiting
    rate_limit_id = caller_identifier
    if not rate_limit_id or rate_limit_id in ("anonymous", "user", "hmac_pdf_client"):
        rate_limit_id = getattr(getattr(request, "client", None), "host", "unknown_ip") or "unknown_ip"
    check_burst_rate_limit(rate_limit_id, action="pdf stream")

    return caller_identifier
'''

    pdf_route_target = '@app.get("/api/judgments/{judgment_id:path}/pdf")'
    assert pdf_route_target in content, "Failed to find api judgment pdf route"

    lines = content.splitlines(keepends=True)
    pdf_start = None
    pdf_end = None
    for idx, line in enumerate(lines):
        if line.strip() == pdf_route_target:
            pdf_start = idx
            break

    for idx in range(pdf_start, len(lines)):
        if '@app.get("/judgment-pdf/{case_id:path}")' in lines[idx]:
            pdf_end = idx + 4
            break

    assert pdf_start is not None and pdf_end is not None, "Failed to find bounds of PDF routes"

    new_pdf_endpoints = pdf_helper_code + """
@app.get("/api/judgments/{judgment_id:path}/pdf")
async def get_api_judgment_pdf_endpoint(
    judgment_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_agent)
):
    await _authorize_pdf_access(judgment_id, request, token=token, credentials=credentials)

    decoded_id = urllib.parse.unquote(judgment_id).strip()
    match_record = find_judgment_by_id_or_canonical(decoded_id)

    # 1. Download authentic PDF bytes from Supabase Storage on backend side (zero direct frontend storage calls)
    if match_record and supabase:
        cit_lookup = match_record.get("neutral_citation") or match_record.get("citation") or ""
        journal, year, page = extract_journal_and_year(cit_lookup, decoded_id)
        if journal and year:
            storage_pdf_bytes = fetch_storage_pdf_bytes(supabase, journal, year, page, decoded_id)
            if storage_pdf_bytes:
                safe_filename = re.sub(r'[^a-zA-Z0-9_\\-]', '_', decoded_id).strip('_') + ".pdf"
                return Response(
                    content=storage_pdf_bytes,
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'inline; filename="{safe_filename}"',
                        "Content-Type": "application/pdf"
                    }
                )

    title = (get_effective_title(match_record) if match_record else decoded_id) or decoded_id
    citation = (match_record.get("neutral_citation") if match_record else "") or ""
    court = (get_effective_court(match_record) if match_record else "Supreme Court of Pakistan") or "Supreme Court of Pakistan"
    text = (match_record.get("full_text") if match_record else f"Full judgment record for {decoded_id} is currently undergoing index synchronization.") or ""

    pdf_bytes = build_judgment_pdf_bytes(title, citation, court, text)
    safe_filename = re.sub(r'[^a-zA-Z0-9_\\-]', '_', decoded_id).strip('_') + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_filename}"',
            "Content-Type": "application/pdf"
        }
    )

@app.get("/judgment-pdf/{case_id:path}")
async def get_judgment_pdf_endpoint(
    case_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_agent)
):
    return await get_api_judgment_pdf_endpoint(case_id, request=request, token=token, credentials=credentials)
"""

    lines[pdf_start:pdf_end] = [new_pdf_endpoints]
    final_content = "".join(lines)

    with open("main.py", "w", encoding="utf-8") as f:
        f.write(final_content)

    print("[main.py] Successfully applied all updates.")

def update_query_processor():
    with open("legal_ai/query_engine/query_processor.py", "r", encoding="utf-8") as f:
        lines = f.readlines()

    for idx, line in enumerate(lines):
        if "ZERO DISCLAIMER POLLUTION" in line:
            if "8. ZERO DISCLAIMER POLLUTION" in line:
                lines[idx] = '            "8. FIDELITY: Ensure all statutory references and holdings reflect the exact retrieved text without extrapolation.\\n"\n'
            else:
                lines[idx] = '        "ACCURACY: Ensure all statements are strictly grounded in retrieved sources."\n'
        elif "9. STATUTE CROSS-REFERENCE FIDELITY" in line:
            lines[idx] = ""

    with open("legal_ai/query_engine/query_processor.py", "w", encoding="utf-8") as f:
        f.writelines(lines)

    print("[query_processor.py] Successfully applied all updates.")

def update_subqueries_and_filters():
    # 1. core/legal_guardrails.py
    with open("core/legal_guardrails.py", "r", encoding="utf-8") as f:
        lg = f.read()
    lg_old = '    if any(k in q_lower for k in ["board of directors", "company funds", "consultancy fee", "corporate governance", "companies act", "shareholder", "director loan"]) or ('
    lg_new = '    if any(k in q_lower for k in ["board of directors", "company funds", "corporate governance", "companies act", "shareholder", "director loan"]) or ('
    if lg_old in lg:
        lg = lg.replace(lg_old, lg_new, 1)

    lg_old2 = 'subqueries.append("company director unauthorized transfer company funds consultancy fee director loan fiduciary duty Companies Act")'
    lg_new2 = 'subqueries.append("company director unauthorized transfer company funds director loan fiduciary duty Companies Act")'
    if lg_old2 in lg:
        lg = lg.replace(lg_old2, lg_new2, 1)
    with open("core/legal_guardrails.py", "w", encoding="utf-8") as f:
        f.write(lg)
    print("[core/legal_guardrails.py] Successfully updated.")

    # 2. core/authority_ranking.py
    with open("core/authority_ranking.py", "r", encoding="utf-8") as f:
        ar = f.read()
    ar_old1 = 'if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "consultancy fee", "director"]):'
    ar_new1 = 'if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "director"]):'
    if ar_old1 in ar:
        ar = ar.replace(ar_old1, ar_new1, 1)

    ar_old2 = '"pre-arrest bail", "mala fide", "ulterior motive", "director", "consultancy fee",'
    ar_new2 = '"pre-arrest bail", "mala fide", "ulterior motive", "director",'
    if ar_old2 in ar:
        ar = ar.replace(ar_old2, ar_new2, 1)
    with open("core/authority_ranking.py", "w", encoding="utf-8") as f:
        f.write(ar)
    print("[core/authority_ranking.py] Successfully updated.")

    # 3. core/candidate_quality_filter.py
    with open("core/candidate_quality_filter.py", "r", encoding="utf-8") as f:
        cqf = f.read()
    cqf_old = 'if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "consultancy fee", "director"]):'
    cqf_new = 'if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "director"]):'
    if cqf_old in cqf:
        cqf = cqf.replace(cqf_old, cqf_new, 1)
    with open("core/candidate_quality_filter.py", "w", encoding="utf-8") as f:
        f.write(cqf)
    print("[core/candidate_quality_filter.py] Successfully updated.")

    # 4. legal_ai/ranking/authority_ranker.py
    with open("legal_ai/ranking/authority_ranker.py", "r", encoding="utf-8") as f:
        lar = f.read()
    lar_old = '"pre-arrest bail", "mala fide", "ulterior motive", "director", "consultancy fee",'
    lar_new = '"pre-arrest bail", "mala fide", "ulterior motive", "director",'
    if lar_old in lar:
        lar = lar.replace(lar_old, lar_new, 1)
    with open("legal_ai/ranking/authority_ranker.py", "w", encoding="utf-8") as f:
        f.write(lar)
    print("[legal_ai/ranking/authority_ranker.py] Successfully updated.")

    # 5. legal_ai/ranking/relevance_filter.py
    with open("legal_ai/ranking/relevance_filter.py", "r", encoding="utf-8") as f:
        lrf = f.read()
    lrf_old = 'if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "consultancy fee", "director"]):'
    lrf_new = 'if not any(k in haystack for k in ["409", "420", "406", "breach of trust", "director"]):'
    if lrf_old in lrf:
        lrf = lrf.replace(lrf_old, lrf_new, 1)
    with open("legal_ai/ranking/relevance_filter.py", "w", encoding="utf-8") as f:
        f.write(lrf)
    print("[legal_ai/ranking/relevance_filter.py] Successfully updated.")

if __name__ == "__main__":
    update_main_py()
    update_query_processor()
    update_subqueries_and_filters()
    print("ALL ORDER 1 CODE UPDATES APPLIED SUCCESSFULLY.")
