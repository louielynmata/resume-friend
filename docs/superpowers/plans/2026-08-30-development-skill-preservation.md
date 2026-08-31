# Development Skill Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee that every skill and tool in a development source resume appears exactly once in the generated resume.

**Architecture:** Extend deterministic QA to parse the source `Toolkit and Technical Skills` categories, restore a canonical `TOOLKIT` block for development resumes, and validate missing or duplicated category values. Keep design behavior unchanged and align both AI prompts with the backend-owned invariant.

**Tech Stack:** Python 3.12, Pydantic, `unittest`, Markdown prompt templates

## Global Constraints

- Apply the preservation rule only when `job_type="development"`.
- Preserve every source category label and value exactly, in source order.
- Represent each normalized source value exactly once across generated `CATEGORY:` lines.
- Never omit source skills for relevance or the two-page layout target.
- Keep page-limit QA fail-closed and keep the existing design category limit.
- Do not infer or add skills absent from the source resume.
- Preserve all unrelated working-tree changes, including overlapping edits in QA and prompt files.

---

### Task 1: Canonical development Toolkit restoration

**Files:**
- Modify: `tests/test_qa_service.py`
- Modify: `backend/services/qa_service.py`

**Interfaces:**
- Consumes: `apply_safe_deterministic_fixes(..., source_resume: str, job_type: str)`
- Produces: `_extract_source_skill_categories(source_resume: str) -> list[tuple[str, list[str]]]`
- Produces: `_restore_development_source_skills(text: str, source_resume: str) -> tuple[str, bool]`

- [ ] **Step 1: Write failing restoration and idempotence tests**

Add a source fixture with more than four categories, including distinct `React` and `React Native` values. Add a development draft that omits values and duplicates one value outside Toolkit. Assert that `apply_safe_deterministic_fixes` emits every source category and value in source order, removes the duplicate, preserves both similar values, and reports a source-skill restoration change.

```python
def test_safe_fixes_restore_every_development_source_skill_exactly_once(self):
    fixed, changes = apply_safe_deterministic_fixes(
        draft_with_incomplete_skill_categories(),
        owner_name="Alex Example",
        source_resume=DEVELOPMENT_SOURCE_WITH_SKILLS,
        job_type="development",
    )

    toolkit = fixed.resume.split("\nTOOLKIT\n", 1)[1].split("\n---\n", 1)[0]
    self.assertIn("CATEGORY: Languages | Python, TypeScript", toolkit)
    self.assertIn("CATEGORY: Frameworks | React, React Native", toolkit)
    self.assertIn("CATEGORY: Delivery | Docker, CI/CD", toolkit)
    self.assertEqual(fixed.resume.count("Python"), 1)
    self.assertEqual(fixed.resume.count("React,"), 1)
    self.assertEqual(fixed.resume.count("React Native"), 1)
    self.assertIn("source skill", " ".join(changes).lower())
```

Add a second application assertion:

```python
fixed_again, second_changes = apply_safe_deterministic_fixes(
    fixed,
    owner_name="Alex Example",
    source_resume=DEVELOPMENT_SOURCE_WITH_SKILLS,
    job_type="development",
)
self.assertEqual(fixed_again, fixed)
self.assertNotIn("source skill", " ".join(second_changes).lower())
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `./.venv/Scripts/python.exe -m unittest tests.test_qa_service.QAServiceTests.test_safe_fixes_restore_every_development_source_skill_exactly_once -v`

Expected: FAIL because the current deterministic limiter removes categories and no general source-skill restorer exists.

- [ ] **Step 3: Implement source extraction**

Add a parser that activates only inside a normalized `## Toolkit and Technical Skills` heading, captures `###` category headings and their bullet values, stops at the next heading of level two or higher, and drops later normalized duplicates while retaining the first exact source spelling.

```python
def _extract_source_skill_categories(
    source_resume: str,
) -> list[tuple[str, list[str]]]:
    categories: list[tuple[str, list[str]]] = []
    seen_values: set[str] = set()
    active_section = False
    current_values: list[str] | None = None

    for raw_line in source_resume.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw_line.strip())
        if heading:
            level = len(heading.group(1))
            label = _plain_text(heading.group(2))
            if level == 2:
                active_section = (
                    _normalized_match_text(label)
                    == "toolkit and technical skills"
                )
                current_values = None
            elif active_section and level == 3:
                current_values = []
                categories.append((label, current_values))
            continue

        if not active_section or current_values is None:
            continue
        bullet = re.match(
            r"^\s*(?:[-+*]|\u25cf|\u2022)\s+(.+?)\s*$",
            raw_line,
        )
        if bullet is None:
            continue
        value = _plain_text(bullet.group(1)).rstrip(".").strip()
        key = _normalized_match_text(value)
        if value and key not in seen_values:
            current_values.append(value)
            seen_values.add(key)

    categories = [
        (label, values) for label, values in categories if values
    ]
    return categories
```

- [ ] **Step 4: Implement canonical restoration**

Build exact source-backed lines with `CATEGORY: {label} | {values}`. Remove normalized source values from every existing compact category section, discard empty category rows, replace an existing Toolkit block or insert one before the first divider preceding the summary/experience content, and call this function after category normalization for development resumes.

```python
if job_type.strip().lower() == "development" and source_resume.strip():
    fixed.resume, source_skills_changed = _restore_development_source_skills(
        fixed.resume,
        source_resume,
    )
    if source_skills_changed:
        changes.append(
            "Restored every source skill and tool exactly once for the development resume."
        )
```

Pass `job_type` into the category limiter decision and skip `_limit_non_toolkit_categories` for development resumes.

- [ ] **Step 5: Run restoration tests and verify GREEN**

Run: `./.venv/Scripts/python.exe -m unittest tests.test_qa_service.QAServiceTests.test_safe_fixes_restore_every_development_source_skill_exactly_once -v`

Expected: PASS.

---

### Task 2: Blocking completeness and duplication validation

**Files:**
- Modify: `tests/test_qa_service.py`
- Modify: `backend/services/qa_service.py`

**Interfaces:**
- Consumes: `_extract_source_skill_categories(source_resume: str)` from Task 1
- Produces: `_resume_category_value_occurrences(text: str) -> dict[str, int]`
- Extends: `validate_draft(..., job_type: str)` with development-only issue codes

- [ ] **Step 1: Write failing validation tests**

Add one test that calls `validate_draft` on an unrepaired development draft missing a source value and another with the same exact category value twice.

```python
self.assertIn(
    "RESUME_SOURCE_SKILLS_MISSING",
    {issue.code for issue in missing_issues},
)
self.assertIn(
    "RESUME_SOURCE_SKILLS_DUPLICATED",
    {issue.code for issue in duplicated_issues},
)
```

Also validate a complete draft containing both `React` and `React Native` and assert that neither issue code is emitted.

- [ ] **Step 2: Run the validation tests and verify RED**

Run: `./.venv/Scripts/python.exe -m unittest tests.test_qa_service.QAServiceTests.test_validator_blocks_missing_development_source_skills tests.test_qa_service.QAServiceTests.test_validator_blocks_duplicated_development_source_skills -v`

Expected: FAIL because neither issue code exists.

- [ ] **Step 3: Implement exact category-value counting**

Parse only valid `CATEGORY:` rows and split their right-hand side on commas. Normalize each whole value with `_normalized_match_text`; do not search resume substrings.

```python
def _resume_category_value_occurrences(text: str) -> dict[str, int]:
    occurrences: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"(?i)^CATEGORY\s*:\s*.+?\s*\|\s*(.+)$", line.strip())
        if match is None:
            continue
        for value in match.group(1).split(","):
            key = _normalized_match_text(value)
            if key:
                occurrences[key] = occurrences.get(key, 0) + 1
    return occurrences
```

- [ ] **Step 4: Add development-only blocking findings**

Thread `job_type` into `_validate_truthfulness`. For development resumes, flatten the extracted source categories, compare normalized values with the occurrence map, and emit `QASeverity.ERROR` findings for counts of zero or greater than one. List exact source display values in each message.

- [ ] **Step 5: Run validation tests and verify GREEN**

Run: `./.venv/Scripts/python.exe -m unittest tests.test_qa_service.QAServiceTests.test_validator_blocks_missing_development_source_skills tests.test_qa_service.QAServiceTests.test_validator_blocks_duplicated_development_source_skills -v`

Expected: PASS.

---

### Task 3: Preserve design behavior and align model instructions

**Files:**
- Modify: `tests/test_qa_service.py`
- Modify: `prompts/system_prompt.md`
- Modify: `prompts/qa_prompt.md`

**Interfaces:**
- Consumes: existing `_limit_non_toolkit_categories(text: str, maximum: int)`
- Produces: track-specific prompt rules consistent with deterministic QA

- [ ] **Step 1: Add a design regression assertion**

Keep the existing design category-limit test and add an explicit development counterpart asserting that a development draft with more than four source categories is not truncated. Run the design test before prompt edits to confirm the existing design behavior stays green.

Run: `./.venv/Scripts/python.exe -m unittest tests.test_qa_service.QAServiceTests.test_safe_fixes_limit_non_toolkit_categories_across_skill_sections -v`

Expected: PASS.

- [ ] **Step 2: Update the generation prompt**

Change the compact-category limit to design-only. Add a development rule requiring every `Toolkit and Technical Skills` category and item exactly once, in source order, with no relevance- or page-count-based removal.

- [ ] **Step 3: Update the QA prompt**

Replace the global two-to-four rule with matching track-specific language. Tell the reviewer to resolve `RESUME_SOURCE_SKILLS_MISSING` and `RESUME_SOURCE_SKILLS_DUPLICATED` without inventing replacements.

- [ ] **Step 4: Run all QA service tests**

Run: `./.venv/Scripts/python.exe -m unittest tests.test_qa_service -v`

Expected: PASS with no warnings or errors.

---

### Task 4: Full verification and handoff

**Files:**
- Verify: `backend/services/qa_service.py`
- Verify: `prompts/system_prompt.md`
- Verify: `prompts/qa_prompt.md`
- Verify: `tests/test_qa_service.py`

**Interfaces:**
- Consumes: completed Tasks 1-3
- Produces: verified backend behavior and a clean scoped diff

- [ ] **Step 1: Run the complete backend suite**

Run: `./.venv/Scripts/python.exe -m unittest discover -s tests -v`

Expected: PASS. No live paid-provider calls are made.

- [ ] **Step 2: Check formatting and scope**

Run: `git diff --check`

Run: `git status --short`

Inspect the scoped diff and confirm that existing unrelated changes remain intact.

- [ ] **Step 3: Report completion**

Report the restored invariant, each changed file, focused and full-suite results, skipped checks, and the remaining risk that complete skills may cause the existing two-page QA check to fail rather than silently trimming applicant knowledge.
