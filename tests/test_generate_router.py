import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from fastapi import HTTPException

from backend.config import settings
from backend.routers.generate import (
    _create_run_output_dir,
    _current_generation_id,
    _generation_progress,
    _http_error,
    _record_generation_progress,
    _run_generation,
    get_generation_status,
    generate,
)
from backend.schemas import GenerateRequest
from backend.services.qa_pipeline import QAPipelineValidationError
from backend.services.work_sample_links import required_work_sample_links


def write_generation_files(root: Path, instructions: str) -> None:
    (root / "design_resume.md").write_text("Design resume facts", encoding="utf-8")
    (root / "dev_resume.md").write_text("Development resume facts", encoding="utf-8")
    (root / "instructions_prompt.md").write_text(instructions, encoding="utf-8")
    (root / "writing_examples.md").write_text("Writing sample", encoding="utf-8")
    (root / "school_transcript.md").write_text("Transcript facts", encoding="utf-8")


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


class GenerateWorkSamplePreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_design_portfolio_fails_before_provider_call(self):
        request = GenerateRequest(
            job_description="A real design job description",
            ai_provider="ollama",
            job_type="design",
            position="Product Designer",
            company="Example Co",
        )
        instructions = (
            "WORK_SAMPLES: [Case Studies and Product Work]"
            "(https://figma.example/case-studies)"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_generation_files(root, instructions)
            with mock.patch.object(
                settings, "model_files_dir", str(root)
            ), mock.patch(
                "backend.routers.generate._call_generation_provider",
                new=AsyncMock(),
            ) as provider:
                with self.assertRaises(HTTPException) as raised:
                    await _run_generation(request, 0.0)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(
            raised.exception.detail["code"],
            "SOURCE_REQUIRED_WORK_SAMPLE_LINK_MISSING",
        )
        self.assertEqual(raised.exception.detail["stage"], "load_model_files")
        provider.assert_not_awaited()

    async def test_work_sample_validation_failure_never_logs_to_notion(self):
        request = GenerateRequest(
            job_description="A real software job description",
            ai_provider="ollama",
            job_type="development",
            position="Software Engineer",
            company="Example Co",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "qa_report.json"
            report_path.write_text("{}", encoding="utf-8")
            model_files = mock.Mock(
                resume="Resume facts",
                instructions="Instructions",
                writing_examples="Writing sample",
                transcript="Transcript",
                system_prompt="System prompt",
                required_work_sample_links={
                    "Case Studies and Product Work":
                    "https://figma.example/case-studies"
                },
            )
            validation_error = QAPipelineValidationError(
                "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
                report_path,
                "artifact_validation",
            )
            with mock.patch(
                "backend.routers.generate._load_generation_model_files",
                return_value=model_files,
            ), mock.patch(
                "backend.routers.generate._call_generation_provider",
                new=AsyncMock(
                    return_value=(
                        "<RESUME>x</RESUME>"
                        "<COVER_LETTER>y</COVER_LETTER>"
                    )
                ),
            ), mock.patch(
                "backend.routers.generate._prepare_run_output",
                return_value=mock.Mock(
                    position_slug="SoftwareEngineer",
                    folder_name="run",
                    output_dir=root,
                ),
            ), mock.patch(
                "backend.routers.generate.run_qa_pipeline",
                new=AsyncMock(side_effect=validation_error),
            ) as pipeline, mock.patch(
                "backend.routers.generate.log_application",
                new=AsyncMock(),
            ) as notion:
                with self.assertRaises(HTTPException) as raised:
                    await _run_generation(request, 0.0)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(
            raised.exception.detail["code"],
            "QA_VALIDATION_FAILED",
        )
        self.assertEqual(
            raised.exception.detail["stage"],
            "artifact_validation",
        )
        self.assertEqual(
            pipeline.await_args.kwargs["required_work_sample_links"],
            {
                "Case Studies and Product Work":
                "https://figma.example/case-studies"
            },
        )
        notion.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
