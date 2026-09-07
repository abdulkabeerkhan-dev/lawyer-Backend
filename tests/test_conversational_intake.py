import unittest
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import QueryRequest, ChatMessagePayload, clean_markdown_formatting

class TestConversationalIntakeEngine(unittest.TestCase):
    def test_query_request_schema_with_messages(self):
        payload = QueryRequest(
            query_text="I want to file a writ application in high court",
            messages=[
                ChatMessagePayload(role="user", content="Hello"),
                ChatMessagePayload(role="assistant", content="How can I assist you today?")
            ]
        )
        self.assertEqual(payload.query_text, "I want to file a writ application in high court")
        self.assertEqual(len(payload.messages), 2)
        self.assertEqual(payload.messages[0].role, "user")

    def test_clean_markdown_formatting_strips_leakage(self):
        leaked_text = (
            "I appreciate the correction. However, reviewing my draft output, I did not recommend Balochistan.\n"
            "### I. EXECUTIVE SUMMARY & LEGAL OPINION\n"
            "This is the clean Senior Advocate opinion text."
        )
        cleaned = clean_markdown_formatting(leaked_text)
        self.assertNotIn("I appreciate the correction", cleaned)
        self.assertTrue(cleaned.startswith("### I. EXECUTIVE SUMMARY & LEGAL OPINION"))

if __name__ == '__main__':
    unittest.main()
