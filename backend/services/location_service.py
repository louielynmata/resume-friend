"""Deterministic job-location normalization and a local persistent catalog."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CATALOG_FILENAME = "normalized_locations.json"
_SEED_LOCATIONS = ["Remote"]
_CATALOG_LOCK = threading.RLock()

_LABEL_RE = re.compile(
    r"^(?:job\s+|work\s+|office\s+)?location\s*[:\-–—]\s*", re.IGNORECASE
)
_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
_PAREN_ARRANGEMENT_RE = re.compile(
    r"\([^)]*\b(?:hybrid|on[- ]?site|remote|wfh|work\s+from\s+(?:home|anywhere))\b[^)]*\)",
    re.IGNORECASE,
)
_SEPARATOR_RE = re.compile(r"\s*(?:,|;|\||/)\s*|\s+[-–—]\s+")
_POSTAL_RE = re.compile(
    r"(?:\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d|\s+\d{5}(?:-\d{4})?)$", re.IGNORECASE
)
_TRAILING_ARRANGEMENT_RE = re.compile(
    r"\s+(?:hybrid|on[- ]?site|wfh|work\s+from\s+(?:home|anywhere))$",
    re.IGNORECASE,
)

_REGION_SUFFIXES = {
    "ab",
    "ak",
    "al",
    "ar",
    "az",
    "bc",
    "ca",
    "co",
    "ct",
    "dc",
    "de",
    "fl",
    "ga",
    "hi",
    "ia",
    "id",
    "il",
    "in",
    "ks",
    "ky",
    "la",
    "ma",
    "mb",
    "md",
    "me",
    "mi",
    "mn",
    "mo",
    "ms",
    "mt",
    "nb",
    "nc",
    "nd",
    "ne",
    "nh",
    "nj",
    "nl",
    "nm",
    "ns",
    "nt",
    "nu",
    "nv",
    "ny",
    "oh",
    "ok",
    "on",
    "or",
    "pa",
    "pe",
    "qc",
    "ri",
    "sc",
    "sd",
    "sk",
    "tn",
    "tx",
    "ut",
    "va",
    "vt",
    "wa",
    "wi",
    "wv",
    "wy",
    "yt",
    "alberta",
    "british columbia",
    "manitoba",
    "new brunswick",
    "newfoundland and labrador",
    "northwest territories",
    "nova scotia",
    "nunavut",
    "ontario",
    "prince edward island",
    "quebec",
    "saskatchewan",
    "yukon",
    "canada",
    "united states",
    "united states of america",
    "usa",
    "u.s.a.",
    "us",
    "u.s.",
    "united kingdom",
    "uk",
    "australia",
}
_ARRANGEMENT_ONLY = {
    "hybrid",
    "on site",
    "on-site",
    "onsite",
    "wfh",
    "work from home",
    "work from anywhere",
    "worldwide",
    "anywhere",
}


class LocationCatalogError(RuntimeError):
    """Raised when the local catalog cannot be safely read or updated."""


@dataclass(frozen=True)
class LocationNormalizationResult:
    raw: str
    normalized: str | None
    added: bool
    locations: list[str]


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _strip_trailing_noise(candidate: str) -> str:
    value = candidate.strip(" ,;|-/–—")
    while True:
        previous = value
        value = _POSTAL_RE.sub("", value).strip()
        value = _TRAILING_ARRANGEMENT_RE.sub("", value).strip()
        lowered = value.casefold()
        for suffix in sorted(_REGION_SUFFIXES, key=len, reverse=True):
            marker = f" {suffix}"
            if lowered.endswith(marker):
                value = value[: -len(marker)].strip(" ,;|-/–—")
                break
        if value == previous:
            return value


def _plausible_city(candidate: str) -> bool:
    lowered = candidate.casefold()
    if not candidate or lowered in _ARRANGEMENT_ONLY or lowered in _REGION_SUFFIXES:
        return False
    if len(candidate) > 80 or len(candidate.split()) > 8:
        return False
    if sum(character.isalpha() for character in candidate) < 2:
        return False
    return all(
        character.isalpha() or character.isspace() or character in "'’.−-"
        for character in candidate
    )


def _smart_title(candidate: str) -> str:
    has_lower = any(character.islower() for character in candidate)
    has_upper = any(character.isupper() for character in candidate)
    if has_lower and has_upper:
        return candidate

    lowered = candidate.lower()
    result: list[str] = []
    capitalize_next = True
    for character in lowered:
        if capitalize_next and character.isalpha():
            result.append(character.upper())
            capitalize_next = False
        else:
            result.append(character)
        if character.isspace() or character == "-":
            capitalize_next = True
    return "".join(result)


def normalize_location(
    raw: str | None, catalog: Iterable[str] = ()
) -> str | None:
    if raw is None:
        return None
    value = _normalize_space(raw)
    if not value:
        return None
    value = _LABEL_RE.sub("", value)
    if _REMOTE_RE.search(value):
        return "Remote"

    value = _PAREN_ARRANGEMENT_RE.sub("", value).strip()
    candidate = _SEPARATOR_RE.split(value, maxsplit=1)[0]
    candidate = _strip_trailing_noise(candidate)
    candidate = _normalize_space(candidate).strip(" .,'’-/–—")
    if not _plausible_city(candidate):
        return None

    for stored in catalog:
        if stored.strip().casefold() == candidate.casefold():
            return stored.strip()
    return _smart_title(candidate)


class LocationCatalog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def list_locations(self) -> list[str]:
        with _CATALOG_LOCK:
            return self._read(create_if_missing=True)

    def normalize(self, raw: str | None, *, persist: bool = False) -> LocationNormalizationResult:
        raw_value = raw or ""
        with _CATALOG_LOCK:
            locations = self._read(create_if_missing=True)
            normalized = normalize_location(raw_value, locations)
            added = False
            if persist and normalized is not None:
                existing = {location.casefold(): location for location in locations}
                matched = existing.get(normalized.casefold())
                if matched is not None:
                    normalized = matched
                else:
                    locations.append(normalized)
                    locations = self._sort(locations)
                    self._write(locations)
                    added = True
            return LocationNormalizationResult(
                raw=raw_value,
                normalized=normalized,
                added=added,
                locations=self._sort(locations),
            )

    def _read(self, *, create_if_missing: bool) -> list[str]:
        if not self.path.exists():
            locations = list(_SEED_LOCATIONS)
            if create_if_missing:
                self._write(locations)
            return locations
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LocationCatalogError(
                f"{self.path.name} is unreadable or contains malformed JSON."
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("locations"), list):
            raise LocationCatalogError(
                f"{self.path.name} must contain an object with a locations list."
            )
        locations = payload["locations"]
        if not all(isinstance(value, str) and value.strip() for value in locations):
            raise LocationCatalogError(
                f"{self.path.name} contains an invalid location entry."
            )
        if "Remote" not in locations:
            raise LocationCatalogError(
                f"{self.path.name} must contain the canonical Remote seed."
            )
        folded = [value.strip().casefold() for value in locations]
        if len(set(folded)) != len(folded):
            raise LocationCatalogError(
                f"{self.path.name} contains duplicate locations that differ only by case."
            )
        return self._sort([value.strip() for value in locations])

    @staticmethod
    def _sort(locations: list[str]) -> list[str]:
        return sorted(locations, key=lambda value: (value.casefold() != "remote", value.casefold()))

    def _write(self, locations: list[str]) -> None:
        temp_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            temp_path = Path(temp_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    {"locations": self._sort(locations)},
                    stream,
                    ensure_ascii=False,
                    indent=2,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
            temp_path = None
        except OSError as exc:
            raise LocationCatalogError(
                f"Could not update {self.path.name}. Check directory permissions and file locks."
            ) from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
