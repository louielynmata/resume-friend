import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.config import settings
from backend.qa_models import (
    ArtifactQAResult,
    QAAgentResult,
    QAIssue,
    QASeverity,
)
from backend.services.qa_pipeline import QAPipelineValidationError, run_qa_pipeline

from tests.test_qa_service import SOURCE_RESUME, valid_draft


class QAPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_values = {
            "qa_enabled": settings.qa_enabled,
            "qa_provider": settings.qa_provider,
            "qa_max_repairs": settings.qa_max_repairs,
            "qa_visual_enabled": settings.qa_visual_enabled,
            "qa_fail_open": settings.qa_fail_open,
        }
        settings.qa_enabled = True
        settings.qa_provider = "same"
        settings.qa_max_repairs = 1
        settings.qa_visual_enabled = False
        settings.qa_fail_open = False

    async def asyncTearDown(self):
        for key, value in self.original_values.items():
            setattr(settings, key, value)

    async def test_pipeline_reviews_builds_and_writes_report(self):
        corrected = valid_draft()
        reviewer_result = QAAgentResult(
            resume=corrected.resume,
            cover_letter=corrected.cover_letter,
            analysis=corrected.analysis,
            issues_found=["Grammar reviewed"],
            changes_made=["Corrected one sentence"],
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ):
            result = await run_qa_pipeline(
                selected_provider="ollama",
                draft=corrected,
                owner_name="Alex Example",
                source_resume=SOURCE_RESUME,
                instructions="Keep all facts truthful.",
                writing_examples="I write concise letters.",
                transcript="Education facts.",
                job_description="Product designer role.",
                company_context="",
                position="Product Designer",
                company="Example Company",
                position_slug="ProductDesigner",
                output_dir=Path(tmp),
            )

            self.assertEqual(result.report.status, "passed")
            self.assertEqual(result.report.iterations, 1)
            self.assertTrue(result.report_path.exists())
            self.assertIn("Corrected one sentence", result.report.changes_made)

    async def test_fail_open_returns_needs_review_and_keeps_notion_gate_available(self):
        invalid = valid_draft()
        invalid.resume = invalid.resume.replace(
            "Product designer focused",
            "I am a product designer focused",
        )
        reviewer_result = QAAgentResult(
            resume=invalid.resume,
            cover_letter=invalid.cover_letter,
            analysis=invalid.analysis,
            issues_found=["First-person resume prose"],
            changes_made=[],
        )
        settings.qa_fail_open = True

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ):
            result = await run_qa_pipeline(
                selected_provider="ollama",
                draft=invalid,
                owner_name="Alex Example",
                source_resume=SOURCE_RESUME,
                instructions="Keep all facts truthful.",
                writing_examples="I write concise letters.",
                transcript="Education facts.",
                job_description="Product designer role.",
                company_context="",
                position="Product Designer",
                company="Example Company",
                position_slug="ProductDesigner",
                output_dir=Path(tmp),
            )

            self.assertEqual(result.report.status, "needs_review")
            self.assertTrue(result.report_path.exists())
            self.assertIsNotNone(result.report.draft_path)
            self.assertTrue(Path(result.report.draft_path).exists())
            self.assertIn(
                "<RESUME>",
                Path(result.report.draft_path).read_text(encoding="utf-8"),
            )

    async def test_pipeline_restores_identity_after_every_model_pass(self):
        draft = valid_draft()
        reviewer_result = QAAgentResult(
            resume=draft.resume.replace("NAME: Alex Example", "NAME: Alex"),
            cover_letter=draft.cover_letter.replace("Alex Example\n", "Alex\n"),
            analysis=draft.analysis.replace("ATS_SCORE: 80", "**ATS_SCORE:** 80/100"),
            changes_made=["Reworded the documents"],
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ) as reviewer, patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ):
            result = await run_qa_pipeline(
                selected_provider="ollama",
                draft=draft,
                owner_name="Alex Example",
                source_resume=SOURCE_RESUME,
                instructions="Keep all facts truthful.",
                writing_examples="I write concise letters.",
                transcript="Education facts.",
                job_description="Product designer role.",
                company_context="",
                position="Product Designer",
                company="Example Company",
                position_slug="ProductDesigner",
                output_dir=Path(tmp),
            )

            self.assertEqual(result.report.status, "passed")
            self.assertEqual(result.report.iterations, 1)
            self.assertIn("NAME: Alex Example", result.draft.resume)
            self.assertIn("Sincerely,\nAlex Example", result.draft.cover_letter)
            self.assertIn("ATS_SCORE: 80", result.draft.analysis)
            self.assertIn(
                "Normalized the cover-letter sign-off and restored the configured "
                "applicant name.",
                result.report.changes_made,
            )
            self.assertEqual(reviewer.await_args.kwargs["owner_name"], "Alex Example")

    async def test_text_validation_failure_reports_qa_review_stage_and_retains_draft(self):
        invalid = valid_draft()
        invalid.resume = invalid.resume.replace(
            "Product designer focused",
            "I am a product designer focused",
        )
        reviewer_result = QAAgentResult(
            resume=invalid.resume,
            cover_letter=invalid.cover_letter,
            analysis=invalid.analysis,
        )
        settings.qa_max_repairs = 0

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(),
        ) as builder:
            with self.assertRaises(QAPipelineValidationError) as raised:
                await run_qa_pipeline(
                    selected_provider="ollama",
                    draft=invalid,
                    owner_name="Alex Example",
                    source_resume=SOURCE_RESUME,
                    instructions="Keep all facts truthful.",
                    writing_examples="I write concise letters.",
                    transcript="Education facts.",
                    job_description="Product designer role.",
                    company_context="",
                    position="Product Designer",
                    company="Example Company",
                    position_slug="ProductDesigner",
                    output_dir=Path(tmp),
                )

            self.assertEqual(raised.exception.stage, "qa_review")
            self.assertTrue((Path(tmp) / "qa_report.json").exists())
            self.assertTrue((Path(tmp) / "qa_draft.xml").exists())
            builder.assert_not_awaited()

    async def test_pipeline_normalizes_model_bullets_before_validation(self):
        draft = valid_draft()
        reviewer_result = QAAgentResult(
            resume=draft.resume.replace("● Built", "* Built"),
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ):
            result = await run_qa_pipeline(
                selected_provider="ollama",
                draft=draft,
                owner_name="Alex Example",
                source_resume=SOURCE_RESUME,
                instructions="Keep all facts truthful.",
                writing_examples="I write concise letters.",
                transcript="Education facts.",
                job_description="Product designer role.",
                company_context="",
                position="Product Designer",
                company="Example Company",
                position_slug="ProductDesigner",
                output_dir=Path(tmp),
            )

            self.assertIn("● Built", result.draft.resume)
            self.assertNotIn("* Built", result.draft.resume)
            self.assertIn(
                "Normalized 1 resume bullet marker(s) to ●.",
                result.report.changes_made,
            )

    async def test_text_failure_after_artifact_retry_is_not_mislabeled(self):
        draft = valid_draft()
        first_review = QAAgentResult(
            resume=draft.resume,
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        invalid_review = QAAgentResult(
            resume=draft.resume.replace(
                "Product designer focused",
                "I am a product designer focused",
            ),
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        artifact_failure = ArtifactQAResult(
            issues=[
                QAIssue(
                    code="PDF_PAGE_LIMIT",
                    category="artifact",
                    severity=QASeverity.ERROR,
                    document="resume",
                    message="The resume exceeds the configured page limit.",
                )
            ],
            resume_pages=3,
            cover_letter_pages=1,
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(side_effect=[first_review, invalid_review]),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ) as builder, patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=artifact_failure,
        ):
            with self.assertRaises(QAPipelineValidationError) as raised:
                await run_qa_pipeline(
                    selected_provider="ollama",
                    draft=draft,
                    owner_name="Alex Example",
                    source_resume=SOURCE_RESUME,
                    instructions="Keep all facts truthful.",
                    writing_examples="I write concise letters.",
                    transcript="Education facts.",
                    job_description="Product designer role.",
                    company_context="",
                    position="Product Designer",
                    company="Example Company",
                    position_slug="ProductDesigner",
                    output_dir=Path(tmp),
                )

            self.assertEqual(raised.exception.stage, "qa_review")
            self.assertIn("review attempt(s)", str(raised.exception))
            self.assertEqual(builder.await_count, 1)
            report = (Path(tmp) / "qa_report.json").read_text(encoding="utf-8")
            self.assertIn("RESUME_FIRST_PERSON", report)
            self.assertNotIn("PDF_PAGE_LIMIT", report)

    async def test_current_artifact_failure_keeps_artifact_stage(self):
        draft = valid_draft()
        reviewer_result = QAAgentResult(
            resume=draft.resume,
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        settings.qa_max_repairs = 0
        artifact_failure = ArtifactQAResult(
            issues=[
                QAIssue(
                    code="PDF_PAGE_LIMIT",
                    category="artifact",
                    severity=QASeverity.ERROR,
                    document="resume",
                    message="The resume exceeds the configured page limit.",
                )
            ],
            resume_pages=3,
            cover_letter_pages=1,
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=artifact_failure,
        ):
            with self.assertRaises(QAPipelineValidationError) as raised:
                await run_qa_pipeline(
                    selected_provider="ollama",
                    draft=draft,
                    owner_name="Alex Example",
                    source_resume=SOURCE_RESUME,
                    instructions="Keep all facts truthful.",
                    writing_examples="I write concise letters.",
                    transcript="Education facts.",
                    job_description="Product designer role.",
                    company_context="",
                    position="Product Designer",
                    company="Example Company",
                    position_slug="ProductDesigner",
                    output_dir=Path(tmp),
                )

            self.assertEqual(raised.exception.stage, "artifact_validation")


if __name__ == "__main__":
    unittest.main()
