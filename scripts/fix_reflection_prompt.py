file_path = "main.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''            print(f"⚠️ Legal Guardrails & Completeness Issues (round {ref_round+1}): {all_issues}. Triggering reflection loop...", file=sys.stderr)

            "3. Ensure all relevant sections are articulated with <<<CARDS>>> JSON.\\n"

            reflection_messages = list(messages) + ['''

replacement = '''            print(f"⚠️ Legal Guardrails & Completeness Issues (round {ref_round+1}): {all_issues}. Triggering reflection loop...", file=sys.stderr)

            reflection_prompt = (
                f"Please address the following legal guardrails and completeness issues in your legal memorandum:\\n"
                + "\\n".join(f"- {iss}" for iss in all_issues)
                + "\\nStrictly preserve verbatim statutory text and ensure all citations are authentic."
            )

            reflection_messages = list(messages) + ['''

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
assert target_norm in content_norm, "target not found"
content_norm = content_norm.replace(target_norm, replacement)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("reflection_prompt restored in main.py")
