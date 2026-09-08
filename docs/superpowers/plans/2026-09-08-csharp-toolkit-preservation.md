# C# Toolkit Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the source development skill `C#` exactly when deterministic QA rebuilds the resume Toolkit.

**Architecture:** Keep development Toolkit restoration source-driven. Correct the shared plain-text normalization boundary so it removes structural Markdown heading prefixes while retaining literal `#` characters inside content.

**Tech Stack:** Python 3.12, `re`, `unittest`, existing `DocumentDraft` and deterministic QA pipeline.

## Global Constraints

- `C#` must remain `C#`; it must never become `C` or `C++`.
- Do not change frontend, provider, document-builder, or Notion behavior.
- Preserve unrelated working-tree changes in `backend/services/qa_service.py` and `tests/test_qa_service.py`.

---

### Task 1: Preserve literal hash characters in source-backed Toolkit skills

**Files:**
- Modify: `tests/test_qa_service.py`
- Modify: `backend/services/qa_service.py:1199-1202`

**Interfaces:**
- Consumes: `apply_safe_deterministic_fixes(draft, owner_name, source_resume, job_type)` and `validate_draft(...)`.
- Produces: `_plain_text(text: str) -> str` behavior that strips a leading Markdown heading marker but preserves a literal `#` in content such as `C#`.

- [ ] **Step 1: Write the failing regression test**

Add this focused test beside the existing development source-skill restoration tests:

```python
def test_safe_fixes_preserve_csharp_source_skill_exactly(self):
    source_resume = """# Alex Example

## Toolkit and Technical Skills

### Languages
- C#
"""
    draft = valid_draft()
    draft.resume = draft.resume.replace(
        "PROFESSIONAL SUMMARY\n",
        "TOOLKIT\nCATEGORY: Languages | C\n\n---\n\nPROFESSIONAL SUMMARY\n",
    )

    fixed, _ = apply_safe_deterministic_fixes(
        draft,
        owner_name="Alex Example",
        source_resume=source_resume,
        job_type="development",
    )

    self.assertIn("CATEGORY: Languages | C#", fixed.resume)
    self.assertNotIn("CATEGORY: Languages | C\n", fixed.resume)
    self.assertNotIn("C++", fixed.resume)
    issues = validate_draft(
        fixed,
        owner_name="Alex Example",
        source_resume=source_resume,
        source_materials=source_resume,
        job_type="development",
    )
    self.assertNotIn(
        "RESUME_SOURCE_SKILLS_MISSING",
        {issue.code for issue in issues},
    )
```

- [ ] **Step 2: Run the new test and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service.QAServiceTests.test_safe_fixes_preserve_csharp_source_skill_exactly -v
```

Expected: `FAIL` because the Toolkit contains `CATEGORY: Languages | C` instead of `CATEGORY: Languages | C#`.

- [ ] **Step 3: Implement the minimal normalization fix**

Change `_plain_text` to remove Markdown heading syntax only at the start of the supplied text, then retain `#` in the inline-formatting removal expression:

```python
def _plain_text(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", text.strip())
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()
```

- [ ] **Step 4: Run focused verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service.QAServiceTests.test_safe_fixes_preserve_csharp_source_skill_exactly -v
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service -v
```

Expected: the new regression test and the complete QA-service module pass.

- [ ] **Step 5: Run the full backend suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all backend tests pass with zero failures and zero errors.

- [ ] **Step 6: Review the final diff**

Run:

```powershell
git diff -- backend/services/qa_service.py tests/test_qa_service.py docs/superpowers/plans/2026-09-08-csharp-toolkit-preservation.md
git status --short
```

Confirm that the production change is limited to Markdown normalization, the regression test covers `C#`, and unrelated working-tree edits remain intact.

- [ ] **Step 7: Commit only the C# preservation changes**

Run:

```powershell
git add -- docs/superpowers/plans/2026-09-08-csharp-toolkit-preservation.md
git add -p -- backend/services/qa_service.py tests/test_qa_service.py
git commit -m "fix: preserve C# in development toolkit"
```

Before committing, inspect the staged diff and exclude any pre-existing hunks that do not belong to this fix.
