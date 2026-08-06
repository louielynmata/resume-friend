import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main_module


class MainAppTests(unittest.TestCase):
    def test_production_app_serves_built_frontend_without_shadowing_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            frontend_dist = Path(tmp)
            (frontend_dist / "index.html").write_text(
                "<!doctype html><title>Container UI</title>",
                encoding="utf-8",
            )

            create_app = getattr(main_module, "create_app", None)
            self.assertIsNotNone(
                create_app,
                "backend.main.create_app is required to configure the built frontend",
            )
            if create_app is None:
                return

            client = TestClient(create_app(frontend_dist=frontend_dist))

            frontend_response = client.get("/")
            health_response = client.get("/api/health")

            self.assertEqual(frontend_response.status_code, 200)
            self.assertIn("Container UI", frontend_response.text)
            self.assertEqual(health_response.status_code, 200)
            self.assertEqual(health_response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
