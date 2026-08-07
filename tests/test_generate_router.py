import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.config import settings
from backend.routers.generate import (
    _create_run_output_dir,
    _current_generation_id,
    _generation_progress,
    _http_error,
    _record_generation_progress,
    get_generation_status,
    generate,
)
from backend.schemas import GenerateRequest


class GenerateRouterTests(unittest.TestCase):
    def test_generation_status_reports_real_stage_and_failure(self):
        generation_id = "progress-test"
        token = _current_generation_id.set(generation_id)
        try:
            _record_generation_progress("call_ai_provider")
            running = get_generation_status(generation_id)

            self.assertEqual(running.stage, "call_ai_provider")
            self.assertEqual(running.status, "running")

            _http_error(
                422,
                stage="qa_review",
                code="QA_VALIDATION_FAILED",
                message="QA failed.",
                detail="A blocking issue remains.",
            )
            failed = get_generation_status(generation_id)

            self.assertEqual(failed.stage, "qa_review")
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.detail, "A blocking issue remains.")
        finally:
            _current_generation_id.reset(token)
            _generation_progress.pop(generation_id, None)

    def test_same_day_runs_use_distinct_output_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ExampleCompany_ProductDesigner_2026-07-21"

            first = _create_run_output_dir(base)
            (first / "qa_report.json").write_text("{}", encoding="utf-8")
            second = _create_run_output_dir(base)
            third = _create_run_output_dir(base)

            self.assertEqual(first, base)
            self.assertEqual(second.name, f"{base.name}_2")
            self.assertEqual(third.name, f"{base.name}_3")
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertTrue(third.is_dir())

    def test_existing_empty_folder_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ExampleCompany_ProductDesigner_2026-07-21"
            base.mkdir()

            resolved = _create_run_output_dir(base)

            self.assertEqual(resolved.name, f"{base.name}_2")

    def test_generation_normalizes_location_before_downstream_side_effects(self):
        captured_location = None

        async def capture_request(req, _started_at):
            nonlocal captured_location
            captured_location = req.location
            return object()

        request = GenerateRequest(
            job_description="A real job description",
            ai_provider="ollama",
            job_type="development",
            position="Developer",
            company="Example Co",
            location="Calgary, AB (Hybrid)",
        )
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            settings, "model_files_dir", tmp
        ), mock.patch(
            "backend.routers.generate._run_generation", side_effect=capture_request
        ):
            asyncio.run(generate(request))

        self.assertEqual(captured_location, "Calgary")


if __name__ == "__main__":
    unittest.main()
