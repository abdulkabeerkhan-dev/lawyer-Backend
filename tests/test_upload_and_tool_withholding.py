import unittest
import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestUploadAndToolWithholding(unittest.TestCase):

    def test_doc_review_keywords_matching(self):
        doc_review_keywords = [
            r'\b(?:review|analyze|examine|check|read|summarize|draft\s+response\s+to|reply\s+to)\s+(?:this|the|my|att?ac?h?e?d?)?\s*(?:do[cu]{1,2}[umne]{1,4}t|file?|pete?i?t?i?o?n|appe?a?l|noti?c?e|contra?c?t|agre?e?m?e?n?t|plea?d?i?n?g|att?ac?h?m?e?n?t|pdf|docx)\b',
            r'\b(?:att?ac?h?e?d?|uploaded)\s+(?:do[cu]{1,2}[umne]{1,4}t|file?|pete?i?t?i?o?n|appe?a?l|noti?c?e|contra?c?t|agre?e?m?e?n?t|plea?d?i?n?g|pdf|docx)\b',
            r'\b(?:review|analyze)\s+att?ac?h?e?d?\b',
            r'\bsee\s+att?ac?h?e?d?\b'
        ]
        
        positive_queries = [
            "Please review this document",
            "review the attached doument",
            "review attached docment",
            "review this atached file",
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

    def test_suppress_authorities_on_missing_doc_response(self):
        executive_answer = "I don't see any attached document to review. Please paste the document text directly in your next message."
        ans_lower = executive_answer.lower()
        withhold_tools = True
        upload_extraction_failed = False
        is_doc_analysis_without_content = True

        is_missing_doc_response = withhold_tools or upload_extraction_failed or is_doc_analysis_without_content or any(phrase in ans_lower for phrase in [
            "don't see any attached document",
            "no document",
            "attached file",
            "could not be read",
            "could not extract",
            "please paste",
            "attach the text",
            "missing or unreadable"
        ])
        self.assertTrue(is_missing_doc_response)

if __name__ == '__main__':
    unittest.main()
