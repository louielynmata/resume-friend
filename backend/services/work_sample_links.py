from __future__ import annotations

import re
from collections.abc import Mapping


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


def required_work_sample_links(
    instructions: str,
    job_type: str,
) -> dict[str, str]:
    normalized_job_type = job_type.strip().lower()
    if normalized_job_type not in _REQUIRED_LABELS:
        raise ValueError("job_type must be design or development.")

    links: dict[str, str] = {}
    invalid: list[str] = []
    for label in _REQUIRED_LABELS[normalized_job_type]:
        pattern = re.compile(
            rf"\[{re.escape(label)}\]\((https?://[^)\s]+)\)",
            re.IGNORECASE,
        )
        urls = list(dict.fromkeys(pattern.findall(instructions)))
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
