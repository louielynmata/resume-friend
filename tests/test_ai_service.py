import unittest
from unittest.mock import patch

from backend.qa_models import VisualQAResult
from backend.services.ai_service import _call_ollama_structured


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": "```json\n{\"passed\": true, \"issues\": [], \"summary\": \"ok\"}\n```"
            }
        }


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.payload = json
        return FakeResponse()


class AIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ollama_structured_uses_schema_and_accepts_fenced_json(self):
        fake_client = FakeAsyncClient()
        with patch(
            "backend.services.ai_service.httpx.AsyncClient",
            return_value=fake_client,
        ):
            result = await _call_ollama_structured(
                "Return JSON",
                "Run a smoke test",
                VisualQAResult,
                [],
            )

        self.assertTrue(result.passed)
        self.assertNotIn("think", fake_client.payload)
        self.assertEqual(
            fake_client.payload["format"],
            VisualQAResult.model_json_schema(),
        )


if __name__ == "__main__":
    unittest.main()
