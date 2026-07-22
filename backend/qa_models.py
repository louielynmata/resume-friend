from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QASeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class QAIssue(BaseModel):
    code: str
    category: Literal["grammar", "structure", "truthfulness", "formatting", "artifact"]
    severity: QASeverity
    document: Literal["resume", "cover_letter", "analysis", "package"]
    message: str


class DocumentDraft(BaseModel):
    resume: str
    cover_letter: str
    analysis: str = ""


class QAAgentResult(BaseModel):
    resume: str = Field(description="Corrected resume body without XML tags.")
    cover_letter: str = Field(description="Corrected cover letter body without XML tags.")
    analysis: str = Field(
        default="",
        description="Corrected ATS analysis body without XML tags.",
    )
    issues_found: list[str] = Field(default_factory=list)
    changes_made: list[str] = Field(default_factory=list)

    def as_draft(self) -> DocumentDraft:
        return DocumentDraft(
            resume=self.resume.strip(),
            cover_letter=self.cover_letter.strip(),
            analysis=self.analysis.strip(),
        )


class VisualQAResult(BaseModel):
    passed: bool = Field(
        description=(
            "True only when no delivery-blocking rendering or reference-fidelity "
            "defects exist."
        )
    )
    issues: list[str] = Field(
        default_factory=list,
        description=(
            "Blocking defects such as clipped, overlapping, unreadable, missing, "
            "corrupt, or orphaned content, plus substantial typography, hierarchy, "
            "spacing, margin, density, or page-balance divergence from the references."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Minor non-blocking polish observations that do not materially change "
            "readability, hierarchy, page balance, or reference fidelity."
        ),
    )
    summary: str = ""


class ArtifactQAResult(BaseModel):
    issues: list[QAIssue] = Field(default_factory=list)
    resume_pages: int | None = None
    cover_letter_pages: int | None = None
    @property
    def blocking_issues(self) -> list[QAIssue]:
        return [issue for issue in self.issues if issue.severity == QASeverity.ERROR]


class QARunReport(BaseModel):
    status: Literal["passed", "passed_with_warnings", "needs_review", "disabled"]
    provider: str
    iterations: int = 0
    issues: list[QAIssue] = Field(default_factory=list)
    agent_findings: list[str] = Field(default_factory=list)
    changes_made: list[str] = Field(default_factory=list)
    resume_pages: int | None = None
    cover_letter_pages: int | None = None
    draft_path: str | None = None
