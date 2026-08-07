"""Allowlisted Markdown-file reads and revision-protected atomic saves."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping


EditorGroup = Literal["personal", "prompts"]
EditorSource = Literal["personal", "example", "prompt"]


@dataclass(frozen=True)
class EditorFileDefinition:
    filename: str
    display_name: str


@dataclass(frozen=True)
class EditorFileDocument:
    group: EditorGroup
    file_id: str
    filename: str
    display_name: str
    exists: bool
    source: EditorSource
    writable: bool
    content: str
    revision: str


class UnknownEditorFileError(ValueError):
    """Raised when a group/file-id pair is not in the registry."""


class InvalidEditorContentError(ValueError):
    """Raised when browser content cannot be safely saved."""


class RevisionConflictError(RuntimeError):
    """Raised when the on-disk source changed after it was loaded."""


class EditorFileSystemError(RuntimeError):
    """Raised for safe, actionable filesystem failures."""


PERSONAL_FILE_REGISTRY: Mapping[str, EditorFileDefinition] = MappingProxyType(
    {
        "design_resume": EditorFileDefinition("design_resume.md", "Design résumé"),
        "dev_resume": EditorFileDefinition("dev_resume.md", "Development résumé"),
        "instructions_prompt": EditorFileDefinition(
            "instructions_prompt.md", "Personal instructions"
        ),
        "school_transcript": EditorFileDefinition(
            "school_transcript.md", "School transcript"
        ),
        "writing_examples": EditorFileDefinition(
            "writing_examples.md", "Writing examples"
        ),
    }
)

PROMPT_FILE_REGISTRY: Mapping[str, EditorFileDefinition] = MappingProxyType(
    {
        "system_prompt": EditorFileDefinition("system_prompt.md", "System prompt"),
        "qa_prompt": EditorFileDefinition("qa_prompt.md", "QA prompt"),
        "visual_qa_prompt": EditorFileDefinition(
            "visual_qa_prompt.md", "Visual QA prompt"
        ),
    }
)

EDITOR_FILE_REGISTRY: Mapping[
    EditorGroup, Mapping[str, EditorFileDefinition]
] = MappingProxyType(
    {"personal": PERSONAL_FILE_REGISTRY, "prompts": PROMPT_FILE_REGISTRY}
)

DEFAULT_MAX_CONTENT_BYTES = 1_000_000
_WRITE_LOCK = threading.RLock()


def personal_file_status(personal_dir: Path) -> dict[str, bool]:
    base = personal_dir.resolve()
    return {
        file_id: (base / definition.filename).is_file()
        for file_id, definition in PERSONAL_FILE_REGISTRY.items()
    }


class EditorService:
    def __init__(
        self,
        *,
        personal_dir: Path,
        example_dir: Path,
        prompts_dir: Path,
        max_content_bytes: int = DEFAULT_MAX_CONTENT_BYTES,
    ) -> None:
        self.personal_dir = Path(personal_dir)
        self.example_dir = Path(example_dir)
        self.prompts_dir = Path(prompts_dir)
        self.max_content_bytes = max_content_bytes

    def list_files(self) -> dict[EditorGroup, list[EditorFileDocument]]:
        return {
            group: [self.read_file(group, file_id) for file_id in registry]
            for group, registry in EDITOR_FILE_REGISTRY.items()
        }

    def read_file(self, group: str, file_id: str) -> EditorFileDocument:
        normalized_group, definition = self._definition(group, file_id)
        return self._read_known_file(normalized_group, file_id, definition)

    def save_file(
        self,
        group: str,
        file_id: str,
        content: str,
        revision: str,
    ) -> EditorFileDocument:
        normalized_group, definition = self._definition(group, file_id)
        encoded = self._validate_content(content)
        target = self._target_path(normalized_group, definition)

        with _WRITE_LOCK:
            current = self._read_known_file(normalized_group, file_id, definition)
            if current.revision != revision:
                raise RevisionConflictError(
                    "The file changed after it was loaded. Reload it before saving again."
                )
            self._atomic_write(target, encoded)
            return self._read_known_file(normalized_group, file_id, definition)

    def personal_file_status(self) -> dict[str, bool]:
        return personal_file_status(self.personal_dir)

    def _definition(
        self, group: str, file_id: str
    ) -> tuple[EditorGroup, EditorFileDefinition]:
        if group not in EDITOR_FILE_REGISTRY:
            raise UnknownEditorFileError("The requested editor file does not exist.")
        normalized_group: EditorGroup = group  # type: ignore[assignment]
        definition = EDITOR_FILE_REGISTRY[normalized_group].get(file_id)
        if definition is None:
            raise UnknownEditorFileError("The requested editor file does not exist.")
        return normalized_group, definition

    def _target_path(
        self, group: EditorGroup, definition: EditorFileDefinition
    ) -> Path:
        base = self.personal_dir if group == "personal" else self.prompts_dir
        return self._contained_path(base, definition.filename)

    @staticmethod
    def _contained_path(base: Path, filename: str) -> Path:
        resolved_base = base.resolve()
        candidate = (resolved_base / filename).resolve(strict=False)
        if not candidate.is_relative_to(resolved_base):
            raise EditorFileSystemError(
                "The configured editor file resolves outside its allowed directory."
            )
        return candidate

    def _read_known_file(
        self,
        group: EditorGroup,
        file_id: str,
        definition: EditorFileDefinition,
    ) -> EditorFileDocument:
        target = self._target_path(group, definition)
        target_exists = target.is_file()
        if group == "personal" and not target_exists:
            source: EditorSource = "example"
            source_path = self._contained_path(self.example_dir, definition.filename)
        else:
            source = "personal" if group == "personal" else "prompt"
            source_path = target

        try:
            content = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
        except (OSError, UnicodeError) as exc:
            raise EditorFileSystemError(
                f"Could not read {definition.filename} as UTF-8."
            ) from exc

        revision = self._revision(source, source_path.is_file(), content)
        return EditorFileDocument(
            group=group,
            file_id=file_id,
            filename=definition.filename,
            display_name=definition.display_name,
            exists=target_exists,
            source=source,
            writable=True,
            content=content,
            revision=revision,
        )

    def _validate_content(self, content: str) -> bytes:
        if "\x00" in content:
            raise InvalidEditorContentError("Markdown content cannot contain null bytes.")
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise InvalidEditorContentError(
                "Markdown content must be valid UTF-8 text."
            ) from exc
        if len(encoded) > self.max_content_bytes:
            raise InvalidEditorContentError(
                f"Markdown content must be at most {self.max_content_bytes} UTF-8 bytes."
            )
        return encoded

    @staticmethod
    def _revision(source: EditorSource, exists: bool, content: str) -> str:
        state = f"{source}:{int(exists)}\0".encode("utf-8")
        return hashlib.sha256(state + content.encode("utf-8")).hexdigest()

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> None:
        temp_path: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temp_path = Path(temp_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, target)
            temp_path = None
        except OSError as exc:
            raise EditorFileSystemError(
                f"Could not save {target.name}. Check directory permissions and file locks."
            ) from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
