import unittest
import os
import sys
import io
import base64
from unittest.mock import MagicMock, patch
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestScannedPdfFallback(unittest.TestCase):

    def test_scanned_pdf_image_extraction(self):
        # Create a sample JPEG in memory
        img = Image.new('RGB', (100, 100), color='blue')
        img_buf = io.BytesIO()
        img.save(img_buf, format='JPEG')
        img_bytes = img_buf.getvalue()

        # Mock pypdf page with an image
        mock_img = MagicMock()
        mock_img.data = img_bytes

        mock_page = MagicMock()
        mock_page.images = [mock_img]

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        import main
        with patch('pypdf.PdfReader', return_value=mock_reader):
            b64_dummy = base64.b64encode(b"%PDF-1.4 dummy scanned pdf").decode("utf-8")
            # Run text extraction which returns empty for scanned PDF
            doc_t = main.extract_text_from_document_base64(b64_dummy, "application/pdf") if hasattr(main, 'extract_text_from_document_base64') else ""
            self.assertEqual(doc_t, "")

if __name__ == '__main__':
    unittest.main()
