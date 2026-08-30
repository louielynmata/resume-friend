# Visible Work-Sample URLs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both required work-sample destinations visible and clickable in resume DOCX files so Word's Print as PDF output retains readable URLs even when hyperlink metadata is lost.

**Architecture:** Keep the semantic `WORK_SAMPLES:` Markdown contract unchanged. Classify that marker separately in the deterministic document builder, then render each parsed label/URL pair as its own centered paragraph using the trusted `required_hyperlinks` mapping for both the label target and visible URL text.

**Tech Stack:** Python 3.12, python-docx, unittest, existing Resume Friend QA and document services.

## Global Constraints

- Preserve exact applicant-supplied URLs; never infer, shorten, rewrite, or substitute them.
- Design renders Design Portfolio and Case Studies; Development renders Case Studies only.
- Keep the existing semantic Markdown-link contract and fail-closed QA/Notion behavior.
- Preserve unrelated uncommitted changes in `backend/services/qa_service.py`, `prompts/qa_prompt.md`, `prompts/system_prompt.md`, and `tests/test_qa_service.py`.
- Do not invoke a live paid AI provider.

---

### Task 1: Render exact visible work-sample URLs in DOCX

**Files:**
- Modify: `tests/test_document_layout.py:432`
- Modify: `backend/services/document_service.py:278-292,423-479,569-580`

**Interfaces:**
- Consumes: `iter_markdown_links(text: str) -> Iterator[MarkdownLink]` and `required_hyperlinks: Mapping[str, str] | None`.
- Produces: `_add_work_sample_lines(doc, text: str, size: int | float, required_hyperlinks: Mapping[str, str] | None) -> None` and a `work_samples` resume-line classification.

- [ ] **Step 1: Write the failing Design regression test**

Update `test_resume_renders_centered_labeled_work_sample_hyperlinks` to use literal URLs containing query strings and assert two distinct centered paragraphs with these exact texts:

```python
"Design Portfolio (Reel and PDF): https://drive.example/design-portfolio?usp=sharing&source=resume"
"Case Studies and Product Work: https://figma.example/case-studies?node-id=1-2"
```

Inspect the real DOCX XML and assert that all four visible hyperlink texts—the two labels and two full URLs—target their corresponding exact source URL.

- [ ] **Step 2: Add the failing Development boundary test**

Build a Development-style fixture containing only the Case Studies Markdown link and assert the output has one centered visible-URL paragraph and no Design Portfolio paragraph.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_document_layout.DocumentLayoutTests.test_resume_renders_centered_labeled_work_sample_hyperlinks tests.test_document_layout.DocumentLayoutTests.test_development_resume_renders_only_visible_case_studies_url -v
```

Expected: both tests fail because the current builder emits one label-only paragraph.

- [ ] **Step 4: Implement the minimal builder behavior**

In `_resume_line_kind`, classify `WORK_SAMPLES:` as `work_samples` before the broader contact-link marker. Add `_add_work_sample_lines` that:

```python
for link in iter_markdown_links(text):
    target = (required_hyperlinks or {}).get(link.label, link.url)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_hyperlink(paragraph, link.label, target, size)
    separator = paragraph.add_run(": ")
    _set_run_font(separator, size=size)
    _add_hyperlink(paragraph, target, target, size)
    _set_para_spacing(paragraph, before=0, after=1)
```

If no valid Markdown links are parsed, render the original text as one contact line so malformed evidence is retained for the existing QA checks rather than silently dropped. Route the new `work_samples` kind through this helper in `_build_resume_docx`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the two focused tests from Step 3 and expect both to pass.

- [ ] **Step 6: Run adjacent document and link tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_document_layout tests.test_document_service tests.test_work_sample_links tests.test_artifact_qa_service -v
```

Expected: all tests pass without errors or warnings from application code.

### Task 2: Clarify the source-preservation rule

**Files:**
- Modify: `prompts/system_prompt.md:32-34,53`
- Modify: `prompts/qa_prompt.md:10`

**Interfaces:**
- Consumes: the existing `[Visible label](exact URL)` semantic contract.
- Produces: provider and independent-review instructions that preserve the exact target the deterministic builder will display.

- [ ] **Step 1: Update generation guidance without changing semantic syntax**

Clarify that every complete Markdown destination is preserved character-for-character because the document builder renders the target as visible URL text beside its label. Do not instruct the provider to duplicate the URL in the semantic draft.

- [ ] **Step 2: Update independent-QA guidance consistently**

Add the same constraint to rule 5 in `prompts/qa_prompt.md`: the reviewer must restore the complete source-supported Markdown pair because its exact target becomes visible in the final document.

- [ ] **Step 3: Review the overlapping diff**

Run:

```powershell
git diff -- prompts/system_prompt.md prompts/qa_prompt.md
```

Verify the previously existing skill-category and Other Work Experience changes remain intact and that only the work-sample sentences were extended for this task.

### Task 3: Validate behavior and rendered layout

**Files:**
- Verify: `backend/services/document_service.py`
- Verify: `tests/test_document_layout.py`
- Verify: `prompts/system_prompt.md`
- Verify: `prompts/qa_prompt.md`

**Interfaces:**
- Consumes: the completed builder and prompt behavior from Tasks 1-2.
- Produces: test and visual evidence for the final handoff.

- [ ] **Step 1: Run the focused QA and pipeline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service tests.test_qa_pipeline tests.test_generate_router -v
```

Expected: all tests pass while preserving fail-closed link validation and Notion gating.

- [ ] **Step 2: Run the complete backend suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all backend tests pass.

- [ ] **Step 3: Generate and inspect a non-personal DOCX fixture**

Use `_build_resume_docx` with the exact Design fixture from Task 1, save it under a temporary directory, render it using the repository's available document/PDF tooling, and visually inspect the header. Confirm two centered entries, complete URLs, natural wrapping, readable spacing, and no truncation. If local Word/PDF conversion is unavailable, inspect the DOCX text/XML and report that PDF visual validation was skipped.

- [ ] **Step 4: Check the final diff and worktree**

Run:

```powershell
git diff --check
git diff -- backend/services/document_service.py tests/test_document_layout.py prompts/system_prompt.md prompts/qa_prompt.md
git status --short
```

Confirm no unrelated file was changed or overwritten. Do not commit the pre-existing user-owned changes unless the user requests a combined commit.
