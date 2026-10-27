"""
scripts/patch_statute_injector_banner.py
"""
import os

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
fpath = os.path.join(REPO_DIR, "legal_ai", "statutes", "statute_injector.py")

with open(fpath, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if i in range(569, 575): # 0-indexed 569 is line 570
        if i == 569:
            new_lines.append('                lines.append("Do NOT print any \'> [!\' banner yourself. System banners are attached automatically after verification.")\n')
            new_lines.append('                lines.append("Human advocate verification against official Gazette page images is required before relying on this text.")\n')
        continue
    new_lines.append(line)

with open(fpath, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Updated lines 570-575 in statute_injector.py successfully!")
