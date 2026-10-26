import os

# 1. Patch legal_ai/query_engine/query_processor.py
qp_file = "legal_ai/query_engine/query_processor.py"
with open(qp_file, "r", encoding="utf-8") as f:
    qp_content = f.read()

qp_old = '''    # ORDER 1.7 - ITEM 10: MEMORANDUM VERIFIER GATE
    # Fail-closed gate: if verification fails, the response is BLOCKED and never returned to the user.
    from legal_ai.verification.memo_verifier import verify_memorandum_text, MemorandumVerificationBlockedError
    verification_gate = verify_memorandum_text(clean_answer)
    if not verification_gate.get('passed', False):'''

qp_new = '''    # ORDER 1.7 & 1.10: MEMORANDUM VERIFIER GATE & SYSTEM DISPUTED BANNER FLOW
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

    if not verification_gate.get('passed', False):'''

qp_content_norm = qp_content.replace("\r\n", "\n")
qp_old_norm = qp_old.replace("\r\n", "\n")
assert qp_old_norm in qp_content_norm, "qp_old not found in query_processor.py"
qp_content_norm = qp_content_norm.replace(qp_old_norm, qp_new.replace("\r\n", "\n"))

with open(qp_file, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(qp_content_norm)

print("query_processor.py successfully patched for system disputed banner flow")

# 2. Patch main.py legacy pipeline
main_file = "main.py"
with open(main_file, "r", encoding="utf-8") as f:
    main_content = f.read()

main_old = '''        # ORDER 1.9 - ITEM 5 & 6: MEMORANDUM VERIFIER GATE WITH BLOCKED UX & AUTO-REGENERATION
        from legal_ai.verification.memo_verifier import verify_memorandum_text, MemorandumVerificationBlockedError
        verification_gate = verify_memorandum_text(display_answer)'''

main_new = '''        # ORDER 1.9 & 1.10: MEMORANDUM VERIFIER GATE WITH SYSTEM DISPUTED BANNER FLOW
        from legal_ai.verification.memo_verifier import (
            verify_memorandum_text,
            MemorandumVerificationBlockedError,
            attach_system_disputed_banner
        )
        verification_gate = verify_memorandum_text(display_answer, is_system_rendered=False)
        if not verification_gate.get('passed', False):
            disputed_notices = verification_gate.get('disputed_notices', [])
            failures = verification_gate.get('failures', [])
            if disputed_notices and all(f.get('category') == 'DISPUTED_TEXT_UNNOTICED' for f in failures):
                bannered_answer = attach_system_disputed_banner(display_answer, disputed_notices)
                re_gate = verify_memorandum_text(bannered_answer, is_system_rendered=True)
                if re_gate.get('passed', False):
                    display_answer = bannered_answer
                    verification_gate = re_gate'''

main_content_norm = main_content.replace("\r\n", "\n")
main_old_norm = main_old.replace("\r\n", "\n")
assert main_old_norm in main_content_norm, "main_old not found in main.py"
main_content_norm = main_content_norm.replace(main_old_norm, main_new.replace("\r\n", "\n"))

with open(main_file, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(main_content_norm)

print("main.py successfully patched for system disputed banner flow")
