file_path = "core/statutory_validator.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''        return {
            "is_valid": True,
            "status": "verified",
            "canonical_id": canonical_id,
            "display_name": record.get("display_name"),
            "title": record.get("title"),
            "status_jurisdiction": record.get("status"),
            "superseded_reference": record.get("superseded_reference"),
            "source_citation": record.get("source_citation"),
            "raw_citation": citation
        }'''

replacement = '''        return {
            "is_valid": True,
            "status": "verified",
            "canonical_id": canonical_id,
            "display_name": record.get("display_name") or record.get("title") or citation,
            "title": record.get("title"),
            "status_jurisdiction": record.get("status"),
            "superseded_reference": record.get("superseded_reference"),
            "source_citation": record.get("source_citation") or record.get("source_file") or "Pakistan Code",
            "raw_citation": citation
        }'''

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
assert target_norm in content_norm, "target not found in statutory_validator.py"
content_norm = content_norm.replace(target_norm, replacement)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("core/statutory_validator.py patched successfully")
