import re

file_path = "legal_ai/statutes/statute_injector.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''        # 15. Pakistan Penal Code (PPC)
        if "ppc" in p_low or any(k in p_low for k in ["409", "420", "406", "489-f", "489f", "302", "376"]):
            act_code = "PPC_1860"
            m_sec = re.search(r'\\b(?:sections?|secs?\\.?|s\\.)\\s*(\\d+[a-z]?(?:-[a-z])?)\\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                sec_clean = sec_num.replace("-", "")
                return act_code, f"{act_code}_SEC_{sec_clean}", f"Section {sec_num}, Pakistan Penal Code, 1860"'''

replacement = '''        # 15. Pakistan Penal Code (PPC)
        if "ppc" in p_low or any(k in p_low for k in ["409", "420", "406", "489-f", "489f", "302", "376"]):
            act_code = "PPC_1860"
            m_sec = re.search(r'\\b(?:sections?|secs?\\.?|s\\.)\\s*(\\d+[a-z]?(?:-[a-z])?)\\b', p_low)
            if m_sec:
                sec_num = m_sec.group(1).upper()
                sec_clean = sec_num.replace("-", "")
                sec_disp = f"{sec_num[:-1]}-{sec_num[-1]}" if re.match(r'^\\d+[A-Z]$', sec_num) else sec_num
                return act_code, f"{act_code}_SEC_{sec_clean}", f"Section {sec_disp}, Pakistan Penal Code, 1860"'''

content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")

assert target_norm in content_norm, "target not found in statute_injector.py"
content_norm = content_norm.replace(target_norm, replacement)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content_norm)

print("statute_injector.py patched successfully")
