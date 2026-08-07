from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..schemas import (
    EditorFileMetadata,
    EditorFileResponse,
    EditorFilesResponse,
    EditorSaveRequest,
    EditorSaveResponse,
    ModelFilesResponse,
)
from ..services.editor_service import (
    EditorFileDocument,
    EditorFileSystemError,
    EditorService,
    InvalidEditorContentError,
    RevisionConflictError,
    UnknownEditorFileError,
)

router = APIRouter(prefix="/api/editor/files", tags=["editor"])
_EXAMPLE_DIR = Path(__file__).parents[2] / "models_personal_example"


def get_editor_service() -> EditorService:
    return EditorService(
        personal_dir=settings.model_files_path,
        example_dir=_EXAMPLE_DIR,
        prompts_dir=settings.app_model_files_path,
    )


def _metadata(document: EditorFileDocument) -> EditorFileMetadata:
    return EditorFileMetadata(
        group=document.group,
        file_id=document.file_id,
        filename=document.filename,
        display_name=document.display_name,
        exists=document.exists,
        source=document.source,
        writable=document.writable,
    )


def _response(document: EditorFileDocument) -> EditorFileResponse:
    return EditorFileResponse(**_metadata(document).model_dump(), content=document.content, revision=document.revision)


def _editor_error(status_code: int, code: str, message: str, hint: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "hint": hint, "status_code": status_code},
    )


@router.get("", response_model=EditorFilesResponse)
def list_editor_files(
    service: EditorService = Depends(get_editor_service),
) -> EditorFilesResponse:
    try:
        groups = {
            group: [_metadata(document) for document in documents]
            for group, documents in service.list_files().items()
        }
        return EditorFilesResponse(groups=groups)
    except EditorFileSystemError as exc:
        raise _editor_error(
            500,
            "EDITOR_FILESYSTEM_ERROR",
            str(exc),
            "Check the configured model and prompt directories, then try again.",
        ) from exc


@router.get("/{group}/{file_id}", response_model=EditorFileResponse)
def read_editor_file(
    group: str,
    file_id: str,
    service: EditorService = Depends(get_editor_service),
) -> EditorFileResponse:
    try:
        return _response(service.read_file(group, file_id))
    except UnknownEditorFileError as exc:
        raise _editor_error(
            404,
            "EDITOR_FILE_NOT_FOUND",
            "The requested editor file is not available.",
            "Choose one of the files listed by /api/editor/files.",
        ) from exc
    except EditorFileSystemError as exc:
        raise _editor_error(
            500,
            "EDITOR_FILESYSTEM_ERROR",
            str(exc),
            "Check the configured directory and UTF-8 file content, then try again.",
        ) from exc


@router.put("/{group}/{file_id}", response_model=EditorSaveResponse)
def save_editor_file(
    group: str,
    file_id: str,
    request: EditorSaveRequest,
    service: EditorService = Depends(get_editor_service),
) -> EditorSaveResponse:
    try:
        document = service.save_file(
            group, file_id, request.content, request.revision
        )
        return EditorSaveResponse(
            **_response(document).model_dump(),
            personal_file_status=ModelFilesResponse(**service.personal_file_status()),
        )
    except UnknownEditorFileError as exc:
        raise _editor_error(
            404,
            "EDITOR_FILE_NOT_FOUND",
            "The requested editor file is not available.",
            "Choose one of the files listed by /api/editor/files.",
        ) from exc
    except InvalidEditorContentError as exc:
        raise _editor_error(
            400,
            "EDITOR_INVALID_CONTENT",
            str(exc),
            "Remove invalid characters or reduce the file size, then try again.",
        ) from exc
    except RevisionConflictError as exc:
        raise _editor_error(
            409,
            "EDITOR_REVISION_CONFLICT",
            str(exc),
            "Reload the file, review the newer content, and apply your changes again.",
        ) from exc
    except EditorFileSystemError as exc:
        raise _editor_error(
            500,
            "EDITOR_FILESYSTEM_ERROR",
            str(exc),
            "Check directory permissions and whether another program has locked the file.",
        ) from exc
