import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_module(test_case: unittest.TestCase, module_name: str):
    test_case.assertIsNotNone(
        importlib.util.find_spec(module_name), f"{module_name} has not been implemented."
    )
    return importlib.import_module(module_name)


class EditorRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.personal_dir = root / "models_personal"
        self.example_dir = root / "models_personal_example"
        self.prompts_dir = root / "prompts"
        self.personal_dir.mkdir()
        self.example_dir.mkdir()
        self.prompts_dir.mkdir()
        self.example_dir.joinpath("design_resume.md").write_text(
            "# Example\n", encoding="utf-8"
        )
        self.prompts_dir.joinpath("system_prompt.md").write_text(
            "# Prompt\n", encoding="utf-8"
        )

        service_module = _load_module(self, "backend.services.editor_service")
        router_module = _load_module(self, "backend.routers.editor")
        self.service = service_module.EditorService(
            personal_dir=self.personal_dir,
            example_dir=self.example_dir,
            prompts_dir=self.prompts_dir,
        )
        app = FastAPI()
        app.include_router(router_module.router)
        app.dependency_overrides[router_module.get_editor_service] = lambda: self.service
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_and_read_responses_keep_groups_and_sources_explicit(self):
        listed = self.client.get("/api/editor/files")
        loaded = self.client.get("/api/editor/files/personal/design_resume")

        self.assertEqual(listed.status_code, 200)
        groups = listed.json()["groups"]
        self.assertEqual(len(groups["personal"]), 5)
        self.assertEqual(len(groups["prompts"]), 3)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(
            loaded.json(),
            {
                "group": "personal",
                "file_id": "design_resume",
                "filename": "design_resume.md",
                "display_name": "Design résumé",
                "exists": False,
                "source": "example",
                "writable": True,
                "content": "# Example\n",
                "revision": loaded.json()["revision"],
            },
        )

    def test_save_returns_new_revision_and_updated_personal_status(self):
        loaded = self.client.get("/api/editor/files/personal/design_resume").json()

        response = self.client.put(
            "/api/editor/files/personal/design_resume",
            json={"content": "# My résumé\n", "revision": loaded["revision"]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "personal")
        self.assertEqual(body["content"], "# My résumé\n")
        self.assertNotEqual(body["revision"], loaded["revision"])
        self.assertTrue(body["personal_file_status"]["design_resume"])

    def test_invalid_id_content_and_stale_revision_have_stable_http_errors(self):
        missing = self.client.get("/api/editor/files/personal/system_prompt")
        loaded = self.client.get("/api/editor/files/prompts/system_prompt").json()
        stale = self.client.put(
            "/api/editor/files/prompts/system_prompt",
            json={"content": "# Edit\n", "revision": "stale-revision"},
        )
        invalid = self.client.put(
            "/api/editor/files/prompts/system_prompt",
            json={"content": "bad\u0000content", "revision": loaded["revision"]},
        )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "EDITOR_FILE_NOT_FOUND")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"]["code"], "EDITOR_REVISION_CONFLICT")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["detail"]["code"], "EDITOR_INVALID_CONTENT")


if __name__ == "__main__":
    unittest.main()
