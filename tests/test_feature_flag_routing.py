import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

# Add project root
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(root_dir, ".env"))

import main
from main import process_query_job, QueryRequest


class TestFeatureFlagRouting(unittest.IsolatedAsyncioTestCase):

    async def test_feature_flag_true_routes_to_legal_ai(self):
        with patch.dict(os.environ, {"USE_LEGAL_AI_PIPELINE": "true"}), \
             patch("legal_ai.query_engine.query_processor.process_query_job_legal_ai", new_callable=AsyncMock) as mock_modern, \
             patch("main._legacy_process_query_job", new_callable=AsyncMock) as mock_legacy:
            
            req = QueryRequest(query_text="Section 420 PPC test", category="criminal")
            await process_query_job("test-job-modern", req, "test-user")
            
            mock_modern.assert_awaited_once()
            mock_legacy.assert_not_awaited()

    async def test_feature_flag_false_routes_to_legacy(self):
        with patch.dict(os.environ, {"USE_LEGAL_AI_PIPELINE": "false"}), \
             patch("legal_ai.query_engine.query_processor.process_query_job_legal_ai", new_callable=AsyncMock) as mock_modern, \
             patch("main._legacy_process_query_job", new_callable=AsyncMock) as mock_legacy:
            
            req = QueryRequest(query_text="Section 420 PPC test", category="criminal")
            await process_query_job("test-job-legacy", req, "test-user")
            
            mock_legacy.assert_awaited_once()
            mock_modern.assert_not_awaited()

    async def test_fallback_to_legacy_on_early_error(self):
        with patch.dict(os.environ, {"USE_LEGAL_AI_PIPELINE": "true"}), \
             patch("legal_ai.query_engine.query_processor.process_query_job_legal_ai", side_effect=RuntimeError("Simulated retrieval failure")), \
             patch("main._legacy_process_query_job", new_callable=AsyncMock) as mock_legacy:
            
            main.jobs_store["test-job-fallback"] = {"stage": "searching_precedents", "status": "processing"}
            req = QueryRequest(query_text="Section 420 PPC test", category="criminal")
            await process_query_job("test-job-fallback", req, "test-user")
            
            mock_legacy.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
