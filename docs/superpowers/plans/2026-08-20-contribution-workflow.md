# Contribution Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository-native contribution templates, conventions, testing guidance, and code-owner review setup instructions for Resume Friend.

**Architecture:** GitHub-recognized files under `.github/` will prompt contributors and assign ownership, while `CONTRIBUTING.md` will be the authoritative human-readable workflow. GitHub's `main` branch protection remains a one-time maintainer setting because repository files cannot enable required approvals by themselves.

**Tech Stack:** Markdown, GitHub pull request and commit templates, GitHub CODEOWNERS, Git branch protection.

## Global Constraints

- Pull request titles use `[RF-001] FEATURE - Input editor for markdown files and stricter QA`.
- Branch names use `001-feature-input-editor-for-markdown-files`.
- Commit subjects omit the ticket and use `type: short imperative summary`.
- Supported commit types are `feat`, `fix`, `test`, `docs`, `refactor`, `style`, `perf`, `build`, `ci`, `chore`, and `revert`.
- `@louielynmata` owns the whole repository and the `.github` configuration.
- Protection for `main` requires a pull request, one approving review, and Code Owner review while allowing administrator bypass.
- Do not run live paid-provider tests by default.
- Preserve the existing unrelated change in `frontend/package-lock.json`.

---

## File Map

- `.github/pull_request_template.md`: Prompts every pull request for traceability, change classification, test evidence, and QA risk review.
- `.github/commit_template.md`: Prompts local and GitHub-authored commits to use the agreed Conventional Commit subject format.
- `.github/CODEOWNERS`: Assigns all repository content and GitHub configuration to `@louielynmata`.
- `CONTRIBUTING.md`: Defines setup, naming conventions, review workflow, test commands, document validation, and maintainer-only branch protection steps.

### Task 1: GitHub Contribution Metadata

**Files:**
- Create: `.github/commit_template.md`
- Modify: `.github/pull_request_template.md`
- Modify: `.github/CODEOWNERS`

**Interfaces:**
- Consumes: GitHub's standard pull request template, commit template, and CODEOWNERS file discovery.
- Produces: Contributor prompts and automatic review requests for `@louielynmata`.

- [ ] **Step 1: Populate the pull request template**

Add the required title example followed by Ticket, Summary, Change type, Testing, QA and risk, and Checklist sections. Include checkboxes for source-backed facts, local tests, no unintended paid-provider calls, documentation updates, and code-owner review readiness.

- [ ] **Step 2: Add the commit template**

Use a commented first-line prompt:

```text
# <type>: <short imperative summary>
# Example: docs: add work-sample hyperlink implementation plan
```

List every supported type and include optional body guidance explaining what changed and why.

- [ ] **Step 3: Make code ownership explicit**

Set the default and GitHub configuration owners to:

```text
* @louielynmata
/.github/ @louielynmata
```

- [ ] **Step 4: Validate GitHub metadata**

Run:

```powershell
Get-Content .github\pull_request_template.md
Get-Content .github\commit_template.md
Get-Content .github\CODEOWNERS
git diff --check -- .github
```

Expected: all three files contain the agreed formats, `@louielynmata` owns every path, and `git diff --check` reports no whitespace errors.

- [ ] **Step 5: Commit the metadata**

```powershell
git add -- .github/pull_request_template.md .github/commit_template.md .github/CODEOWNERS
git commit -m "docs: add contribution templates"
```

### Task 2: Contributor and Testing Guide

**Files:**
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: Commands from `AGENTS.md`, `backend/requirements.txt`, and `frontend/package.json`.
- Produces: The authoritative contribution and review workflow for humans and coding agents.

- [ ] **Step 1: Document setup and naming rules**

Explain how to create the Python environment and install backend and frontend dependencies. Add exact PR title, branch name, and commit subject patterns with the approved examples and supported commit type meanings.

- [ ] **Step 2: Document the pull request workflow**

Require a focused branch, small coherent commits, completion of the PR template, preservation of unrelated changes, test evidence, and approval before merging.

- [ ] **Step 3: Document testing commands**

Include the exact backend focused and full-suite commands:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Include the exact frontend commands:

```powershell
Set-Location frontend
npm run lint
npm test
npm run build
```

Explain when focused tests, the full backend suite, frontend checks, and rendered DOCX/PDF inspection are required. State that provider boundaries must be mocked unless a live paid-provider test is explicitly requested.

- [ ] **Step 4: Document `main` protection**

Add maintainer steps for GitHub repository Settings, Branches or Rulesets, targeting `main`, requiring a pull request, one approval, and Code Owner review. Explicitly leave administrator bypass enabled because the sole code owner cannot approve their own pull request.

- [ ] **Step 5: Validate the guide**

Run:

```powershell
rg -n "RF-001|001-feature|feat|test_qa_service|unittest discover|npm run lint|npm test|npm run build|Code Owner|administrator bypass" CONTRIBUTING.md
git diff --check -- CONTRIBUTING.md
```

Expected: every required convention, test command, and protection setting is present with no whitespace errors.

- [ ] **Step 6: Commit the contributor guide**

```powershell
git add -- CONTRIBUTING.md
git commit -m "docs: add contributing and review guidance"
```

### Task 3: Final Repository Verification

**Files:**
- Verify: `.github/pull_request_template.md`
- Verify: `.github/commit_template.md`
- Verify: `.github/CODEOWNERS`
- Verify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: Deliverables from Tasks 1 and 2.
- Produces: Evidence that the implementation matches the approved design and excludes unrelated work.

- [ ] **Step 1: Inspect final status and committed diff**

Run:

```powershell
git status --short
git diff HEAD~2..HEAD --check
git diff HEAD~2..HEAD -- .github CONTRIBUTING.md
```

Expected: the existing `frontend/package-lock.json` modification remains uncommitted and unchanged; the two implementation commits contain only the intended contribution files.

- [ ] **Step 2: Confirm repository file discovery**

Run:

```powershell
rg --files .github
```

Expected: `.github/CODEOWNERS`, `.github/pull_request_template.md`, and `.github/commit_template.md` are present.

- [ ] **Step 3: Report the external maintainer action**

State clearly that files and instructions are complete, but the GitHub approval rule is not active until `@louielynmata` performs the documented one-time repository Settings change.

