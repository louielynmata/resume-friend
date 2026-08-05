from __future__ import annotations

import re


RESUME_SECTION_NAMES = frozenset(
    {
        "PROFESSIONAL SUMMARY",
        "CORE SKILLS",
        "DESIGN SKILLS",
        "TECHNICAL SKILLS",
        "CREATIVE SKILLS",
        "SKILLS",
        "TOOLKIT",
        "WORK EXPERIENCE",
        "RELATED WORK EXPERIENCES",
        "OTHER EXPERIENCES",
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

CATEGORY_SECTION_NAMES = frozenset(
    {
        "CORE SKILLS",
        "DESIGN SKILLS",
        "TECHNICAL SKILLS",
        "CREATIVE SKILLS",
        "SKILLS",
        "TOOLKIT",
    }
)

# System-prompt section labels that the AI occasionally echoes are never headers.
BLOCKED_SECTION_NAMES = frozenset(
    {
        "INSTRUCTIONS",
        "WRITING STYLE EXAMPLES",
        "WRITING STYLE",
        "TRANSCRIPT",
        "ANALYSIS",
    }
)

ENTRY_BULLET_SECTIONS = frozenset(
    {
        "PROJECTS",
        "NOTABLE PROJECTS",
        "WORK EXPERIENCE",
        "RELATED WORK EXPERIENCES",
        "OTHER EXPERIENCES",
        "EXPERIENCE",
        "CREATIVE EXPERIENCE",
    }
)


_NON_CANONICAL_BULLET_RE = re.compile(
    r"^[ \t]*(?:[-+*\u2022\u25e6\u25aa\u2023]|\d+\.)[ \t]+"
)


def normalize_resume_bullets(text: str) -> tuple[str, int]:
    """Return resume text with every line-leading bullet normalized to U+25CF."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    replacements = 0

    for line in normalized.split("\n"):
        repaired, count = _NON_CANONICAL_BULLET_RE.subn("\u25cf ", line, count=1)
        lines.append(repaired)
        replacements += count

    return "\n".join(lines), replacements
