from __future__ import annotations

import re

from ..config import settings
from ..qa_models import (
    DocumentDraft,
    QAAgentResult,
    QAIssue,
    QASeverity,
)
from .ai_service import generate_structured
from .document_normalization import normalize_resume_bullets


_TAG_RE = re.compile(r"<(?P<tag>RESUME|COVER_LETTER|ANALYSIS)>(?P<body>.*?)</(?P=tag)>", re.DOTALL)
_FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I've|I'd|I'll|me|my|mine|myself)\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    r"\[(?:copy|insert|add|placeholder|hiring team|primary role|section header|continue|keyword)",
    re.IGNORECASE,
)
_META_RE = re.compile(
    r"\b(?:as an ai|formatting explanation|placeholder section|this section is reserved|as per the prompt)\b",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s|)>]+|\b(?:linkedin|github|gitlab)\.com/[^\s|)>]+", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_COVER_LETTER_CLOSING_RE = re.compile(
    r"^(?:sincerely(?:\s+and\s+(?:thankfully|gratefully))?"
    r"|cheers|best|best regards|kind regards|regards|thank you|warm regards)[,!]?$",
    re.IGNORECASE,
)
_NAME_CANDIDATE_RE = re.compile(r"^[A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){0,4}$")
_VALID_ATS_SCORE_RE = re.compile(r"(?im)^ATS_SCORE:\s*(?:100|[1-9]?\d)\s*$")
_QA_PROMPT_FILE = "qa_prompt.md"


def parse_document_draft(ai_response: str) -> DocumentDraft:
    sections = {
        match.group("tag"): match.group("body").strip()
        for match in _TAG_RE.finditer(ai_response)
    }
    missing = [
        tag for tag in ("RESUME", "COVER_LETTER") if not sections.get(tag)
    ]
    if missing:
        raise ValueError(
            "AI response did not contain required section(s): " + ", ".join(missing)
        )
    return DocumentDraft(
        resume=sections["RESUME"],
        cover_letter=sections["COVER_LETTER"],
        analysis=sections.get("ANALYSIS", ""),
    )


def draft_to_ai_response(draft: DocumentDraft) -> str:
    return (
        f"<RESUME>\n{draft.resume.strip()}\n</RESUME>\n\n"
        f"<COVER_LETTER>\n{draft.cover_letter.strip()}\n</COVER_LETTER>\n\n"
        f"<ANALYSIS>\n{draft.analysis.strip()}\n</ANALYSIS>"
    )


def apply_safe_deterministic_fixes(
    draft: DocumentDraft,
    *,
    owner_name: str,
    previous_analysis: str | None = None,
) -> tuple[DocumentDraft, list[str]]:
    """Restore trusted mechanical invariants without asking an AI to infer them."""
    fixed = draft.model_copy(deep=True)
    changes: list[str] = []

    fixed.resume, bullet_replacements = normalize_resume_bullets(fixed.resume)
    if bullet_replacements:
        changes.append(
            f"Normalized {bullet_replacements} resume bullet marker(s) to \u25cf."
        )

    if owner_name.strip():
        fixed.resume, resume_changed = _restore_resume_name(
            fixed.resume,
            owner_name.strip(),
        )
        if resume_changed:
            changes.append("Restored the configured applicant name in the resume header.")

        fixed.cover_letter, cover_changed = _restore_cover_letter_signoff(
            fixed.cover_letter,
            owner_name.strip(),
        )
        if cover_changed:
            changes.append(
                "Normalized the cover-letter sign-off and restored the configured "
                "applicant name."
            )

    fixed.analysis, score_changed = _normalize_ats_score(fixed.analysis)
    if score_changed:
        changes.append("Normalized ATS_SCORE to the required integer format.")

    if previous_analysis is not None:
        fixed.analysis, score_restored = _restore_previous_ats_score(
            fixed.analysis,
            previous_analysis,
        )
        if score_restored:
            changes.append("Restored the prior validated ATS_SCORE after model review.")

    return fixed, changes


def validate_draft(
    draft: DocumentDraft,
    *,
    owner_name: str,
    source_resume: str,
    source_materials: str,
) -> list[QAIssue]:
    issues: list[QAIssue] = []

    def add(
        code: str,
        category: str,
        severity: QASeverity,
        document: str,
        message: str,
    ) -> None:
        issues.append(
            QAIssue(
                code=code,
                category=category,
                severity=severity,
                document=document,
                message=message,
            )
        )

    resume = draft.resume.strip()
    cover_letter = draft.cover_letter.strip()
    analysis = draft.analysis.strip()

    for marker in ("NAME:", "ROLE:", "CONTACT:"):
        if not re.search(rf"(?im)^{re.escape(marker)}\s*\S+", resume):
            add(
                f"RESUME_{marker[:-1]}_MISSING",
                "structure",
                QASeverity.ERROR,
                "resume",
                f"The resume must contain a populated {marker} line.",
            )

    if owner_name and owner_name.lower() not in resume.lower():
        add(
            "OWNER_NAME_MISSING_RESUME",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "The configured applicant name is missing from the resume.",
        )
    if owner_name and not _cover_letter_signoff_has_name(cover_letter, owner_name):
        add(
            "OWNER_NAME_MISSING_COVER_LETTER",
            "truthfulness",
            QASeverity.ERROR,
            "cover_letter",
            "The configured applicant name is missing from the cover letter sign-off.",
        )

    if _FIRST_PERSON_RE.search(resume):
        add(
            "RESUME_FIRST_PERSON",
            "grammar",
            QASeverity.ERROR,
            "resume",
            "Resume prose must not use first-person pronouns.",
        )
    if not _FIRST_PERSON_RE.search(cover_letter):
        add(
            "COVER_LETTER_FIRST_PERSON_MISSING",
            "grammar",
            QASeverity.ERROR,
            "cover_letter",
            "The cover letter must use a natural first-person voice.",
        )

    if not re.search(r"(?im)^cover letter\s*$", cover_letter):
        add(
            "COVER_LETTER_HEADING_MISSING",
            "structure",
            QASeverity.ERROR,
            "cover_letter",
            "The cover letter must start with the 'Cover Letter' heading.",
        )
    if not re.search(r"(?im)^(?:to|dear)\b.+[, :]?\s*$", cover_letter):
        add(
            "COVER_LETTER_GREETING_MISSING",
            "structure",
            QASeverity.ERROR,
            "cover_letter",
            "The cover letter must include a greeting.",
        )

    for document_name, text in (
        ("resume", resume),
        ("cover_letter", cover_letter),
        ("analysis", analysis),
    ):
        if _PLACEHOLDER_RE.search(text):
            add(
                f"{document_name.upper()}_PLACEHOLDER",
                "structure",
                QASeverity.ERROR,
                document_name,
                "Unresolved placeholder text remains.",
            )
        if _META_RE.search(text):
            add(
                f"{document_name.upper()}_META_COMMENTARY",
                "structure",
                QASeverity.ERROR,
                document_name,
                "AI or formatting meta-commentary remains in the document.",
            )
        if "```" in text:
            add(
                f"{document_name.upper()}_CODE_FENCE",
                "formatting",
                QASeverity.ERROR,
                document_name,
                "Markdown code fences must not appear in generated documents.",
            )
        if "\u2014" in text:
            add(
                f"{document_name.upper()}_EM_DASH",
                "formatting",
                QASeverity.ERROR,
                document_name,
                "Em dashes are not allowed as sentence connectors.",
            )

    invalid_bullets = [
        line for line in resume.splitlines()
        if re.match(r"^\s*(?:[-+*]|\d+\.)\s+", line) and line.strip() != "---"
    ]
    if invalid_bullets:
        add(
            "RESUME_INVALID_BULLETS",
            "formatting",
            QASeverity.ERROR,
            "resume",
            "Resume bullets must use the required bullet character, not hyphens, asterisks, plus signs, or numbers.",
        )

    source_lower = source_materials.lower()
    for value in sorted(set(_EMAIL_RE.findall(f"{resume}\n{cover_letter}"))):
        if value.lower() not in source_lower:
            add(
                "UNSUPPORTED_EMAIL",
                "truthfulness",
                QASeverity.ERROR,
                "package",
                f"Generated email is not present in applicant source materials: {value}",
            )
    for value in sorted(set(_URL_RE.findall(f"{resume}\n{cover_letter}"))):
        normalized = value.rstrip(".,;").lower()
        if normalized not in source_lower:
            add(
                "UNSUPPORTED_URL",
                "truthfulness",
                QASeverity.ERROR,
                "package",
                f"Generated URL is not present in applicant source materials: {value}",
            )

    source_years = set(_YEAR_RE.findall(source_materials))
    generated_years = set(_YEAR_RE.findall(resume))
    unsupported_years = sorted(generated_years - source_years)
    if unsupported_years:
        add(
            "UNSUPPORTED_RESUME_YEAR",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "Resume contains year(s) absent from the source resume: "
            + ", ".join(unsupported_years),
        )

    if not analysis:
        add(
            "ANALYSIS_MISSING",
            "structure",
            QASeverity.WARNING,
            "analysis",
            "The optional ATS analysis section is empty.",
        )
    elif not re.search(r"(?im)^ATS_SCORE:\s*(?:100|[1-9]?\d)\s*$", analysis):
        add(
            "ANALYSIS_SCORE_INVALID",
            "structure",
            QASeverity.WARNING,
            "analysis",
            "ATS analysis does not contain a valid ATS_SCORE between 0 and 100.",
        )

    return issues


async def review_and_fix_draft(
    *,
    provider: str,
    draft: DocumentDraft,
    issues: list[QAIssue],
    source_resume: str,
    instructions: str,
    writing_examples: str,
    transcript: str,
    job_description: str,
    company_context: str,
    position: str,
    company: str,
    owner_name: str,
) -> QAAgentResult:
    prompt_path = settings.app_model_files_path / _QA_PROMPT_FILE
    if not prompt_path.exists():
        raise FileNotFoundError(f"{_QA_PROMPT_FILE} was not found in {prompt_path.parent}.")
    system_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not system_prompt:
        raise ValueError(f"{_QA_PROMPT_FILE} is empty.")

    issue_text = "\n".join(
        f"- [{issue.severity.value}] {issue.code}: {issue.message}" for issue in issues
    ) or "- No deterministic issue was found. Perform an independent grammar and formatting review."

    user_prompt = f"""LANGUAGE VARIANT: {settings.qa_language}
TARGET POSITION: {position}
TARGET COMPANY: {company}
APPLICANT NAME (exact; required in the resume header and cover-letter sign-off): {owner_name}

DETERMINISTIC QA FINDINGS:
{issue_text}

JOB DESCRIPTION:
{job_description}

SUPPORTED COMPANY CONTEXT:
{company_context or "Not supplied."}

SOURCE RESUME (authoritative facts):
{source_resume}

APPLICANT INSTRUCTIONS:
{instructions}

WRITING EXAMPLES:
{writing_examples}

TRANSCRIPT / EDUCATION SOURCE:
{transcript}

DRAFT RESUME:
{draft.resume}

DRAFT COVER LETTER:
{draft.cover_letter}

DRAFT ANALYSIS:
{draft.analysis}
"""
    result = await generate_structured(
        provider,
        system_prompt,
        user_prompt,
        QAAgentResult,
    )
    result.resume = _strip_optional_tag(result.resume, "RESUME")
    result.cover_letter = _strip_optional_tag(result.cover_letter, "COVER_LETTER")
    result.analysis = _strip_optional_tag(result.analysis, "ANALYSIS")
    return result


def _strip_optional_tag(text: str, tag: str) -> str:
    match = re.fullmatch(rf"\s*<{tag}>(.*?)</{tag}>\s*", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _restore_resume_name(text: str, owner_name: str) -> tuple[str, bool]:
    lines = text.strip().splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^\s*NAME:\s*", line, re.IGNORECASE):
            replacement = f"NAME: {owner_name}"
            if line == replacement:
                return text.strip(), False
            lines[index] = replacement
            return "\n".join(lines).strip(), True

    lines.insert(0, f"NAME: {owner_name}")
    return "\n".join(lines).strip(), True


def _restore_cover_letter_signoff(text: str, owner_name: str) -> tuple[str, bool]:
    lines = text.strip().splitlines()
    lines, duplicates_removed = _remove_duplicate_signoff_blocks(
        lines,
        owner_name,
    )
    closing_index = next(
        (
            index
            for index in range(len(lines) - 1, -1, -1)
            if _COVER_LETTER_CLOSING_RE.fullmatch(lines[index].strip())
        ),
        None,
    )

    if closing_index is None:
        suffix = ["", "Sincerely,", owner_name]
        return "\n".join([*lines, *suffix]).strip(), True

    first_content_index = next(
        (
            index
            for index in range(closing_index + 1, len(lines))
            if lines[index].strip()
        ),
        None,
    )
    if first_content_index is not None:
        candidate = lines[first_content_index].strip()
        if candidate.casefold() == owner_name.casefold():
            return "\n".join(lines).strip(), duplicates_removed
        if _NAME_CANDIDATE_RE.fullmatch(candidate):
            lines[first_content_index] = owner_name
            return "\n".join(lines).strip(), True

    lines.insert(closing_index + 1, owner_name)
    return "\n".join(lines).strip(), True


def _remove_duplicate_signoff_blocks(
    lines: list[str],
    owner_name: str,
) -> tuple[list[str], bool]:
    blocks: list[tuple[int, int]] = []
    for closing_index, line in enumerate(lines):
        if not _COVER_LETTER_CLOSING_RE.fullmatch(line.strip()):
            continue
        name_index = next(
            (
                index
                for index in range(closing_index + 1, len(lines))
                if lines[index].strip()
            ),
            None,
        )
        if (
            name_index is not None
            and lines[name_index].strip().casefold() == owner_name.casefold()
        ):
            blocks.append((closing_index, name_index))

    if len(blocks) < 2:
        return lines, False

    repaired = list(lines)
    for closing_index, name_index in reversed(blocks[1:]):
        del repaired[closing_index:name_index + 1]

    while repaired and not repaired[-1].strip():
        repaired.pop()
    return repaired, True


def _cover_letter_signoff_has_name(text: str, owner_name: str) -> bool:
    lines = text.strip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if not _COVER_LETTER_CLOSING_RE.fullmatch(lines[index].strip()):
            continue
        following_content = [line.strip() for line in lines[index + 1:] if line.strip()]
        return bool(
            following_content
            and following_content[0].casefold() == owner_name.strip().casefold()
        )
    return False


def _normalize_ats_score(text: str) -> tuple[str, bool]:
    lines = text.strip().splitlines()
    for index, line in enumerate(lines):
        if not re.search(r"\bATS_SCORE\b", line, re.IGNORECASE):
            continue
        score_match = re.search(
            r"\b(100|[1-9]?\d)(?:\s*(?:/\s*100|%))?\b",
            line,
        )
        if not score_match:
            return text.strip(), False
        replacement = f"ATS_SCORE: {score_match.group(1)}"
        if line == replacement:
            return text.strip(), False
        lines[index] = replacement
        return "\n".join(lines).strip(), True
    return text.strip(), False


def _restore_previous_ats_score(
    text: str,
    previous_analysis: str,
) -> tuple[str, bool]:
    if _VALID_ATS_SCORE_RE.search(text):
        return text.strip(), False

    normalized_previous, _ = _normalize_ats_score(previous_analysis)
    previous_match = _VALID_ATS_SCORE_RE.search(normalized_previous)
    if previous_match is None:
        return text.strip(), False

    retained_lines = [
        line
        for line in text.strip().splitlines()
        if not re.search(r"\bATS_SCORE\b", line, re.IGNORECASE)
    ]
    retained = "\n".join(retained_lines).strip()
    restored = previous_match.group(0)
    if retained:
        restored = f"{restored}\n\n{retained}"
    return restored, True
