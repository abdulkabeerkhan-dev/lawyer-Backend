import os
import sys
import re
import csv
import glob
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

csv.field_size_limit(100 * 1024 * 1024)

INPUT_DIR = r"D:\missing_gaps_verified\cleaned_CSVs"
BASE_OUTPUT_DIR = r"D:\missing_gaps_verified\PDFs"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#4A5568"))
        
        # Header on page 2+
        if self._pageNumber > 1:
            self.drawString(54, 11 * 72 - 36, "PAKISTAN LAW SITE - OFFICIAL CASE REPORT")
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.5)
            self.line(54, 11 * 72 - 42, 8.5 * 72 - 54, 11 * 72 - 42)

        # Footer on all pages
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * 72 - 54, 34, page_text)
        self.drawString(54, 34, "Official & Verified Legal Record - Pakistan Legal Corpus")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(54, 46, 8.5 * 72 - 54, 46)
        self.restoreState()

def deep_clean_text(text: str) -> str:
    if not text:
        return ""
    
    # 1. Unicode replacement character, soft hyphens & zero-width artifacts
    text = str(text).replace('\ufffd', ' ').replace('\xad', '')
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    
    # 2. Spaces normalization
    text = re.sub(r'[\u00a0\u2002\u2003\u2009\u202f]', ' ', text)
    
    # 3. Unicode dashes and hyphens -> ASCII hyphens / dashes (fixes black box glyphs in PDFs)
    text = re.sub(r'[\u2010\u2011\u2012\u2212]', '-', text)
    text = re.sub(r'[\u2013\u2014\u2015]', '--', text)
    
    # 4. Unicode quotes -> ASCII quotes (fixes black box glyphs in PDFs)
    text = re.sub(r'[\u2018\u2019\u201a\u201b\u2032\u0060\u00b4]', "'", text)
    text = re.sub(r'[\u201c\u201d\u201e\u201f\u2033]', '"', text)
    
    # 5. Arabic / Urdu script blocks (render as black blocks in Type 1 fonts)
    text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+', ' ', text)
    
    # 6. Possessives and contractions with ? (e.g. petitioner?s -> petitioner's, don?t -> don't)
    text = re.sub(r'\b([A-Za-z]+)\?(s|t|ll|ve|re|d|m)\b', r"\1'\2", text)
    
    # 7. Common broken OCR syllable wraps (govern?ment -> government)
    common_syllable_joins = {
        'government', 'circumstances', 'therefore', 'section', 'possession',
        'consideration', 'constitution', 'application', 'proceedings', 'property',
        'fundamental', 'respondent', 'jurisdiction', 'commissioner', 'provisions',
        'amendment', 'dissolution', 'consequently', 'appellant', 'prosecution',
        'according', 'assessment', 'contention', 'defendants'
    }
    
    def fix_word(m):
        w = m.group(0)
        pure = w.replace('?', '')
        if pure.lower() in common_syllable_joins:
            return pure
        return w.replace('?', '-')
    
    text = re.sub(r'\b[A-Za-z]{2,}\?[A-Za-z]{2,}\b', fix_word, text)
    
    # 8. Consecutive question mark runs (OCR margin leader dots or corruption)
    # If at end of line before outcome: S. G. D. ??? Revision dismissed
    text = re.sub(r'([A-Za-z\.\/\-0-9]+)\s*\?{2,}\s*([A-Za-z]+)', r'\1 -- \2', text)
    # General runs of 2+ question marks
    text = re.sub(r'\?{2,}', ' ', text)
    
    # Clean redundant spaces per line
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in text.split('\n')]
    return '\n'.join(lines).strip()

def sanitize_for_xml(text):
    if not text:
        return ""
    text = deep_clean_text(text)
    # Strip any remaining control characters / null bytes
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    # Break any abnormally long unbroken token (> 70 chars) to prevent ReportLab wrap crashes
    def break_tokens(match):
        tok = match.group(0)
        return " ".join([tok[i:i+60] for i in range(0, len(tok), 60)])
    text = re.sub(r'\S{70,}', break_tokens, text)
    return text

def sanitize_filename(name):
    name = str(name).strip()
    name = re.sub(r'[\\/*?:"<>|\r\n\t]', '_', name)
    name = re.sub(r'[\s\.\(\)\-]+', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name[:60]

def build_pdf_worker(row: dict) -> bool:
    try:
        journal = str(row.get("journal", "LAW")).strip().upper()
        year = str(row.get("year", "2026")).strip()
        case_idx = str(row.get("case_index", "0")).strip()
        citation = str(row.get("citation", f"{year} {journal} {case_idx}")).strip()
        title = str(row.get("title", "Untitled Case")).strip()
        court = str(row.get("court", "")).strip()
        bench = str(row.get("bench", "")).strip()
        docket = str(row.get("docket_number", "")).strip()
        if len(docket) > 120:
            docket = docket[:117] + "..."
        date = str(row.get("decision_date", "")).strip()

        headnotes = str(row.get("headnotes", "")).strip()
        judgment_body = str(row.get("judgment_body", "")).strip()
        is_complete = str(row.get("is_complete", "True")).strip() == "True"

        # Directory: BASE_OUTPUT_DIR \ [journal] \ [year]
        year_dir = os.path.join(BASE_OUTPUT_DIR, journal, year)
        os.makedirs(year_dir, exist_ok=True)

        cit_slug = sanitize_filename(citation)
        court_short = sanitize_filename(court.split()[0]) if court else ""
        if court_short and court_short.lower() not in cit_slug.lower():
            pdf_name = f"{cit_slug}_{court_short}_{case_idx}.pdf"
        else:
            pdf_name = f"{cit_slug}_Case_{case_idx}.pdf"

        pdf_path = os.path.join(year_dir, pdf_name)


        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#0F2942"),
            spaceAfter=4
        )

        parties_style = ParagraphStyle(
            'PartiesStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#2C5282"),
            spaceAfter=10
        )

        meta_cell_style = ParagraphStyle(
            'MetaCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#2D3748")
        )

        section_heading = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#1A365D"),
            spaceBefore=12,
            spaceAfter=6
        )

        headnote_style = ParagraphStyle(
            'HeadnoteBody',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor("#2D3748"),
            spaceAfter=6
        )

        body_style = ParagraphStyle(
            'JudgmentBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#1A202C"),
            spaceAfter=6
        )

        story = []

        # Title & Parties
        story.append(Paragraph(sanitize_for_xml(citation), title_style))
        story.append(Paragraph(sanitize_for_xml(title), parties_style))

        # Structured Metadata Table
        meta_data = []
        r1 = [
            Paragraph(f"<b>Journal:</b> {sanitize_for_xml(journal)}", meta_cell_style),
            Paragraph(f"<b>Year:</b> {sanitize_for_xml(year)}", meta_cell_style),
            Paragraph(f"<b>Case Index:</b> #{sanitize_for_xml(case_idx)}", meta_cell_style)
        ]
        meta_data.append(r1)

        if court or bench:
            r2 = [
                Paragraph(f"<b>Court:</b> {sanitize_for_xml(court or 'N/A')}", meta_cell_style),
                Paragraph(f"<b>Bench:</b> {sanitize_for_xml(bench or 'N/A')}", meta_cell_style),
                Paragraph(f"<b>Date:</b> {sanitize_for_xml(date or 'N/A')}", meta_cell_style)
            ]
            meta_data.append(r2)

        if docket or not is_complete:
            r3 = [
                Paragraph(f"<b>Docket No:</b> {sanitize_for_xml(docket or 'N/A')}", meta_cell_style),
                Paragraph(f"<b>Status:</b> {'Complete Judgment' if is_complete else 'Indexed Summary'}", meta_cell_style),
                Paragraph("", meta_cell_style)
            ]
            meta_data.append(r3)

        meta_table = Table(meta_data, colWidths=[170, 200, 134])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E0")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # Headnotes Section
        if headnotes:
            story.append(Paragraph("HEADNOTES &amp; LEGAL SYLLABUS", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2B6CB0"), spaceBefore=2, spaceAfter=8))
            paras = [p.strip() for p in headnotes.split('\n\n') if p.strip()]
            for p in paras:
                lines = [sanitize_for_xml(l) for l in p.split('\n') if l.strip()]
                story.append(Paragraph("<br/>".join(lines), headnote_style))

        # Judgment Body Section
        if judgment_body and judgment_body != headnotes:
            story.append(Paragraph("JUDGMENT / ORDER", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A365D"), spaceBefore=2, spaceAfter=8))
            paras = [p.strip() for p in judgment_body.split('\n\n') if p.strip()]
            for p in paras:
                lines = [sanitize_for_xml(l) for l in p.split('\n') if l.strip()]
                story.append(Paragraph("<br/>".join(lines), body_style))

        doc.build(story, canvasmaker=NumberedCanvas)
        return True
    except Exception as e:
        return False

def process_cleaned_csv(csv_path: str, max_workers: int = 8):
    filename = os.path.basename(csv_path)
    print(f"\n>>> Starting PDF generation for: {filename}")
    
    rows = []
    with open(csv_path, 'r', encoding='utf-8-sig', errors='replace') as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            rows.append(r)

    total = len(rows)
    print(f"    Loaded {total:,} records from {filename}")
    
    start_time = time.time()
    completed = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(build_pdf_worker, r): r for r in rows}
        for future in as_completed(futures):
            res = future.result()
            if res:
                completed += 1
            else:
                errors += 1
            if (completed + errors) % 500 == 0 or (completed + errors) == total:
                elapsed = time.time() - start_time
                rate = (completed + errors) / (elapsed + 0.001)
                print(f"    Progress: {completed + errors:,}/{total:,} PDFs generated ({rate:.1f} PDFs/sec)...")

    elapsed = time.time() - start_time
    print(f"    Completed {filename}: {completed:,} generated, {errors} errors in {elapsed:.1f}s.")
    return completed

def main():
    print("=" * 80)
    print("PAKISTAN LEGAL MASTER CORPUS - PRODUCTION BATCH PDF GENERATOR")
    print(f"Input Directory:  {INPUT_DIR}")
    print(f"Output Directory: {BASE_OUTPUT_DIR}")
    print("=" * 80)

    csv_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*_cleaned.csv")))
    print(f"Found {len(csv_files)} cleaned datasets to convert.")

    max_workers = min(8, os.cpu_count() or 4)
    print(f"Parallel Worker Threads: {max_workers}")

    grand_total = 0
    t0 = time.time()
    for f in csv_files:
        count = process_cleaned_csv(f, max_workers=max_workers)
        grand_total += count

    total_time = time.time() - t0
    print("\n" + "=" * 80)
    print(f"ALL DATASETS PROCESSED!")
    print(f"Total PDFs Generated: {grand_total:,}")
    print(f"Total Time Taken:     {total_time:.1f}s ({total_time/60:.2f} mins)")
    print(f"Average Speed:        {grand_total/(total_time+0.001):.1f} PDFs/sec")
    print(f"Saved in:             {BASE_OUTPUT_DIR}")
    print("=" * 80)

if __name__ == "__main__":
    main()
