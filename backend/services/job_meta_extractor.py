"""
Job metadata extractor.

Strategy — two layers:
  1. Regex / heuristics (fast, free, offline-safe).
  2. Lightweight AI fallback (Haiku or GPT-4o-mini) when position or company
     couldn't be found by regex.  Only fires when an API key is configured.
"""

import json
import re
from datetime import date, datetime, timedelta
from typing import Optional


# ── Separators & noise ────────────────────────────────────────────────────────

# Middle-dot separators used by LinkedIn / Glassdoor:
# "Software Engineer · Google · Calgary, AB · 3 days ago"
_SEP_PAT = re.compile(r"\s*[·|•]\s*")

_BULLET_PAT = re.compile(r"^[•·▸▶►◆●■□▪▫\-\*]+\s*")

GENERIC_LINES = {
    "about the job", "job description", "full job description", "overview",
    "summary", "apply now", "quick apply", "apply", "description", "job details",
    "job information", "about this role", "about the role", "about this position",
    "the opportunity", "position overview", "role overview", "responsibilities",
    "requirements", "qualifications", "benefits", "what you'll do", "who we are",
    "what we offer", "why join us", "our team",
}

_SKIP_POSITION = re.compile(
    r"\b(full[- ]time|part[- ]time|contract|salary|apply|internship|"
    r"permanent|temporary|remote|hybrid|on[- ]?site|urgent|immediate|"
    r"relocation|visa|authorized)\b",
    re.I,
)

_COMPANY_NOISE = re.compile(
    r"\b(full[- ]time|part[- ]time|contract|remote|hybrid|on[- ]?site|"
    r"permanent|temporary|internship|\d+\s*(?:day|week|month|year)s?\s+ago|"
    r"easy apply|quick apply)\b",
    re.I,
)


# ── Labelled field patterns ────────────────────────────────────────────────────

_LABELLED: dict[str, list[re.Pattern]] = {
    "position": [
        re.compile(
            r"^(?:job\s+title|title|position|role|opening|vacancy|job)\s*[:\-]\s*(.+)$",
            re.I,
        ),
        re.compile(r"^we(?:'re|re| are)\s+(?:hiring|looking\s+for)\s+(?:a\s+|an\s+)?(.+)$", re.I),
        re.compile(r"^(?:hiring|looking\s+for)\s*[:\-]\s*(.+)$", re.I),
    ],
    "company": [
        re.compile(
            r"^(?:company|employer|organization|client|hiring\s+company|posted\s+by"
            r"|company\s+name)\s*[:\-]\s*(.+)$",
            re.I,
        ),
    ],
    "location": [
        re.compile(
            r"^(?:location|work\s+location|job\s+location|office\s+location|"
            r"work\s+type|work\s+arrangement|work\s+model)\s*[:\-]\s*(.+)$",
            re.I,
        ),
    ],
    "date_job_posted": [
        re.compile(
            r"^(?:date\s+posted|posted(?:\s+on)?|posting\s+date|listed(?:\s+on)?|"
            r"date\s+listed)\s*[:\-]\s*(.+)$",
            re.I,
        ),
    ],
}


# ── Text helpers ──────────────────────────────────────────────────────────────

def _clean_line(raw: str) -> str:
    line = _BULLET_PAT.sub("", raw)
    return re.sub(r"\s+", " ", line).strip(" -|\t")


def _clean_field(value: str) -> Optional[str]:
    value = _clean_line(value)
    if not value:
        return None
    # Strip trailing pipe/dot-separated metadata
    value = re.sub(r"\s+[|·•]\s+.*$", "", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" ,;-")
    return value or None


# ── Location helpers ──────────────────────────────────────────────────────────

_CANADIAN_PROVINCES = {
    "AB", "BC", "ON", "QC", "MB", "SK", "NS", "NB", "PE", "NL",
    "YT", "NT", "NU", "Alberta", "British Columbia", "Ontario", "Quebec", "Manitoba", "Saskatchewan",
    "Nova Scotia", "New Brunswick", "Prince Edward Island", "Newfoundland and Labrador",
    "Yukon", "Northwest Territories", "Nunavut", "Calgary", "Edmonton", "Toronto", "Vancouver", "Montreal", "Ottawa", "Winnipeg", "Saskatoon", "Regina", "Halifax", "Fredericton", "Charlottetown", "St. John's", "Yellowknife", "Whitehorse", "Iqaluit", "Ontario"
}

_WORK_ARRANGEMENT = re.compile(
    r"\b(remote|hybrid|on[- ]?site|work\s+from\s+(?:home|anywhere)|wfh|relocate)\b",
    re.I,
)


def _looks_like_location(line: str) -> bool:
    if _WORK_ARRANGEMENT.search(line):
        return True
    # "City, AB" — check the two-letter code is a known Canadian province
    m = re.search(r"\b[A-Za-z .'-]+,\s*([A-Z]{2})\b", line)
    if m and m.group(1) in _CANADIAN_PROVINCES:
        return True
    # Generic "City, ST" or "City, Province/State" pattern
    if re.search(r"\b[A-Za-z .'-]+,\s*[A-Z][a-z]{1,}\b", line):
        return True
    # Country names
    if re.search(
        r"\b(canada|united states|usa|u\.s\.a\.|uk|united kingdom|australia|worldwide|anywhere)\b",
        line, re.I,
    ):
        return True
    return False


# ── Salary ────────────────────────────────────────────────────────────────────

def _k_to_float(raw: str) -> Optional[float]:
    """'80K' → 80000.0, '80,000' → 80000.0, '80.5' → 80.5"""
    cleaned = raw.replace(",", "").strip()
    m = re.match(r"^([\d.]+)\s*([kK])?$", cleaned)
    if not m:
        return None
    num = float(m.group(1))
    return num * 1000 if m.group(2) else num


_ANNUAL_KEYWORDS = r"(?:per\s+year|a\s+year|/\s*year|annually|annual\b)"
_HOURLY_KEYWORDS = r"(?:per\s+hour|an?\s+hour|/\s*hr\b|/\s*hour\b|hourly\b)"
_CURRENCY    = r"(?:CAD|USD|AUD|GBP|\$)"
_AMOUNT      = r"([\d,]+(?:\.\d+)?)\s*[kK]?"
_RANGE_SEP   = r"(?:\s*[-–—to]+\s*" + _CURRENCY + r"?\s*" + _AMOUNT + r")?"


def _extract_salary(text: str) -> tuple[Optional[float], Optional[float]]:
    annual: Optional[float] = None
    hourly: Optional[float] = None

    # Annual with explicit keyword
    annual_pat = re.compile(
        _CURRENCY + r"?\s*" + _AMOUNT + _RANGE_SEP + r"\s*" + _ANNUAL_KEYWORDS,
        re.I,
    )
    m = annual_pat.search(text)
    if m:
        annual = _k_to_float(m.group(1))

    # Hourly with explicit keyword
    hourly_pat = re.compile(
        _CURRENCY + r"?\s*" + _AMOUNT + _RANGE_SEP + r"\s*" + _HOURLY_KEYWORDS,
        re.I,
    )
    m = hourly_pat.search(text)
    if m:
        hourly = _k_to_float(m.group(1))

    # Fallback: bare K-notation without annual/hourly qualifier → treat as annual
    if annual is None:
        for m in re.finditer(r"\$\s*([\d,]+(?:\.\d+)?)\s*[kK]\b", text, re.I):
            val = _k_to_float(m.group(1))
            if val and val >= 20000:   # sanity: annual must be >= $20K
                annual = val
                break

    return annual, hourly


# ── Date ──────────────────────────────────────────────────────────────────────

def _parse_date(value: str) -> Optional[str]:
    text = _clean_line(value).lower()
    today = date.today()

    if text in ("today", "just now", "just posted"):
        return today.isoformat()
    if text == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    m = re.search(r"(\d+)\s+(day|week|month)s?\s+ago", text)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        days = amount if unit == "day" else amount * 7 if unit == "week" else amount * 30
        return (today - timedelta(days=days)).isoformat()

    normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value.strip(), flags=re.I)
    for fmt in (
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y",
        "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
        "%d %B %Y", "%d %b %Y", "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(normalized.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ── Labelled extraction ───────────────────────────────────────────────────────

def _extract_labelled(lines: list[str], field: str) -> Optional[str]:
    for line in lines[:60]:
        for pat in _LABELLED[field]:
            m = pat.match(line)
            if m:
                val = _clean_field(m.group(1))
                if val and len(val) < 150:
                    return val
    return None


def _extract_email(text: str) -> Optional[str]:
    m = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    return m.group(0) if m else None


# ── Position extraction ───────────────────────────────────────────────────────

def _extract_top_position(lines: list[str]) -> Optional[str]:
    for line in lines[:25]:
        # Split on LinkedIn/Glassdoor separators; first segment is often the title
        parts = [p for p in _SEP_PAT.split(line) if p.strip()]
        candidate = _clean_field(parts[0]) if parts else None
        if not candidate:
            continue
        if candidate.lower() in GENERIC_LINES:
            continue
        if _looks_like_location(candidate):
            continue
        if _SKIP_POSITION.search(candidate):
            continue
        word_count = len(candidate.split())
        if word_count < 1 or word_count > 9:
            continue
        if len(candidate) > 100:
            continue
        # Titles don't end with a full stop
        if candidate.endswith("."):
            continue
        return candidate
    return None


# ── Company extraction ────────────────────────────────────────────────────────

_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|corp|co\b|company|technologies|technology|systems|group|"
    r"studio|labs|solutions|services|consulting|agency|media|software|digital|"
    r"creative|design|health|capital|ventures|partners|industries|enterprises|"
    r"international|global|communications|networks|holdings)\b",
    re.I,
)


def _looks_like_company(line: str) -> bool:
    if not line or _looks_like_location(line):
        return False
    if _COMPANY_NOISE.search(line):
        return False
    if _COMPANY_SUFFIXES.search(line):
        return True
    words = line.split()
    # Short, title-cased phrase without sentence punctuation → likely a brand name
    return (
        1 <= len(words) <= 6
        and len(line) <= 60
        and not line.endswith(".")
        and not re.search(r"\d{4}", line)  # years suggest dates, not companies
    )


def _extract_top_company(lines: list[str], position: Optional[str]) -> Optional[str]:
    for line in lines[:25]:
        # Split on separators: handle "Title · Company · Location · Date"
        parts = [_clean_field(p) for p in _SEP_PAT.split(line) if _clean_field(p)]
        for part in parts:
            if part and part != position and not _looks_like_location(part):
                if _looks_like_company(part):
                    return part

        cleaned = _clean_field(line)
        if cleaned and cleaned != position and cleaned.lower() not in GENERIC_LINES:
            if _looks_like_company(cleaned):
                return cleaned

    # Scan deeper for "About [CompanyName]" sections
    about_pat = re.compile(r"^about\s+([A-Z][A-Za-z0-9 &.,'\-]{1,50})$", re.I)
    for line in lines:
        m = about_pat.match(line)
        if m:
            candidate = _clean_field(m.group(1))
            if (
                candidate
                and candidate.lower() not in GENERIC_LINES
                and not _looks_like_location(candidate)
                and len(candidate.split()) <= 6
            ):
                return candidate

    return None


# ── Location extraction ───────────────────────────────────────────────────────

def _extract_location(lines: list[str]) -> Optional[str]:
    labelled = _extract_labelled(lines, "location")
    if labelled:
        return labelled
    for line in lines[:35]:
        for part in _SEP_PAT.split(line):
            cleaned = _clean_field(part)
            if cleaned and _looks_like_location(cleaned) and len(cleaned.split()) <= 8:
                return cleaned
    return None


# ── Regex layer ───────────────────────────────────────────────────────────────

def _regex_extract(text: str) -> dict:
    lines = [_clean_line(ln) for ln in text.splitlines() if _clean_line(ln)]

    position   = _extract_labelled(lines, "position") or _extract_top_position(lines)
    company    = _extract_labelled(lines, "company")  or _extract_top_company(lines, position)
    location   = _extract_location(lines)
    date_raw   = _extract_labelled(lines, "date_job_posted")
    ann, hrly  = _extract_salary(text)

    return {
        "position":        position,
        "company":         company,
        "location":        location,
        "salary_annual":   ann,
        "salary_hourly":   hrly,
        "date_job_posted": _parse_date(date_raw) if date_raw else None,
        "contact_email":   _extract_email(text),
    }


# ── AI fallback ───────────────────────────────────────────────────────────────

_AI_SYSTEM = (
    "You are a precise data extractor. Given a job description, extract the listed fields. "
    "Return ONLY valid JSON — no markdown, no explanation. Use null for any field not explicitly stated."
)

_AI_SCHEMA = """{
  "position": "exact job title or null",
  "company": "company name or null",
  "location": "city/province or work arrangement (Remote/Hybrid) or null",
  "salary_annual": <number or null>,
  "salary_hourly": <number or null>,
  "date_job_posted": "YYYY-MM-DD or null",
  "contact_email": "email or null"
}"""


def _ai_available() -> bool:
    from ..config import settings
    return bool(settings.anthropic_api_key or settings.openai_api_key)


async def _ai_extract(text: str) -> dict:
    from ..config import settings
    truncated = text[:4000]
    prompt = (
        f"Extract job metadata from the description below.\n\n"
        f"Job description:\n{truncated}\n\n"
        f"Return JSON matching exactly this schema:\n{_AI_SCHEMA}"
    )

    raw = ""
    try:
        if settings.anthropic_api_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=_AI_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text

        elif settings.openai_api_key:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _AI_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
    except Exception:
        return {}

    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

async def extract_job_meta(text: str) -> dict:
    """
    Extract job metadata from raw job-description text.
    Regex runs first (fast, free).  If position or company are still missing
    and an AI key is configured, a cheap model fills the gaps.
    """
    result = _regex_extract(text)

    if (result["position"] is None or result["company"] is None) and _ai_available():
        ai = await _ai_extract(text)
        for key, val in ai.items():
            if result.get(key) is None and val is not None:
                result[key] = val

    return result
