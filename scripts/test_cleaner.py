import json, re

with open('data/statutes_v3_staging/ITO_2001.json', 'r', encoding='utf-8') as f:
    ito = json.load(f)

r122 = next(r for r in ito if r.get('section') == '122')
raw = r122['raw_text']

def clean_section_text_improved(raw_text):
    re_page_footer = re.compile(r'^\s*Page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE)
    re_gazette_header = re.compile(r'^\s*(?:THE\s+GAZETTE\s+OF\s+PAKISTAN|EXTRAORDINARY|PART\s+[IVX]+)\s*$', re.IGNORECASE)
    re_running_header = re.compile(r'^\s*(?:Chapter|Part)\s+[IVX0-9]+.*?_{3,}\s*$', re.IGNORECASE)
    re_page_num_alone = re.compile(r'^\s*\d{1,4}\s*$')
    re_footnote_line = re.compile(
        r'^\s*\d+\s*(?:\[\s*\d*\s*\]\s*)?(?:Ins\.|Subs\.|Added|Omitted|Deleted|New\s+section|Replaced|For\s+the|The\s+words|Words?|Clause|Sub-section|Section|Proviso|Paragraph|Full\s+stop|Comma|In\s+section|Under\s+the|\*|Ommited)\b',
        re.IGNORECASE
    )

    lines = raw_text.splitlines()
    clean_lines = []
    amendment_notes = []
    in_footnote_block = False

    for line in lines:
        s_line = line.strip()
        if not s_line:
            clean_lines.append("")
            in_footnote_block = False
            continue

        if re_page_footer.match(s_line) or re_gazette_header.match(s_line) or re_running_header.match(s_line):
            continue

        if re_page_num_alone.match(s_line):
            continue

        if re_footnote_line.match(s_line):
            amendment_notes.append(s_line)
            in_footnote_block = True
            continue
        elif in_footnote_block and (s_line.startswith("(") or "Ordinance" in s_line or "Act" in s_line or "s." in s_line or "w.e.f." in s_line) and not s_line.startswith("Provided"):
            if amendment_notes:
                amendment_notes[-1] += " " + s_line
            else:
                amendment_notes.append(s_line)
            continue
        else:
            in_footnote_block = False

        clean_lines.append(line)

    text = "\n".join(clean_lines)

    # 1. Disentangle footnote markers from preceding words/numbers
    # (a) section/article/rule/clause/order + number + footnote: 'section 1215[' -> 'section 121 ['
    text = re.sub(r'\b(sections?|articles?|sub-sections?|rules?|orders?|clauses?)\s+(\d{1,4})(\d{1,2})\[', r'\1 \2 [', text, flags=re.IGNORECASE)
    # (b) 4-digit years: '19731[' -> '1973 ['
    text = re.sub(r'\b(18\d\d|19\d\d|20\d\d)(\d{1,2})\[', r'\1 [', text)
    # (c) words: 'Commissioner1[' -> 'Commissioner ['
    text = re.sub(r'([a-zA-Z])(\d{1,2})\[', r'\1 [', text)

    # 2. Footnote markers before [: e.g. ' 5[' -> ' ['
    text = re.sub(r'(?:^|(?<=[\s\(\,\.\;\:\—\-\"]))(\d{1,3})\[', ' [', text)

    # 3. Strip omission markers [* * *] or [***] or [   ]
    text = re.sub(r'\[\s*\*+\s*\]', '', text)
    text = re.sub(r'\[\s*\]', '', text)

    # 4. Unwrap amended text: [something] -> something
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)
    text = text.replace("[", "").replace("]", "")

    # Soft unwrap lines broken mid-sentence
    paragraphs = text.split("\n\n")
    unwrapped_paras = []
    for para in paragraphs:
        p_lines = [l.strip() for l in para.splitlines() if l.strip()]
        if not p_lines:
            continue
        merged = []
        for l in p_lines:
            is_new_clause = bool(re.match(r'^(?:\([a-zA-Z0-9]+\)|\d+\.|Provided\b)', l))
            if merged and not is_new_clause and not merged[-1].endswith((".", ":", ";")):
                if merged[-1].endswith("-"):
                    merged[-1] = merged[-1][:-1] + l
                else:
                    merged[-1] = merged[-1] + " " + l
            else:
                merged.append(l)
        unwrapped_paras.append("\n".join(merged))

    cleaned_text = "\n\n".join(unwrapped_paras).strip()
    cleaned_text = re.sub(r'\bwilful\b', 'willful', cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)

    return cleaned_text, amendment_notes

cleaned, notes = clean_section_text_improved(raw)
print('=' * 80)
print('CLEANED ITO 122 FIRST 400 CHARS:')
print(repr(cleaned[:400]))
print('=' * 80)
print('NOTES EXTRACTED:', len(notes))
for n in notes[:5]:
    print('  Note:', repr(n))
