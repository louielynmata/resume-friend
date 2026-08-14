from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..config import settings
from ..qa_models import (
    DocumentDraft,
    QAAgentResult,
    QAIssue,
    QASeverity,
)
from .ai_service import generate_structured
from .document_normalization import (
    CATEGORY_SECTION_NAMES as _CATEGORY_SECTION_NAMES,
    RESUME_SECTION_NAMES as _RESUME_SECTION_NAMES,
    normalize_resume_bullets,
)
from .work_sample_links import format_work_samples_line


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
_AddIssue = Callable[[str, str, QASeverity, str, str], None]

_HEADER_MARKERS = frozenset(
    {
        "CONTACT",
        "LINKS",
        "LINK",
        "PORTFOLIO",
        "WORK_SAMPLES",
        "WORK SAMPLES",
        "CASE_STUDIES",
        "CASE STUDIES",
    }
)
_SECTION_GROUPS: dict[str, frozenset[str]] = {
    "education": frozenset({"EDUCATION", "EDUCATIONAL ATTAINMENT"}),
    "projects": frozenset({"PROJECTS", "NOTABLE PROJECTS"}),
    "related_work": frozenset({"RELATED WORK EXPERIENCES"}),
    "other_work": frozenset({"OTHER EXPERIENCES", "OTHER WORK EXPERIENCES"}),
    "certificates": frozenset(
        {"CERTIFICATIONS", "CERTIFICATIONS AND AWARDS", "CERTIFICATES"}
    ),
    "awards": frozenset({"ACHIEVEMENTS", "AWARDS AND ACHIEVEMENTS"}),
}
_CANONICAL_TRACK_SECTIONS = {
    "education": "EDUCATION",
    "projects": "PROJECTS",
    "related_work": "RELATED WORK EXPERIENCES",
    "other_work": "OTHER WORK EXPERIENCES",
    "certificates": "CERTIFICATES",
    "awards": "AWARDS AND ACHIEVEMENTS",
}


@dataclass(frozen=True)
class _DesignReferenceEntry:
    company: str
    context: str
    role_titles: tuple[str, ...]
    role_lines: tuple[str, ...]
    bullets: tuple[str, ...]
    notable_label: str
    notable_bullets: tuple[str, ...]


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
    target_role: str = "",
    source_resume: str = "",
    source_materials: str = "",
    job_type: str = "",
    required_work_sample_links: Mapping[str, str] | None = None,
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

    fixed.cover_letter, heading_changed = _restore_cover_letter_heading(
        fixed.cover_letter
    )
    if heading_changed:
        changes.append("Restored the exact Cover Letter heading at the start.")

    if target_role.strip():
        fixed.resume, role_changed = _restore_resume_role(
            fixed.resume,
            target_role,
        )
        if role_changed:
            changes.append(
                "Restored the target ROLE line in the resume header."
            )

    if source_resume.strip():
        fixed.resume, role_entries_changed = _normalize_source_role_entries(
            fixed.resume,
            source_resume,
        )
        if role_entries_changed:
            changes.append(
                "Normalized verified role titles and dates to the resume entry format."
            )

        fixed.resume, source_dates_changed = _restore_source_dates(
            fixed.resume,
            source_resume,
        )
        if source_dates_changed:
            changes.append(
                "Restored verified role titles and work or education dates from "
                "the source resume."
            )

        (
            fixed.resume,
            development_sections_changed,
        ) = _restore_development_reference_sections(
            fixed.resume,
            source_resume,
        )
        if development_sections_changed:
            changes.append(
                "Restored the development reference sections for Projects, "
                "Related Work Experiences, and Other Experiences."
            )

        if job_type.strip().lower() == "design":
            fixed.resume, design_entries_changed = (
                _restore_design_reference_entries(
                    fixed.resume,
                    source_resume,
                )
            )
            if design_entries_changed:
                changes.append(
                    "Restored fixed design entry structure and Notable Clients; "
                    "kept additions to source-supported bullet lines only."
                )

    trusted_materials = source_materials or source_resume
    if trusted_materials.strip():
        fixed.resume, header_changed = _restore_required_resume_header(
            fixed.resume,
            trusted_materials,
            job_type=job_type,
            required_work_sample_links=required_work_sample_links,
        )
        if header_changed:
            if required_work_sample_links:
                changes.append(
                    "Restored the track-required work-sample links from applicant instructions."
                )
            else:
                changes.append(
                    "Restored the track-specific resume header links from the applicant instructions."
                )

        fixed.resume, resume_urls_changed = _restore_source_supported_urls(
            fixed.resume,
            trusted_materials,
        )
        fixed.cover_letter, cover_urls_changed = _restore_source_supported_urls(
            fixed.cover_letter,
            trusted_materials,
        )
        if resume_urls_changed or cover_urls_changed:
            changes.append(
                "Restored a source-supported URL spelling from the applicant materials."
            )

    fixed.resume, categories_changed = _normalize_resume_categories(fixed.resume)
    fixed.resume, categories_consolidated = _consolidate_resume_categories(
        fixed.resume
    )
    if categories_changed or categories_consolidated:
        changes.append(
            "Normalized compact skill sections to comma-separated CATEGORY "
            "builder markers."
        )

    if source_resume.strip():
        fixed.resume, ai_tools_changed = _restore_source_ai_tools(
            fixed.resume,
            source_resume,
        )
        if ai_tools_changed:
            changes.append(
                "Restored the source-backed AI tools category for the "
                "development resume."
            )

    fixed.resume, section_order_changed = _apply_track_section_contract(
        fixed.resume,
        job_type=job_type,
    )
    if section_order_changed:
        changes.append(f"Applied the {job_type} resume section order.")

    dash_replacements = 0
    fixed.resume, resume_dashes = _normalize_em_dashes(fixed.resume)
    fixed.cover_letter, cover_dashes = _normalize_em_dashes(fixed.cover_letter)
    fixed.analysis, analysis_dashes = _normalize_em_dashes(fixed.analysis)
    dash_replacements += resume_dashes + cover_dashes + analysis_dashes
    if dash_replacements:
        changes.append(
            f"Replaced {dash_replacements} prohibited em dash"
            f"{'es' if dash_replacements != 1 else ''} with sentence-safe punctuation."
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

    fixed.analysis, score_estimated = _estimate_missing_ats_score(fixed.analysis)
    if score_estimated:
        changes.append(
            "Calculated the missing ATS_SCORE from the analysis keyword coverage."
        )

    return fixed, changes


def validate_draft(
    draft: DocumentDraft,
    *,
    owner_name: str,
    source_resume: str,
    source_materials: str,
    job_type: str = "",
    required_work_sample_links: Mapping[str, str] | None = None,
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

    _validate_structure(
        resume=resume,
        cover_letter=cover_letter,
        owner_name=owner_name,
        source_materials=source_materials,
        job_type=job_type,
        required_work_sample_links=required_work_sample_links,
        add=add,
    )
    source_requirements = _validate_truthfulness(
        resume=resume,
        source_resume=source_resume,
        add=add,
    )
    _validate_track_section_contract(
        resume=resume,
        source_resume=source_resume,
        job_type=job_type,
        add=add,
    )
    _validate_design_reference_entries(
        resume=resume,
        source_resume=source_resume,
        job_type=job_type,
        add=add,
    )
    _validate_formatting(
        resume=resume,
        cover_letter=cover_letter,
        analysis=analysis,
        source_materials=source_materials,
        source_requirements=source_requirements,
        add=add,
    )
    _validate_dates(
        resume=resume,
        analysis=analysis,
        source_materials=source_materials,
        add=add,
    )

    return issues


def _validate_structure(
    *,
    resume: str,
    cover_letter: str,
    owner_name: str,
    source_materials: str,
    job_type: str,
    required_work_sample_links: Mapping[str, str] | None = None,
    add: _AddIssue,
) -> None:

    for marker in ("NAME:", "ROLE:", "CONTACT:"):
        if not re.search(rf"(?im)^{re.escape(marker)}\s*\S+", resume):
            add(
                f"RESUME_{marker[:-1]}_MISSING",
                "structure",
                QASeverity.ERROR,
                "resume",
                f"The resume must contain a populated {marker} line.",
            )

    required_header_lines = _required_resume_header_lines(
        source_materials,
        job_type=job_type,
        required_work_sample_links=required_work_sample_links,
    )
    required_work_sample_line = (
        format_work_samples_line(required_work_sample_links)
        if required_work_sample_links
        else None
    )
    if required_work_sample_line and not re.search(
        rf"(?im)^{re.escape(required_work_sample_line)}\s*$",
        resume,
    ):
        add(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            "structure",
            QASeverity.ERROR,
            "resume",
            "The resume must preserve the required labeled work-sample links exactly.",
        )
    missing_header_lines = [
        line
        for line in required_header_lines
        if line != required_work_sample_line
        if not re.search(rf"(?im)^{re.escape(line)}\s*$", resume)
    ]
    if missing_header_lines:
        add(
            "RESUME_REQUIRED_HEADER_MISMATCH",
            "structure",
            QASeverity.ERROR,
            "resume",
            "The resume must copy these required header lines exactly: "
            + "; ".join(missing_header_lines),
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

    first_cover_line = next(
        (line.strip() for line in cover_letter.splitlines() if line.strip()),
        "",
    )
    if first_cover_line != "Cover Letter":
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

    required_closing_lines = _extract_required_block(
        source_materials,
        "COVER LETTER CLOSING BLOCK - REQUIRED EXACT LINES:",
        "END REQUIRED COVER LETTER CLOSING BLOCK",
    )
    missing_closing_lines = [
        line
        for line in required_closing_lines
        if not re.search(rf"(?im)^{re.escape(line)}\s*$", cover_letter)
    ]
    if missing_closing_lines:
        add(
            "COVER_LETTER_REQUIRED_CLOSING_MISMATCH",
            "structure",
            QASeverity.ERROR,
            "cover_letter",
            "The cover letter must copy these required closing lines exactly and in order: "
            + "; ".join(missing_closing_lines),
        )

    if not re.search(r"(?m)^---\s*$", resume):
        add(
            "RESUME_DIVIDER_MISSING",
            "formatting",
            QASeverity.ERROR,
            "resume",
            "The resume must retain horizontal divider markers between major sections.",
        )

    bullet_section_headers = []
    for line in resume.splitlines():
        match = re.match(r"^\s*●\s+(.+?)\s*$", line)
        if match and _plain_text(match.group(1)).upper() in _RESUME_SECTION_NAMES:
            bullet_section_headers.append(match.group(1).strip())
    if bullet_section_headers:
        add(
            "RESUME_SECTION_AS_BULLET",
            "formatting",
            QASeverity.ERROR,
            "resume",
            "Section headings must not be bullets: " + ", ".join(bullet_section_headers),
        )

    missing_category_sections = _category_sections_without_markers(resume)
    if missing_category_sections:
        add(
            "RESUME_CATEGORY_MARKERS_MISSING",
            "formatting",
            QASeverity.ERROR,
            "resume",
            "Compact skill/tool sections must use `CATEGORY: Label | values`: "
            + ", ".join(missing_category_sections),
        )

    semicolon_categories = [
        match.group(1).strip()
        for line in resume.splitlines()
        if (
            match := re.match(
                r"(?i)^CATEGORY\s*:\s*(.+?)\s*\|\s*(.+)$",
                line.strip(),
            )
        )
        and ";" in match.group(2)
    ]
    if semicolon_categories:
        add(
            "RESUME_CATEGORY_DELIMITER_INVALID",
            "formatting",
            QASeverity.ERROR,
            "resume",
            "Compact skill/tool values must use commas, not semicolons: "
            + ", ".join(semicolon_categories),
        )


def _validate_truthfulness(
    *,
    resume: str,
    source_resume: str,
    add: _AddIssue,
) -> dict[str, object]:
    source_requirements = _extract_source_resume_requirements(source_resume)
    generated_normalized = _normalized_match_text(resume)

    missing_roles = [
        role
        for role in source_requirements["roles"]
        if _normalized_match_text(role) not in generated_normalized
    ]
    if missing_roles:
        add(
            "RESUME_SOURCE_ROLES_MISSING",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "The resume dropped source role(s): " + ", ".join(missing_roles),
        )

    missing_employers = [
        employer
        for employer in source_requirements["employers"]
        if _normalized_match_text(employer) not in generated_normalized
    ]
    if missing_employers:
        add(
            "RESUME_SOURCE_EMPLOYERS_MISSING",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "The resume dropped source employer(s): " + ", ".join(missing_employers),
        )

    generated_years = set(_YEAR_RE.findall(resume))
    missing_required_years = sorted(source_requirements["years"] - generated_years)
    if missing_required_years:
        add(
            "RESUME_SOURCE_DATES_MISSING",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "The resume dropped required work or education year(s): "
            + ", ".join(missing_required_years),
        )

    missing_achievements = [
        label
        for label in source_requirements["achievements"]
        if _normalized_match_text(label) not in generated_normalized
    ]
    if missing_achievements:
        add(
            "RESUME_SOURCE_ACHIEVEMENTS_MISSING",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "The resume dropped named source achievement(s): "
            + ", ".join(missing_achievements),
        )

    source_ai_tools = source_requirements["ai_tools"]
    generated_ai_tools = _resume_category_values(resume, "AI Tools")
    generated_ai_tools_normalized = {
        _normalized_match_text(tool) for tool in generated_ai_tools
    }
    missing_ai_tools = [
        tool
        for tool in source_ai_tools
        if _normalized_match_text(tool) not in generated_ai_tools_normalized
    ]
    if missing_ai_tools:
        add(
            "RESUME_SOURCE_AI_TOOLS_MISSING",
            "truthfulness",
            QASeverity.ERROR,
            "resume",
            "The development resume must keep every tool from the source "
            "`AI Tools` subsection in a `CATEGORY: AI Tools | ...` line: "
            + ", ".join(missing_ai_tools),
        )

    if source_ai_tools and _resume_has_ai_content_outside_category(
        resume,
        source_ai_tools,
    ):
        add(
            "RESUME_AI_CONTENT_OUTSIDE_TOOLS_CATEGORY",
            "structure",
            QASeverity.ERROR,
            "resume",
            "Keep named AI tool references only in the compact "
            "`CATEGORY: AI Tools | ...` line. Remove duplicated tool names "
            "from the summary, experience, projects, and other resume prose. "
            "Source-backed AI or LLM product descriptions may remain.",
        )

    generated_sections = {
        _plain_text(line).upper()
        for line in resume.splitlines()
        if line.strip()
    }
    missing_experience_sections = [
        section
        for section in source_requirements["experience_sections"]
        if section not in generated_sections
    ]
    if missing_experience_sections:
        add(
            "RESUME_SOURCE_EXPERIENCE_SECTIONS_MISSING",
            "structure",
            QASeverity.ERROR,
            "resume",
            "Preserve the source work grouping with these exact section "
            "headings: " + ", ".join(missing_experience_sections),
        )


    return source_requirements


def _validate_formatting(
    *,
    resume: str,
    cover_letter: str,
    analysis: str,
    source_materials: str,
    source_requirements: dict[str, object],
    add: _AddIssue,
) -> None:
    malformed_role_lines = _malformed_required_role_lines(
        resume,
        source_requirements["roles"],
    )
    if malformed_role_lines:
        add(
            "RESUME_ROLE_FORMAT_INVALID",
            "formatting",
            QASeverity.ERROR,
            "resume",
            "Role titles must be uppercase and keep verified dates on the same line: "
            + ", ".join(malformed_role_lines),
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


def _validate_dates(
    *,
    resume: str,
    analysis: str,
    source_materials: str,
    add: _AddIssue,
) -> None:
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


def _extract_required_block(text: str, start: str, end: str) -> list[str]:
    match = re.search(
        rf"(?ims)^\s*{re.escape(start)}\s*$\n(.*?)^\s*{re.escape(end)}\s*$",
        text,
    )
    if not match:
        return []
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _required_resume_header_lines(
    text: str,
    *,
    job_type: str,
    required_work_sample_links: Mapping[str, str] | None = None,
) -> list[str]:
    required = _extract_required_block(
        text,
        "RESUME HEADER - REQUIRED EXACT VALUES:",
        "END REQUIRED RESUME HEADER",
    )
    normalized_job_type = job_type.strip().upper()
    if normalized_job_type in {"DESIGN", "DEVELOPMENT"}:
        required.extend(
            _extract_required_block(
                text,
                f"{normalized_job_type} RESUME HEADER - REQUIRED EXACT VALUES:",
                f"END {normalized_job_type} RESUME HEADER",
            )
        )
    if required_work_sample_links:
        required = [
            line
            for line in required
            if _header_marker_name(line) not in {"WORK_SAMPLES", "WORK SAMPLES"}
        ]
        required.append(format_work_samples_line(required_work_sample_links))
    return list(dict.fromkeys(required))


def _header_marker_name(line: str) -> str | None:
    match = re.match(r"^\s*([A-Z][A-Z_ ]+?)\s*:", line, re.IGNORECASE)
    if match is None:
        return None
    marker = re.sub(r"\s+", " ", match.group(1).strip().upper())
    if marker in _HEADER_MARKERS:
        return marker
    marker_with_underscores = marker.replace(" ", "_")
    return marker_with_underscores if marker_with_underscores in _HEADER_MARKERS else None


def _restore_required_resume_header(
    text: str,
    source_materials: str,
    *,
    job_type: str,
    required_work_sample_links: Mapping[str, str] | None = None,
) -> tuple[str, bool]:
    required = _required_resume_header_lines(
        source_materials,
        job_type=job_type,
        required_work_sample_links=required_work_sample_links,
    )
    if not required:
        return text.strip(), False

    lines = text.strip().splitlines()
    first_section = next(
        (
            index
            for index, line in enumerate(lines)
            if _resume_section_name(line) is not None
        ),
        len(lines),
    )
    required_markers = {
        marker
        for line in required
        if (marker := _header_marker_name(line)) is not None
    }
    header = [
        line
        for line in lines[:first_section]
        if _header_marker_name(line) not in required_markers
    ]
    body = lines[first_section:]

    identity_index = max(
        (
            index
            for index, line in enumerate(header)
            if re.match(r"^\s*(?:NAME|ROLE|TAGLINE)\s*:", line, re.IGNORECASE)
        ),
        default=len(header) - 1,
    )
    insertion_index = identity_index + 1
    while insertion_index < len(header) and not header[insertion_index].strip():
        header.pop(insertion_index)
    header[insertion_index:insertion_index] = [*required, ""]

    restored = _collapse_blank_lines([*header, *body])
    return restored, restored != text.strip()


def _section_group(section_name: str) -> str | None:
    for group, names in _SECTION_GROUPS.items():
        if section_name in names:
            return group
    return None


def _resume_section_blocks(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lines = text.strip().splitlines()
    headings = [
        (index, section)
        for index, line in enumerate(lines)
        if (section := _resume_section_name(line)) is not None
    ]
    if not headings:
        return lines, []

    first_heading = headings[0][0]
    prefix = lines[:first_heading]
    while prefix and (not prefix[-1].strip() or prefix[-1].strip() == "---"):
        prefix.pop()

    blocks: list[tuple[str, list[str]]] = []
    for position, (start, section_name) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        block = lines[start:end]
        while block and (not block[-1].strip() or block[-1].strip() == "---"):
            block.pop()
        blocks.append((section_name, block))
    return prefix, blocks


def _merge_section_group(
    blocks: list[tuple[str, list[str]]],
    group: str,
) -> tuple[str, list[str]] | None:
    matching = [block for section, block in blocks if _section_group(section) == group]
    if not matching:
        return None

    merged = [_CANONICAL_TRACK_SECTIONS[group]]
    for block in matching:
        content = list(block[1:])
        while content and not content[0].strip():
            content.pop(0)
        while content and not content[-1].strip():
            content.pop()
        if content:
            if len(merged) > 1:
                merged.append("")
            merged.extend(content)
    return _CANONICAL_TRACK_SECTIONS[group], merged


def _render_resume_section_blocks(
    prefix: list[str],
    blocks: list[tuple[str, list[str]]],
) -> str:
    rendered_blocks = ["\n".join(block).strip() for _, block in blocks if block]
    sections = "\n\n---\n\n".join(rendered_blocks)
    header = "\n".join(prefix).strip()
    if header and sections:
        return f"{header}\n\n{sections}".strip()
    return (header or sections).strip()


def _apply_track_section_contract(text: str, *, job_type: str) -> tuple[str, bool]:
    normalized_job_type = job_type.strip().lower()
    if normalized_job_type not in {"design", "development"}:
        return text.strip(), False

    prefix, blocks = _resume_section_blocks(text)
    if not blocks:
        return text.strip(), False

    if normalized_job_type == "design":
        moved_groups = {"education", "certificates", "awards"}
        ordered_groups = ("education", "awards")
    else:
        moved_groups = set(_CANONICAL_TRACK_SECTIONS)
        ordered_groups = (
            "education",
            "projects",
            "related_work",
            "other_work",
            "certificates",
            "awards",
        )

    reordered = [
        (section, block)
        for section, block in blocks
        if _section_group(section) not in moved_groups
    ]
    for group in ordered_groups:
        merged = _merge_section_group(blocks, group)
        if merged is not None:
            reordered.append(merged)

    restored = _render_resume_section_blocks(prefix, reordered)
    return restored, restored != text.strip()


def _source_section_groups(source_resume: str) -> set[str]:
    groups: set[str] = set()
    for line in source_resume.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line.strip())
        if heading is None:
            continue
        normalized = _normalized_match_text(heading.group(1)).upper()
        section_name = next(
            (
                section
                for section in _RESUME_SECTION_NAMES
                if _normalized_match_text(section).upper() == normalized
            ),
            None,
        )
        if section_name and (group := _section_group(section_name)):
            groups.add(group)
    return groups


def _validate_track_section_contract(
    *,
    resume: str,
    source_resume: str,
    job_type: str,
    add: _AddIssue,
) -> None:
    normalized_job_type = job_type.strip().lower()
    if normalized_job_type not in {"design", "development"}:
        return

    _, blocks = _resume_section_blocks(resume)
    block_groups = [_section_group(section) for section, _ in blocks]
    generated_groups = [group for group in block_groups if group is not None]
    source_groups = _source_section_groups(source_resume)

    if normalized_job_type == "design":
        if "certificates" in generated_groups:
            add(
                "RESUME_DESIGN_CERTIFICATES_PRESENT",
                "structure",
                QASeverity.ERROR,
                "resume",
                "Design resumes must omit the certificates or certifications section.",
            )
        required_order = [
            group for group in ("education", "awards") if group in source_groups
        ]
    else:
        required_order = [
            group
            for group in (
                "education",
                "projects",
                "related_work",
                "other_work",
                "certificates",
                "awards",
            )
            if group in source_groups
        ]

    missing = [group for group in required_order if group not in generated_groups]
    if missing:
        add(
            "RESUME_TRACK_SECTION_MISSING",
            "structure",
            QASeverity.ERROR,
            "resume",
            "The resume is missing required track section(s): "
            + ", ".join(_CANONICAL_TRACK_SECTIONS[group] for group in missing),
        )
        return

    if required_order and block_groups[-len(required_order):] != required_order:
        add(
            "RESUME_TRACK_SECTION_ORDER_INVALID",
            "structure",
            QASeverity.ERROR,
            "resume",
            "The final resume sections must be ordered as: "
            + ", ".join(_CANONICAL_TRACK_SECTIONS[group] for group in required_order),
        )


def _plain_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`~#]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_match_text(text: str) -> str:
    plain = _plain_text(text).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _restore_source_supported_urls(
    text: str,
    source_materials: str,
) -> tuple[str, bool]:
    """Restore source spelling for scheme/`www` variants of the same URL."""
    candidates = _source_url_candidates(source_materials)
    by_canonical: dict[str, str] = {}
    for candidate in candidates:
        canonical = _canonical_url(candidate)
        if canonical and canonical not in by_canonical:
            by_canonical[canonical] = candidate

    source_lower = source_materials.casefold()
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        value = match.group(0)
        clean = value.rstrip(".,;")
        suffix = value[len(clean):]
        if clean.casefold() in source_lower:
            return value
        replacement = by_canonical.get(_canonical_url(clean))
        if replacement is None or replacement == clean:
            return value
        changed = True
        return f"{replacement}{suffix}"

    return _URL_RE.sub(replace, text).strip(), changed


def _source_url_candidates(source_materials: str) -> list[str]:
    candidates: list[str] = []

    def add(value: str) -> None:
        clean = value.strip().rstrip(".,;")
        if _canonical_url(clean) and clean not in candidates:
            candidates.append(clean)

    for match in re.finditer(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        source_materials,
        re.IGNORECASE,
    ):
        add(match.group(1))
        add(match.group(2))

    for value in _URL_RE.findall(source_materials):
        add(value)

    for match in re.finditer(
        r"(?<!@)\b(?:[A-Z0-9-]+\.)+[A-Z]{2,}(?:/[^\s|)>]*)?",
        source_materials,
        re.IGNORECASE,
    ):
        add(match.group(0))

    return candidates


def _canonical_url(value: str) -> str:
    candidate = value.strip().rstrip("/.,;")
    if not candidate or " " in candidate or "." not in candidate:
        return ""
    parsed = urlsplit(
        candidate if re.match(r"^[a-z][a-z0-9+.-]*://", candidate, re.IGNORECASE)
        else f"//{candidate}"
    )
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return ""
    try:
        parsed_port = parsed.port
    except ValueError:
        return ""
    port = f":{parsed_port}" if parsed_port is not None else ""
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{host}{port}{path}{query}{fragment}"


def _category_sections_without_markers(resume: str) -> list[str]:
    lines = [line.strip() for line in resume.splitlines()]
    missing: list[str] = []
    for index, line in enumerate(lines):
        section = _plain_text(line).upper()
        if section not in _CATEGORY_SECTION_NAMES:
            continue
        block: list[str] = []
        for candidate in lines[index + 1:]:
            candidate_clean = _plain_text(candidate).upper()
            if candidate == "---" or candidate_clean in _RESUME_SECTION_NAMES:
                break
            if candidate:
                block.append(candidate)
        if not any(re.match(r"(?i)^CATEGORY\s*:\s*.+?\s*\|\s*.+", item) for item in block):
            missing.append(section)
    return missing


def _markdown_section_lines(text: str, names: set[str]) -> list[str]:
    lines: list[str] = []
    active = False
    normalized_names = {_normalized_match_text(name) for name in names}
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line.strip())
        if heading:
            active = _normalized_match_text(heading.group(1)) in normalized_names
            continue
        if active:
            lines.append(line)
    return lines


def _markdown_section_entries(
    text: str,
    names: set[str],
) -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []

    for raw_line in _markdown_section_lines(text, names):
        heading = re.match(r"^###\s+(.+?)\s*$", raw_line.strip())
        if heading:
            if current_heading:
                entries.append((current_heading, current_lines))
            current_heading = _plain_text(heading.group(1))
            current_lines = []
            continue
        if current_heading:
            current_lines.append(raw_line)

    if current_heading:
        entries.append((current_heading, current_lines))
    return entries


def _source_design_reference_entries(
    source_resume: str,
) -> list[_DesignReferenceEntry]:
    entries: list[_DesignReferenceEntry] = []
    work_entries = _markdown_section_entries(
        source_resume,
        {
            "Work Experience",
            "Work Experiences",
            "Related Work Experience",
            "Related Work Experiences",
            "Other Experience",
            "Other Experiences",
            "Creative Experience",
        },
    )

    for heading, raw_lines in work_entries:
        role_titles = tuple(
            role
            for role in re.split(r"\s*/\s*", _plain_text(heading))
            if role
        )
        company = ""
        context = ""
        generic_dates = ""
        role_dates: dict[str, str] = {}
        bullets: list[str] = []
        notable_label = ""
        notable_bullets: list[str] = []
        in_notable_clients = False

        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line or line == "---":
                continue

            subheading = re.match(r"^#{4,6}\s+(.+?)\s*$", line)
            if subheading is not None:
                candidate = _plain_text(subheading.group(1))
                in_notable_clients = _normalized_match_text(candidate) in {
                    "notable clients",
                    "notable clients and works",
                }
                if in_notable_clients:
                    notable_label = candidate
                continue

            bullet = re.match(
                r"^\s*(?:[-+*]|\u25cf|\u2022)\s+(.+?)\s*$",
                line,
            )
            if bullet is not None:
                target = notable_bullets if in_notable_clients else bullets
                value = _reference_safe_text(bullet.group(1))
                if not in_notable_clients:
                    value = _resume_voice_reference_bullet(value)
                target.append(value)
                continue

            plain_line = _plain_text(line)
            explicit = re.match(r"^(.+?):\s*(.+)$", plain_line)
            if explicit is not None and _line_has_resume_date(explicit.group(2)):
                matching_role = next(
                    (
                        role
                        for role in role_titles
                        if _normalized_match_text(role)
                        == _normalized_match_text(explicit.group(1))
                    ),
                    None,
                )
                if matching_role is not None:
                    role_dates[matching_role] = _canonical_source_dates(
                        explicit.group(2)
                    )
                    continue

            bold = re.match(r"^\*\*(.+?)\*\*\s*$", line)
            if bold is not None and not company:
                company = _reference_safe_text(_plain_text(bold.group(1))).rstrip(":")
                continue

            if _line_has_resume_date(plain_line) and not generic_dates:
                generic_dates = _canonical_source_dates(plain_line)
                continue

            if company and not context and not in_notable_clients:
                context = _reference_safe_text(plain_line)

        if not company or not role_titles or not notable_label:
            continue

        rendered_roles = tuple(
            role.upper()
            + (
                f" - {dates}"
                if (dates := role_dates.get(role, generic_dates))
                else ""
            )
            for role in role_titles
        )
        entries.append(
            _DesignReferenceEntry(
                company=company,
                context=context,
                role_titles=role_titles,
                role_lines=rendered_roles,
                bullets=tuple(bullets),
                notable_label=notable_label,
                notable_bullets=tuple(notable_bullets),
            )
        )

    return entries


def _design_company_line(entry: _DesignReferenceEntry) -> str:
    context = f" | {entry.context}" if entry.context else ""
    return f"COMPANY: {entry.company}{context}"


def _design_entry_lines(
    entry: _DesignReferenceEntry,
    extra_bullets: list[str],
) -> list[str]:
    lines = [
        _design_company_line(entry),
        *entry.role_lines,
        *(f"\u25cf {bullet}" for bullet in entry.bullets),
        *(f"\u25cf {bullet}" for bullet in extra_bullets),
        "",
        f"SUBHEADING: {entry.notable_label}",
        *(f"\u25cf {bullet}" for bullet in entry.notable_bullets),
    ]
    return lines


def _line_matches_design_company(line: str, company: str) -> bool:
    clean = re.sub(
        r"(?i)^\s*COMPANY\s*:\s*",
        "",
        _plain_text(line),
    )
    candidate = clean.split("|", 1)[0].rstrip(" ,:")
    return _normalized_match_text(candidate) == _normalized_match_text(company)


def _line_matches_design_role(line: str, roles: tuple[str, ...]) -> bool:
    candidate = _resume_role_line_title(line)
    if candidate is None:
        return False
    normalized_roles = {_normalized_match_text(role) for role in roles}
    return _normalized_match_text(candidate) in normalized_roles


_DESIGN_BULLET_MATCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "these",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)


def _design_bullet_content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _normalized_match_text(text).split()
        if token not in _DESIGN_BULLET_MATCH_STOPWORDS
    }


def _design_bullet_numbers(text: str) -> set[str]:
    return {
        token.casefold().removesuffix("+")
        for token in re.findall(
            r"(?i)(?<!\w)\d+(?:[.,]\d+)?(?:[kmb])?%?\+?(?!\w)",
            text,
        )
    }


def _design_bullets_are_redundant(candidate: str, reference: str) -> bool:
    if _normalized_match_text(candidate) == _normalized_match_text(reference):
        return True

    candidate_numbers = _design_bullet_numbers(candidate)
    reference_numbers = _design_bullet_numbers(reference)
    if candidate_numbers != reference_numbers:
        return False

    candidate_tokens = _design_bullet_content_tokens(candidate)
    reference_tokens = _design_bullet_content_tokens(reference)
    if not candidate_tokens or not reference_tokens:
        return False

    overlap = len(candidate_tokens & reference_tokens)
    return (
        overlap >= 6
        and overlap / len(candidate_tokens) >= 0.6
        and overlap / len(reference_tokens) >= 0.6
    )


def _design_entry_extra_bullets(
    lines: list[str],
    entry: _DesignReferenceEntry,
) -> list[str]:
    source_bullets = (*entry.bullets, *entry.notable_bullets)
    extras: list[str] = []
    in_notable_clients = False
    notable_normalized = _normalized_match_text(entry.notable_label)

    for line in lines:
        clean = _plain_text(line)
        if (
            _resume_section_name(line) == "NOTABLE CLIENTS"
            or (
                re.match(r"(?i)^\s*SUBHEADING\s*:", clean)
                and notable_normalized in _normalized_match_text(clean)
            )
        ):
            in_notable_clients = True
            continue
        if in_notable_clients:
            continue
        bullet = re.match(r"^\s*(?:[-+*]|\u25cf|\u2022)\s+(.+?)\s*$", line)
        if bullet is None:
            continue
        value = _resume_voice_reference_bullet(bullet.group(1))
        if not _normalized_match_text(value):
            continue
        if any(
            _design_bullets_are_redundant(value, source_bullet)
            for source_bullet in source_bullets
        ):
            continue
        if any(
            _design_bullets_are_redundant(value, existing)
            for existing in extras
        ):
            continue
        extras.append(value)
    return extras


def _design_entry_span(
    lines: list[str],
    entry: _DesignReferenceEntry,
    *,
    all_companies: tuple[str, ...],
    all_roles: tuple[str, ...],
) -> tuple[int, int] | None:
    anchors = [
        index
        for index, line in enumerate(lines)
        if _line_matches_design_company(line, entry.company)
        or _line_matches_design_role(line, entry.role_titles)
    ]
    if not anchors:
        return None

    start = min(anchors)
    last_anchor = max(anchors)
    other_companies = tuple(
        company
        for company in all_companies
        if _normalized_match_text(company) != _normalized_match_text(entry.company)
    )
    entry_role_names = {
        _normalized_match_text(role) for role in entry.role_titles
    }
    other_roles = tuple(
        role
        for role in all_roles
        if _normalized_match_text(role) not in entry_role_names
    )

    end = len(lines)
    for index in range(last_anchor + 1, len(lines)):
        section = _resume_section_name(lines[index])
        if section is not None and section != "NOTABLE CLIENTS":
            end = index
            break
        if any(
            _line_matches_design_company(lines[index], company)
            for company in other_companies
        ) or _line_matches_design_role(lines[index], other_roles):
            end = index
            break
    return start, end


def _design_entry_insertion_index(lines: list[str]) -> int:
    work_sections = {
        "WORK EXPERIENCE",
        "RELATED WORK EXPERIENCES",
        "OTHER EXPERIENCES",
        "OTHER WORK EXPERIENCES",
        "EXPERIENCE",
        "CREATIVE EXPERIENCE",
    }
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if _resume_section_name(line) in work_sections
        ),
        None,
    )
    if start is None:
        return len(lines)
    return next(
        (
            index
            for index in range(start + 1, len(lines))
            if (
                (section := _resume_section_name(lines[index])) is not None
                and section not in {"NOTABLE CLIENTS"}
            )
        ),
        len(lines),
    )


def _restore_design_reference_entries(
    text: str,
    source_resume: str,
) -> tuple[str, bool]:
    reference_entries = _source_design_reference_entries(source_resume)
    if not reference_entries:
        return text.strip(), False

    requirements = _extract_source_resume_requirements(source_resume)
    all_companies = tuple(
        company
        for company in requirements.get("employers", [])
        if isinstance(company, str)
    )
    all_roles = tuple(
        role
        for role in requirements.get("roles", [])
        if isinstance(role, str)
    )
    lines = text.strip().splitlines()

    for entry in reference_entries:
        span = _design_entry_span(
            lines,
            entry,
            all_companies=all_companies,
            all_roles=all_roles,
        )
        if span is None:
            start = end = _design_entry_insertion_index(lines)
            extra_bullets: list[str] = []
        else:
            start, end = span
            extra_bullets = _design_entry_extra_bullets(lines[start:end], entry)

        replacement = _design_entry_lines(entry, extra_bullets)
        if end < len(lines) and lines[end].strip():
            replacement.append("")
        lines[start:end] = replacement

    restored = _collapse_blank_lines(lines)
    return restored, restored != text.strip()


def _validate_design_reference_entries(
    *,
    resume: str,
    source_resume: str,
    job_type: str,
    add: _AddIssue,
) -> None:
    if job_type.strip().lower() != "design":
        return
    _, changed = _restore_design_reference_entries(resume, source_resume)
    if changed:
        add(
            "RESUME_DESIGN_REFERENCE_ENTRY_MISMATCH",
            "structure",
            QASeverity.ERROR,
            "resume",
            "Design entries with source Notable Clients must preserve the exact "
            "company descriptor, separate role/date lines, source bullets, and "
            "complete Notable Clients block. Only source-supported bullet lines "
            "may be added.",
        )


def _restore_development_reference_sections(
    text: str,
    source_resume: str,
) -> tuple[str, bool]:
    projects = _source_projects_reference_block(source_resume)
    related = _source_work_reference_block(
        source_resume,
        {"Related Work Experience", "Related Work Experiences"},
        "RELATED WORK EXPERIENCES",
    )
    other = _source_work_reference_block(
        source_resume,
        {"Other Experience", "Other Experiences"},
        "OTHER WORK EXPERIENCES",
    )
    if not projects or not related or not other:
        return text.strip(), False

    replacement = "\n\n---\n\n".join((projects, related, other))
    lines = text.strip().splitlines()
    targets = {
        "PROJECTS",
        "NOTABLE PROJECTS",
        "RELATED WORK EXPERIENCES",
        "OTHER EXPERIENCES",
        "OTHER WORK EXPERIENCES",
    }
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        section = _resume_section_name(lines[index])
        if section not in targets:
            index += 1
            continue

        start = index
        if start > 0 and lines[start - 1].strip() == "---":
            start -= 1
        end = index + 1
        while end < len(lines) and _resume_section_name(lines[end]) is None:
            end += 1
        spans.append((start, end))
        index = end

    if spans:
        insertion_index = min(start for start, _ in spans)
    else:
        insertion_index = next(
            (
                candidate
                for candidate, line in enumerate(lines)
                if _resume_section_name(line)
                in {"CERTIFICATIONS", "ACHIEVEMENTS", "AWARDS AND ACHIEVEMENTS"}
            ),
            len(lines),
        )

    removed = {
        candidate
        for start, end in spans
        for candidate in range(start, end)
    }
    replacement_lines = replacement.splitlines()
    rebuilt: list[str] = []
    inserted = False
    for candidate, line in enumerate(lines):
        if candidate == insertion_index and not inserted:
            rebuilt.extend(replacement_lines)
            inserted = True
        if candidate not in removed:
            rebuilt.append(line)
    if not inserted:
        if rebuilt and rebuilt[-1].strip():
            rebuilt.append("")
        rebuilt.extend(replacement_lines)

    restored = _collapse_blank_lines(rebuilt)
    original = text.strip()
    return restored, restored != original


def _source_projects_reference_block(source_resume: str) -> str:
    entries = _markdown_section_entries(source_resume, {"Projects"})
    if not entries:
        return ""

    output = ["PROJECTS"]
    for title, raw_lines in entries:
        context = ""
        dates = ""
        bullets: list[str] = []
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line or line == "---":
                continue
            bullet = re.match(r"^\s*(?:[-+*]|\u25cf|\u2022)\s+(.+?)\s*$", line)
            if bullet:
                bullets.append(_reference_safe_text(bullet.group(1)))
                continue
            bold = re.match(r"^\*\*(.+?)\*\*\s*$", line)
            if bold and not context:
                context = _reference_safe_text(_plain_text(bold.group(1)))
                continue
            if _line_has_resume_date(line) and not dates:
                dates = _canonical_source_dates(line)

        project_title = _reference_safe_text(title)
        if context:
            output.append(f"PROJECT: {project_title}")
            meta = context + (f" | {dates}" if dates else "")
            output.append(f"PROJECT_META: {meta}")
        else:
            project = project_title + (f" | {dates}" if dates else "")
            output.append(f"PROJECT: {project}")
        output.extend(f"\u25cf {bullet}" for bullet in bullets)

    return "\n".join(output).strip()


def _source_work_reference_block(
    source_resume: str,
    names: set[str],
    output_heading: str,
) -> str:
    entries = _markdown_section_entries(source_resume, names)
    if not entries:
        return ""

    output = [output_heading]
    for heading, raw_lines in entries:
        roles = [
            role
            for role in re.split(r"\s*/\s*", _plain_text(heading))
            if role
        ]
        company = ""
        generic_dates = ""
        role_dates: dict[str, str] = {}
        bullets: list[str] = []

        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line or line == "---":
                continue
            bullet = re.match(r"^\s*(?:[-+*]|\u25cf|\u2022)\s+(.+?)\s*$", line)
            if bullet:
                bullets.append(_reference_safe_text(bullet.group(1)))
                continue
            bold = re.match(r"^\*\*(.+?)\*\*\s*$", line)
            if bold and not company:
                company = _reference_safe_text(_plain_text(bold.group(1)))
                continue

            explicit = re.match(r"^(.+?):\s*(.+)$", _plain_text(line))
            if explicit and _line_has_resume_date(explicit.group(2)):
                explicit_role = _plain_text(explicit.group(1))
                matching_role = next(
                    (
                        role
                        for role in roles
                        if _normalized_match_text(role)
                        == _normalized_match_text(explicit_role)
                    ),
                    None,
                )
                if matching_role:
                    role_dates[matching_role] = _canonical_source_dates(
                        explicit.group(2)
                    )
                    continue

            if _line_has_resume_date(line) and not generic_dates:
                generic_dates = _canonical_source_dates(line)

        if not company or not roles:
            continue

        output.append(f"COMPANY: {company}")
        for role in roles:
            dates = role_dates.get(role, generic_dates)
            role_line = role.upper() + (f" - {dates}" if dates else "")
            output.append(role_line)
        output.extend(f"\u25cf {bullet}" for bullet in bullets)

    return "\n".join(output).strip()


def _resume_section_name(line: str) -> str | None:
    clean = _plain_text(line)
    clean = re.sub(r"^#{1,6}\s*", "", clean).strip().upper()
    return clean if clean in _RESUME_SECTION_NAMES else None


def _reference_safe_text(text: str) -> str:
    return re.sub(r"\s*\u2014\s*", ", ", text).strip()


def _resume_voice_reference_bullet(text: str) -> str:
    """Canonicalize trusted source bullets without changing their facts."""
    value = _reference_safe_text(text)
    value = re.sub(
        r"(?i)^I(?:\s+(?:am|have|had|was)|'(?:m|ve))\s+",
        "",
        value,
    )
    value = re.sub(r"(?i)^I\s+", "", value)
    value = re.sub(r"(?i)\bunder\s+my\s+team\b", "on the team", value)
    value = re.sub(r"(?i)\bmy\s+team\b", "the team", value)

    replacements = (
        (r"(?i)\bI'm\b", "the applicant is"),
        (r"(?i)\bI've\b", "the applicant has"),
        (r"(?i)\bI'll\b", "the applicant will"),
        (r"(?i)\bmyself\b", "the applicant"),
        (r"(?i)\bmine\b", "the applicant's"),
        (r"(?i)\bmy\b", "the applicant's"),
        (r"(?i)\bme\b", "the applicant"),
        (r"(?i)\bI\b", "the applicant"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)

    first_letter = re.search(r"[A-Za-z]", value)
    if first_letter is not None:
        index = first_letter.start()
        value = f"{value[:index]}{value[index].upper()}{value[index + 1:]}"
    return value.strip()


def _collapse_blank_lines(lines: list[str]) -> str:
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        collapsed.append(line.rstrip())
        previous_blank = blank
    return "\n".join(collapsed).strip()


def _markdown_subsection_items(text: str, name: str) -> list[str]:
    items: list[str] = []
    active = False
    active_level = 0
    expected = _normalized_match_text(name)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            if active and level <= active_level:
                break
            if _normalized_match_text(heading.group(2)) == expected:
                active = True
                active_level = level
            continue
        if not active:
            continue

        bullet = re.match(
            r"^\s*(?:[-+*]|\u25cf|\u2022)\s+(.+?)\s*$",
            raw_line,
        )
        if bullet is None:
            continue
        item = _plain_text(bullet.group(1)).rstrip(".").strip()
        normalized_item = _normalized_match_text(item)
        if item and normalized_item not in {
            _normalized_match_text(existing) for existing in items
        }:
            items.append(item)

    return items


def _required_experience_sections(source_resume: str) -> list[str]:
    required: list[str] = []
    for line in source_resume.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line.strip())
        if heading is None:
            continue
        normalized = _normalized_match_text(heading.group(1))
        if normalized in {"related work experience", "related work experiences"}:
            if "RELATED WORK EXPERIENCES" not in required:
                required.append("RELATED WORK EXPERIENCES")
        elif normalized in {"other experience", "other experiences"}:
            if "OTHER WORK EXPERIENCES" not in required:
                required.append("OTHER WORK EXPERIENCES")
    return required


def _extract_source_resume_requirements(source_resume: str) -> dict[str, object]:
    work_lines = _markdown_section_lines(
        source_resume,
        {
            "Work Experience",
            "Work Experiences",
            "Related Work Experience",
            "Related Work Experiences",
            "Other Experience",
            "Other Experiences",
            "Creative Experience",
        },
    )
    education_lines = _markdown_section_lines(
        source_resume,
        {"Education", "Educational Attainment"},
    )
    achievement_lines = _markdown_section_lines(
        source_resume,
        {"Achievements", "Awards and Achievements"},
    )

    roles: list[str] = []
    employers: list[str] = []
    waiting_for_company = False
    for raw_line in work_lines:
        line = raw_line.strip()
        role_match = re.match(r"^###\s+(.+?)\s*$", line)
        if role_match:
            heading = _plain_text(role_match.group(1))
            for role in re.split(r"\s*/\s*", heading):
                if role and role not in roles:
                    roles.append(role)
            waiting_for_company = True
            continue
        if waiting_for_company:
            company_match = re.match(r"^\*\*(.+?)\*\*\s*$", line)
            if company_match:
                company = _plain_text(company_match.group(1)).rstrip(":")
                company = re.split(r"\s+[–—]\s+", company, maxsplit=1)[0].strip()
                if company and company not in employers:
                    employers.append(company)
                waiting_for_company = False

    achievements: list[str] = []
    for line in achievement_lines:
        match = re.match(r"^\s*[-●•]\s+\*\*(.+?)(?::)?\*\*", line)
        if match:
            label = _plain_text(match.group(1)).rstrip(":")
            if label and label not in achievements:
                achievements.append(label)

    required_years = set(
        _YEAR_RE.findall("\n".join([*work_lines, *education_lines]))
    )
    return {
        "roles": roles,
        "employers": employers,
        "years": required_years,
        "achievements": achievements,
        "ai_tools": _markdown_subsection_items(source_resume, "AI Tools"),
        "experience_sections": _required_experience_sections(source_resume),
    }


def _malformed_required_role_lines(resume: str, roles: object) -> list[str]:
    malformed: list[str] = []
    resume_lines = [line.strip() for line in resume.splitlines() if line.strip()]
    for role in roles if isinstance(roles, list) else []:
        role_normalized = _normalized_match_text(role)
        matching_lines = [
            line
            for line in resume_lines
            if role_normalized in _normalized_match_text(line)
        ]
        if not matching_lines:
            continue
        has_valid_line = False
        for matching_line in matching_lines:
            clean = _plain_text(matching_line)
            role_portion = re.split(r"\s+[-–—]\s+", clean, maxsplit=1)[0]
            has_date = bool(_YEAR_RE.search(clean) or re.search(
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                clean,
                re.IGNORECASE,
            ))
            if role_portion == role_portion.upper() and has_date:
                has_valid_line = True
                break
        if not has_valid_line:
            malformed.append(role)
    return malformed


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
    job_type: str = "development",
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
APPLICATION TRACK: {job_type.upper()}
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


def _restore_resume_role(text: str, target_role: str) -> tuple[str, bool]:
    """Keep the request-specific ROLE marker stable across full-draft QA rewrites."""
    normalized_role = " ".join(target_role.split())
    replacement = f"ROLE: {normalized_role}"
    lines = text.strip().splitlines()

    for index, line in enumerate(lines):
        if re.match(r"^\s*ROLE:\s*", line, re.IGNORECASE):
            if line == replacement:
                return text.strip(), False
            lines[index] = replacement
            return "\n".join(lines).strip(), True

    name_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^\s*NAME:\s*", line, re.IGNORECASE)
        ),
        -1,
    )
    lines.insert(name_index + 1, replacement)
    return "\n".join(lines).strip(), True


def _restore_cover_letter_heading(text: str) -> tuple[str, bool]:
    """Keep the builder heading exact, first, and free of Markdown markers."""
    lines = text.strip().splitlines()
    heading_indices = [
        index
        for index, line in enumerate(lines)
        if _plain_text(line).casefold() == "cover letter"
    ]
    if heading_indices == [0] and lines[0].strip() == "Cover Letter":
        return text.strip(), False

    body = [
        line
        for index, line in enumerate(lines)
        if index not in heading_indices
    ]
    while body and not body[0].strip():
        body.pop(0)
    repaired = ["Cover Letter"]
    if body:
        repaired.extend(["", *body])
    return "\n".join(repaired).strip(), True


def _normalize_source_role_entries(
    text: str,
    source_resume: str,
) -> tuple[str, bool]:
    """Repair common model rewrites of verified role, entity, and date lines.

    The source role and the dates are already verified. This only moves them back
    into the builder's canonical two-line shape; it does not infer new content.
    """
    requirements = _extract_source_resume_requirements(source_resume)
    roles = requirements.get("roles", [])
    if not isinstance(roles, list) or not roles:
        return text.strip(), False

    lines = text.strip().splitlines()
    changed = False
    for role in roles:
        if not isinstance(role, str) or not role.strip():
            continue
        role_normalized = _normalized_match_text(role)
        if not role_normalized:
            continue

        for index, line in enumerate(lines):
            clean_line = _plain_text(line).strip()
            if _normalized_match_text(clean_line) == role_normalized:
                company_index = next(
                    (
                        candidate
                        for candidate in range(index + 1, len(lines))
                        if lines[candidate].strip()
                    ),
                    None,
                )
                if company_index is not None:
                    company_line = _plain_text(lines[company_index]).strip()
                    company_parts = [
                        part.strip() for part in company_line.split("|", 1)
                    ]
                    company = company_line
                    dates = ""
                    end_index = company_index
                    if (
                        len(company_parts) == 2
                        and _line_has_resume_date(company_parts[1])
                    ):
                        company, dates = company_parts
                    elif not _line_has_resume_date(company_line):
                        date_index = next(
                            (
                                candidate
                                for candidate in range(
                                    company_index + 1,
                                    len(lines),
                                )
                                if lines[candidate].strip()
                            ),
                            None,
                        )
                        if date_index is not None:
                            candidate_dates = _plain_text(
                                lines[date_index]
                            ).strip()
                            if _line_has_resume_date(candidate_dates):
                                dates = candidate_dates
                                end_index = date_index
                    if dates:
                        lines[index:end_index + 1] = [
                            company,
                            f"{role.upper()} - {dates}",
                        ]
                        changed = True
                        break

            role_company_match = re.match(
                r"^(.+?)\s+[-\u2013\u2014]\s+(.+)$",
                clean_line,
            )
            if role_company_match is not None:
                generated_role, company_line = role_company_match.groups()
                next_index = next(
                    (
                        candidate
                        for candidate in range(index + 1, len(lines))
                        if lines[candidate].strip()
                    ),
                    None,
                )
                if (
                    _normalized_match_text(generated_role) == role_normalized
                    and not _line_has_resume_date(company_line)
                    and next_index is not None
                ):
                    dates = _plain_text(lines[next_index]).strip()
                    if _line_has_resume_date(dates):
                        lines[index:next_index + 1] = [
                            company_line.strip(),
                            f"{role.upper()} - {dates}",
                        ]
                        changed = True
                        break

            parts = [part.strip() for part in line.split("|", 1)]
            if len(parts) != 2:
                continue
            entity, possible_role = parts
            inline_role_match = re.match(
                r"^(.+?)\s+[-\u2013\u2014]\s+(.+)$",
                _plain_text(possible_role).strip(),
            )
            if inline_role_match is not None:
                generated_role, dates = inline_role_match.groups()
                if (
                    _normalized_match_text(generated_role) == role_normalized
                    and _line_has_resume_date(dates)
                ):
                    lines[index:index + 1] = [
                        entity,
                        f"{role.upper()} - {dates.strip()}",
                    ]
                    changed = True
                    break
            if _normalized_match_text(possible_role) != role_normalized:
                continue

            next_index = next(
                (
                    candidate
                    for candidate in range(index + 1, len(lines))
                    if lines[candidate].strip()
                ),
                None,
            )
            if next_index is None:
                continue

            next_line = _plain_text(lines[next_index]).strip()
            next_parts = [part.strip() for part in next_line.split("|", 1)]
            context = ""
            dates = next_line
            if len(next_parts) == 2 and _line_has_resume_date(next_parts[1]):
                context, dates = next_parts
            if not _line_has_resume_date(dates):
                continue

            company_line = f"{entity} | {context}" if context else entity
            role_line = f"{role.upper()} - {dates}"
            lines[index:next_index + 1] = [company_line, role_line]
            changed = True
            break

    return "\n".join(lines).strip(), changed


def _line_has_resume_date(text: str) -> bool:
    return bool(
        _YEAR_RE.search(text)
        or re.search(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
            text,
            re.IGNORECASE,
        )
    )


def _normalize_resume_categories(text: str) -> tuple[str, bool]:
    """Convert common legacy skill shapes into the builder's CATEGORY syntax."""
    lines = text.strip().splitlines()
    changed = False
    index = 0

    while index < len(lines):
        section = _plain_text(lines[index]).upper()
        if section not in _CATEGORY_SECTION_NAMES:
            index += 1
            continue

        end = index + 1
        while end < len(lines):
            candidate = lines[end].strip()
            candidate_section = _plain_text(candidate).upper()
            if candidate == "---" or candidate_section in _RESUME_SECTION_NAMES:
                break
            end += 1

        block = lines[index + 1:end]
        normalized_block: list[str] = []
        for line in block:
            stripped = line.strip()
            category = re.match(
                r"^CATEGORY\s*:\s*(.+?)\s*\|\s*(.+)$",
                stripped,
                re.IGNORECASE,
            )
            if category:
                label, raw_values = category.groups()
                normalized_line = (
                    f"CATEGORY: {label.strip()} | "
                    f"{_normalize_category_values(raw_values)}"
                )
                normalized_block.append(normalized_line)
                if normalized_line != stripped:
                    changed = True
                continue

            legacy = re.match(
                r"^(?!CATEGORY\s*:)(?!\u25cf\s)([^:]{1,60}):\s*(.+)$",
                stripped,
                re.IGNORECASE,
            )
            if legacy:
                label, raw_values = legacy.groups()
                values = _normalize_category_values(raw_values)
                normalized_block.append(
                    f"CATEGORY: {label.strip()} | {values}"
                )
                changed = True
            else:
                normalized_block.append(line)

        content = [line.strip() for line in normalized_block if line.strip()]
        has_category = any(
            re.match(r"(?i)^CATEGORY\s*:\s*.+?\s*\|\s*.+", line)
            for line in content
        )
        if content and not has_category and all(
            line.startswith("\u25cf ") for line in content
        ):
            values = ", ".join(
                line[2:].strip().rstrip(".")
                for line in content
            )
            normalized_block = [
                "",
                f"CATEGORY: {section.title()} | {values}",
                "",
            ]
            changed = True

        lines[index + 1:end] = normalized_block
        index += 1 + len(normalized_block)

    return "\n".join(lines).strip(), changed


def _normalize_category_values(raw_values: str) -> str:
    values = [
        re.sub(r"\s+", " ", value).strip()
        for value in re.split(r"\s*[;,|]\s*", raw_values)
    ]
    return ", ".join(value for value in values if value)


def _resume_category_values(text: str, label: str) -> list[str]:
    expected = _normalized_match_text(label)
    for line in text.splitlines():
        match = re.match(
            r"(?i)^CATEGORY\s*:\s*(.+?)\s*\|\s*(.+)$",
            line.strip(),
        )
        if match and _normalized_match_text(match.group(1)) == expected:
            return [
                value.strip()
                for value in match.group(2).split(",")
                if value.strip()
            ]
    return []


def _resume_has_ai_content_outside_category(
    text: str,
    source_ai_tools: object,
) -> bool:
    content_lines: list[str] = []
    for line in text.splitlines():
        category = re.match(
            r"(?i)^CATEGORY\s*:\s*(.+?)\s*\|\s*(.+)$",
            line.strip(),
        )
        if (
            category
            and _normalized_match_text(category.group(1)) == "ai tools"
        ):
            continue
        if _plain_text(line).upper() == "AI TOOLS":
            continue
        content_lines.append(line)

    content = "\n".join(content_lines)
    terms: list[str] = []
    for tool in source_ai_tools if isinstance(source_ai_tools, list) else []:
        for term in re.split(r"\s+(?:and|&)\s+", tool, flags=re.IGNORECASE):
            clean = term.strip()
            if clean and clean.casefold() not in {
                existing.casefold() for existing in terms
            }:
                terms.append(clean)
    return any(
        re.search(
            rf"(?i)(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
            content,
        )
        for term in terms
    )


def _restore_source_ai_tools(
    text: str,
    source_resume: str,
) -> tuple[str, bool]:
    tools = _markdown_subsection_items(source_resume, "AI Tools")
    if not tools:
        return text.strip(), False

    desired = f"CATEGORY: AI Tools | {', '.join(tools)}"
    lines = text.strip().splitlines()
    for index, line in enumerate(lines):
        match = re.match(
            r"(?i)^CATEGORY\s*:\s*(.+?)\s*\|\s*(.+)$",
            line.strip(),
        )
        if match and _normalized_match_text(match.group(1)) == "ai tools":
            if line.strip() == desired:
                return text.strip(), False
            lines[index] = desired
            return "\n".join(lines).strip(), True

    preferred_sections = (
        "TECHNICAL SKILLS",
        "TOOLKIT",
        "CORE SKILLS",
        "SKILLS",
    )
    section_index = next(
        (
            index
            for section in preferred_sections
            for index, line in enumerate(lines)
            if _plain_text(line).upper() == section
        ),
        None,
    )
    if section_index is not None:
        end = section_index + 1
        while end < len(lines):
            candidate = lines[end].strip()
            candidate_section = _plain_text(candidate).upper()
            if candidate == "---" or candidate_section in _RESUME_SECTION_NAMES:
                break
            end += 1
        while end > section_index + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, desired)
        return "\n".join(lines).strip(), True

    return text.strip(), False


def _consolidate_resume_categories(text: str) -> tuple[str, bool]:
    """Merge repeated compact skill sections into the first reference-style grid."""
    lines = text.strip().splitlines()
    sections: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        section = _plain_text(lines[index]).upper()
        if section not in _CATEGORY_SECTION_NAMES or section == "TOOLKIT":
            index += 1
            continue

        end = index + 1
        while end < len(lines):
            candidate = lines[end].strip()
            candidate_section = _plain_text(candidate).upper()
            if candidate == "---" or candidate_section in _RESUME_SECTION_NAMES:
                break
            end += 1
        content = [line.strip() for line in lines[index + 1:end] if line.strip()]
        if content and all(
            re.match(r"(?i)^CATEGORY\s*:\s*.+?\s*\|\s*.+", line)
            for line in content
        ):
            sections.append((index, end))
        index = max(end, index + 1)

    if len(sections) < 2:
        return text.strip(), False

    merged: dict[str, tuple[str, list[str]]] = {}
    for section_index, (start, end) in enumerate(sections):
        for line in lines[start + 1:end]:
            match = re.match(
                r"(?i)^CATEGORY\s*:\s*(.+?)\s*\|\s*(.+)$",
                line.strip(),
            )
            if match is None:
                continue
            label, raw_values = match.groups()
            key = _normalized_match_text(label)
            if section_index > 0 and key in merged:
                label = _expanded_category_label(label)
                key = _normalized_match_text(label)
            display_label, values = merged.setdefault(key, (label.strip(), []))
            for value in re.split(r"\s*[;,|]\s*", raw_values):
                clean_value = value.strip()
                if clean_value and _normalized_match_text(clean_value) not in {
                    _normalized_match_text(existing) for existing in values
                }:
                    values.append(clean_value)
            merged[key] = (display_label, values)

    first_start, first_end = sections[0]
    replacement = [lines[first_start], ""]
    replacement.extend(
        f"CATEGORY: {label} | {', '.join(values)}"
        for label, values in merged.values()
    )
    replacement.append("")
    lines[first_start:first_end] = replacement

    offset = len(replacement) - (first_end - first_start)
    for start, end in reversed(sections[1:]):
        adjusted_start = start + offset
        adjusted_end = end + offset
        del lines[adjusted_start:adjusted_end]

    consolidated = "\n".join(lines).strip()
    consolidated = re.sub(
        r"(?m)^---\s*$\n(?:\s*\n)*^---\s*$",
        "---",
        consolidated,
    )
    return consolidated.strip(), True


def _expanded_category_label(label: str) -> str:
    normalized = _normalized_match_text(label)
    if normalized == "design skills":
        return "Design Delivery"
    if normalized == "technical skills":
        return "Technical Delivery"
    return f"Additional {label.strip()}"


def _restore_source_dates(text: str, source_resume: str) -> tuple[str, bool]:
    lines = text.strip().splitlines()
    changed = False

    source_roles = _extract_source_role_dates(source_resume)
    generated_role_lines = [
        (index, role)
        for index, line in enumerate(lines)
        if (role := _resume_role_line_title(line)) is not None
    ]
    assignments: dict[int, list[tuple[int, str, str]]] = {}

    for source_index, (role, dates) in enumerate(source_roles):
        best_line_index: int | None = None
        best_score = 0.0
        for line_index, generated_role in generated_role_lines:
            score = _role_title_similarity(role, generated_role)
            if score > best_score:
                best_line_index = line_index
                best_score = score
        if best_line_index is not None and best_score >= 0.65:
            assignments.setdefault(best_line_index, []).append(
                (source_index, role, dates)
            )

    for line_index in sorted(assignments, reverse=True):
        replacements = [
            f"{role.upper()} - {dates}"
            for _, role, dates in sorted(assignments[line_index])
        ]
        if lines[line_index:line_index + 1] != replacements:
            lines[line_index:line_index + 1] = replacements
            changed = True

    for institution, credential, dates in _extract_source_education_dates(
        source_resume
    ):
        current_section: str | None = None
        for index, line in enumerate(lines):
            section = _resume_section_name(line)
            if section is not None:
                current_section = section
                continue
            if current_section not in {"EDUCATION", "EDUCATIONAL ATTAINMENT"}:
                continue
            if not _education_anchor_matches(institution, line):
                continue
            replacement = f"{_reference_safe_text(institution)} | {dates}"
            if lines[index] != replacement:
                lines[index] = replacement
                changed = True

            credential_normalized = _normalized_match_text(credential)
            other_lines = "\n".join(
                candidate
                for candidate_index, candidate in enumerate(lines)
                if candidate_index != index
            )
            if (
                credential_normalized
                and credential_normalized not in _normalized_match_text(other_lines)
            ):
                lines.insert(index + 1, credential)
                changed = True
            break

    return "\n".join(lines).strip(), changed


def _resume_role_line_title(line: str) -> str | None:
    if re.match(r"^\s*(?:[-+*\u25cf\u2022]|\d+[.)])\s+", line):
        return None
    clean = _plain_text(line)
    match = re.match(r"^(.+?)\s+[-\u2013\u2014]\s+(.+)$", clean)
    if match is None:
        return None
    role = match.group(1).strip()
    letters = re.sub(r"[^A-Za-z]", "", role)
    if not letters or _plain_text(role).upper() in _RESUME_SECTION_NAMES:
        return None
    return role


def _role_title_similarity(source_role: str, generated_role: str) -> float:
    source_tokens = set(_normalized_match_text(source_role).split())
    generated_tokens = set(_normalized_match_text(generated_role).split())
    if not source_tokens or not generated_tokens:
        return 0.0
    overlap = len(source_tokens & generated_tokens)
    if overlap == 0:
        return 0.0
    source_coverage = overlap / len(source_tokens)
    generated_coverage = overlap / len(generated_tokens)
    return (
        2 * source_coverage * generated_coverage
        / (source_coverage + generated_coverage)
    )


def _extract_source_role_dates(source_resume: str) -> list[tuple[str, str]]:
    work_lines = _markdown_section_lines(
        source_resume,
        {
            "Work Experience",
            "Work Experiences",
            "Related Work Experience",
            "Related Work Experiences",
            "Other Experience",
            "Other Experiences",
            "Creative Experience",
        },
    )
    entries: list[tuple[str, str]] = []
    current_roles: list[str] = []

    for raw_line in work_lines:
        line = raw_line.strip()
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current_roles = [
                role
                for role in re.split(r"\s*/\s*", _plain_text(heading.group(1)))
                if role
            ]
            continue

        explicit = re.match(r"^(.+?):\s*(.+)$", _plain_text(line))
        if (
            explicit
            and any(
                _normalized_match_text(explicit.group(1))
                == _normalized_match_text(role)
                for role in current_roles
            )
            and _YEAR_RE.search(explicit.group(2))
        ):
            entries.append(
                (
                    _plain_text(explicit.group(1)),
                    _canonical_source_dates(explicit.group(2)),
                )
            )
            continue

        if (
            len(current_roles) == 1
            and _YEAR_RE.search(line)
            and not re.match(r"^\s*[-\u25cf\u2022]", line)
        ):
            entries.append(
                (current_roles[0], _canonical_source_dates(line))
            )

    return entries


def _extract_source_education_dates(
    source_resume: str,
) -> list[tuple[str, str, str]]:
    education_lines = _markdown_section_lines(
        source_resume,
        {"Education", "Educational Attainment"},
    )
    entries: list[tuple[str, str, str]] = []
    index = 0
    while index < len(education_lines):
        heading = re.match(r"^###\s+(.+?)\s*$", education_lines[index].strip())
        if heading is None:
            index += 1
            continue

        institution = _plain_text(heading.group(1))
        credential = ""
        dates = ""
        cursor = index + 1
        while cursor < len(education_lines):
            candidate = education_lines[cursor].strip()
            if re.match(r"^###\s+", candidate):
                break
            credential_match = re.match(r"^\*\*(.+?)\*\*", candidate)
            if credential_match and not credential:
                credential = _plain_text(credential_match.group(1))
            if _YEAR_RE.search(candidate) and not dates:
                dates = _canonical_source_dates(candidate)
            cursor += 1

        if institution and credential and dates:
            entries.append((institution, credential, dates))
        index = cursor

    return entries


def _canonical_source_dates(text: str) -> str:
    clean = _plain_text(text).replace("\u2013", " - ").replace("\u2014", " - ")
    clean = re.sub(r"\s+-\s+", " - ", clean)
    parts = [part.strip() for part in clean.split("|")]
    if len(parts) == 2 and re.search(
        r"\b(?:co-?op|internship|placement)\b",
        parts[0],
        re.IGNORECASE,
    ):
        return f"{parts[1]} ({parts[0]})"
    return "; ".join(parts)


def _education_anchor_matches(institution: str, candidate: str) -> bool:
    candidate_anchor = candidate.split("|", 1)[0]
    institution_normalized = _normalized_match_text(institution)
    candidate_normalized = _normalized_match_text(candidate_anchor)
    if (
        candidate_normalized
        and (
            institution_normalized in candidate_normalized
            or candidate_normalized in institution_normalized
        )
    ):
        return True
    acronyms = re.findall(r"\b[A-Z]{2,}\b", institution)
    return any(
        re.search(rf"\b{re.escape(acronym)}\b", candidate_anchor, re.IGNORECASE)
        for acronym in acronyms
    )


def _normalize_em_dashes(text: str) -> tuple[str, int]:
    normalized, replacements = re.subn(r"\s*\u2014\s*", ", ", text)
    normalized = re.sub(r",\s*,", ",", normalized)
    return normalized.strip(), replacements


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


def _estimate_missing_ats_score(text: str) -> tuple[str, bool]:
    """Add a reproducible fallback score when the model supplies keyword lists only."""
    if _VALID_ATS_SCORE_RE.search(text):
        return text.strip(), False

    applied = _analysis_list_item_count(
        text,
        "KEYWORDS_APPLIED",
        "KEYWORDS_MISSING",
    )
    missing = _analysis_list_item_count(
        text,
        "KEYWORDS_MISSING",
        "KEY_DECISIONS",
    )
    total = applied + missing
    if total == 0:
        return text.strip(), False

    score = round(100 * applied / total)
    retained_lines = [
        line
        for line in text.strip().splitlines()
        if not re.search(r"\bATS_SCORE\b", line, re.IGNORECASE)
    ]
    retained = "\n".join(retained_lines).strip()
    return f"ATS_SCORE: {score}\n\n{retained}".strip(), True


def _analysis_list_item_count(text: str, start: str, end: str) -> int:
    match = re.search(
        rf"(?ims)^\s*{re.escape(start)}:\s*$\n(.*?)^\s*{re.escape(end)}:\s*$",
        text,
    )
    if match is None:
        return 0
    return sum(
        1
        for line in match.group(1).splitlines()
        if re.match(r"^\s*[-*â—â€¢]\s+\S", line)
    )
