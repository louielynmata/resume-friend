from __future__ import annotations

import re
import tempfile
from pathlib import Path

from docx import Document

from ..config import settings
from ..qa_models import ArtifactQAResult, QAIssue, QASeverity, VisualQAResult
from .ai_service import generate_structured


_VISUAL_QA_PROMPT_FILE = "visual_qa_prompt.md"


def inspect_artifacts(docs: dict) -> ArtifactQAResult:
    result = ArtifactQAResult()
    _inspect_docx(docs.get("resume_docx"), "resume", result)
    _inspect_docx(docs.get("cover_letter_docx"), "cover_letter", result)

    result.resume_pages = _inspect_pdf(
        docs.get("resume_pdf"),
        "resume",
        settings.qa_resume_max_pages,
        result,
    )
    result.cover_letter_pages = _inspect_pdf(
        docs.get("cover_letter_pdf"),
        "cover_letter",
        settings.qa_cover_letter_max_pages,
        result,
    )
    return result


async def inspect_artifacts_visually(
    *,
    provider: str,
    docs: dict,
) -> VisualQAResult:
    pdfs = [
        ("Resume", docs.get("resume_pdf")),
        ("Cover letter", docs.get("cover_letter_pdf")),
    ]
    available = [(label, Path(path)) for label, path in pdfs if path and Path(path).exists()]
    if not available:
        return VisualQAResult(
            passed=True,
            summary="Visual QA skipped because no PDF files were available.",
        )

    prompt_path = settings.app_model_files_path / _VISUAL_QA_PROMPT_FILE
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"{_VISUAL_QA_PROMPT_FILE} was not found in {prompt_path.parent}."
        )
    system_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not system_prompt:
        raise ValueError(f"{_VISUAL_QA_PROMPT_FILE} is empty.")

    temp_root = settings.qa_temp_path
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="visual-qa-", dir=temp_root) as tmp:
        image_paths: list[Path] = []
        page_labels: list[str] = []
        for document_label, pdf_path in available:
            pages = _render_pdf(pdf_path, Path(tmp), document_label)
            first_image_number = len(page_labels) + 1
            image_paths.extend(pages)
            page_labels.extend(
                f"Image {first_image_number + index}: {document_label}, page {index + 1}"
                for index in range(len(pages))
            )

        if not image_paths:
            return VisualQAResult(
                passed=True,
                summary="Visual QA skipped because the PDFs could not be rendered.",
            )

        user_prompt = (
            "Inspect these rendered pages in the listed order.\n"
            + "\n".join(page_labels)
        )
        return await generate_structured(
            provider,
            system_prompt,
            user_prompt,
            VisualQAResult,
            image_paths=image_paths,
        )


def _inspect_docx(path_value: str | None, document_name: str, result: ArtifactQAResult) -> None:
    if not path_value:
        _add_issue(
            result,
            "DOCX_MISSING",
            QASeverity.ERROR,
            document_name,
            "The DOCX artifact was not created.",
        )
        return

    path = Path(path_value)
    if not path.exists() or path.stat().st_size == 0:
        _add_issue(
            result,
            "DOCX_EMPTY",
            QASeverity.ERROR,
            document_name,
            f"The DOCX artifact is missing or empty: {path}",
        )
        return

    try:
        document = Document(path)
    except Exception as exc:
        _add_issue(
            result,
            "DOCX_UNREADABLE",
            QASeverity.ERROR,
            document_name,
            f"The DOCX artifact could not be reopened: {exc}",
        )
        return

    text = "\n".join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
    if len(text) < 80:
        _add_issue(
            result,
            "DOCX_CONTENT_TOO_SHORT",
            QASeverity.ERROR,
            document_name,
            "The rendered DOCX contains too little readable text.",
        )
    if "```" in text or re.search(r"\[(?:placeholder|insert|copy)\b", text, re.IGNORECASE):
        _add_issue(
            result,
            "DOCX_ARTIFACT_TEXT",
            QASeverity.ERROR,
            document_name,
            "The rendered DOCX still contains a code fence or placeholder.",
        )

    for section in document.sections:
        margins = [
            section.top_margin,
            section.bottom_margin,
            section.left_margin,
            section.right_margin,
        ]
        if any(margin is None or margin.inches < 0.4 for margin in margins):
            _add_issue(
                result,
                "DOCX_MARGIN_TOO_SMALL",
                QASeverity.ERROR,
                document_name,
                "A document margin is below 0.4 inches and risks clipping.",
            )
            break


def _inspect_pdf(
    path_value: str | None,
    document_name: str,
    max_pages: int,
    result: ArtifactQAResult,
) -> int | None:
    if not path_value:
        _add_issue(
            result,
            "PDF_NOT_AVAILABLE",
            QASeverity.WARNING,
            document_name,
            "PDF QA was skipped because PDF conversion was unavailable.",
        )
        return None

    path = Path(path_value)
    if not path.exists() or path.stat().st_size == 0:
        _add_issue(
            result,
            "PDF_EMPTY",
            QASeverity.ERROR,
            document_name,
            f"The PDF artifact is missing or empty: {path}",
        )
        return None

    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        page_count = len(reader.pages)
        if page_count == 0:
            _add_issue(
                result,
                "PDF_NO_PAGES",
                QASeverity.ERROR,
                document_name,
                "The PDF contains no pages.",
            )
        elif page_count > max_pages:
            _add_issue(
                result,
                "PDF_PAGE_LIMIT",
                QASeverity.ERROR,
                document_name,
                f"The {document_name.replace('_', ' ')} is {page_count} pages; the limit is {max_pages}.",
            )

        for index, page in enumerate(reader.pages):
            extracted = (page.extract_text() or "").strip()
            if len(extracted) < 20:
                _add_issue(
                    result,
                    "PDF_BLANK_OR_UNREADABLE_PAGE",
                    QASeverity.ERROR,
                    document_name,
                    f"Page {index + 1} is blank or has too little extractable text.",
                )
        return page_count
    except ImportError:
        _add_issue(
            result,
            "PDF_READER_UNAVAILABLE",
            QASeverity.WARNING,
            document_name,
            "pypdf is not installed, so PDF page validation was skipped.",
        )
    except Exception as exc:
        _add_issue(
            result,
            "PDF_UNREADABLE",
            QASeverity.ERROR,
            document_name,
            f"The PDF could not be validated: {exc}",
        )
    return None


def _render_pdf(pdf_path: Path, output_dir: Path, label: str) -> list[Path]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required when QA_VISUAL_ENABLED is true."
        ) from exc

    rendered: list[Path] = []
    with pymupdf.open(pdf_path) as pdf:
        for index, page in enumerate(pdf):
            output_path = output_dir / f"{label.lower().replace(' ', '-')}-{index + 1}.png"
            page.get_pixmap(dpi=150, alpha=False).save(output_path)
            rendered.append(output_path)
    return rendered


def _add_issue(
    result: ArtifactQAResult,
    code: str,
    severity: QASeverity,
    document: str,
    message: str,
) -> None:
    result.issues.append(
        QAIssue(
            code=code,
            category="artifact",
            severity=severity,
            document=document,
            message=message,
        )
    )
