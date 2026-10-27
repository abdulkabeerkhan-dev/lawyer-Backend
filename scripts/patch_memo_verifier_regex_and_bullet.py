"""
scripts/patch_memo_verifier_regex_and_bullet.py
1. Fixes non-greedy regex in extract_statutory_citations that was truncating 'Contract Act' into 'Contract'
2. Adds 'application' and 'opinion' to in_exempt_section
3. Allows Markdown bullet points starting with '-' and numbered lists in Rule (e)
"""

with open("legal_ai/verification/memo_verifier.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Fix statutory citation patterns
old_pat = """            # 3. Section N(x)(y) of Act / s. N
            r'\\b(?:Section|Sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?(?:\\(\\d+\\))*(?:\\([a-z]\\))*)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO))\\b',
            # 4. Section multiple: ss. 10 and 22
            r'\\b(?:ss\\.|sections)\\s*(\\d+[A-Za-z]?)\\s+and\\s+(\d+[A-Za-z]?)(?:\\s*(?:of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)))?\\b',
            # 5. Article N of Act / Constitution / QSO
            r'\\b(?:Article|Art\\.)\\s*(\\d+[A-Za-z]?)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Constitution|QSO|Qanun-e-Shahadat))\\b',"""

new_pat = """            # 3. Section N(x)(y) of Act / s. N
            r'\\b(?:Section|Sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?(?:\\(\\d+\\))*(?:\\([a-z]\\))*)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?\\b(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)\\b(?:\\s*,\\s*\\d{4})?)',
            # 4. Section multiple: ss. 10 and 22
            r'\\b(?:ss\\.|sections)\\s*(\\d+[A-Za-z]?)\\s+and\\s+(\d+[A-Za-z]?)(?:\\s*(?:of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?\\b(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)\\b(?:\\s*,\\s*\\d{4})?))?',
            # 5. Article N of Act / Constitution / QSO
            r'\\b(?:Article|Art\\.)\\s*(\\d+[A-Za-z]?)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?\\b(?:Constitution|QSO|Qanun-e-Shahadat|Limitation\\s+Act|Act)\\b(?:\\s*,\\s*\\d{4})?)',"""

# 2. Fix in_exempt_section
old_exempt = """                in_exempt_section = (
                    "legal issue" in lower_h or 
                    "unreviewed analysis" in lower_h or 
                    "statutory provisions" in lower_h or
                    "relevant provisions" in lower_h
                )"""

new_exempt = """                in_exempt_section = (
                    "legal issue" in lower_h or 
                    "unreviewed analysis" in lower_h or 
                    "statutory provisions" in lower_h or
                    "relevant provisions" in lower_h or
                    "application" in lower_h or
                    "opinion" in lower_h
                )"""

# 3. Fix bullet line skip in Rule (e)
old_bullet = """            if (s_line.startswith("*") or s_line.startswith(">") or s_line.startswith("|") or 
                s_line.startswith("---") or s_line.startswith("- **[analysis") or s_line.startswith("- **[paraphrase")):
                continue"""

new_bullet = """            if (s_line.startswith("*") or s_line.startswith("-") or s_line.startswith(">") or 
                s_line.startswith("|") or s_line.startswith("---") or re.match(r'^\\d+\\.', s_line)):
                continue"""

text_norm = text.replace("\r\n", "\n")
old_pat_norm = old_pat.replace("\r\n", "\n")
new_pat_norm = new_pat.replace("\r\n", "\n")
old_exempt_norm = old_exempt.replace("\r\n", "\n")
new_exempt_norm = new_exempt.replace("\r\n", "\n")
old_bullet_norm = old_bullet.replace("\r\n", "\n")
new_bullet_norm = new_bullet.replace("\r\n", "\n")

c1 = old_pat_norm in text_norm
c2 = old_exempt_norm in text_norm
c3 = old_bullet_norm in text_norm

print(f"Match 1 (pat): {c1}, Match 2 (exempt): {c2}, Match 3 (bullet): {c3}")

if c1:
    text_norm = text_norm.replace(old_pat_norm, new_pat_norm, 1)
if c2:
    text_norm = text_norm.replace(old_exempt_norm, new_exempt_norm, 1)
if c3:
    text_norm = text_norm.replace(old_bullet_norm, new_bullet_norm, 1)

with open("legal_ai/verification/memo_verifier.py", "w", encoding="utf-8") as f:
    f.write(text_norm)
print("Updated legal_ai/verification/memo_verifier.py successfully.")
