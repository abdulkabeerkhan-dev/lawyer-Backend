file_path = "tests/test_statute_store.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_block = """def test_ni_act_138_confirmed_absent():
    res = lookup("NI Act", "Section 138")
    assert res.status == "CONFIRMED_ABSENT"
    assert res.exists is False
    assert res.confirmed_absent is True
    assert "Section 489-F PPC" in (res.pakistani_equivalent or "")
    assert "Negotiable Instruments Act" in (res.explanation or "")


def test_ni_act_118_exists():
    res = lookup("NI Act", "Section 118")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.confirmed_absent is False
    assert "Presumptions" in (res.title or "")"""

new_block = """def test_ni_act_138_confirmed_absent():
    # Order 1.9 - Item 8: NI Act is quarantined (no official PDF); lookups return UNVERIFIED
    res = lookup("NI Act", "Section 138")
    assert res.status == "UNVERIFIED"
    assert res.exists is False
    assert res.confirmed_absent is False


def test_ni_act_118_exists():
    # Order 1.9 - Item 8: NI Act is quarantined (no official PDF); lookups return UNVERIFIED
    res = lookup("NI Act", "Section 118")
    assert res.status == "UNVERIFIED"
    assert res.exists is False
    assert res.confirmed_absent is False"""

content_norm = content.replace("\r\n", "\n")
old_block_norm = old_block.replace("\r\n", "\n")
assert old_block_norm in content_norm, "old_block not found in test_statute_store.py"
content_norm = content_norm.replace(old_block_norm, new_block.replace("\r\n", "\n"))

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("test_statute_store.py patched successfully")
