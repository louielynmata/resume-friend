import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
from docx import Document

from backend.config import settings
from backend.qa_models import QASeverity, VisualQAResult
from backend.services.artifact_qa_service import (
    inspect_artifacts,
    inspect_artifacts_visually,
)
from backend.services.document_service import _build_resume_docx
from backend.services.work_sample_links import (
    CASE_STUDIES_LABEL,
    DESIGN_PORTFOLIO_LABEL,
)


DESIGN_LINKS = {
    DESIGN_PORTFOLIO_LABEL: "https://drive.example/design-portfolio",
    CASE_STUDIES_LABEL: "https://figma.example/case-studies",
}


def write_docx(path: Path, label: str) -> None:
    document = Document()
    document.add_heading(label, level=1)
    document.add_paragraph(
        "This artifact contains enough readable text to exercise the document "
        "validator and confirm the generated Word package can be reopened."
    )
    document.save(path)


def write_pdf(path: Path, pages: int) -> None:
    with pymupdf.open() as document:
        for index in range(pages):
            page = document.new_page()
            page.insert_text(
                (72, 72),
                f"Page {index + 1} contains readable validation text for Resume Friend.",
            )
        document.save(path)


def write_resume_docx(
    path: Path,
    rendered_links: dict[str, str] | None,
    plain_labels: tuple[str, ...] = (),
) -> None:
    work_samples = ""
    if rendered_links is not None:
        pairs = " | ".join(
            f"[{label}]({url})" for label, url in rendered_links.items()
        )
        work_samples = f"\nWORK_SAMPLES: {pairs}"
    elif plain_labels:
        work_samples = "\nWORK_SAMPLES: " + " | ".join(plain_labels)
    _build_resume_docx(
        "NAME: Alex Example\n"
        "ROLE: Product Designer\n"
        "CONTACT: alex@example.com\n"
        "LINKS: alex.example"
        + work_samples
        + "\n\nPROFESSIONAL SUMMARY\n"
        "This artifact contains enough readable text for validation.",
        path,
    )


def write_linked_pdf(
    path: Path,
    visible_labels: tuple[str, ...],
    targets: dict[str, str | tuple[str, ...]],
) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 48), "Resume artifact validation text")
        for index, label in enumerate(visible_labels):
            point = (72, 84 + index * 24)
            page.insert_text(point, label)
            rect = page.search_for(label)[0]
            label_targets = targets.get(label, ())
            if isinstance(label_targets, str):
                label_targets = (label_targets,)
            for target in label_targets:
                page.insert_link(
                    {
                        "kind": pymupdf.LINK_URI,
                        "from": rect,
                        "uri": target,
                    }
                )
        document.save(path)


class ArtifactQAServiceTests(unittest.TestCase):
    def inspect_resume_pair(
        self,
        root: Path,
        *,
        docx_links: dict[str, str] | None,
        docx_plain_labels: tuple[str, ...],
        pdf_labels: tuple[str, ...],
        pdf_targets: dict[str, str | tuple[str, ...]],
        required: dict[str, str],
    ):
        resume_docx = root / "resume.docx"
        cover_docx = root / "cover.docx"
        resume_pdf = root / "resume.pdf"
        cover_pdf = root / "cover.pdf"
        write_resume_docx(resume_docx, docx_links, docx_plain_labels)
        write_docx(cover_docx, "Cover Letter")
        write_linked_pdf(resume_pdf, pdf_labels, pdf_targets)
        write_pdf(cover_pdf, 1)
        return inspect_artifacts(
            {
                "resume_docx": str(resume_docx),
                "cover_letter_docx": str(cover_docx),
                "resume_pdf": str(resume_pdf),
                "cover_letter_pdf": str(cover_pdf),
            },
            required_resume_hyperlinks=required,
        )

    def test_exact_docx_and_pdf_links_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=DESIGN_LINKS,
                docx_plain_labels=(),
                pdf_labels=tuple(DESIGN_LINKS),
                pdf_targets=DESIGN_LINKS,
                required=DESIGN_LINKS,
            )
        self.assertFalse(result.blocking_issues)

    def test_plain_text_docx_label_is_blocking(self):
        expected = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=None,
                docx_plain_labels=(CASE_STUDIES_LABEL,),
                pdf_labels=(CASE_STUDIES_LABEL,),
                pdf_targets=expected,
                required=expected,
            )
        self.assertIn(
            "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_missing_design_docx_label_is_blocking_for_design_track(self):
        case_only = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=case_only,
                docx_plain_labels=(),
                pdf_labels=tuple(DESIGN_LINKS),
                pdf_targets=DESIGN_LINKS,
                required=DESIGN_LINKS,
            )
        self.assertIn(
            "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_wrong_docx_target_is_blocking(self):
        expected = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links={
                    CASE_STUDIES_LABEL: "https://wrong.example/case-studies"
                },
                docx_plain_labels=(),
                pdf_labels=(CASE_STUDIES_LABEL,),
                pdf_targets=expected,
                required=expected,
            )
        self.assertIn(
            "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH",
            {issue.code for issue in result.blocking_issues},
        )

    def test_visible_pdf_label_without_annotation_is_blocking(self):
        expected = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=expected,
                docx_plain_labels=(),
                pdf_labels=(CASE_STUDIES_LABEL,),
                pdf_targets={},
                required=expected,
            )
        self.assertIn(
            "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_missing_design_pdf_label_is_blocking_for_design_track(self):
        case_only = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=DESIGN_LINKS,
                docx_plain_labels=(),
                pdf_labels=tuple(case_only),
                pdf_targets=case_only,
                required=DESIGN_LINKS,
            )
        self.assertIn(
            "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_wrong_pdf_annotation_target_is_blocking(self):
        expected = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=expected,
                docx_plain_labels=(),
                pdf_labels=(CASE_STUDIES_LABEL,),
                pdf_targets={
                    CASE_STUDIES_LABEL: "https://wrong.example/case-studies"
                },
                required=expected,
            )
        self.assertIn(
            "PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH",
            {issue.code for issue in result.blocking_issues},
        )

    def test_mixed_pdf_targets_pass_when_exact_target_is_present(self):
        expected = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=expected,
                docx_plain_labels=(),
                pdf_labels=(CASE_STUDIES_LABEL,),
                pdf_targets={
                    CASE_STUDIES_LABEL: (
                        "https://wrong.example/case-studies",
                        DESIGN_LINKS[CASE_STUDIES_LABEL],
                    )
                },
                required=expected,
            )
        codes = {issue.code for issue in result.blocking_issues}
        self.assertNotIn("PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING", codes)
        self.assertNotIn("PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH", codes)

    def test_development_does_not_require_design_portfolio(self):
        development = {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]}
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=development,
                docx_plain_labels=(),
                pdf_labels=tuple(development),
                pdf_targets=development,
                required=development,
            )
        codes = {issue.code for issue in result.blocking_issues}
        self.assertNotIn("DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING", codes)
        self.assertNotIn("PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING", codes)

    def test_pdf_unavailable_keeps_existing_warning_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_docx = root / "resume.docx"
            cover_docx = root / "cover.docx"
            write_resume_docx(resume_docx, DESIGN_LINKS)
            write_docx(cover_docx, "Cover Letter")
            result = inspect_artifacts(
                {
                    "resume_docx": str(resume_docx),
                    "cover_letter_docx": str(cover_docx),
                },
                required_resume_hyperlinks=DESIGN_LINKS,
            )
        self.assertIn("PDF_NOT_AVAILABLE", {issue.code for issue in result.issues})
        self.assertNotIn(
            "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_artifacts_pass_with_expected_page_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_docx = root / "resume.docx"
            cover_docx = root / "cover.docx"
            resume_pdf = root / "resume.pdf"
            cover_pdf = root / "cover.pdf"
            write_docx(resume_docx, "Resume")
            write_docx(cover_docx, "Cover Letter")
            write_pdf(resume_pdf, 2)
            write_pdf(cover_pdf, 1)

            result = inspect_artifacts(
                {
                    "resume_docx": str(resume_docx),
                    "cover_letter_docx": str(cover_docx),
                    "resume_pdf": str(resume_pdf),
                    "cover_letter_pdf": str(cover_pdf),
                }
            )

            self.assertEqual(result.resume_pages, 2)
            self.assertEqual(result.cover_letter_pages, 1)
            self.assertFalse(result.blocking_issues)

    def test_resume_page_limit_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_docx = root / "resume.docx"
            cover_docx = root / "cover.docx"
            resume_pdf = root / "resume.pdf"
            cover_pdf = root / "cover.pdf"
            write_docx(resume_docx, "Resume")
            write_docx(cover_docx, "Cover Letter")
            write_pdf(resume_pdf, 3)
            write_pdf(cover_pdf, 1)

            result = inspect_artifacts(
                {
                    "resume_docx": str(resume_docx),
                    "cover_letter_docx": str(cover_docx),
                    "resume_pdf": str(resume_pdf),
                    "cover_letter_pdf": str(cover_pdf),
                }
            )

            page_limit = [
                issue for issue in result.issues if issue.code == "PDF_PAGE_LIMIT"
            ]
            self.assertEqual(len(page_limit), 1)
            self.assertEqual(page_limit[0].severity, QASeverity.ERROR)


class VisualArtifactQAServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_visual_qa_renders_pdf_pages_for_the_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_pdf = root / "resume.pdf"
            write_pdf(resume_pdf, 2)
            original_temp_dir = settings.qa_temp_dir
            original_reference_dir = settings.reference_dir
            settings.qa_temp_dir = str(root / "rendered")
            settings.reference_dir = str(root / "references")

            async def verify_images(*args, **kwargs):
                image_paths = kwargs["image_paths"]
                self.assertEqual(len(image_paths), 2)
                self.assertTrue(all(path.exists() for path in image_paths))
                return VisualQAResult(passed=True, summary="Looks good")

            try:
                with patch(
                    "backend.services.artifact_qa_service.generate_structured",
                    new=AsyncMock(side_effect=verify_images),
                ):
                    result = await inspect_artifacts_visually(
                        provider="ollama",
                        docs={"resume_pdf": str(resume_pdf)},
                    )
            finally:
                settings.qa_temp_dir = original_temp_dir
                settings.reference_dir = original_reference_dir

            self.assertTrue(result.passed)

    async def test_visual_qa_includes_reference_pages_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_pdf = root / "resume.pdf"
            references = root / "references"
            references.mkdir()
            reference_pdf = references / "Design Resume Reference.pdf"
            write_pdf(resume_pdf, 1)
            write_pdf(reference_pdf, 2)
            original_temp_dir = settings.qa_temp_dir
            original_reference_dir = settings.reference_dir
            settings.qa_temp_dir = str(root / "rendered")
            settings.reference_dir = str(references)

            async def verify_reference_context(*args, **kwargs):
                self.assertEqual(len(kwargs["image_paths"]), 3)
                self.assertIn("Reference: Design Resume Reference", args[2])
                return VisualQAResult(passed=True, summary="Matches reference")

            try:
                with patch(
                    "backend.services.artifact_qa_service.generate_structured",
                    new=AsyncMock(side_effect=verify_reference_context),
                ):
                    result = await inspect_artifacts_visually(
                        provider="ollama",
                        docs={"resume_pdf": str(resume_pdf)},
                    )
            finally:
                settings.qa_temp_dir = original_temp_dir
                settings.reference_dir = original_reference_dir

            self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
