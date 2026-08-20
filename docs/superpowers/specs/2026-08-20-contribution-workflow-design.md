# Contribution Workflow Design

## Goal

Give Resume Friend contributors one clear, repository-native workflow for naming branches, titling pull requests, writing commits, recording test evidence, and obtaining code-owner approval before merging to `main`.

## Conventions

- Pull request titles use `[RF-001] FEATURE - Input editor for markdown files and stricter QA`.
- Branch names use `001-feature-input-editor-for-markdown-files`.
- Commit subjects use Conventional Commit prefixes without the ticket, for example `docs: add work-sample hyperlink implementation plan`.
- Supported commit types are `feat`, `fix`, `test`, `docs`, `refactor`, `style`, `perf`, `build`, `ci`, `chore`, and `revert`.

These rules are documented and prompted by repository templates. This change does not add a CI naming-policy workflow, so naming remains a review-time convention rather than an automated merge check.

## Repository Files

### Pull request template

Populate `.github/pull_request_template.md` with sections for the ticket, summary, change type, testing evidence, QA or risk notes, and a contributor checklist. The template will show the required title format and remind authors not to include unsupported applicant facts or live paid-provider tests.

### Commit template

Add `.github/commit_template.md` with a commented subject-line prompt, the supported types, and examples. Contributors can configure local Git to use it with:

```powershell
git config commit.template .github/commit_template.md
```

### Code ownership

Keep `@louielynmata` as the global owner in `.github/CODEOWNERS`. The global rule also owns the `.github` files themselves.

### Contributor guide

Populate `CONTRIBUTING.md` with:

- local setup guidance;
- branch, pull request, and commit naming rules;
- the pull request workflow and review expectations;
- focused and full backend test commands;
- frontend lint, test, and build commands;
- document-layout and PDF validation expectations;
- the rule against live paid-provider tests by default; and
- maintainer instructions for protecting `main`.

## GitHub Protection

The repository files identify and request the code owner, but GitHub settings enforce approval. The maintainer instructions will configure a protection rule for `main` that:

1. requires a pull request before merging;
2. requires one approving review;
3. requires review from Code Owners; and
4. leaves administrator bypass enabled.

Administrator bypass is necessary because GitHub does not permit pull request authors to approve their own changes and `@louielynmata` is currently the sole code owner. Collaborator-authored pull requests still require that code-owner approval.

## Validation

Validation will confirm that the expected files exist, the CODEOWNERS rule targets the whole repository, documented commands match the current backend and frontend configuration, and the final diff contains only the intended documentation and template changes. Application tests are not required for this documentation-only change, but their exact commands will be documented for future contributors.

