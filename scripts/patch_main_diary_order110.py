import os

file_path = "main.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_block = '''    # ORDER 1.9 - ITEM 5: DIARY FAIL-CLOSED CITATION & QUOTE GATE
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

new_block = '''    # ORDER 1.10 - ITEM 10: DIARY WARNING POLICY (WARN, DO NOT BLOCK)
    diary_warning = None
    if payload.notes and ("> " in payload.notes or any(k in payload.notes.lower() for k in ["section ", "order ", "article "])):
        from legal_ai.verification.memo_verifier import verify_pleading_citations_and_quotes
        v_diary = verify_pleading_citations_and_quotes(payload.notes)
        if not v_diary.get("passed", False):
            diary_warning = {
                "warning": "UNVERIFIED_LEGAL_CITATIONS",
                "message": "Note contains unverified legal citations or quotes; check manually before court reliance.",
                "total_failures": v_diary.get("total_failures", 0),
                "failures": v_diary.get("failures", [])
            }'''

old_return = '''    return {"status": "success", "data": res.data[0] if res.data else None}'''
new_return = '''    resp_payload = {"status": "success", "data": res.data[0] if res.data else None}
    if diary_warning:
        resp_payload["warning"] = diary_warning
    return resp_payload'''

content_norm = content.replace("\r\n", "\n")
old_block_norm = old_block.replace("\r\n", "\n")
old_return_norm = old_return.replace("\r\n", "\n")

assert old_block_norm in content_norm, "old_block not found in main.py"
assert old_return_norm in content_norm, "old_return not found in main.py"

content_norm = content_norm.replace(old_block_norm, new_block.replace("\r\n", "\n"))
content_norm = content_norm.replace(old_return_norm, new_return.replace("\r\n", "\n"))

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("main.py diary gate successfully updated to warning policy")
