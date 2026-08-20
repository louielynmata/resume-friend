from __future__ import annotations

import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from ..config import settings
from ..qa_models import ArtifactQAResult, QAIssue, QASeverity, VisualQAResult
from .ai_service import generate_structured
from .document_service import _exact_pdf_label_rects


_VISUAL_QA_PROMPT_FILE = "visual_qa_prompt.md"
WORK_SAMPLE_ARTIFACT_ISSUE_CODES = frozenset(
    {
        "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
        "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH",
        "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
        "PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH",
    }
)


def inspect_artifacts(
    docs: dict,
    *,
    resume_max_pages: int | None = None,
    required_resume_hyperlinks: Mapping[str, str] | None = None,
) -> ArtifactQAResult:
    result = ArtifactQAResult()
    _inspect_docx(
        docs.get("resume_docx"),
        "resume",
        result,
        required_hyperlinks=required_resume_hyperlinks,
    )
    _inspect_docx(docs.get("cover_letter_docx"), "cover_letter", result)

    result.resume_pages = _inspect_pdf(
        docs.get("resume_pdf"),
        "resume",
        resume_max_pages or settings.qa_resume_max_pages,
        result,
        required_hyperlinks=required_resume_hyperlinks,
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

        reference_files = (
            sorted(settings.reference_path.glob("*.pdf"))
            if settings.reference_path.exists()
            else []
        )
        for reference_path in reference_files:
            reference_label = f"Reference: {reference_path.stem}"
            pages = _render_pdf(reference_path, Path(tmp), reference_label)
            first_image_number = len(page_labels) + 1
            image_paths.extend(pages)
            page_labels.extend(
                f"Image {first_image_number + index}: {reference_label}, page {index + 1}"
                for index in range(len(pages))
            )

        if not image_paths:
            return VisualQAResult(
                passed=True,
                summary="Visual QA skipped because the PDFs could not be rendered.",
            )

        user_prompt = (
            "Inspect these rendered output and reference pages in the listed order. "
            "The Resume and Cover letter images are delivery candidates. Images "
            "labelled Reference are visual authorities for comparison.\n"
            + "\n".join(page_labels)
        )
        return await generate_structured(
            provider,
            system_prompt,
            user_prompt,
            VisualQAResult,
            image_paths=image_paths,
        )


def _inspect_docx(
    path_value: str | None,
    document_name: str,
    result: ArtifactQAResult,
    *,
    required_hyperlinks: Mapping[str, str] | None = None,
) -> None:
    if not path_value:
        _add_issue(
            result,
            "DOCX_MISSING",
            QASeverity.ERROR,
            document_name,
            "The DOCX artifact was not created.",
        )
        _add_missing_required_docx_hyperlinks(
            result,
            document_name,
            required_hyperlinks,
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
        _add_missing_required_docx_hyperlinks(
            result,
            document_name,
            required_hyperlinks,
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
        _add_missing_required_docx_hyperlinks(
            result,
            document_name,
            required_hyperlinks,
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

    if required_hyperlinks:
        hyperlinks = _collect_docx_hyperlinks(document)
        for label, expected_url in required_hyperlinks.items():
            targets = hyperlinks.get(label)
            if not targets:
                _add_issue(
                    result,
                    "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
                    QASeverity.ERROR,
                    document_name,
                    f'The required work-sample label "{label}" is not a DOCX hyperlink.',
                )
            elif any(target != expected_url for target in targets):
                _add_issue(
                    result,
                    "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH",
                    QASeverity.ERROR,
                    document_name,
                    f'The DOCX hyperlink for "{label}" has the wrong target.',
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


def _collect_docx_hyperlinks(document: Document) -> dict[str, list[str]]:
    hyperlinks: dict[str, list[str]] = {}
    for hyperlink in document.element.iter(qn("w:hyperlink")):
        label = "".join(
            text_node.text or "" for text_node in hyperlink.iter(qn("w:t"))
        )
        relationship_id = hyperlink.get(qn("r:id"))
        relationship = document.part.rels.get(relationship_id)
        if (
            label
            and relationship is not None
            and relationship.reltype == RT.HYPERLINK
        ):
            hyperlinks.setdefault(label, []).append(relationship.target_ref)
    return hyperlinks


def _add_missing_required_docx_hyperlinks(
    result: ArtifactQAResult,
    document_name: str,
    required_hyperlinks: Mapping[str, str] | None,
) -> None:
    if document_name != "resume" or not required_hyperlinks:
        return
    for label in required_hyperlinks:
        _add_issue(
            result,
            "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
            QASeverity.ERROR,
            document_name,
            f'The required work-sample label "{label}" could not be inspected in the DOCX.',
        )


def _inspect_pdf(
    path_value: str | None,
    document_name: str,
    max_pages: int,
    result: ArtifactQAResult,
    *,
    required_hyperlinks: Mapping[str, str] | None = None,
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
        _add_missing_required_pdf_hyperlinks(
            result,
            document_name,
            required_hyperlinks,
        )
        return None

    page_count: int | None = None
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

    if required_hyperlinks:
        try:
            _inspect_required_pdf_hyperlinks(path, required_hyperlinks, result)
        except Exception:
            _add_missing_required_pdf_hyperlinks(
                result,
                document_name,
                required_hyperlinks,
            )
    return page_count


def _inspect_required_pdf_hyperlinks(
    path: Path,
    required_hyperlinks: Mapping[str, str],
    result: ArtifactQAResult,
) -> None:
    import pymupdf

    found_targets = {label: [] for label in required_hyperlinks}
    found_labels = {label: False for label in required_hyperlinks}
    with pymupdf.open(path) as document:
        for page in document:
            uri_links = [
                link
                for link in page.get_links()
                if link.get("kind") == pymupdf.LINK_URI and link.get("uri")
            ]
            for label in required_hyperlinks:
                label_rects = _exact_pdf_label_rects(page, label)
                if not label_rects:
                    continue
                found_labels[label] = True
                for link in uri_links:
                    link_rect = pymupdf.Rect(link["from"])
                    if any(link_rect.intersects(rect) for rect in label_rects):
                        found_targets[label].append(link["uri"])

    for label, expected_url in required_hyperlinks.items():
        targets = found_targets[label]
        if not found_labels[label] or not targets:
            _add_issue(
                result,
                "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
                QASeverity.ERROR,
                "resume",
                f'The required work-sample label "{label}" is not linked in the PDF.',
            )
        elif any(target != expected_url for target in targets):
            _add_issue(
                result,
                "PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH",
                QASeverity.ERROR,
                "resume",
                f'The PDF link for "{label}" has the wrong target.',
            )


def _add_missing_required_pdf_hyperlinks(
    result: ArtifactQAResult,
    document_name: str,
    required_hyperlinks: Mapping[str, str] | None,
) -> None:
    if document_name != "resume" or not required_hyperlinks:
        return
    for label in required_hyperlinks:
        _add_issue(
            result,
            "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            QASeverity.ERROR,
            document_name,
            f'The required work-sample label "{label}" could not be inspected in the PDF.',
        )


def _render_pdf(pdf_path: Path, output_dir: Path, label: str) -> list[Path]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required when QA_VISUAL_ENABLED is true."
        ) from exc

    rendered: list[Path] = []
    safe_label = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")
    with pymupdf.open(pdf_path) as pdf:
        for index, page in enumerate(pdf):
            output_path = output_dir / f"{safe_label}-{index + 1}.png"
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
