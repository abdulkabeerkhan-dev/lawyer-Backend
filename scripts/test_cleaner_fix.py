import re

def clean_footnotes(text: str) -> str:
    # 1. Glued provision keyword + number + footnote: e.g. 'section 1215[' -> 'section 121 ['
    def fix_glued_section_footnote(m):
        kw = m.group(1) # 'section', 'article', etc.
        full_num = m.group(2)
        # Check split points: e.g. '121' + '5', '497' + '2'
        for split_at in [len(full_num)-1, len(full_num)-2]:
            if split_at > 0:
                sec_num = int(full_num[:split_at])
                fn_num = int(full_num[split_at:])
                if 1 <= sec_num <= 511 and 1 <= fn_num <= 99:
                    return f"{kw} {sec_num} ["
        return m.group(0)

    text = re.sub(r'\b(section|article|sub-section|order|rule)\s+(\d{2,6})\[', fix_glued_section_footnote, text, flags=re.I)
    
    # 2. Year glued to footnote: '20241[' -> '2024 ['
    text = re.sub(r'\b(18\d\d|19\d\d|20\d\d)(\d{1,2})\[', r'\1 [', text)
    
    # 3. Word glued to footnote: 'section11[' -> 'section ['
    text = re.sub(r'([a-zA-Z])(\d{1,2})\[', r'\1 [', text)
    
    # 4. Standalone footnote before bracket: ' 1[' or ' 32[' -> ' ['
    text = re.sub(r'(?:^|(?<=[\s\(\,\.\;\:\—\-\"]))(\d{1,3})\[', r' [', text)
    
    # 5. Unpack brackets: '[text]' -> 'text'
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)
    # remove empty brackets '[]'
    text = re.sub(r'\[\s*\]', '', text)
    
    # Clean up double punctuation resulting from empty omissions: ', ,' -> ','
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r',\s*or\s*,', ' or ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()

samples = [
    ("ITO 122", "Commissioner may amend an assessment order treated as issued under section 120 or issued under section 1215[, 6[ ] 7[or 8[ ], by making"),
    ("Customs 217", "in pursuance of this Act or the rules 32[and notwithstanding anything in any other law"),
    ("ITO 235", "collected under this section11[and under section 235] shall be a 11[minimum] tax"),
    ("CrPC 497", "subject to the provisions of section 4972[a person accused of an offence")
]

for label, s in samples:
    print(f"--- {label} ---")
    print("RAW  :", s)
    print("CLEAN:", clean_footnotes(s))
