file_path = "legal_ai/verification/memo_verifier.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''def verify_memorandum_text(memo_text: str) -> Dict[str, Any]:
    verifier = MemoVerifier()
    return verifier.verify_memo(memo_text)'''

replacement = '''def verify_memorandum_text(memo_text: str, is_system_rendered: bool = False) -> Dict[str, Any]:
    verifier = MemoVerifier()
    return verifier.verify_memo(memo_text, is_system_rendered=is_system_rendered)'''

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
assert target_norm in content_norm, "target not found"
content_norm = content_norm.replace(target_norm, replacement)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("verify_memorandum_text now accepts is_system_rendered")
