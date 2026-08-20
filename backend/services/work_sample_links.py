from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Iterator


DESIGN_PORTFOLIO_LABEL = "Design Portfolio (Reel and PDF)"
CASE_STUDIES_LABEL = "Case Studies and Product Work"

_REQUIRED_LABELS = {
    "design": (DESIGN_PORTFOLIO_LABEL, CASE_STUDIES_LABEL),
    "development": (CASE_STUDIES_LABEL,),
}


class RequiredWorkSampleLinkError(ValueError):
    def __init__(self, labels: tuple[str, ...]):
        self.labels = labels
        super().__init__(
            "Required work-sample Markdown link is missing or ambiguous for: "
            + ", ".join(labels)
        )


@dataclass(frozen=True)
class MarkdownLink:
    start: int
    end: int
    label: str
    url: str


def iter_markdown_links(text: str) -> Iterator[MarkdownLink]:
    """Yield HTTP(S) Markdown links while preserving balanced destinations."""
    position = 0
    label_pattern = re.compile(r"\[([^\]\r\n]+)\]\(")
    while position < len(text):
        label_match = label_pattern.search(text, position)
        if label_match is None:
            return

        label_start = label_match.start()
        label = label_match.group(1)
        url_start = label_match.end()
        if not text.startswith(("http://", "https://"), url_start):
            position = label_start + 1
            continue

        depth = 0
        cursor = url_start
        while cursor < len(text):
            character = text[cursor]
            if character.isspace():
                break
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    yield MarkdownLink(
                        start=label_start,
                        end=cursor + 1,
                        label=label,
                        url=text[url_start:cursor],
                    )
                    position = cursor + 1
                    break
                depth -= 1
            cursor += 1
        else:
            return

        if cursor >= len(text) or text[cursor].isspace():
            position = label_start + 1


def required_work_sample_links(
    instructions: str,
    job_type: str,
) -> dict[str, str]:
    normalized_job_type = job_type.strip().lower()
    if normalized_job_type not in _REQUIRED_LABELS:
        raise ValueError("job_type must be design or development.")

    links: dict[str, str] = {}
    invalid: list[str] = []
    parsed_links = tuple(iter_markdown_links(instructions))
    for label in _REQUIRED_LABELS[normalized_job_type]:
        urls = list(
            dict.fromkeys(
                link.url for link in parsed_links if link.label == label
            )
        )
        if len(urls) != 1:
            invalid.append(label)
            continue
        links[label] = urls[0]

    if invalid:
        raise RequiredWorkSampleLinkError(tuple(invalid))
    return links


def format_work_samples_line(links: Mapping[str, str]) -> str:
    rendered = " | ".join(f"[{label}]({url})" for label, url in links.items())
    return f"WORK_SAMPLES: {rendered}"
