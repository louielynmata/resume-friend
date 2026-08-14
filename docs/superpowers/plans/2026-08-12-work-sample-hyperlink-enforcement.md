# Work-Sample Hyperlink Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the current track-specific work-sample rules while guaranteeing that every required label uses its exact applicant-supplied URL and remains clickable in generated DOCX and PDF artifacts.

**Architecture:** Add a small pure domain module that extracts and formats trusted work-sample links, preflight it before any provider call, and pass its typed mapping through deterministic QA, document generation, and artifact inspection. The document builder will repair PDF link annotations when conversion strips them; artifact QA remains the final fail-closed gate for both DOCX relationships and PDF annotations.

**Tech Stack:** Python 3.12, FastAPI, `unittest`, `python-docx`, `docx2pdf`, PyMuPDF, Pydantic.

## Global Constraints

- Design resumes require `Design Portfolio (Reel and PDF)` and `Case Studies and Product Work`.
- Development resumes require `Case Studies and Product Work` only; do not add the Design Portfolio link.
- Preserve each applicant-supplied URL character-for-character. Never invent, infer, canonicalize, shorten, or substitute a URL.
- Required source links must use exact `[Visible label](https://source-url)` Markdown syntax.
- Missing, plain-text, or incorrectly targeted required links are blocking even when general AI QA is disabled.
- When PDF conversion is unavailable, preserve the existing non-blocking `PDF_NOT_AVAILABLE` warning. When a resume PDF exists, every track-required link must be clickable.
- Blocking failures retain `qa_report.json` and `qa_draft.xml` when a draft exists and never reach Notion logging.
- Do not expose applicant URLs in public prompts, committed fixtures, error messages, or final reports; use `example` domains in tests.
- Do not call a live AI provider or Notion during automated tests.
- Keep the backend as the sole owner of link selection, deterministic repair, artifact validation, and Notion gating; no frontend contract changes are required.

---

## File Map

**Create:**

- `backend/services/work_sample_links.py` — exact labels, track selection, trusted Markdown extraction, ambiguity detection, and canonical `WORK_SAMPLES:` formatting.
- `tests/test_work_sample_links.py` — pure contract tests plus example-configuration coverage.
- `tests/test_document_service.py` — deterministic PDF-annotation repair and build wiring tests without Microsoft Word.

**Modify:**

- `backend/routers/generate.py` — source preflight before provider use; carry the trusted link mapping in `_LoadedModelFiles`.
- `backend/services/qa_service.py` — restore and validate the exact track-required semantic header line.
- `backend/services/document_service.py` — accept trusted resume hyperlinks and repair missing/wrong PDF URI annotations after conversion.
- `backend/services/artifact_qa_service.py` — validate label-to-target relationships in DOCX and PDF, not text presence alone.
- `backend/services/qa_pipeline.py` — thread one trusted mapping through repair, validation, building, and artifact QA; enforce work-sample artifact checks even with AI QA disabled.
- `prompts/system_prompt.md` — state that every included work-sample label must retain its Markdown target.
- `prompts/qa_prompt.md` — prohibit returning a required work-sample label as plain text.
- `models_personal_example/instructions_prompt.md` — document the clickable-link requirement while retaining the current track rules.
- `tests/test_generate_router.py` — prove preflight happens before provider use and link failures stop before Notion.
- `tests/test_qa_service.py` — semantic repair and mismatch regression tests.
- `tests/test_document_layout.py` — strengthen the existing DOCX work-sample test to bind each visible label to its exact relationship target.
- `tests/test_artifact_qa_service.py` — DOCX/PDF pass, missing, plain-text, wrong-target, track-scope, and PDF-unavailable cases.
- `tests/test_qa_pipeline.py` — trusted mapping propagation, disabled-QA enforcement, retained evidence, and artifact-stage failure tests.

---

### Task 1: Trusted Work-Sample Contract and Provider Preflight

**Files:**

- Create: `backend/services/work_sample_links.py`
- Create: `tests/test_work_sample_links.py`
- Modify: `backend/routers/generate.py:44-50,331-408,682-701`
- Modify: `tests/test_generate_router.py:1-99`

**Interfaces:**

- Produces: `DESIGN_PORTFOLIO_LABEL: str`
- Produces: `CASE_STUDIES_LABEL: str`
- Produces: `RequiredWorkSampleLinkError(ValueError)` with `labels: tuple[str, ...]`
- Produces: `required_work_sample_links(instructions: str, job_type: str) -> dict[str, str]`
- Produces: `format_work_samples_line(links: Mapping[str, str]) -> str`
- Produces: `_LoadedModelFiles.required_work_sample_links: dict[str, str]`
- Consumed later by: `qa_service`, `document_service`, `artifact_qa_service`, and `qa_pipeline`.

- [ ] **Step 1: Write the pure contract tests**

Create `tests/test_work_sample_links.py` with these complete cases:

```python
import unittest
from pathlib import Path

from backend.services.work_sample_links import (
    CASE_STUDIES_LABEL,
    DESIGN_PORTFOLIO_LABEL,
    RequiredWorkSampleLinkError,
    format_work_samples_line,
    required_work_sample_links,
)


PORTFOLIO_URL = "https://drive.example/design-portfolio?usp=sharing&source=resume"
CASE_STUDIES_URL = "https://figma.example/case-studies?node-id=1-2"
INSTRUCTIONS = f"""DESIGN RESUME HEADER - REQUIRED EXACT VALUES:
WORK_SAMPLES: [{DESIGN_PORTFOLIO_LABEL}]({PORTFOLIO_URL}) | [{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})
END DESIGN RESUME HEADER

DEVELOPMENT RESUME HEADER - REQUIRED EXACT VALUES:
WORK_SAMPLES: [{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})
END DEVELOPMENT RESUME HEADER"""


class WorkSampleLinkTests(unittest.TestCase):
    def test_design_requires_both_exact_source_links_in_display_order(self):
        self.assertEqual(
            required_work_sample_links(INSTRUCTIONS, "design"),
            {
                DESIGN_PORTFOLIO_LABEL: PORTFOLIO_URL,
                CASE_STUDIES_LABEL: CASE_STUDIES_URL,
            },
        )

    def test_development_requires_case_studies_only(self):
        self.assertEqual(
            required_work_sample_links(INSTRUCTIONS, "development"),
            {CASE_STUDIES_LABEL: CASE_STUDIES_URL},
        )

    def test_repeated_identical_case_study_link_is_unambiguous(self):
        repeated = INSTRUCTIONS + (
            f"\n[{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})"
        )
        self.assertEqual(
            required_work_sample_links(repeated, "development"),
            {CASE_STUDIES_LABEL: CASE_STUDIES_URL},
        )

    def test_conflicting_urls_for_one_label_fail_closed(self):
        conflicting = INSTRUCTIONS + (
            f"\n[{CASE_STUDIES_LABEL}](https://other.example/case-studies)"
        )
        with self.assertRaises(RequiredWorkSampleLinkError) as raised:
            required_work_sample_links(conflicting, "development")
        self.assertEqual(raised.exception.labels, (CASE_STUDIES_LABEL,))
        self.assertNotIn(CASE_STUDIES_URL, str(raised.exception))

    def test_plain_text_label_does_not_count_as_a_link(self):
        plain_text = f"WORK_SAMPLES: {CASE_STUDIES_LABEL} | {CASE_STUDIES_URL}"
        with self.assertRaises(RequiredWorkSampleLinkError) as raised:
            required_work_sample_links(plain_text, "development")
        self.assertEqual(raised.exception.labels, (CASE_STUDIES_LABEL,))

    def test_formatter_preserves_exact_labels_and_urls(self):
        self.assertEqual(
            format_work_samples_line(
                {
                    DESIGN_PORTFOLIO_LABEL: PORTFOLIO_URL,
                    CASE_STUDIES_LABEL: CASE_STUDIES_URL,
                }
            ),
            f"WORK_SAMPLES: [{DESIGN_PORTFOLIO_LABEL}]({PORTFOLIO_URL}) | "
            f"[{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})",
        )

    def test_example_instructions_preserve_current_track_rules(self):
        example = Path("models_personal_example/instructions_prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            tuple(required_work_sample_links(example, "design")),
            (DESIGN_PORTFOLIO_LABEL, CASE_STUDIES_LABEL),
        )
        self.assertEqual(
            tuple(required_work_sample_links(example, "development")),
            (CASE_STUDIES_LABEL,),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_work_sample_links -v
```

Expected: import failure because `backend.services.work_sample_links` does not exist.

- [ ] **Step 3: Implement the minimal pure contract**

Create `backend/services/work_sample_links.py`:

```python
from __future__ import annotations

import re
from collections.abc import Mapping


DESIGN_PORTFOLIO_LABEL = "Design Portfolio (Reel and PDF)"
CASE_STUDIES_LABEL = "Case Studies and Product Work"

_REQUIRED_LABELS = {
    "design": (DESIGN_PORTFOLIO_LABEL, CASE_STUDIES_LABEL),
    "development": (CASE_STUDIES_LABEL,),
}


class RequiredWorkSampleLinkError(ValueError):
    def __init__(self, labels: tuple[str, ...]):
        self.labels = labels
        super().__init__(
            "Required work-sample Markdown link is missing or ambiguous for: "
            + ", ".join(labels)
        )


def required_work_sample_links(
    instructions: str,
    job_type: str,
) -> dict[str, str]:
    normalized_job_type = job_type.strip().lower()
    if normalized_job_type not in _REQUIRED_LABELS:
        raise ValueError("job_type must be design or development.")

    links: dict[str, str] = {}
    invalid: list[str] = []
    for label in _REQUIRED_LABELS[normalized_job_type]:
        pattern = re.compile(
            rf"\[{re.escape(label)}\]\((https?://[^)\s]+)\)",
            re.IGNORECASE,
        )
        urls = list(dict.fromkeys(pattern.findall(instructions)))
        if len(urls) != 1:
            invalid.append(label)
            continue
        links[label] = urls[0]

    if invalid:
        raise RequiredWorkSampleLinkError(tuple(invalid))
    return links


def format_work_samples_line(links: Mapping[str, str]) -> str:
    rendered = " | ".join(f"[{label}]({url})" for label, url in links.items())
    return f"WORK_SAMPLES: {rendered}"
```

- [ ] **Step 4: Run the contract tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_work_sample_links -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Write the failing provider-preflight test**

Add imports for `HTTPException`, `AsyncMock`, `_run_generation`, and
`required_work_sample_links` to `tests/test_generate_router.py`. Add this async
test class and helper:

```python
from fastapi import HTTPException
from unittest.mock import AsyncMock

from backend.routers.generate import _run_generation


def write_generation_files(root: Path, instructions: str) -> None:
    (root / "design_resume.md").write_text("Design resume facts", encoding="utf-8")
    (root / "dev_resume.md").write_text("Development resume facts", encoding="utf-8")
    (root / "instructions_prompt.md").write_text(instructions, encoding="utf-8")
    (root / "writing_examples.md").write_text("Writing sample", encoding="utf-8")
    (root / "school_transcript.md").write_text("Transcript facts", encoding="utf-8")


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
```

- [ ] **Step 6: Run the preflight test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_generate_router.GenerateWorkSamplePreflightTests.test_missing_design_portfolio_fails_before_provider_call -v
```

Expected: the provider mock is awaited because `_load_generation_model_files`
does not yet preflight the source links.

- [ ] **Step 7: Wire source preflight into the generation boundary**

In `backend/routers/generate.py`:

1. Import `RequiredWorkSampleLinkError` and `required_work_sample_links`.
2. Add `required_work_sample_links: dict[str, str]` to `_LoadedModelFiles`.
3. Immediately after loading `instructions_prompt.md`, call
   `required_work_sample_links(instructions, req.job_type)`.
4. Convert `RequiredWorkSampleLinkError` into `_http_error` with:
   - HTTP 422
   - stage `load_model_files`
   - code `SOURCE_REQUIRED_WORK_SAMPLE_LINK_MISSING`
   - message `Applicant instructions are missing a required work-sample link.`
   - detail from the exception, which contains labels but no URLs
   - hint `Add the exact labeled Markdown link to models_personal/instructions_prompt.md.`
5. Store the returned mapping on `_LoadedModelFiles`.

Use this exact preflight block:

```python
    try:
        work_sample_links = required_work_sample_links(instructions, req.job_type)
    except RequiredWorkSampleLinkError as exc:
        raise _http_error(
            422,
            stage="load_model_files",
            code="SOURCE_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            message="Applicant instructions are missing a required work-sample link.",
            detail=str(exc),
            hint=(
                "Add the exact labeled Markdown link to "
                "models_personal/instructions_prompt.md."
            ),
        ) from exc
```

- [ ] **Step 8: Run both Task 1 test modules**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_work_sample_links tests.test_generate_router -v
```

Expected: all tests pass and no provider mock is awaited in the source-failure case.

- [ ] **Step 9: Commit Task 1**

```powershell
git add backend/services/work_sample_links.py backend/routers/generate.py tests/test_work_sample_links.py tests/test_generate_router.py
git commit -m "feat: preflight required work-sample links"
```

---

### Task 2: Semantic Restoration, Validation, and Prompt Contract

**Files:**

- Modify: `backend/services/qa_service.py:116-298,301-412,803-885`
- Modify: `tests/test_qa_service.py:1-10,369-422,706-772`
- Modify: `prompts/system_prompt.md:32,47-52`
- Modify: `prompts/qa_prompt.md:5-11`
- Modify: `models_personal_example/instructions_prompt.md:19-28`

**Interfaces:**

- Consumes: `format_work_samples_line(links: Mapping[str, str]) -> str`
- Adds keyword `required_work_sample_links: Mapping[str, str] | None = None`
  to `apply_safe_deterministic_fixes`, `validate_draft`, and
  `_required_resume_header_lines`, preserving all existing parameters.
- Adds the same optional keyword to `_restore_required_resume_header` and
  `_validate_structure` so the trusted mapping reaches both operations.
- Produces blocking code: `RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH`

- [ ] **Step 1: Write semantic RED tests**

Add these constants and tests to `tests/test_qa_service.py`:

```python
from backend.services.work_sample_links import (
    CASE_STUDIES_LABEL,
    DESIGN_PORTFOLIO_LABEL,
    format_work_samples_line,
)


DESIGN_LINKS = {
    DESIGN_PORTFOLIO_LABEL: "https://drive.example/design-portfolio",
    CASE_STUDIES_LABEL: "https://figma.example/case-studies",
}
DEVELOPMENT_LINKS = {
    CASE_STUDIES_LABEL: "https://figma.example/case-studies",
}
SOURCE_WITH_DEVELOPMENT_LINKS = (
    SOURCE_RESUME + "\n" + format_work_samples_line(DEVELOPMENT_LINKS)
)


class WorkSampleSemanticQATests(unittest.TestCase):
    def test_safe_fixes_restore_design_links_without_relying_on_model_output(self):
        draft = valid_draft()
        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_materials=SOURCE_RESUME,
            job_type="design",
            required_work_sample_links=DESIGN_LINKS,
        )
        self.assertIn(format_work_samples_line(DESIGN_LINKS), fixed.resume)
        self.assertIn("work-sample links", " ".join(changes).lower())

    def test_safe_fixes_keep_development_track_case_studies_only(self):
        draft = valid_draft()
        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_materials=SOURCE_RESUME,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )
        self.assertIn(format_work_samples_line(DEVELOPMENT_LINKS), fixed.resume)
        self.assertNotIn(DESIGN_PORTFOLIO_LABEL, fixed.resume)

    def test_validator_rejects_plain_text_required_label(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            f"WORK_SAMPLES: {CASE_STUDIES_LABEL}",
        )
        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )
        self.assertIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )

    def test_validator_rejects_wrong_required_target(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]"
            "(https://wrong.example/case-studies)",
        )
        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )
        self.assertIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )

    def test_validator_accepts_exact_track_required_line(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            + format_work_samples_line(DEVELOPMENT_LINKS),
        )
        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )
        self.assertNotIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )
```

Also strengthen the existing Design and Development header tests to compare the
entire `WORK_SAMPLES:` line, including both expected Design targets and the
Case-Studies-only Development target.

- [ ] **Step 2: Run semantic tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service.WorkSampleSemanticQATests -v
```

Expected: `TypeError` because the new keyword arguments do not exist.

- [ ] **Step 3: Implement deterministic semantic restoration**

In `backend/services/qa_service.py`:

1. Import `Mapping` and `format_work_samples_line`.
2. Add the optional mapping keyword to the five interfaces listed above.
3. Pass the mapping from `apply_safe_deterministic_fixes` into
   `_restore_required_resume_header`, and from there into
   `_required_resume_header_lines`.
4. Pass the mapping from `validate_draft` into `_validate_structure`.
5. In `_required_resume_header_lines`, remove any source `WORK_SAMPLES:` line
   when the trusted mapping is supplied, then append exactly
   `format_work_samples_line(required_work_sample_links)`.
6. Let `_restore_required_resume_header` replace any existing header marker with
   that canonical source-backed line.
7. Record the deterministic change as
   `Restored the track-required work-sample links from applicant instructions.`

Use this replacement logic after collecting common and track-specific header lines:

```python
    if required_work_sample_links:
        required = [
            line
            for line in required
            if _header_marker_name(line) not in {"WORK_SAMPLES", "WORK SAMPLES"}
        ]
        required.append(format_work_samples_line(required_work_sample_links))
```

- [ ] **Step 4: Implement the specific semantic blocker**

In `_validate_structure`, compute the exact expected line when a trusted mapping
is present. If the resume lacks that whole line, add:

```python
        add(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            "structure",
            QASeverity.ERROR,
            "resume",
            "The resume must preserve the required labeled work-sample links exactly.",
        )
```

Exclude that expected line from the generic
`RESUME_REQUIRED_HEADER_MISMATCH` list so one defect produces one actionable
issue code.

- [ ] **Step 5: Tighten prompts and the example source contract**

Make these exact behavioral clarifications without inserting personal URLs:

- `prompts/system_prompt.md`: after the track rule, add `Never output an included work-sample label as plain text; preserve the complete [label](exact URL) pair.`
- `prompts/qa_prompt.md`: add `A required work-sample label without its Markdown target is a blocking defect; restore the complete source-supported pair.`
- `models_personal_example/instructions_prompt.md`: after the current final-link rule, add `Every included work-sample label must keep its complete Markdown URL so the DOCX and PDF remain clickable.`

Do not change the current Design-versus-Development inclusion rules.

- [ ] **Step 6: Run focused semantic and contract tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_work_sample_links tests.test_qa_service -v
```

Expected: all tests pass, including exact Design and Development header assertions.

- [ ] **Step 7: Commit Task 2**

```powershell
git add backend/services/qa_service.py prompts/system_prompt.md prompts/qa_prompt.md models_personal_example/instructions_prompt.md tests/test_qa_service.py tests/test_work_sample_links.py
git commit -m "feat: enforce semantic work-sample links"
```

---

### Task 3: Deterministic DOCX-to-PDF Link Preservation

**Files:**

- Modify: `backend/services/document_service.py:1-61,342-470,1000-1007`
- Create: `tests/test_document_service.py`
- Modify: `tests/test_document_layout.py:431-463`

**Interfaces:**

- Adds keyword `required_resume_hyperlinks: Mapping[str, str] | None = None`
  to the existing `build_documents` interface and preserves its `dict` return.
- Produces: `_ensure_pdf_hyperlinks(pdf_path: Path, required_hyperlinks: Mapping[str, str]) -> None`
- Keeps `_to_pdf(docx_path: Path) -> Optional[str]` unchanged.

- [ ] **Step 1: Write PDF-repair tests**

Create `tests/test_document_service.py`:

```python
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
```

- [ ] **Step 2: Run PDF-repair tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_document_service -v
```

Expected: import failure for `_ensure_pdf_hyperlinks` and a signature failure for
`required_resume_hyperlinks`.

- [ ] **Step 3: Implement deterministic annotation repair**

In `backend/services/document_service.py`:

1. Import `Mapping`.
2. Add the optional trusted mapping to `build_documents`.
3. After resume conversion returns a real path, call
   `_ensure_pdf_hyperlinks(Path(resume_pdf), required_resume_hyperlinks)`.
4. Never apply resume work-sample mappings to the cover letter.

Implement `_ensure_pdf_hyperlinks` with this behavior:

```python
def _ensure_pdf_hyperlinks(
    pdf_path: Path,
    required_hyperlinks: Mapping[str, str],
) -> None:
    if not required_hyperlinks or not pdf_path.exists():
        return
    try:
        import pymupdf

        changed = False
        with pymupdf.open(pdf_path) as document:
            for page in document:
                links = page.get_links()
                for label, expected_url in required_hyperlinks.items():
                    for label_rect in page.search_for(label):
                        overlapping = [
                            link
                            for link in links
                            if pymupdf.Rect(link["from"]).intersects(label_rect)
                        ]
                        exact = [
                            link
                            for link in overlapping
                            if link.get("uri") == expected_url
                        ]
                        if exact:
                            continue
                        for link in overlapping:
                            page.delete_link(link)
                        page.insert_link(
                            {
                                "kind": pymupdf.LINK_URI,
                                "from": label_rect,
                                "uri": expected_url,
                            }
                        )
                        changed = True
            if changed:
                document.saveIncr()
    except Exception:
        return
```

The broad fallback is safe here because artifact QA is the authoritative gate;
the builder must not claim success based on this repair attempt.

- [ ] **Step 4: Strengthen the existing DOCX builder test**

In `tests/test_document_layout.py`, enhance
`test_resume_renders_centered_labeled_work_sample_hyperlinks` to inspect each
`w:hyperlink` node's visible text and `r:id`, then assert this exact mapping:

```python
            rendered_targets = {}
            for hyperlink in document.element.body.iter(qn("w:hyperlink")):
                label = "".join(
                    node.text or "" for node in hyperlink.iter(qn("w:t"))
                )
                relationship_id = hyperlink.get(qn("r:id"))
                rendered_targets[label] = document.part.rels[
                    relationship_id
                ].target_ref

            self.assertEqual(
                rendered_targets["Design Portfolio (Reel and PDF)"],
                portfolio_url,
            )
            self.assertEqual(
                rendered_targets["Case Studies and Product Work"],
                case_studies_url,
            )
```

Add `from docx.oxml.ns import qn` to `tests/test_document_layout.py`.

- [ ] **Step 5: Run document service and layout tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_document_service tests.test_document_layout -v
```

Expected: all tests pass without invoking Microsoft Word.

- [ ] **Step 6: Commit Task 3**

```powershell
git add backend/services/document_service.py tests/test_document_service.py tests/test_document_layout.py
git commit -m "fix: preserve work-sample links in PDFs"
```

---

### Task 4: Final DOCX and PDF Hyperlink Artifact Gate

**Files:**

- Modify: `backend/services/artifact_qa_service.py:1-38,116-262`
- Modify: `tests/test_artifact_qa_service.py:1-91`

**Interfaces:**

- Adds keyword `required_resume_hyperlinks: Mapping[str, str] | None = None`
  to the existing `inspect_artifacts` interface and preserves its
  `ArtifactQAResult` return.
- Produces: `WORK_SAMPLE_ARTIFACT_ISSUE_CODES: frozenset[str]`
- Produces codes:
  - `DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING`
  - `DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH`
  - `PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING`
  - `PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH`

- [ ] **Step 1: Add real linked-artifact test helpers**

In `tests/test_artifact_qa_service.py`, import `_build_resume_docx` and the two
label constants. Add:

```python
DESIGN_LINKS = {
    "Design Portfolio (Reel and PDF)": "https://drive.example/design-portfolio",
    "Case Studies and Product Work": "https://figma.example/case-studies",
}


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
    targets: dict[str, str],
) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 48), "Resume artifact validation text")
        for index, label in enumerate(visible_labels):
            point = (72, 84 + index * 24)
            page.insert_text(point, label)
            rect = page.search_for(label)[0]
            if label in targets:
                page.insert_link(
                    {
                        "kind": pymupdf.LINK_URI,
                        "from": rect,
                        "uri": targets[label],
                    }
                )
        document.save(path)
```

- [ ] **Step 2: Write all artifact-gate RED tests**

Add these tests to `ArtifactQAServiceTests`:

```python
    def inspect_resume_pair(
        self,
        root: Path,
        *,
        docx_links: dict[str, str] | None,
        docx_plain_labels: tuple[str, ...],
        pdf_labels: tuple[str, ...],
        pdf_targets: dict[str, str],
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.inspect_resume_pair(
                root,
                docx_links=None,
                docx_plain_labels=("Case Studies and Product Work",),
                pdf_labels=("Case Studies and Product Work",),
                pdf_targets={
                    "Case Studies and Product Work": DESIGN_LINKS[
                        "Case Studies and Product Work"
                    ]
                },
                required={
                    "Case Studies and Product Work": DESIGN_LINKS[
                        "Case Studies and Product Work"
                    ]
                },
            )
        self.assertIn(
            "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_missing_design_docx_label_is_blocking_for_design_track(self):
        case_only = {
            "Case Studies and Product Work": "https://figma.example/case-studies"
        }
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
        expected = {
            "Case Studies and Product Work": "https://figma.example/case-studies"
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links={
                    "Case Studies and Product Work":
                    "https://wrong.example/case-studies"
                },
                docx_plain_labels=(),
                pdf_labels=tuple(expected),
                pdf_targets=expected,
                required=expected,
            )
        self.assertIn(
            "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH",
            {issue.code for issue in result.blocking_issues},
        )

    def test_visible_pdf_label_without_annotation_is_blocking(self):
        expected = {
            "Case Studies and Product Work": "https://figma.example/case-studies"
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=expected,
                docx_plain_labels=(),
                pdf_labels=tuple(expected),
                pdf_targets={},
                required=expected,
            )
        self.assertIn(
            "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
            {issue.code for issue in result.blocking_issues},
        )

    def test_missing_design_pdf_label_is_blocking_for_design_track(self):
        case_only = {
            "Case Studies and Product Work": "https://figma.example/case-studies"
        }
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
        expected = {
            "Case Studies and Product Work": "https://figma.example/case-studies"
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_resume_pair(
                Path(tmp),
                docx_links=expected,
                docx_plain_labels=(),
                pdf_labels=tuple(expected),
                pdf_targets={
                    "Case Studies and Product Work":
                    "https://wrong.example/case-studies"
                },
                required=expected,
            )
        self.assertIn(
            "PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH",
            {issue.code for issue in result.blocking_issues},
        )

    def test_development_does_not_require_design_portfolio(self):
        development = {
            "Case Studies and Product Work": "https://figma.example/case-studies"
        }
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
```

- [ ] **Step 3: Run artifact tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_artifact_qa_service.ArtifactQAServiceTests -v
```

Expected: signature failure because `required_resume_hyperlinks` is unsupported.

- [ ] **Step 4: Implement exact DOCX relationship inspection**

Add a private collector that reads each `w:hyperlink` node, its complete visible
`w:t` text, and the relationship target from `document.part.rels`. For each
required label:

- no exact visible hyperlink label: add `DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING`;
- exact label present but expected target absent: add `DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH`.

Both are `QASeverity.ERROR`, category `artifact`, document `resume`. Messages
name only the label.

- [ ] **Step 5: Implement label-bound PDF annotation inspection**

When a resume PDF exists, open it with PyMuPDF in addition to the current pypdf
page checks. For each expected label:

1. Find exact visible label rectangles with `page.search_for(label)`.
2. Find URI link rectangles from `page.get_links()` that intersect those label
   rectangles.
3. If no visible label or no intersecting URI annotation exists, add
   `PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING`.
4. If an intersecting URI exists but none equals the exact expected URL, add
   `PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH`.

Do not accept the expected URL elsewhere on the page as proof that the label is
clickable.

Export this exact code set for the disabled-QA pipeline branch:

```python
WORK_SAMPLE_ARTIFACT_ISSUE_CODES = frozenset(
    {
        "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING",
        "DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH",
        "PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING",
        "PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH",
    }
)
```

- [ ] **Step 6: Run all artifact and document tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_artifact_qa_service tests.test_document_service tests.test_document_layout -v
```

Expected: all tests pass; page-count, margin, visual-QA, and PDF-unavailable
behavior remain unchanged.

- [ ] **Step 7: Commit Task 4**

```powershell
git add backend/services/artifact_qa_service.py tests/test_artifact_qa_service.py
git commit -m "feat: validate rendered work-sample hyperlinks"
```

---

### Task 5: Pipeline Propagation, Disabled-QA Safety, and Notion Gate

**Files:**

- Modify: `backend/services/qa_pipeline.py:14-21,43-103,152-192`
- Modify: `backend/routers/generate.py:495-535,682-701`
- Modify: `tests/test_qa_pipeline.py:1-600`
- Modify: `tests/test_generate_router.py:1-140`

**Interfaces:**

- Adds required keyword `required_work_sample_links: Mapping[str, str]` to the
  existing `run_qa_pipeline` interface and preserves its `QAPipelineResult`
  return.
- Passes the same mapping to semantic repair, semantic validation, document building, and artifact inspection.
- Consumes: `WORK_SAMPLE_ARTIFACT_ISSUE_CODES`.

- [ ] **Step 1: Update existing pipeline fixtures to state their link scope**

Add to `tests/test_qa_pipeline.py`:

```python
from backend.services.work_sample_links import CASE_STUDIES_LABEL


CASE_STUDIES_LINKS = {
    CASE_STUDIES_LABEL: "https://figma.example/case-studies"
}
CASE_STUDIES_INSTRUCTIONS = (
    "WORK_SAMPLES: [Case Studies and Product Work]"
    "(https://figma.example/case-studies)"
)
```

For existing tests unrelated to work-sample behavior, pass
`required_work_sample_links={}` explicitly to every `run_qa_pipeline` call.
This keeps each existing test isolated while making the new production boundary
explicit.

- [ ] **Step 2: Write mapping-propagation and disabled-QA RED tests**

Add:

```python
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
```

- [ ] **Step 3: Run pipeline tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_pipeline -v
```

Expected: signature failures and missing mapping propagation; the disabled-QA
test returns status `disabled` instead of raising.

- [ ] **Step 4: Thread the mapping through every pipeline layer**

In `run_qa_pipeline`:

1. Add required keyword `required_work_sample_links: Mapping[str, str]`.
2. Pass it to every initial and post-review call to
   `apply_safe_deterministic_fixes` and `validate_draft`.
3. Pass it to every `build_documents` call as
   `required_resume_hyperlinks=required_work_sample_links`.
4. Pass it to `inspect_artifacts` as
   `required_resume_hyperlinks=required_work_sample_links`.

In `_run_review_fix_build_validate_stages`, pass
`model_files.required_work_sample_links` into `run_qa_pipeline`.

- [ ] **Step 5: Keep the link gate active when AI QA is disabled**

In the `if not settings.qa_enabled` branch:

1. Apply deterministic fixes with the trusted mapping before building.
2. Build with the trusted mapping so PDF repair still runs.
3. Call `inspect_artifacts` with the trusted mapping.
4. Filter blocking issues to codes in `WORK_SAMPLE_ARTIFACT_ISSUE_CODES`.
5. If any remain, call `_finish_or_raise_validation` with stage inferred as
   `artifact_validation`, `iterations=0`, and retained draft/report evidence.
6. If none remain, keep the current `status="disabled"` report and do not make
   unrelated page, margin, or visual checks blocking.

- [ ] **Step 6: Write the Notion non-call regression test**

Add to `tests/test_generate_router.py`:

```python
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
                new=AsyncMock(return_value="<RESUME>x</RESUME><COVER_LETTER>y</COVER_LETTER>"),
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
            ), mock.patch(
                "backend.routers.generate.log_application",
                new=AsyncMock(),
            ) as notion:
                with self.assertRaises(HTTPException) as raised:
                    await _run_generation(request, 0.0)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail["code"], "QA_VALIDATION_FAILED")
        self.assertEqual(raised.exception.detail["stage"], "artifact_validation")
        notion.assert_not_awaited()
```

Import `QAPipelineValidationError` in this test module.

- [ ] **Step 7: Run pipeline and route tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_pipeline tests.test_generate_router -v
```

Expected: all tests pass; link artifact failures retain evidence and stop before Notion.

- [ ] **Step 8: Commit Task 5**

```powershell
git add backend/services/qa_pipeline.py backend/routers/generate.py tests/test_qa_pipeline.py tests/test_generate_router.py
git commit -m "feat: gate generation on clickable work-sample links"
```

---

### Task 6: Full Regression and Delivery Verification

**Files:**

- Verify: all modified backend, prompt, example, and test files
- Verify: `docs/superpowers/specs/2026-08-12-work-sample-hyperlink-enforcement-design.md`

**Interfaces:**

- Consumes all prior task outputs.
- Produces fresh evidence that semantic, DOCX, PDF, route, pipeline, and Notion-gate behavior satisfy the approved spec.

- [ ] **Step 1: Run every focused module independently**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_work_sample_links -v
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service -v
.\.venv\Scripts\python.exe -m unittest tests.test_document_service -v
.\.venv\Scripts\python.exe -m unittest tests.test_document_layout -v
.\.venv\Scripts\python.exe -m unittest tests.test_artifact_qa_service -v
.\.venv\Scripts\python.exe -m unittest tests.test_qa_pipeline -v
.\.venv\Scripts\python.exe -m unittest tests.test_generate_router -v
```

Expected: every command exits 0 with no failures or errors.

- [ ] **Step 2: Run the complete backend suite**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all tests pass. This command must remain mocked at provider and Notion
boundaries and must not make paid network calls.

- [ ] **Step 3: Re-run the real DOCX/PDF relationship regressions after the full suite**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_document_service.DocumentBuildHyperlinkTests tests.test_artifact_qa_service.ArtifactQAServiceTests.test_exact_docx_and_pdf_links_pass tests.test_document_layout.DocumentLayoutTests.test_resume_renders_centered_labeled_work_sample_hyperlinks -v
```

Expected: the real DOCX relationship mapping and PyMuPDF annotation checks pass.

- [ ] **Step 4: Verify source/privacy and track-scope constraints**

Run:

```powershell
rg -n "drive\.example|figma\.example|Design Portfolio \(Reel and PDF\)|Case Studies and Product Work" backend prompts models_personal_example tests docs/superpowers
rg -n "models_personal[/\\]" .gitignore
```

Expected:

- example URLs appear only in tests or public example material;
- no real applicant URL was added to committed backend, prompt, test, or docs files;
- `models_personal/` remains ignored;
- prompt and example text still state Design gets both links and Development gets Case Studies only.

- [ ] **Step 5: Verify formatting and worktree scope**

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors; only the files listed in this plan are changed.
Frontend lint/build is not required because no frontend file or API response type changes.

- [ ] **Step 6: Review acceptance criteria line by line**

Confirm from fresh test output:

- Design semantic drafts require and restore both exact labeled links.
- Development semantic drafts require and restore Case Studies only.
- Source configuration fails before provider use when a track-required link is absent or ambiguous.
- DOCX visible labels map to exact hyperlink relationship targets.
- PDF conversion repair adds or corrects label-bound URI annotations without guessing missing-label coordinates.
- DOCX/PDF plain text, missing links, and wrong targets are blocking artifact issues.
- PDF unavailability remains a warning, but an existing resume PDF cannot pass with missing links.
- Link enforcement remains active when AI QA is disabled.
- Blocking link failures retain QA evidence and do not log to Notion.
- No unsupported URL or private applicant URL appears in committed code or fixtures.

- [ ] **Step 7: Commit any verification-only correction, if one was required**

If verification required a code or test correction, repeat the failing focused
test first, apply the minimal fix, rerun the focused and full suites, then commit
only that correction:

```powershell
git add backend prompts models_personal_example tests
git commit -m "test: complete work-sample hyperlink coverage"
```

If no correction was required, do not create an empty commit.
