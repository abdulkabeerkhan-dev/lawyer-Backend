import re

file_path = "main.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update export/court-pleading
old_export = '''    # ORDER 1.8 - ITEM 6: FAIL-CLOSED VERIFICATION ON PLEADING EXPORT
    # Unverified or fabricated memorandum text can NEVER be exported as a legal pleading.
    if payload.memorandum_text:
        v_res = verify_memorandum_text(payload.memorandum_text)
        if not v_res.get("passed", False):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "EXPORT_VERIFICATION_BLOCKED",
                    "verdict": "BLOCKED",
                    "message": "Pleading export rejected: memorandum text failed ground-truth verification.",
                    "total_failures": v_res.get("total_failures", 0),
                    "failures": v_res.get("failures", [])
                }
            )'''

new_export = '''    # ORDER 1.9 - ITEM 7: FAIL-CLOSED VERIFICATION ON PLEADING EXPORT (CITATIONS AND QUOTES ONLY)
    # Allows client facts in user-supplied pleadings while strictly gating all cited statutes and authorities.
    if payload.memorandum_text:
        from legal_ai.verification.memo_verifier import verify_pleading_citations_and_quotes
        v_res = verify_pleading_citations_and_quotes(payload.memorandum_text)
        if not v_res.get("passed", False):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "EXPORT_VERIFICATION_BLOCKED",
                    "verdict": "BLOCKED",
                    "message": "Pleading export rejected: memorandum text failed ground-truth verification.",
                    "total_failures": v_res.get("total_failures", 0),
                    "failures": v_res.get("failures", [])
                }
            )'''

# Normalize newlines
content_norm = content.replace("\r\n", "\n")
old_export_norm = old_export.replace("\r\n", "\n")
assert old_export_norm in content_norm, "old_export not found in main.py"
content_norm = content_norm.replace(old_export_norm, new_export.replace("\r\n", "\n"))

# 2. Wire gate in POST /generate-pleading
old_gen = '''        draft_markdown = response.content[0].text

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"LLM Generation failed: {str(e)}")



    # 4. Generate the DOCX'''

new_gen = '''        draft_markdown = response.content[0].text

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"LLM Generation failed: {str(e)}")

    # ORDER 1.9 - ITEM 5: PLEADING GENERATION VERIFICATION GATE
    from legal_ai.verification.memo_verifier import verify_pleading_citations_and_quotes
    v_res = verify_pleading_citations_and_quotes(draft_markdown)
    if not v_res.get("passed", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "GENERATE_PLEADING_VERIFICATION_BLOCKED",
                "verdict": "BLOCKED",
                "message": "Generated pleading failed ground-truth verification.",
                "total_failures": v_res.get("total_failures", 0),
                "failures": v_res.get("failures", [])
            }
        )

    # 4. Generate the DOCX'''

old_gen_norm = old_gen.replace("\r\n", "\n")
assert old_gen_norm in content_norm, "old_gen not found in main.py"
content_norm = content_norm.replace(old_gen_norm, new_gen.replace("\r\n", "\n"))

# 3. Wire gate in POST /query/{job_id}/continue
old_cont = '''    return {"answer": updated_raw, "status": "done"}'''
new_cont = '''    # ORDER 1.9 - ITEM 5: CONTINUATION FAIL-CLOSED VERIFICATION GATE
    from legal_ai.verification.memo_verifier import verify_memorandum_text
    v_cont = verify_memorandum_text(updated_raw)
    if not v_cont.get("passed", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "CONTINUE_VERIFICATION_BLOCKED",
                "verdict": "BLOCKED",
                "result": None,
                "message": "Continuation output failed ground-truth verification.",
                "total_failures": v_cont.get("total_failures", 0),
                "failures": v_cont.get("failures", [])
            }
        )
    return {"answer": updated_raw, "status": "done"}'''

assert old_cont in content_norm, "old_cont not found in main.py"
content_norm = content_norm.replace(old_cont, new_cont)

# 4. Gate in POST /diary
old_diary = '''@app.post("/diary")

async def add_diary_entry(payload: DiaryEntryPayload, authenticated_user_id: str = Depends(verify_clerk_session)):

    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")'''

new_diary = '''@app.post("/diary")

async def add_diary_entry(payload: DiaryEntryPayload, authenticated_user_id: str = Depends(verify_clerk_session)):

    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")

    # ORDER 1.9 - ITEM 5: DIARY FAIL-CLOSED CITATION & QUOTE GATE
    if payload.notes and ("> " in payload.notes or any(k in payload.notes.lower() for k in ["section ", "order ", "article "])):
        from legal_ai.verification.memo_verifier import verify_pleading_citations_and_quotes
        v_diary = verify_pleading_citations_and_quotes(payload.notes)
        if not v_diary.get("passed", False):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "DIARY_NOTE_VERIFICATION_BLOCKED",
                    "verdict": "BLOCKED",
                    "message": "Diary note rejected: contains unverified legal citations or quotes.",
                    "total_failures": v_diary.get("total_failures", 0),
                    "failures": v_diary.get("failures", [])
                }
            )'''

old_diary_norm = old_diary.replace("\r\n", "\n")
assert old_diary_norm in content_norm, "old_diary not found in main.py"
content_norm = content_norm.replace(old_diary_norm, new_diary.replace("\r\n", "\n"))

# 5. Blocked UX metadata & fallback in main query pipeline
old_pipeline_gate = '''        # ORDER 1.7 - ITEM 10: MEMORANDUM VERIFIER GATE (Legacy pipeline)
        from legal_ai.verification.memo_verifier import verify_memorandum_text, MemorandumVerificationBlockedError
        verification_gate = verify_memorandum_text(display_answer)
        if not verification_gate.get('passed', False):
            log_runtime_diagnostic('MEMORANDUM_VERIFICATION_BLOCKED', verification_gate)
            if job_id in jobs_store:
                jobs_store[job_id].update({
                    'status': 'error',
                    'stage': 'verification_blocked',
                    'error': 'MEMORANDUM_VERIFICATION_FAILED',
                    'result': None,
                    'verification_report': verification_gate,
                    'completed_at': datetime.now(timezone.utc),
                })
            raise MemorandumVerificationBlockedError(verification_gate)'''

new_pipeline_gate = '''        # ORDER 1.9 - ITEM 5 & 6: MEMORANDUM VERIFIER GATE WITH BLOCKED UX & AUTO-REGENERATION
        from legal_ai.verification.memo_verifier import verify_memorandum_text, MemorandumVerificationBlockedError
        verification_gate = verify_memorandum_text(display_answer)

        # Automatic regeneration loop (max 2 attempts total) with failure fed back as constraints
        if not verification_gate.get('passed', False) and async_anthropic_client:
            log_runtime_diagnostic('MEMORANDUM_VERIFICATION_FIRST_ATTEMPT_FAILED', verification_gate)
            first_fail = verification_gate.get("failures", [{}])[0]
            cat_label = first_fail.get("category") or first_fail.get("label") or "VERIFICATION_FAILURE"
            constraint_prompt = f"CRITICAL REQUIREMENT: Your prior answer failed ground-truth verification ({cat_label}). You must quote only verbatim text from verified statutory context and cite only verified authorities."
            try:
                regen_resp = await safe_create_anthropic_message(
                    model=CLAUDE_MODEL,
                    max_tokens=4000,
                    system="You are a legal research assistant in Pakistan. Strictly quote law verbatim.",
                    messages=[
                        {"role": "user", "content": f"{request.query_text}\\n\\n{constraint_prompt}"}
                    ]
                )
                candidate_text = "".join(getattr(b, "text", "") for b in regen_resp.content)
                candidate_gate = verify_memorandum_text(candidate_text)
                if candidate_gate.get('passed', False):
                    display_answer = candidate_text
                    verification_gate = candidate_gate
            except Exception as e:
                print(f"Regeneration attempt exception: {e}")

        if not verification_gate.get('passed', False):
            log_runtime_diagnostic('MEMORANDUM_VERIFICATION_BLOCKED', verification_gate)
            first_fail = verification_gate.get("failures", [{}])[0] if verification_gate.get("failures") else {}
            err_cat = first_fail.get("category", "VERIFICATION_FAILURE")
            safe_reason = first_fail.get("issue", "Ground-truth verification failed.")
            if ": " in safe_reason:
                safe_reason = safe_reason.split(": ", 1)[0]
            
            # Fetch authentic statute text fallback from verified store
            verified_fallback = []
            for cm in verification_gate.get("cited_provisions_metadata", []):
                if cm.get("is_valid") and cm.get("canonical_id"):
                    rec = get_unified_statute_store().get_by_canonical_id(cm["canonical_id"])
                    if rec and (rec.get("text") or rec.get("statutory_text")):
                        verified_fallback.append({
                            "canonical_id": cm["canonical_id"],
                            "display_name": rec.get("display_name"),
                            "text": (rec.get("text") or rec.get("statutory_text"))[:400]
                        })

            blocked_payload = {
                'status': 'error',
                'stage': 'verification_blocked',
                'error': 'MEMORANDUM_VERIFICATION_FAILED',
                'error_category': err_cat,
                'safe_reason': safe_reason,
                'retry_guidance': "Ensure all statutory quotes verbatim match authentic gazettes and all case citations exist in verified index.",
                'verified_statute_fallback': verified_fallback,
                'result': None,
                'early_display': None,
                'verification_report': {
                    "verdict": "BLOCKED",
                    "total_failures": verification_gate.get("total_failures", 0),
                    "failures": verification_gate.get("failures", [])
                },
                'completed_at': datetime.now(timezone.utc),
            }
            if job_id in jobs_store:
                jobs_store[job_id].update(blocked_payload)
            raise MemorandumVerificationBlockedError(verification_gate)'''

old_pipeline_gate_norm = old_pipeline_gate.replace("\r\n", "\n")
assert old_pipeline_gate_norm in content_norm, "old_pipeline_gate not found in main.py"
content_norm = content_norm.replace(old_pipeline_gate_norm, new_pipeline_gate.replace("\r\n", "\n"))

# 6. Blocked UX handling in GET /query/{job_id}
old_get_job = '''    job = jobs_store[job_id]

    if job["user_id"] != authenticated_user_id:

        raise HTTPException(status_code=403, detail="Not authorized to access this job.")

    return {

        "status": job["status"],

        "stage": job.get("stage"),

        "early_display": job.get("early_display"),

        "result": job.get("result"),'''

new_get_job = '''    job = jobs_store[job_id]

    if job["user_id"] != authenticated_user_id:

        raise HTTPException(status_code=403, detail="Not authorized to access this job.")

    if job.get("status") == "error":
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
        }

    return {

        "status": job["status"],

        "stage": job.get("stage"),

        "early_display": job.get("early_display"),

        "result": job.get("result"),'''

old_get_job_norm = old_get_job.replace("\r\n", "\n")
assert old_get_job_norm in content_norm, "old_get_job not found in main.py"
content_norm = content_norm.replace(old_get_job_norm, new_get_job.replace("\r\n", "\n"))

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("main.py patched successfully with all fail-closed gates and blocked UX")
