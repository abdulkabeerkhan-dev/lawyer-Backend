import unittest
import os
import sys
import asyncio
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestModelFallback(unittest.TestCase):

    def test_safe_create_anthropic_message_primary_success(self):
        import main
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value="success_primary")

        with patch.object(main, 'async_anthropic_client', mock_client):
            res = asyncio.run(main.safe_create_anthropic_message(model="claude-3-7-sonnet-20250219", messages=[]))
            self.assertEqual(res, "success_primary")
            mock_client.messages.create.assert_called_once_with(model="claude-3-7-sonnet-20250219", messages=[])

    def test_safe_create_anthropic_message_non_404_raises(self):
        import main
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=ValueError("Rate limit exceeded"))

        with patch.object(main, 'async_anthropic_client', mock_client):
            with self.assertRaises(ValueError):
                asyncio.run(main.safe_create_anthropic_message(model="claude-3-7-sonnet-20250219"))

    def test_safe_create_anthropic_message_404_no_fallback_raises_runtime_error(self):
        import main
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("404 model_not_found"))

        env_copy = dict(os.environ)
        env_copy.pop("ANTHROPIC_FALLBACK_MODEL", None)
        with patch.dict(os.environ, env_copy, clear=True), patch.object(main, 'async_anthropic_client', mock_client):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(main.safe_create_anthropic_message(model="claude-3-7-sonnet-20250219"))
            self.assertIn("Model 'claude-3-7-sonnet-20250219' is not accessible", str(ctx.exception))

    def test_safe_create_anthropic_message_404_with_fallback_success(self):
        import main
        mock_client = AsyncMock()
        def side_effect(**kwargs):
            if kwargs.get("model") == "claude-3-7-sonnet-20250219":
                raise Exception("404 model_not_found")
            return "success_fallback"
        mock_client.messages.create = AsyncMock(side_effect=side_effect)

        with patch.dict(os.environ, {"ANTHROPIC_FALLBACK_MODEL": "claude-3-5-sonnet-20241022"}), patch.object(main, 'async_anthropic_client', mock_client):
            res = asyncio.run(main.safe_create_anthropic_message(model="claude-3-7-sonnet-20250219"))
            self.assertEqual(res, "success_fallback")

if __name__ == '__main__':
    unittest.main()
