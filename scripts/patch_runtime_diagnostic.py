import re

file_path = "legal_ai/synthesis/memorandum_generator.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''def log_runtime_diagnostic(stage: str, text: str) -> None:

    """

    Prints diagnostic runtime logging for output synthesis, boundary enforcement, and final display.

    """

    if not text:

        preview = "None / Empty"

        headers = []

    else:

        preview = text.strip()[:200].replace("\\n", " ")

        headers = [

            line.strip()

            for line in text.split("\\n")

            if re.match(r'^(?:#{1,6}|\\*{2}|\\d+[\\.\\)])\\s+', line.strip())

        ]

    print(f"[RUNTIME LOG] {stage}: First 200 chars: '{preview}...' | Section Headers: {headers}", file=sys.stderr, flush=True)'''

replacement = '''def log_runtime_diagnostic(stage: str, text: Any) -> None:
    """
    Prints diagnostic runtime logging for output synthesis, boundary enforcement, and final display.
    ORDER 1.9 - ITEM 5: Strips all raw memo text spans from logs. Emits only metadata and counts.
    """
    if not text:
        print(f"[RUNTIME LOG] {stage}: Empty/None", file=sys.stderr, flush=True)
        return

    if isinstance(text, dict):
        safe_keys = {k: v for k, v in text.items() if k not in ("span", "raw", "text", "memo_cleaned", "cleaned_memo_text")}
        print(f"[RUNTIME LOG] {stage}: dict metadata: {safe_keys}", file=sys.stderr, flush=True)
        return

    text_str = str(text)
    header_count = sum(1 for line in text_str.splitlines() if re.match(r'^(?:#{1,6}|\\*{2}|\\d+[\\.\\)])\\s+', line.strip()))
    sha_pref = hashlib.sha256(text_str.encode("utf-8")).hexdigest()[:12]
    print(f"[RUNTIME LOG] {stage}: length={len(text_str)} chars, lines={len(text_str.splitlines())}, headers_count={header_count}, sha256_prefix={sha_pref}", file=sys.stderr, flush=True)'''

# Normalize newlines to match
content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")

assert target_norm in content_norm, "target function not found in memorandum_generator.py"
content_norm = content_norm.replace(target_norm, replacement)

# Also ensure hashlib is imported
if "import hashlib" not in content_norm:
    content_norm = "import hashlib\n" + content_norm

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("memorandum_generator.py patched successfully")
