r"""
scripts/statutes/parse_pakistan_code_pdf.py

Splits an official Pakistan Code PDF (pakistancode.gov.pk layout) into provisions:
  {"number": "199", "heading": "Jurisdiction of High Court", "text": "...", "omitted": False}

Layout handled:
  - a table of contents first ("199. \n Jurisdiction of High Court"), skipped: the body starts at
    the first provision line that carries its heading and body on one line;
  - provision starts like "199. Jurisdiction of High Court.__ (1) ..." or "{187. Issue ...__",
    with amendment markers ("1[", "{") before the number or heading;
  - omitted provisions written "186. 1[* * * *]" (one star per line);
  - page furniture ("Page 11 of 176") and amendment footnotes at page ends
    ("1 Subs. by the Constitution (Twenty-seventh Amendment) Act, 2025 ...") removed.
Footnote markers inside the text ("2[the Supreme Court]") are kept as square brackets with the
digit dropped, which is how statutes_v3_staging already writes them.
"""
import re
import sys
from typing import Dict, List

import pymupdf

PAGE_RE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.I)
FOOT_RE = re.compile(r"^\s*\d{1,3}\s*(?:Subs|Ins|Omitted|Added|Renumbered|Rep\.|Repealed|The\s+(?:words|word|original|comma|brackets)|"
                     r"For\s+the|Sub-|Earlier|Now|See|Clause|Para|Article|Section|Art\.|S\.|Proviso|Explanation|Words|"
                     r"Inserted|Substituted|Re-numbered|Deleted|Vide|Ibid|Shall|Notified|Brought)", re.I)
START_RE = re.compile(
    r"^\s*[\{\[]?(?:\d{1,2}\[)?\{?\s*(?P<num>\d{1,3}[A-Z]{0,3})\s*\.\s*(?:\d{1,2}\[)?\[?"
    r"(?P<head>[A-Z\"'“(\[][^\n]{2,220}?)(?:\.\]?\s*(?:_{2}|—|―|–|‑|-{1,2})|_{2}|—\s|―\s|\.\s+(?=[A-Z(\[]))")
OMIT_RE = re.compile(r"^\s*[\{\[]?(?:\d{1,2}\[)?\s*(?P<num>\d{1,3}[A-Z]{0,3})\s*\.\s*(?:\d{1,2}\[)\s*\*")


def clean_lines(pdf_path: str) -> List[str]:
    out = []
    for page in pymupdf.open(pdf_path):
        lines = page.get_text().split("\n")
        # footnotes sit at the end of a page: drop a trailing run of footnote-looking lines
        keep = list(lines)
        j = len(keep) - 1
        while j >= 0 and (not keep[j].strip() or PAGE_RE.match(keep[j]) or FOOT_RE.match(keep[j])
                          or (j > 0 and FOOT_RE.match(keep[j - 1]) and not START_RE.match(keep[j]))):
            j -= 1
        for ln in keep[: j + 1]:
            if PAGE_RE.match(ln):
                continue
            out.append(ln.rstrip())
    return out


def _tidy(t: str) -> str:
    t = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n", t)                    # page-break blank runs
    t = re.sub(r"(?<![A-Za-z0-9])\d{1,2}\[", "[", t)          # footnote digit before an amendment bracket
    t = re.sub(r"\n\s*\*\s*(?=\n)", " *", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"[ \t]*\n(?!\s*(?:\(|\d+[A-Z]?\.|[a-z]{1,4}\)|\[|Explanation|Illustration|Provided))", " ", t)
    t = re.sub(r" {2,}", " ", t).strip()
    for _ in range(3):
        t = re.sub(r"\s*\[?\s*(?:CHAPTER|PART)\s+[0-9IVXLC]+[A-Z]?\b[^\]]*\]?\s*$", "", t)
        t = re.sub(r"\s*\[\s*$", "", t).strip()
    return t


def parse(pdf_path: str) -> List[Dict]:
    lines = clean_lines(pdf_path)
    # the body begins at the first provision line that has its heading AND body text on one line
    starts = [i for i, ln in enumerate(lines) if START_RE.match(ln) or OMIT_RE.match(ln)]
    body = next((i for i in starts if START_RE.match(lines[i]) and len(lines[i]) > 40), 0)
    provs: List[Dict] = []
    cur = None
    seen = set()
    for ln in lines[body:]:
        m = START_RE.match(ln)
        o = None if m else OMIT_RE.match(ln)
        hit = m or o
        if hit:
            num = hit.group("num")
            # a number must move forward (cross references such as "see 199." inside text are ignored)
            if num not in seen and (not provs or _order_ok(provs[-1]["number"], num)):
                if cur:
                    provs.append(cur)
                seen.add(num)
                if m:
                    head = m.group("head").strip().rstrip(".]").strip()
                    cur = {"number": num, "heading": re.sub(r"^\d{1,2}\[", "", head).strip("[] "),
                           "text": ln.strip(), "omitted": False}
                else:
                    cur = {"number": num, "heading": "", "text": ln.strip(), "omitted": True}
                continue
        if cur is not None:
            cur["text"] += "\n" + ln
    if cur:
        provs.append(cur)
    for p in provs:
        p["text"] = _tidy(p["text"])
        if not p["omitted"] and re.fullmatch(r"\W*\d{1,3}[A-Z]{0,3}\s*\.\s*\[?\s*(?:\*\s*)+\]?\W*", p["text"]):
            p["omitted"] = True
    return provs


def _key(n: str):
    m = re.match(r"(\d+)([A-Z]*)", n)
    return (int(m.group(1)), m.group(2))


def _order_ok(prev: str, nxt: str) -> bool:
    a, b = _key(prev), _key(nxt)
    return b > a and b[0] - a[0] <= 40


TOC_NUM = re.compile(r"^\s*(\d{1,3}[A-Z]{0,3})\.\s*(.*)$")


def parse_toc(lines: List[str]):
    """[(number, heading)] from the CONTENTS block: 'N.' then a heading line, or 'N. Heading'."""
    try:
        i = next(k for k, ln in enumerate(lines) if ln.strip().upper() in ("CONTENTS", "CONTENT", "TABLE OF CONTENTS"))
    except StopIteration:
        return [], 0
    toc, k, last = [], i + 1, None
    while k < len(lines):
        ln = lines[k].strip()
        m = TOC_NUM.match(ln)
        if m and len(ln) < 160:
            num, rest = m.group(1), m.group(2).strip()
            if not rest:
                j = k + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                rest = lines[j].strip() if j < len(lines) else ""
                if TOC_NUM.match(rest) and len(rest) < 12:
                    rest = ""                           # entry without a heading (usually omitted)
                else:
                    k = j
            if last and _key(num) <= _key(last):
                break                               # numbering restarted: the body has begun
            if len(rest) > 160:
                break
            toc.append((num, rest.rstrip(".")))
            last = num
        elif m is None and toc and len(ln) > 160:
            break
        k += 1
    return toc, k


def _norm(s: str) -> str:
    s = re.sub(r"(?<![A-Za-z])\d{1,2}\[", "", s)
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def parse_with_toc(pdf_path: str) -> List[Dict]:
    lines = clean_lines(pdf_path)
    toc, body_at = parse_toc(lines)
    heads = [h for _, h in toc]
    bogus = bool(heads) and (sum(len(h) for h in heads) / len(heads) > 70 or
                             sum(1 for h in heads if re.search(r"__|—|―|\bshall\b|\bmay be called\b", h)) > len(heads) / 3)
    if len(toc) < 3 or bogus:
        return parse(pdf_path)
    body = "\n".join(lines[body_at:])
    body = re.sub(r"(?<![A-Za-z0-9])\d{1,2}\[", "[", body)      # footnote markers: "2[or impeachment]"
    body = re.sub(r"(?m)^\s*_{5,}\s*$", "", body)
    flat, pos_map = [], []                              # normalised body with a map back to offsets
    for idx, ch in enumerate(body):
        c = ch.lower()
        if c.isalnum():
            flat.append(c); pos_map.append(idx)
    flat = "".join(flat)
    out, cursor = [], 0
    starts = []
    for num, head in toc:
        omitted_toc = bool(re.fullmatch(r"\[?\s*omitted\s*\]?\.?", head, re.I))
        found = None
        if not omitted_toc:
            key = _norm(num) + _norm(head)[:28]
            j = flat.find(key, cursor)
            if j < 0:                                    # footnote digit fused onto the number ("11." for 1.)
                j2 = re.compile(r"\d" + re.escape(key)).search(flat, cursor)
                j = j2.start() + 1 if j2 else -1
            if j >= 0:
                found = pos_map[j]
                cursor = j + len(key)
        else:
            m = re.compile(r"(?:^|\n)\D{0,4}" + re.escape(num) + r"\s*\.\s*(?:\[?\s*\*|\[[^\]\n]{2,120}\]\s*Omitted)").search(body, pos_map[cursor] if cursor < len(pos_map) else len(body))
            if m:
                found = m.start()
        starts.append((num, head, found, omitted_toc))
    # entries not found by heading: look for "N." at a line start between the neighbours that were found
    order = {s[0]: i for i, s in enumerate(starts)}
    for i, (num, head, st, om) in enumerate(starts):
        if st is not None:
            continue
        lo = next((starts[j][2] for j in range(i - 1, -1, -1) if starts[j][2] is not None), 0)
        hi = next((starts[j][2] for j in range(i + 1, len(starts)) if starts[j][2] is not None), len(body))
        m = re.compile(r"(?:^|\n)\W{0,3}" + re.escape(num) + r"\s*[.,]\s*\S").search(body, lo + 1, hi)
        if m:
            starts[i] = (num, head, m.start() + (1 if body[m.start()] == "\n" else 0), om)
    located = [s for s in starts if s[2] is not None]
    located.sort(key=lambda s: s[2])
    for a, b in zip(located, located[1:] + [(None, None, len(body), None)]):
        num, head, st, om = a
        seg = body[st:b[2]]
        seg = re.sub(r"(?:\n\s*(?:PART\s+[IVXLC]+[A-Z]?\b.*|CHAPTER\s+\d+[A-Z]?\b.*|CHAPTER\s+[IVXLC]+\b.*|[A-Z][A-Z ,\-’'()&\[\]]{6,}))+\s*$", "", seg)
        text = _tidy(seg)
        is_omit = om or bool(re.match(r"\W*" + re.escape(num) + r"\s*\.\s*\[[^\]]{2,120}\]\s*Omitted", text)) or bool(re.fullmatch(r"\W*\d{0,2}" + re.escape(num) + r"\s*\.\s*\[?\s*(?:\*\s*)+\]?\W*", text))
        out.append({"number": num, "heading": head if not om else "", "text": text, "omitted": is_omit})
    missing = [s[0] for s in starts if s[2] is None]
    if missing:
        sys.stderr.write(f"{pdf_path}: {len(missing)} TOC entries not located: {missing[:20]}\n")
    return out


if __name__ == "__main__":
    ps = parse_with_toc(sys.argv[1])
    print(len(ps), "provisions")
    for p in ps[: int(sys.argv[2]) if len(sys.argv) > 2 else 5]:
        print(p["number"], "|", p["heading"][:60], "| omitted" if p["omitted"] else "", "|", p["text"][:120])
