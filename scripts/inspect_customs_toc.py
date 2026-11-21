import re
import json

with open(r'D:\pakistan_code_text\Customs Act, 1969 (Same as on the official website of FBR dated 30-06-2025).txt', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

c_idx = text.find('CONTENTS')
m_preamble = re.search(r'\b(An\s+Act\s+to\s+consolidate|WHEREAS\s+it\s+is\s+expedient|Preamble)\b', text[c_idx:], re.I)
toc_text = text[c_idx:c_idx + m_preamble.start()]
raw_lines = [l.strip() for l in toc_text.splitlines() if l.strip()]

# Filter out running headers and chapter headers
clean_lines = []
for l in raw_lines:
    if l.upper() in ["CONTENTS", "SECTION", "PAGE", "NO.", "THE CUSTOMS ACT, 1969", "THE CUSTOMS ACT,1969"]:
        continue
    if re.match(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$', l, re.I):
        continue
    if re.match(r'^CHAPTER\s+[IVXLCDM]+', l, re.I):
        continue
    clean_lines.append(l)

# In clean_lines, an entry starts with section number (e.g. 1, 2, 3, 3A, 3AAA., 221A, etc.)
# Followed by description, followed by page number (integer)
sec_pat = re.compile(r'^([0-9]{1,3}[A-Z]{0,4})\.?$')

toc_entries = []
i = 0
while i < len(clean_lines):
    line = clean_lines[i]
    m = sec_pat.match(line)
    if m:
        sec_num = m.group(1)
        i += 1
        desc_parts = []
        while i < len(clean_lines):
            nxt = clean_lines[i]
            # Check if nxt is a page number (integer)
            if nxt.isdigit() and int(nxt) <= 350:
                i += 1
                break
            # Check if nxt is next section number
            if sec_pat.match(nxt):
                # could be next section without page number
                break
            desc_parts.append(nxt)
            i += 1
        desc = " ".join(desc_parts)
        toc_entries.append((sec_num, desc))
    else:
        i += 1

print(f"Total reconstructed TOC entries: {len(toc_entries)}")

# Load staged sections
with open(r'data\statutes_v3_staging\CUSTOMS_1969.json', 'r', encoding='utf-8') as fp:
    staged = json.load(fp)

staged_secs = {r['section']: r for r in staged}
toc_secs = {e[0]: e[1] for e in toc_entries}

print(f"Total staged sections: {len(staged_secs)}")
print(f"Total unique TOC sections: {len(toc_secs)}")

# Normalize section IDs for matching (e.g. 155-I vs 155I, 221-A vs 221A)
def norm_sec(s):
    return s.replace("-", "").upper()

norm_staged = {norm_sec(k): k for k in staged_secs}
norm_toc = {norm_sec(k): k for k in toc_secs}

missing_in_staged = set(norm_toc.keys()) - set(norm_staged.keys())
extra_in_staged = set(norm_staged.keys()) - set(norm_toc.keys())

print(f"\nMissing in staged (in TOC but not parsed as section): {len(missing_in_staged)}")
for m in sorted(list(missing_in_staged)):
    orig = norm_toc[m]
    print(f"  TOC Section {orig}: {toc_secs[orig]}")

print(f"\nExtra in staged (in text as section but not in TOC): {len(extra_in_staged)}")
for e in sorted(list(extra_in_staged)):
    orig = norm_staged[e]
    print(f"  Staged Section {orig}: {staged_secs[orig].get('heading', '')[:60]}")
