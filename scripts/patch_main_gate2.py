import os

main_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'main.py')
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = "        inserted_row_id = str(uuid.uuid4())\n"
replacement = """        # STAGE 5 GATE 2: ANTI-PATTERN GUARDRAIL & GUARDIAN INTERVENTION
        from legal_ai.verification.anti_pattern_guard import AntiPatternGuard
        anti_guard = AntiPatternGuard()
        guard_res = anti_guard.check_text(display_answer)
        if not guard_res["is_clean"]:
            display_answer = guard_res["sanitized_text"]
            guardian_notice = anti_guard.format_guardian_notice(guard_res["guardian_interventions"])
            if guardian_notice:
                display_answer = guardian_notice + "\\n\\n" + display_answer

        inserted_row_id = str(uuid.uuid4())\n"""

assert target in content, "Target not found in main.py!"
content = content.replace(target, replacement, 1)

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully patched main.py with Gate 2 Anti-Pattern Guardrail")
