from fastapi import APIRouter
from ..config import settings
from ..schemas import ModelFilesResponse
from ..services.editor_service import personal_file_status

router = APIRouter(prefix="/api/model-files", tags=["model-files"])

@router.get("", response_model=ModelFilesResponse)
def get_model_files():
    return ModelFilesResponse(**personal_file_status(settings.model_files_path))
