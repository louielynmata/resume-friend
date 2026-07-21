from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..qa_models import (
    DocumentDraft,
    QAIssue,
    QARunReport,
    QASeverity,
)
from .artifact_qa_service import inspect_artifacts, inspect_artifacts_visually
from .document_service import build_documents
from .qa_service import (
    apply_safe_deterministic_fixes,
    draft_to_ai_response,
    review_and_fix_draft,
    validate_draft,
)


@dataclass
class QAPipelineResult:
    draft: DocumentDraft
    docs: dict
    report: QARunReport
    report_path: Path


class QAPipelineReviewError(RuntimeError):
    pass


class QAPipelineValidationError(RuntimeError):
    def __init__(self, message: str, report_path: Path, stage: str):
        super().__init__(message)
        self.report_path = report_path
        self.stage = stage


async def run_qa_pipeline(
    *,
    selected_provider: str,
    draft: DocumentDraft,
    owner_name: str,
    source_resume: str,
    instructions: str,
    writing_examples: str,
    transcript: str,
    job_description: str,
    company_context: str,
    position: str,
    company: str,
    position_slug: str,
    output_dir: Path,
) -> QAPipelineResult:
    qa_provider = _resolve_provider(selected_provider)
    source_materials = "\n\n".join(
        (source_resume, instructions, writing_examples, transcript)
    )

    if not settings.qa_enabled:
        docs = await build_documents(
            ai_response=draft_to_ai_response(draft),
            owner_name=owner_name,
            position_slug=position_slug,
            output_dir=output_dir,
        )
        report = QARunReport(status="disabled", provider=qa_provider)
        report_path = _write_report(output_dir, report)
        return QAPipelineResult(draft, docs, report, report_path)

    # One independent review is mandatory; QA_MAX_REPAIRS controls bounded retries.
    max_reviews = 1 + max(0, settings.qa_max_repairs)
    iterations = 0
    changes_made: list[str] = []
    agent_findings: list[str] = []
    docs: dict | None = None
    final_issues: list[QAIssue] = []

    draft, deterministic_changes = apply_safe_deterministic_fixes(
        draft,
        owner_name=owner_name,
    )
    _extend_unique(changes_made, deterministic_changes)

    pending_issues = validate_draft(
        draft,
        owner_name=owner_name,
        source_resume=source_resume,
        source_materials=source_materials,
    )

    while True:
        if iterations == 0 or _blocking(pending_issues):
            if iterations >= max_reviews:
                if settings.qa_fail_open and docs is None:
                    docs = await build_documents(
                        ai_response=draft_to_ai_response(draft),
                        owner_name=owner_name,
                        position_slug=position_slug,
                        output_dir=output_dir,
                    )
                return _finish_or_raise_validation(
                    output_dir=output_dir,
                    provider=qa_provider,
                    iterations=iterations,
                    issues=pending_issues,
                    findings=agent_findings,
                    changes=changes_made,
                    draft=draft,
                    docs=docs,
                )
            try:
                correction = await review_and_fix_draft(
                    provider=qa_provider,
                    draft=draft,
                    issues=pending_issues,
                    source_resume=source_resume,
                    instructions=instructions,
                    writing_examples=writing_examples,
                    transcript=transcript,
                    job_description=job_description,
                    company_context=company_context,
                    position=position,
                    company=company,
                    owner_name=owner_name,
                )
            except Exception as exc:
                raise QAPipelineReviewError(str(exc)) from exc

            previous_analysis = draft.analysis
            draft = correction.as_draft()
            if not draft.analysis:
                draft.analysis = previous_analysis
            # Any documents from an earlier iteration no longer represent this draft.
            docs = None
            draft, deterministic_changes = apply_safe_deterministic_fixes(
                draft,
                owner_name=owner_name,
                previous_analysis=previous_analysis,
            )
            iterations += 1
            _extend_unique(changes_made, correction.changes_made)
            _extend_unique(changes_made, deterministic_changes)
            _extend_unique(agent_findings, correction.issues_found)

        pending_issues = validate_draft(
            draft,
            owner_name=owner_name,
            source_resume=source_resume,
            source_materials=source_materials,
        )
        if _blocking(pending_issues):
            continue

        docs = await build_documents(
            ai_response=draft_to_ai_response(draft),
            owner_name=owner_name,
            position_slug=position_slug,
            output_dir=output_dir,
        )
        artifact_result = inspect_artifacts(docs)
        final_issues = [*pending_issues, *artifact_result.issues]

        if settings.qa_visual_enabled and not _blocking(artifact_result.issues):
            try:
                visual_result = await inspect_artifacts_visually(
                    provider=qa_provider,
                    docs=docs,
                )
            except Exception as exc:
                if settings.qa_fail_open:
                    final_issues.append(
                        QAIssue(
                            code="VISUAL_QA_UNAVAILABLE",
                            category="artifact",
                            severity=QASeverity.WARNING,
                            document="package",
                            message=f"Visual QA could not run: {exc}",
                        )
                    )
                else:
                    raise QAPipelineReviewError(
                        f"Visual QA could not run: {exc}"
                    ) from exc
            else:
                if not visual_result.passed:
                    final_issues.extend(
                        QAIssue(
                            code="VISUAL_QA_FAILED",
                            category="formatting",
                            severity=QASeverity.ERROR,
                            document="package",
                            message=issue,
                        )
                        for issue in visual_result.issues
                    )

        if not _blocking(final_issues):
            status = "passed_with_warnings" if final_issues else "passed"
            report = QARunReport(
                status=status,
                provider=qa_provider,
                iterations=iterations,
                issues=final_issues,
                agent_findings=agent_findings,
                changes_made=changes_made,
                resume_pages=artifact_result.resume_pages,
                cover_letter_pages=artifact_result.cover_letter_pages,
            )
            report_path = _write_report(output_dir, report)
            return QAPipelineResult(draft, docs, report, report_path)

        pending_issues = _blocking(final_issues)
        if iterations >= max_reviews:
            return _finish_or_raise_validation(
                output_dir=output_dir,
                provider=qa_provider,
                iterations=iterations,
                issues=final_issues,
                findings=agent_findings,
                changes=changes_made,
                resume_pages=artifact_result.resume_pages,
                cover_letter_pages=artifact_result.cover_letter_pages,
                draft=draft,
                docs=docs,
            )


def _resolve_provider(selected_provider: str) -> str:
    provider = settings.qa_provider.strip().lower()
    if provider == "same":
        return selected_provider
    if provider not in {"claude", "openai", "ollama"}:
        raise ValueError("QA_PROVIDER must be same, claude, openai, or ollama.")
    return provider


def _blocking(issues: list[QAIssue]) -> list[QAIssue]:
    return [issue for issue in issues if issue.severity == QASeverity.ERROR]


def _finish_or_raise_validation(
    *,
    output_dir: Path,
    provider: str,
    iterations: int,
    issues: list[QAIssue],
    findings: list[str],
    changes: list[str],
    resume_pages: int | None = None,
    cover_letter_pages: int | None = None,
    draft: DocumentDraft,
    docs: dict | None,
) -> QAPipelineResult:
    draft_path = _write_failed_draft(output_dir, draft)
    report = QARunReport(
        status="needs_review",
        provider=provider,
        iterations=iterations,
        issues=issues,
        agent_findings=findings,
        changes_made=changes,
        resume_pages=resume_pages,
        cover_letter_pages=cover_letter_pages,
        draft_path=str(draft_path.resolve()),
    )
    report_path = _write_report(output_dir, report)
    if settings.qa_fail_open:
        return QAPipelineResult(draft, docs or {}, report, report_path)
    codes = ", ".join(issue.code for issue in _blocking(issues))
    raise QAPipelineValidationError(
        f"QA could not resolve all blocking issues after {iterations} review attempt(s): {codes}",
        report_path,
        "artifact_validation" if docs is not None else "qa_review",
    )


def _write_report(output_dir: Path, report: QARunReport) -> Path:
    report_path = output_dir / "qa_report.json"
    report_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return report_path


def _write_failed_draft(output_dir: Path, draft: DocumentDraft) -> Path:
    draft_path = output_dir / "qa_draft.xml"
    draft_path.write_text(draft_to_ai_response(draft), encoding="utf-8")
    return draft_path


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in target:
            target.append(normalized)
