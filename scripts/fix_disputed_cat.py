file_path = "legal_ai/verification/memo_verifier.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })'''

replacement = '''                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT_UNNOTICED" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })'''

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
assert target_norm in content_norm, "target not found"
content_norm = content_norm.replace(target_norm, replacement)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("Updated category to DISPUTED_TEXT_UNNOTICED while keeping label as DISPUTED_TEXT_NOTICE")
