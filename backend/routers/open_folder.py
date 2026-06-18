import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import OpenFolderRequest, OpenFolderResponse

router = APIRouter(prefix="/api/open-folder", tags=["open-folder"])


def _resolve_allowed_directory(folder_path: str) -> Path:
    requested = Path(folder_path).expanduser().resolve()
    allowed_root = settings.output_path.resolve()

    if requested == allowed_root or allowed_root in requested.parents:
        return requested

    raise HTTPException(
        status_code=403,
        detail="Folder access is restricted to the outputs directory.",
    )


@router.post("", response_model=OpenFolderResponse)
def open_folder(req: OpenFolderRequest):
    target = _resolve_allowed_directory(req.folder_path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Folder does not exist.")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a folder.")

    try:
        os.startfile(str(target))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open folder: {exc}") from exc

    return OpenFolderResponse(opened=True)
