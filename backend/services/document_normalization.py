from __future__ import annotations

import re


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
