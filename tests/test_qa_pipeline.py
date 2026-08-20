import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
from docx import Document

from backend.config import settings
from backend.qa_models import (
    ArtifactQAResult,
    QAAgentResult,
    QAIssue,
    QASeverity,
    VisualQAResult,
)
from backend.services.qa_pipeline import (
    QAPipelineValidationError,
    run_qa_pipeline,
)
from backend.services.document_service import _build_resume_docx
from backend.services.work_sample_links import CASE_STUDIES_LABEL

from tests.test_qa_service import SOURCE_RESUME, valid_draft


CASE_STUDIES_LINKS = {
    CASE_STUDIES_LABEL: "https://figma.example/case-studies"
}
CASE_STUDIES_INSTRUCTIONS = (
    "WORK_SAMPLES: [Case Studies and Product Work]"
    "(https://figma.example/case-studies)"
)


def write_required_resume_docx(path: Path) -> None:
    _build_resume_docx(
        "NAME: Alex Example\n"
        "ROLE: Software Engineer\n"
        "CONTACT: alex@example.com\n"
        "LINKS: alex.example\n"
        f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]"
        f"({CASE_STUDIES_LINKS[CASE_STUDIES_LABEL]})\n\n"
        "PROFESSIONAL SUMMARY\n"
        "This artifact contains enough readable text for validation.",
        path,
    )


def write_cover_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph(
        "This cover letter contains enough readable text for artifact validation."
    )
    document.save(path)


def write_required_resume_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 48), "Resume artifact validation text")
        page.insert_text((72, 84), CASE_STUDIES_LABEL)
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": page.search_for(CASE_STUDIES_LABEL)[0],
                "uri": CASE_STUDIES_LINKS[CASE_STUDIES_LABEL],
            }
        )
        document.save(path)


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

    async def _run_work_sample_case(self, root: Path):
        return await run_qa_pipeline(
            selected_provider="ollama",
            draft=valid_draft(),
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            instructions=CASE_STUDIES_INSTRUCTIONS,
            writing_examples="I write concise letters.",
            transcript="Education facts.",
            job_description="Software role.",
            company_context="",
            position="Software Engineer",
            company="Example Company",
            position_slug="SoftwareEngineer",
            output_dir=root,
            job_type="development",
            required_work_sample_links=CASE_STUDIES_LINKS,
        )

    async def test_pipeline_reviews_builds_and_writes_report(self):
        corrected = valid_draft()
        progress_events: list[str] = []
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
                required_work_sample_links={},
                progress_callback=progress_events.append,
            )

            self.assertEqual(result.report.status, "passed")
            self.assertEqual(result.report.iterations, 1)
            self.assertTrue(result.report_path.exists())
            self.assertIn("Corrected one sentence", result.report.changes_made)
            self.assertEqual(
                progress_events[-2:],
                ["build_documents", "artifact_validation"],
            )
            self.assertIn("qa_review", progress_events)

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
                required_work_sample_links={},
            )

            self.assertEqual(result.report.status, "needs_review")
            self.assertTrue(result.report_path.exists())
            self.assertIsNotNone(result.report.draft_path)
            self.assertTrue(Path(result.report.draft_path).exists())
            self.assertIn(
                "<RESUME>",
                Path(result.report.draft_path).read_text(encoding="utf-8"),
            )

    async def test_fail_open_hard_fails_required_semantic_link_mismatch(self):
        settings.qa_fail_open = True
        settings.qa_max_repairs = 0
        semantic_failure = QAIssue(
            code="RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            category="structure",
            severity=QASeverity.ERROR,
            document="resume",
            message="The required work-sample link differs from the source.",
        )
        reviewer_result = QAAgentResult(
            resume=valid_draft().resume,
            cover_letter=valid_draft().cover_letter,
            analysis=valid_draft().analysis,
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.validate_draft",
            return_value=[semantic_failure],
        ), patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ) as inspector:
            with self.assertRaises(QAPipelineValidationError) as raised:
                await self._run_work_sample_case(Path(tmp))

            self.assertEqual(raised.exception.stage, "qa_review")
            inspector.assert_called_once()
            self.assertTrue((Path(tmp) / "qa_report.json").exists())
            self.assertTrue((Path(tmp) / "qa_draft.xml").exists())
            report = (Path(tmp) / "qa_report.json").read_text(encoding="utf-8")
            self.assertIn("RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH", report)

    async def test_fail_open_inspects_and_merges_required_artifact_failure(self):
        settings.qa_fail_open = True
        settings.qa_max_repairs = 0
        semantic_failure = QAIssue(
            code="RESUME_FIRST_PERSON",
            category="formatting",
            severity=QASeverity.ERROR,
            document="resume",
            message="The resume uses first-person prose.",
        )
        artifact_failure = QAIssue(
            code="PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            category="artifact",
            severity=QASeverity.ERROR,
            document="resume",
            message="The required work-sample link cannot be inspected.",
        )
        reviewer_result = QAAgentResult(
            resume=valid_draft().resume,
            cover_letter=valid_draft().cover_letter,
            analysis=valid_draft().analysis,
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.validate_draft",
            return_value=[semantic_failure],
        ), patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(issues=[artifact_failure]),
        ) as inspector:
            with self.assertRaises(QAPipelineValidationError) as raised:
                await self._run_work_sample_case(Path(tmp))

            self.assertEqual(raised.exception.stage, "qa_review")
            inspector.assert_called_once()
            report = (Path(tmp) / "qa_report.json").read_text(encoding="utf-8")
            self.assertIn("RESUME_FIRST_PERSON", report)
            self.assertIn("PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING", report)

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
                required_work_sample_links={},
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

    async def test_pipeline_repairs_retained_failure_cluster_after_one_review(self):
        source_resume = """# Alex Example
alex@example.com
[alex.example](https://alex.example/)

## Work Experience

### Creative Lead & Multimedia Artist
**Example Network**
March – July 2015
"""
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Multimedia Designer
CONTACT: alex@example.com
LINKS: www.alex.example

PROFESSIONAL SUMMARY
Multimedia designer focused on accessible digital experiences.

---

EXPERIENCE
Example Network
CREATIVE LEAD & MULTIMEDIA ARTIST - N/A
● Led a multidisciplinary creative team.
"""
        draft.cover_letter = draft.cover_letter.replace(
            "Cover Letter",
            "# Cover Letter",
            1,
        )
        reviewer_result = QAAgentResult(
            resume=draft.resume,
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        settings.qa_max_repairs = 4

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
                source_resume=source_resume,
                instructions="Keep all facts truthful.",
                writing_examples="I write concise letters.",
                transcript="Education facts.",
                job_description="Multimedia designer role.",
                company_context="",
                position="Multimedia Designer",
                company="Example Company",
                position_slug="MultimediaDesigner",
                output_dir=Path(tmp),
                job_type="design",
                required_work_sample_links={},
            )

            self.assertEqual(result.report.status, "passed")
            self.assertEqual(result.report.iterations, 1)
            self.assertEqual(reviewer.await_count, 1)
            self.assertTrue(result.draft.cover_letter.startswith("Cover Letter\n"))
            self.assertIn(
                "CREATIVE LEAD & MULTIMEDIA ARTIST - March - July 2015",
                result.draft.resume,
            )
            self.assertIn("LINKS: alex.example", result.draft.resume)

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
                    required_work_sample_links={},
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
                required_work_sample_links={},
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
                    required_work_sample_links={},
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
                    required_work_sample_links={},
                )

            self.assertEqual(raised.exception.stage, "artifact_validation")

    async def test_minor_visual_warning_is_non_blocking(self):
        draft = valid_draft()
        reviewer_result = QAAgentResult(
            resume=draft.resume,
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        settings.qa_visual_enabled = True

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ) as reviewer, patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts_visually",
            new=AsyncMock(
                return_value=VisualQAResult(
                    passed=True,
                    warnings=[
                        "Cover letter, page 1: excessive whitespace after the greeting."
                    ],
                )
            ),
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
                required_work_sample_links={},
            )

            self.assertEqual(result.report.status, "passed_with_warnings")
            self.assertEqual(reviewer.await_count, 1)
            self.assertEqual(result.report.issues[-1].code, "VISUAL_QA_ADVISORY")
            self.assertEqual(result.report.issues[-1].severity, QASeverity.WARNING)

    async def test_visual_reference_fidelity_issue_is_blocking(self):
        draft = valid_draft()
        reviewer_result = QAAgentResult(
            resume=draft.resume,
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        settings.qa_visual_enabled = True
        settings.qa_max_repairs = 0

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ), patch(
            "backend.services.qa_pipeline.inspect_artifacts_visually",
            new=AsyncMock(
                return_value=VisualQAResult(
                    passed=False,
                    issues=[
                        "Resume page 1 uses an oversized black header that diverges from the compact teal reference hierarchy."
                    ],
                )
            ),
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
                    required_work_sample_links={},
                )

            report = Path(raised.exception.report_path).read_text(encoding="utf-8")
            self.assertIn("VISUAL_QA_FAILED", report)
            self.assertIn('"severity": "error"', report)

    async def test_pipeline_allows_five_total_review_attempts(self):
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
        settings.qa_max_repairs = 4

        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ) as reviewer, patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ):
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
                    required_work_sample_links={},
                )

            report = Path(raised.exception.report_path).read_text(encoding="utf-8")
            self.assertEqual(reviewer.await_count, 5)
            self.assertIn('"iterations": 5', report)

    async def test_pipeline_passes_one_trusted_mapping_to_every_stage(self):
        draft = valid_draft()
        reviewer_result = QAAgentResult(
            resume=draft.resume,
            cover_letter=draft.cover_letter,
            analysis=draft.analysis,
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.services.qa_pipeline.review_and_fix_draft",
            new=AsyncMock(return_value=reviewer_result),
        ), patch(
            "backend.services.qa_pipeline.build_documents",
            new=AsyncMock(return_value={"resume_docx": "resume.docx"}),
        ) as builder, patch(
            "backend.services.qa_pipeline.inspect_artifacts",
            return_value=ArtifactQAResult(resume_pages=2, cover_letter_pages=1),
        ) as inspector:
            result = await run_qa_pipeline(
                selected_provider="ollama",
                draft=draft,
                owner_name="Alex Example",
                source_resume=SOURCE_RESUME,
                instructions=CASE_STUDIES_INSTRUCTIONS,
                writing_examples="I write concise letters.",
                transcript="Education facts.",
                job_description="Software role.",
                company_context="",
                position="Software Engineer",
                company="Example Company",
                position_slug="SoftwareEngineer",
                output_dir=Path(tmp),
                job_type="development",
                required_work_sample_links=CASE_STUDIES_LINKS,
            )

        self.assertIn("WORK_SAMPLES:", result.draft.resume)
        self.assertEqual(
            builder.await_args.kwargs["required_resume_hyperlinks"],
            CASE_STUDIES_LINKS,
        )
        self.assertEqual(
            inspector.call_args.kwargs["required_resume_hyperlinks"],
            CASE_STUDIES_LINKS,
        )

    async def test_required_link_artifact_failure_blocks_when_ai_qa_disabled(self):
        draft = valid_draft()
        settings.qa_enabled = False
        settings.qa_fail_open = True
        artifact_failure = ArtifactQAResult(
            issues=[
                QAIssue(
                    code="PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
                    category="artifact",
                    severity=QASeverity.ERROR,
                    document="resume",
                    message="Required label is not clickable.",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
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
                    instructions=CASE_STUDIES_INSTRUCTIONS,
                    writing_examples="I write concise letters.",
                    transcript="Education facts.",
                    job_description="Software role.",
                    company_context="",
                    position="Software Engineer",
                    company="Example Company",
                    position_slug="SoftwareEngineer",
                    output_dir=Path(tmp),
                    job_type="development",
                    required_work_sample_links=CASE_STUDIES_LINKS,
                )

            self.assertEqual(raised.exception.stage, "artifact_validation")
            report = Path(raised.exception.report_path).read_text(encoding="utf-8")
            self.assertIn("PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING", report)
            self.assertTrue((Path(tmp) / "qa_draft.xml").exists())

    async def test_disabled_qa_blocks_unreadable_required_resume_docx(self):
        settings.qa_enabled = False
        settings.qa_fail_open = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_docx = root / "resume.docx"
            cover_docx = root / "cover.docx"
            resume_docx.write_bytes(b"not a Word package")
            write_cover_docx(cover_docx)
            docs = {
                "resume_docx": str(resume_docx),
                "cover_letter_docx": str(cover_docx),
            }

            with patch(
                "backend.services.qa_pipeline.build_documents",
                new=AsyncMock(return_value=docs),
            ):
                with self.assertRaises(QAPipelineValidationError) as raised:
                    await self._run_work_sample_case(root)

            self.assertEqual(raised.exception.stage, "artifact_validation")

    async def test_disabled_qa_blocks_unreadable_existing_resume_pdf(self):
        settings.qa_enabled = False
        settings.qa_fail_open = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_docx = root / "resume.docx"
            cover_docx = root / "cover.docx"
            resume_pdf = root / "resume.pdf"
            write_required_resume_docx(resume_docx)
            write_cover_docx(cover_docx)
            resume_pdf.write_bytes(b"not a PDF")
            docs = {
                "resume_docx": str(resume_docx),
                "cover_letter_docx": str(cover_docx),
                "resume_pdf": str(resume_pdf),
            }

            with patch(
                "backend.services.qa_pipeline.build_documents",
                new=AsyncMock(return_value=docs),
            ):
                with self.assertRaises(QAPipelineValidationError) as raised:
                    await self._run_work_sample_case(root)

            self.assertEqual(raised.exception.stage, "artifact_validation")

    async def test_disabled_qa_blocks_unavailable_required_pdf_inspector(self):
        settings.qa_enabled = False
        settings.qa_fail_open = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_docx = root / "resume.docx"
            cover_docx = root / "cover.docx"
            resume_pdf = root / "resume.pdf"
            write_required_resume_docx(resume_docx)
            write_cover_docx(cover_docx)
            write_required_resume_pdf(resume_pdf)
            docs = {
                "resume_docx": str(resume_docx),
                "cover_letter_docx": str(cover_docx),
                "resume_pdf": str(resume_pdf),
            }

            with patch(
                "backend.services.qa_pipeline.build_documents",
                new=AsyncMock(return_value=docs),
            ), patch.dict("sys.modules", {"pymupdf": None}):
                with self.assertRaises(QAPipelineValidationError) as raised:
                    await self._run_work_sample_case(root)

            self.assertEqual(raised.exception.stage, "artifact_validation")


if __name__ == "__main__":
    unittest.main()
