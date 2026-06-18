import re
from datetime import date, datetime, timedelta
from typing import Optional


LABELLED_FIELD_PATTERNS = {
    "position": [
        re.compile(r"^(?:job\s+title|title|position|role)\s*[:\-]\s*(.+)$", re.I),
    ],
    "company": [
        re.compile(r"^(?:company|employer|organization|client)\s*[:\-]\s*(.+)$", re.I),
    ],
    "location": [
        re.compile(r"^(?:location|work\s+location|job\s+location)\s*[:\-]\s*(.+)$", re.I),
    ],
    "date_job_posted": [
        re.compile(r"^(?:date\s+posted|posted(?:\s+on)?|posting\s+date)\s*[:\-]\s*(.+)$", re.I),
    ],
}

GENERIC_TOP_LINES = {
    "about the job",
    "job description",
    "full job description",
    "overview",
    "summary",
    "apply now",
}


def _clean_line(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -|\t")
    return value.strip()


def _clean_field(value: str) -> Optional[str]:
    value = _clean_line(value)
    if not value:
        return None
    value = re.sub(r"\s+\|\s+.*$", "", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" ,;-")
    return value or None


def _normalize_amount(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    return float(match.group(0))


def _parse_date(value: str) -> Optional[str]:
    text = _clean_line(value).lower()
    today = date.today()

    if text == "today":
        return today.isoformat()
    if text == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    relative_match = re.search(r"(\d+)\s+(day|week|month)s?\s+ago", text)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        delta_days = amount if unit == "day" else amount * 7 if unit == "week" else amount * 30
        return (today - timedelta(days=delta_days)).isoformat()

    normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value.strip(), flags=re.I)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(normalized, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_labelled(lines: list[str], field: str) -> Optional[str]:
    for line in lines[:40]:
        for pattern in LABELLED_FIELD_PATTERNS[field]:
            match = pattern.match(line)
            if match:
                return _clean_field(match.group(1))
    return None


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    return match.group(0) if match else None


def _extract_salary(text: str) -> tuple[Optional[float], Optional[float]]:
    annual_match = re.search(
        r"\$?\s*([\d,]+(?:\.\d+)?)\s*(?:-|to)?\s*\$?\s*([\d,]+(?:\.\d+)?)?\s*(?:per\s+year|a\s+year|/year|annually|annual)",
        text,
        re.I,
    )
    hourly_match = re.search(
        r"\$?\s*([\d,]+(?:\.\d+)?)\s*(?:-|to)?\s*\$?\s*([\d,]+(?:\.\d+)?)?\s*(?:per\s+hour|an\s+hour|a\s+hour|/hour|hourly|hr\b)",
        text,
        re.I,
    )

    annual = _normalize_amount(annual_match.group(1)) if annual_match else None
    hourly = _normalize_amount(hourly_match.group(1)) if hourly_match else None

    return annual, hourly


def _looks_like_location(line: str) -> bool:
    lowered = line.lower()
    return bool(
        re.search(r"\b(remote|hybrid|on-?site|relocate)\b", lowered)
        or re.search(r"\b[a-z .'-]+,\s*[A-Z]{2}\b", line)
        or re.search(r"\b[a-z .'-]+,\s*[A-Z][a-z]+\b", line)
    )


def _looks_like_company(line: str) -> bool:
    lowered = line.lower()
    if _looks_like_location(line):
        return False
    if any(token in lowered for token in ("full-time", "part-time", "contract", "internship", "temporary")):
        return False
    return bool(re.search(r"\b(inc|llc|ltd|corp|company|technologies|technology|systems|group|studio|labs)\b", lowered)) or (
        1 <= len(line.split()) <= 6 and len(line) <= 60
    )


def _extract_top_position(lines: list[str]) -> Optional[str]:
    for line in lines[:12]:
        cleaned = _clean_field(line)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in GENERIC_TOP_LINES:
            continue
        if _looks_like_location(cleaned):
            continue
        if re.search(r"\b(full-time|part-time|contract|salary|apply)\b", lowered):
            continue
        if len(cleaned) > 80:
            continue
        return cleaned
    return None


def _extract_top_company(lines: list[str], position: Optional[str]) -> Optional[str]:
    for line in lines[:15]:
        cleaned = _clean_field(line)
        if not cleaned or cleaned == position:
            continue
        if _looks_like_company(cleaned):
            return cleaned
    return None


def _extract_location(lines: list[str]) -> Optional[str]:
    labelled = _extract_labelled(lines, "location")
    if labelled:
        return labelled
    for line in lines[:20]:
        cleaned = _clean_field(line)
        if cleaned and _looks_like_location(cleaned):
            return cleaned
    return None


def extract_job_meta(text: str) -> dict[str, Optional[str] | Optional[float]]:
    lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]

    position = _extract_labelled(lines, "position") or _extract_top_position(lines)
    company = _extract_labelled(lines, "company") or _extract_top_company(lines, position)
    location = _extract_location(lines)
    date_value = _extract_labelled(lines, "date_job_posted")
    salary_annual, salary_hourly = _extract_salary(text)

    return {
        "position": position,
        "company": company,
        "location": location,
        "salary_annual": salary_annual,
        "salary_hourly": salary_hourly,
        "date_job_posted": _parse_date(date_value) if date_value else None,
        "contact_email": _extract_email(text),
    }
