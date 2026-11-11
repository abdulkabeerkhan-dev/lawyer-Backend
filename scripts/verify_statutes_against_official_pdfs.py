"""
Verify statute provision text against the official PDFs in data/official_pdfs.

A record is tagged `official_pdf_match` only if its text (cleaned `verbatim_text`/`text`,
or else the raw extraction `text_raw`) appears contiguously in the official PDF's body
text after normalisation (case/whitespace/punctuation-insensitive; running headers,
page numbers and footnote bodies removed; footnote markers like "2[" ignored).

Usage: python verify_statutes.py [ACT_CODE ...] [--write]
Without --write it only reports.
"""
import hashlib, json, os, re, sys, collections, datetime
import pymupdf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(REPO, "data", "official_pdfs")
V2 = os.path.join(REPO, "data", "statutes_v2")
PDF_FOR = {
    "BCO_1962": "banking_companies_ordinance_1962.pdf",
    "CONTRACT_1872": "contract_act_1872.pdf",
    "CPC_1908": "cpc_1908.pdf",
    "CRPC_1898": "crpc_1898.pdf",
    "FIO_2001": "fio_2001.pdf",
    "LIMITATION_1908": "limitation_act_1908.pdf",
    "PPC_1860": "ppc_1860.pdf",
    "REGISTRATION_1908": "registration_act_1908.pdf",
    "STAMP_1899": "stamp_act_1899.pdf",
    "TPA_1882": "transfer_of_property_act_1882.pdf",
}

_FN_MARK = re.compile(r"\d+\s*\[")          # footnote markers like 2[  or 1 [
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)
_PAGE_FOOTER = re.compile(r"page\d+of\d*")
_DIGITS = re.compile(r"\d")
_MARKER = re.compile(r"^\s*\d{1,3}\s*\[?\s*$")   # superscript footnote markers like "6" or "2["


def norm(s: str) -> str:
    s = (s or "").replace("\u00ad", "").replace("­", "")
    s = _FN_MARK.sub("[", s)
    return _NON_ALNUM.sub("", s).lower()


def pdf_body(path):
    """Return (normalised body text, list of (offset, page_no)) dropping small-font footnotes/headers."""
    doc = pymupdf.open(path)
    sizes = collections.Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    sizes[round(s["size"])] += len(s["text"])
    body_size = sizes.most_common(1)[0][0]
    parts, offsets, pos = [], [], 0
    full_parts, mark_parts = [], []
    for pno, page in enumerate(doc, 1):
        h = page.rect.height
        page_txt, page_full, page_mark = [], [], []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                y0 = l["bbox"][1]
                all_txt = "".join(s["text"] for s in l["spans"])
                line = "".join(s["text"] for s in l["spans"] if s["size"] >= body_size - 1.5)
                # running header/footer zones: page numbers and short header lines
                if (y0 < 0.06 * h or y0 > 0.94 * h) and len(all_txt.strip()) < 60:
                    continue
                with_marks = "".join(s["text"] for s in l["spans"]
                                     if s["size"] >= body_size - 1.5 or _MARKER.match(s["text"]))
                if all_txt.strip():
                    page_full.append(all_txt)
                if line.strip():
                    page_txt.append(line)
                if with_marks.strip():
                    page_mark.append(with_marks)
        n = _PAGE_FOOTER.sub("", norm(" ".join(page_txt)))
        offsets.append((pos, pno))
        parts.append(n)
        pos += len(n)
        full_parts.append(_PAGE_FOOTER.sub("", norm(" ".join(page_full))))
        mark_parts.append(_PAGE_FOOTER.sub("", norm(" ".join(page_mark))))
    # "full" = body + footnote bodies; "marks" = body + inline footnote markers only
    return ("".join(parts), offsets, body_size, hashlib.sha256(open(path, "rb").read()).hexdigest(),
            "".join(full_parts), "".join(mark_parts))


def page_of(offsets, idx):
    p = 1
    for off, pno in offsets:
        if off > idx:
            break
        p = pno
    return p


def load_records(act):
    path = os.path.join(V2, f"{act}.json")
    data = json.load(open(path, encoding="utf-8"))
    recs = data if isinstance(data, list) else (data.get("records") or data.get("sections") or data.get("provisions") or [])
    return path, data, recs


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    acts = args or list(PDF_FOR)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    grand = collections.Counter()
    review_rows = []
    for act in acts:
        body, offsets, bsize, pdf_sha, full, marks = pdf_body(os.path.join(PDF_DIR, PDF_FOR[act]))
        body_nd = _DIGITS.sub("", body)
        path, data, recs = load_records(act)
        c = collections.Counter(); fails = []
        for r in recs:
            if not isinstance(r, dict) or not r.get("canonical_id"):
                continue
            c["records"] += 1
            cand = [("verbatim_text", r.get("verbatim_text") or r.get("text")), ("text_raw", r.get("text_raw"))]
            hit = None
            for field, txt in cand:
                n = norm(txt)
                if len(n) < 25:          # too short to verify meaningfully (e.g. heading-only)
                    continue
                i = body.find(n)
                if i >= 0:
                    hit = (field, i)
                    break
                j = marks.find(n)
                if j >= 0:
                    # same wording, only inline footnote markers differ; map to body page approx.
                    hit = (field, min(j, len(body) - 1))
                    break
            if hit:
                field, i = hit
                c[f"match_{field}"] += 1
                r["verification"] = {
                    "status": "official_pdf_match",
                    "matched_field": field,
                    "method": "normalised contiguous match against official PDF body text",
                    "source_pdf": PDF_FOR[act],
                    "source_pdf_sha256": pdf_sha,
                    "page": page_of(offsets, i),
                    "verified_at": now,
                }
            elif any(len(norm(t)) >= 25 and _DIGITS.sub("", norm(t)) in body_nd for _, t in cand):
                # Wording identical to the official PDF except numerals (footnote markers or
                # sub-section labels like "(4)"). Numbers can matter in law -> human check.
                c["near_match_numerals_only"] += 1
                review_rows.append((r["canonical_id"], "differs from official PDF only in numerals (footnote markers / sub-section labels)", PDF_FOR[act]))
                r["verification"] = {"status": "near_match_needs_review",
                                     "reason": "wording matches official PDF except numerals (footnote markers / sub-section labels)",
                                     "source_pdf": PDF_FOR[act], "source_pdf_sha256": pdf_sha, "checked_at": now}
            elif any(len(norm(t)) >= 25 and norm(t) in full for _, t in cand):
                # Wording matches the PDF only when footnote text is included: the stored
                # text has footnotes mixed into the provision. Faithful source, wrong quote.
                c["footnote_contaminated"] += 1
                review_rows.append((r["canonical_id"], "footnote text mixed into provision wording", PDF_FOR[act]))
                r["verification"] = {"status": "unverified", "reason": "stored text mixes footnote text into the provision wording",
                                     "source_pdf": PDF_FOR[act], "checked_at": now}
            else:
                c["no_match"] += 1
                fails.append(r["canonical_id"])
                review_rows.append((r["canonical_id"], "not found in official PDF", PDF_FOR[act]))
                r["verification"] = {"status": "unverified", "reason": "text not found contiguously in official PDF",
                                     "source_pdf": PDF_FOR[act], "checked_at": now}
        grand.update(c)
        print(f"{act}: {dict(c)}  (body font {bsize})  e.g. unmatched {fails[:6]}", flush=True)
        if write:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    print("TOTAL:", dict(grand))
    if write:
        import csv
        out = os.path.join(REPO, "data", "reviews", "statute_review_queue.csv")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["canonical_id", "problem", "official_pdf"])
            w.writerows(review_rows)
        print("review queue:", out, len(review_rows), "rows")


if __name__ == "__main__":
    main()
