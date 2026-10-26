import os

repo_dir = r"I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
qp_path = os.path.join(repo_dir, "legal_ai", "query_engine", "query_processor.py")

with open(qp_path, "r", encoding="utf-8") as f:
    text = f.read()

target = """            regen_message = await anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": regen_content}]
            )"""

replacement = """            regen_message = await safe_create_anthropic_message(
                model=CLAUDE_MODEL,
                max_tokens=synthesis_max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": regen_content}]
            )"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open(qp_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("SUCCESS: Patched safe_create_anthropic_message")
else:
    print("WARNING: target not found")
