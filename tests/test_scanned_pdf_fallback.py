import unittest
import os
import sys
import io
import base64
import pypdf
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestScannedPdfFallback(unittest.TestCase):

    def test_scanned_pdf_image_extraction(self):
        # Create a synthetic PDF in memory containing an embedded image page
        img = Image.new('RGB', (200, 200), color = 'red')
        img_buf = io.BytesIO()
        img.save(img_buf, format='JPEG')
        img_bytes = img_buf.getvalue()

        # Build simple PDF with pypdf containing an image
        writer = pypdf.PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        # Add image to page resources
        page.images.append((img_bytes, "test.jpg"))

        pdf_buf = io.BytesIO()
        writer.write(pdf_buf)
        pdf_bytes = pdf_buf.getvalue()
        b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

        import main
        # Verify text extraction returns empty (no font text streams)
        doc_t = main.extract_text_from_document_base64(b64_pdf, "application/pdf")
        self.assertEqual(doc_t, "")

if __name__ == '__main__':
    unittest.main()
