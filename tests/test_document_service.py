import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from backend.services.document_service import (
    _ensure_pdf_hyperlinks,
    build_documents,
)
from backend.services.qa_service import draft_to_ai_response
from backend.services.work_sample_links import (
    CASE_STUDIES_LABEL,
    DESIGN_PORTFOLIO_LABEL,
)
from tests.test_qa_service import valid_draft


DESIGN_LINKS = {
    DESIGN_PORTFOLIO_LABEL: "https://drive.example/design-portfolio",
    CASE_STUDIES_LABEL: "https://figma.example/case-studies",
}


def write_visible_labels_pdf(path: Path, labels: tuple[str, ...]) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        for index, label in enumerate(labels):
            page.insert_text((72, 72 + index * 24), label)
        document.save(path)


def linked_targets_for_label(path: Path, label: str) -> list[str]:
    targets: list[str] = []
    with pymupdf.open(path) as document:
        for page in document:
            label_rects = page.search_for(label)
            for link in page.get_links():
                link_rect = pymupdf.Rect(link["from"])
                if any(link_rect.intersects(rect) for rect in label_rects):
                    if link.get("uri"):
                        targets.append(link["uri"])
    return targets


class PDFHyperlinkRepairTests(unittest.TestCase):
    def test_adds_exact_uri_annotations_to_visible_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.pdf"
            write_visible_labels_pdf(path, tuple(DESIGN_LINKS))
            _ensure_pdf_hyperlinks(path, DESIGN_LINKS)
            for label, url in DESIGN_LINKS.items():
                self.assertEqual(linked_targets_for_label(path, label), [url])

    def test_repair_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.pdf"
            write_visible_labels_pdf(path, tuple(DESIGN_LINKS))
            _ensure_pdf_hyperlinks(path, DESIGN_LINKS)
            _ensure_pdf_hyperlinks(path, DESIGN_LINKS)
            for label, url in DESIGN_LINKS.items():
                self.assertEqual(linked_targets_for_label(path, label), [url])

    def test_replaces_wrong_target_on_the_required_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.pdf"
            write_visible_labels_pdf(path, (CASE_STUDIES_LABEL,))
            with pymupdf.open(path) as document:
                page = document[0]
                page.insert_link(
                    {
                        "kind": pymupdf.LINK_URI,
                        "from": page.search_for(CASE_STUDIES_LABEL)[0],
                        "uri": "https://wrong.example/case-studies",
                    }
                )
                document.saveIncr()
            _ensure_pdf_hyperlinks(
                path,
                {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]},
            )
            self.assertEqual(
                linked_targets_for_label(path, CASE_STUDIES_LABEL),
                [DESIGN_LINKS[CASE_STUDIES_LABEL]],
            )

    def test_removes_wrong_target_when_exact_target_also_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.pdf"
            write_visible_labels_pdf(path, (CASE_STUDIES_LABEL,))
            with pymupdf.open(path) as document:
                page = document[0]
                label_rect = page.search_for(CASE_STUDIES_LABEL)[0]
                for url in (
                    DESIGN_LINKS[CASE_STUDIES_LABEL],
                    "https://wrong.example/case-studies",
                ):
                    page.insert_link(
                        {
                            "kind": pymupdf.LINK_URI,
                            "from": label_rect,
                            "uri": url,
                        }
                    )
                document.saveIncr()
            _ensure_pdf_hyperlinks(
                path,
                {CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]},
            )
            self.assertEqual(
                linked_targets_for_label(path, CASE_STUDIES_LABEL),
                [DESIGN_LINKS[CASE_STUDIES_LABEL]],
            )

    def test_does_not_guess_a_rectangle_for_missing_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.pdf"
            write_visible_labels_pdf(path, ("Resume",))
            _ensure_pdf_hyperlinks(path, DESIGN_LINKS)
            with pymupdf.open(path) as document:
                self.assertEqual(document[0].get_links(), [])


class DocumentBuildHyperlinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_documents_repairs_the_converted_resume_pdf(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            "WORK_SAMPLES: [Case Studies and Product Work]"
            "(https://figma.example/case-studies)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            converted_resume = root / "converted-resume.pdf"
            write_visible_labels_pdf(converted_resume, (CASE_STUDIES_LABEL,))
            with patch(
                "backend.services.document_service._to_pdf",
                side_effect=[str(converted_resume), None],
            ):
                result = await build_documents(
                    ai_response=draft_to_ai_response(draft),
                    owner_name="Alex Example",
                    position_slug="ProductDesigner",
                    output_dir=root,
                    required_resume_hyperlinks={
                        CASE_STUDIES_LABEL: DESIGN_LINKS[CASE_STUDIES_LABEL]
                    },
                )
            self.assertEqual(result["resume_pdf"], str(converted_resume))
            self.assertEqual(
                linked_targets_for_label(converted_resume, CASE_STUDIES_LABEL),
                [DESIGN_LINKS[CASE_STUDIES_LABEL]],
            )


if __name__ == "__main__":
    unittest.main()
