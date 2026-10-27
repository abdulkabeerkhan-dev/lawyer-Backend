import os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'legal_ai', 'verification', 'memo_verifier.py')
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content_norm = content.replace('\r\n', '\n')

old_block = """            if s_line.startswith("#"):
                lower_h = s_line.lower()
                in_exempt_section = (
                    "legal issue" in lower_h or 
                    "unreviewed analysis" in lower_h or 
                    "statutory provisions" in lower_h or
                    "relevant provisions" in lower_h or
                    "application" in lower_h or
                    "opinion" in lower_h
                )
                continue"""

new_block = """            if s_line.startswith("#"):
                m_header = re.match(r'^(#{1,6})\s*(.*)', s_line)
                if m_header:
                    hashes, title = m_header.group(1), m_header.group(2).lower()
                    is_main_heading = len(hashes) <= 2
                    exempt_keywords = (
                        "legal issue", "unreviewed analysis", "statutory provisions",
                        "relevant provisions", "statutory framework", "controlling law",
                        "application", "opinion", "analysis", "summary", "executive summary",
                        "remedy", "remedies", "conclusion", "recommendation", "roadmap"
                    )
                    matches_exempt = any(kw in title for kw in exempt_keywords)
                    if is_main_heading:
                        in_exempt_section = matches_exempt
                    elif matches_exempt:
                        in_exempt_section = True
                continue"""

assert old_block in content_norm, "old_block not found in content_norm!"
content_norm = content_norm.replace(old_block, new_block, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content_norm)

print("Successfully replaced header block in memo_verifier.py")
