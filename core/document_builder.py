from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io

def generate_court_docx(case_title, court_name, pleading_text):
    doc = Document()
    
    # Pakistani Court Standards: A4/Legal size, Wide left margin for binding/stamping
    sections = doc.sections
    for section in sections:
        section.left_margin = Inches(1.5)
        section.right_margin = Inches(1.0)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)

    # Court Name Header (Centered, Bold)
    court_p = doc.add_paragraph()
    court_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    court_run = court_p.add_run(f"IN THE {court_name.upper()}")
    court_run.bold = True
    court_run.font.size = Pt(14)
    court_run.font.name = 'Times New Roman'

    doc.add_paragraph() # Spacer

    # Cause Title
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run(case_title)
    title_run.bold = True
    title_run.font.size = Pt(12)
    title_run.font.name = 'Times New Roman'

    doc.add_paragraph() # Spacer

    # Body Text (Justified, 1.5 Spacing)
    # Note: In production, parse the Markdown to apply bolding/italics correctly.
    # For MVP, appending as structured paragraphs based on double-newlines.
    paragraphs = pleading_text.split('\n\n')
    for para in paragraphs:
        if not para.strip(): continue
        p = doc.add_paragraph(para.strip())
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.5
        for run in p.runs:
            run.font.size = Pt(12)
            run.font.name = 'Times New Roman'

    # Save to memory buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
