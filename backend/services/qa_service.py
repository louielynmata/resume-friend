from __future__ import annotations

import re
from urllib.parse import urlsplit

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
_RESUME_SECTION_NAMES = frozenset(
    {
        "PROFESSIONAL SUMMARY",
        "CORE SKILLS",
        "DESIGN SKILLS",
        "TECHNICAL SKILLS",
        "CREATIVE SKILLS",
        "SKILLS",
        "TOOLKIT",
        "WORK EXPERIENCE",
        "EXPERIENCE",
        "CREATIVE EXPERIENCE",
        "EDUCATION",
        "EDUCATIONAL ATTAINMENT",
        "CERTIFICATIONS",
        "CERTIFICATIONS AND AWARDS",
        "ACHIEVEMENTS",
        "AWARDS AND ACHIEVEMENTS",
        "PROJECTS",
        "NOTABLE PROJECTS",
        "NOTABLE CLIENTS",
    }
)
_CATEGORY_SECTION_NAMES = frozenset(
    {"CORE SKILLS", "DESIGN SKILLS", "TECHNICAL SKILLS", "CREATIVE SKILLS", "SKILLS", "TOOLKIT"}
)


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

    trusted_materials = source_materials or source_resume
    if trusted_materials.strip():
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

    required_header_lines = _extract_required_block(
        source_materials,
        "RESUME HEADER - REQUIRED EXACT VALUES:",
        "END REQUIRED RESUME HEADER",
    )
    missing_header_lines = [
        line
        for line in required_header_lines
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


def _extract_required_block(text: str, start: str, end: str) -> list[str]:
    match = re.search(
        rf"(?ims)^\s*{re.escape(start)}\s*$\n(.*?)^\s*{re.escape(end)}\s*$",
        text,
    )
    if not match:
        return []
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


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


def _extract_source_resume_requirements(source_resume: str) -> dict[str, object]:
    work_lines = _markdown_section_lines(
        source_resume,
        {
            "Work Experience",
            "Work Experiences",
            "Related Work Experience",
            "Related Work Experiences",
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
    """Repair the common `entity | role` plus `context | dates` model rewrite.

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

        # A canonical uppercase role/date line already exists.
        if not _malformed_required_role_lines("\n".join(lines), [role]):
            continue

        for index, line in enumerate(lines):
            parts = [part.strip() for part in line.split("|", 1)]
            if len(parts) != 2:
                continue
            entity, possible_role = parts
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
        for index, line in enumerate(lines):
            if not _education_anchor_matches(institution, line):
                continue
            replacement = f"{institution} | {dates}"
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

        explicit = re.match(r"^\*\*(.+?):\*\*\s*(.+)$", line)
        if explicit and _YEAR_RE.search(explicit.group(2)):
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
