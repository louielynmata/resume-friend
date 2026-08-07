import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_editor_service(test_case: unittest.TestCase):
    module_name = "backend.services.editor_service"
    test_case.assertIsNotNone(
        importlib.util.find_spec(module_name),
        "The allowlisted editor service has not been implemented.",
    )
    return importlib.import_module(module_name)


class EditorServiceTests(unittest.TestCase):
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
            "# Example résumé\n", encoding="utf-8"
        )
        self.prompts_dir.joinpath("system_prompt.md").write_text(
            "# Public prompt\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def service(self, *, max_content_bytes: int = 1024):
        module = _load_editor_service(self)
        return module.EditorService(
            personal_dir=self.personal_dir,
            example_dir=self.example_dir,
            prompts_dir=self.prompts_dir,
            max_content_bytes=max_content_bytes,
        )

    def test_registry_exposes_only_the_supported_group_file_pairs(self):
        module = _load_editor_service(self)
        service = self.service()

        groups = service.list_files()

        self.assertEqual(
            [item.file_id for item in groups["personal"]],
            [
                "design_resume",
                "dev_resume",
                "instructions_prompt",
                "school_transcript",
                "writing_examples",
            ],
        )
        self.assertEqual(
            [item.file_id for item in groups["prompts"]],
            ["system_prompt", "qa_prompt", "visual_qa_prompt"],
        )
        with self.assertRaises(module.UnknownEditorFileError):
            service.read_file("personal", "system_prompt")
        with self.assertRaises(module.UnknownEditorFileError):
            service.read_file("personal", "../prompts/system_prompt")

    def test_missing_personal_file_loads_example_but_saves_to_personal(self):
        service = self.service()
        example_before = self.example_dir.joinpath("design_resume.md").read_bytes()

        loaded = service.read_file("personal", "design_resume")
        saved = service.save_file(
            "personal",
            "design_resume",
            "# José's résumé\n",
            loaded.revision,
        )

        self.assertEqual(loaded.source, "example")
        self.assertEqual(loaded.content, "# Example résumé\n")
        self.assertEqual(saved.source, "personal")
        self.assertEqual(saved.content, "# José's résumé\n")
        self.assertEqual(
            self.personal_dir.joinpath("design_resume.md").read_text(encoding="utf-8"),
            "# José's résumé\n",
        )
        self.assertEqual(
            self.example_dir.joinpath("design_resume.md").read_bytes(), example_before
        )

    def test_save_rejects_a_stale_revision_without_overwriting_external_changes(self):
        target = self.prompts_dir / "system_prompt.md"
        service = self.service()
        loaded = service.read_file("prompts", "system_prompt")
        target.write_text("# Changed elsewhere\n", encoding="utf-8")
        module = _load_editor_service(self)

        with self.assertRaises(module.RevisionConflictError):
            service.save_file(
                "prompts", "system_prompt", "# Browser edit\n", loaded.revision
            )

        self.assertEqual(target.read_text(encoding="utf-8"), "# Changed elsewhere\n")

    def test_save_rejects_oversized_or_non_utf8_content(self):
        service = self.service(max_content_bytes=8)
        loaded = service.read_file("prompts", "system_prompt")
        module = _load_editor_service(self)

        with self.assertRaises(module.InvalidEditorContentError):
            service.save_file("prompts", "system_prompt", "123456789", loaded.revision)
        with self.assertRaises(module.InvalidEditorContentError):
            service.save_file("prompts", "system_prompt", "bad \ud800", loaded.revision)

    def test_failed_atomic_replace_preserves_the_original_file(self):
        target = self.prompts_dir / "system_prompt.md"
        service = self.service()
        loaded = service.read_file("prompts", "system_prompt")
        module = _load_editor_service(self)

        with mock.patch.object(module.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(module.EditorFileSystemError):
                service.save_file(
                    "prompts", "system_prompt", "# Replacement\n", loaded.revision
                )

        self.assertEqual(target.read_text(encoding="utf-8"), "# Public prompt\n")
        self.assertEqual(list(self.prompts_dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
