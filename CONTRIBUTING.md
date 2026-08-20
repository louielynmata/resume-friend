# Contributing to Resume Friend

Thank you for helping improve Resume Friend. Keep each change focused,
truthful, testable, and easy to review. The backend owns validation and
document-generation rules; the frontend owns input collection and clear
status and error presentation.

## Before you start

Use Python 3.12 for the backend and a Node.js version supported by the current
`frontend/package.json` and lockfile. From the repository root, create the
backend environment and install dependencies:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install frontend dependencies from the lockfile:

```powershell
Set-Location frontend
npm ci
Set-Location ..
```

If Windows PowerShell blocks `npm.ps1` because script execution is disabled,
run the same commands with `npm.cmd`, for example `npm.cmd test`.

Do not place applicant-specific facts in committed prompts or fixtures. Keep
private source material under `models_personal/` and never commit tokens, API
keys, generated application packages, or other secrets.

## Naming conventions

### Branches

Use the zero-padded issue number, lowercase change type, and a short kebab-case
description:

```text
001-feature-input-editor-for-markdown-files
```

Pattern:

```text
<three-digit-number>-<type>-<short-kebab-case-description>
```

Use a type that describes the primary change: `feature`, `fix`, `test`,
`docs`, `refactor`, `style`, `performance`, `build`, `ci`, `chore`, or
`revert`.

### Pull request titles

Put the Resume Friend ticket first, use an uppercase change type, then add a
concise description:

```text
[RF-001] FEATURE - Input editor for markdown files and stricter QA
```

Pattern:

```text
[RF-<three-digit-number>] <TYPE> - <Concise description>
```

The ticket digits in the PR title and branch name must match. Complete every
applicable section of the pull request template and explain any check that was
not run.

### Commit messages

Commit subjects follow Conventional Commit style and do not include the RF
ticket:

```text
docs: add work-sample hyperlink implementation plan
```

Use an imperative, lowercase summary after the colon. Keep commits small and
coherent. Add a body when the reason or trade-off is not obvious from the
subject.

| Type | Use it for |
| --- | --- |
| `feat` | User-visible behavior |
| `fix` | Defect corrections |
| `test` | Tests and test fixtures |
| `docs` | Documentation-only changes |
| `refactor` | Internal restructuring without behavior changes |
| `style` | Formatting-only changes |
| `perf` | Performance improvements |
| `build` | Dependencies and build tooling |
| `ci` | Continuous-integration configuration |
| `chore` | Repository maintenance |
| `revert` | Reverting an earlier commit |

To use the repository commit prompt locally, run:

```powershell
git config commit.template .github/commit_template.md
```

## Pull request workflow

1. Start from the latest `main` and create a branch using the required format.
2. Inspect `git status --short` and preserve unrelated work already present in
   the checkout.
3. Make the smallest coherent change. Do not duplicate backend business rules
   in React.
4. Add a focused regression test before fixing application behavior. Mock AI
   provider and Notion boundaries in automated tests.
5. Run the checks appropriate to every layer you changed and record their
   commands and results in the pull request.
6. Complete the PR template, use the required title, and request review.
7. Resolve review conversations and obtain the required code-owner approval
   before merging.

Do not run live provider or external-integration tests by default. A live
Claude, OpenAI, Ollama, or Notion test must be explicitly requested. Minimize
personal data and side effects, and treat remote paid-provider calls as a cost
that must be justified.

## Testing

Run commands from the repository root unless a command changes directories.

### Backend focused tests

During development, run the smallest module that covers the changed behavior.
For example:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_qa_service -v
```

Replace `tests.test_qa_service` with the relevant test module. A regression
test should fail for the original defect and pass after the implementation.

### Full backend suite

Before requesting review for backend code, shared contracts, QA rules, document
generation, or configuration, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Report the number of tests and failures. Do not describe the suite as passing
when failures predate the change; identify baseline failures separately.

### Frontend checks

For frontend code, API types, routes, UI behavior, or frontend dependencies,
run all three checks:

```powershell
Set-Location frontend
npm run lint
npm test
npm run build
Set-Location ..
```

On Windows systems that block `npm.ps1`, use:

```powershell
Set-Location frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
Set-Location ..
```

When backend response schemas or generation-stage identifiers change, run both
the backend suite and all frontend checks.

### Document and QA changes

For changes to DOCX/PDF generation, artifact QA, layout, typography, spacing,
pagination, or hyperlinks:

1. Run the focused document or artifact test module.
2. Run the full backend suite.
3. Generate representative DOCX and PDF artifacts without a live paid-provider
   call.
4. Inspect page counts, headings, bullets, role/date lines, margins, spacing,
   hyperlinks, and cover-letter sign-off.
5. Compare rendered output with the PDFs under `ref/` when visual fidelity is
   affected.

State plainly when PDF conversion or visual validation was skipped because
Microsoft Word, `docx2pdf`, PyMuPDF, or another local dependency was
unavailable.

### Documentation-only changes

Application tests are normally unnecessary when a change affects only
Markdown or GitHub templates and does not alter commands or contracts. Still
inspect the rendered Markdown and run:

```powershell
git diff --check
```

If documentation changes a command, configuration value, schema, or workflow,
run the relevant check to prove the instruction is accurate.

## Code-owner review and `main` protection

`.github/CODEOWNERS` assigns the whole repository to `@louielynmata`. That file
automatically requests review, but it does not enforce approval by itself. A
repository administrator must configure GitHub once:

1. Open the repository on GitHub and go to **Settings**.
2. Under **Code and automation**, open **Branches**.
3. Add or edit a branch protection rule whose branch name pattern is `main`.
4. Enable **Require a pull request before merging**.
5. Enable required approvals and set **Required number of approvals before
   merging** to `1`.
6. Enable **Require review from Code Owners**.
7. Leave **Do not allow bypassing the above settings** disabled so repository
   administrators can bypass the rule when necessary.
8. Save the rule.

Administrator bypass is intentional while `@louielynmata` is the sole code
owner because GitHub does not allow a pull request author to approve their own
pull request. Pull requests authored by other contributors still require one
approval from the code owner. If another maintainer becomes an eligible code
owner, reconsider whether administrator bypass should remain enabled.

GitHub also supports repository rulesets as an alternative to classic branch
protection. Whichever mechanism is used, the effective rule for `main` must
require a pull request, one approval, and Code Owner review.

See GitHub's documentation on
[managing branch protection rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)
and [Code Owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).
