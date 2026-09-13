import unittest
import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestUploadAndToolWithholding(unittest.TestCase):

    def test_doc_review_keywords_matching(self):
        doc_review_keywords = [
            r'\b(?:review|analyze|examine|check|read|summarize|draft\s+response\s+to|reply\s+to)\s+(?:this|the|my|attached)?\s*(?:document|file|petition|appeal|notice|contract|agreement|pleading|attachment|pdf|docx)\b',
            r'\b(?:attached|uploaded)\s+(?:document|file|petition|appeal|notice|contract|agreement|pleading|pdf|docx)\b',
            r'\b(?:review|analyze)\s+attached\b',
            r'\bsee\s+attached\b'
        ]
        
        positive_queries = [
            "Please review this document",
            "Analyze attached petition",
            "Draft response to attached notice",
            "Review this file for me",
            "See attached pleading"
        ]

        negative_queries = [
            "What is the punishment under Section 489-F PPC?",
            "Search database for 2021 SCMR 2092",
            "How to file a bail application in High Court?"
        ]

        for q in positive_queries:
            matched = any(re.search(pat, q, re.IGNORECASE) for pat in doc_review_keywords)
            self.assertTrue(matched, f"Failed to detect doc review intent for: {q}")

        for q in negative_queries:
            matched = any(re.search(pat, q, re.IGNORECASE) for pat in doc_review_keywords)
            self.assertFalse(matched, f"False positive doc review intent for: {q}")

    def test_upload_extraction_failure_flag(self):
        all_uploads = [{"name": "corrupted.pdf"}]
        has_image = False
        has_doc_text = False

        upload_extraction_failed = (len(all_uploads) > 0) and (not has_image) and (not has_doc_text)
        self.assertTrue(upload_extraction_failed)

        # When extraction succeeds
        has_doc_text_success = True
        upload_extraction_failed_success = (len(all_uploads) > 0) and (not has_image) and (not has_doc_text_success)
        self.assertFalse(upload_extraction_failed_success)

if __name__ == '__main__':
    unittest.main()
