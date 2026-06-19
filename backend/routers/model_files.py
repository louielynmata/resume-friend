from email.mime import base

from fastapi import APIRouter
from ..config import settings
from ..schemas import ModelFilesResponse

router = APIRouter(prefix="/api/model-files", tags=["model-files"])

_FILES = {
    "design_resume": "design_resume.md",
    "dev_resume": "dev_resume.md",
    "instructions_prompt": "instructions_prompt.md",
    "writing_examples": "writing_examples.md",
    "sait_transcript": "sait_transcript.md",
}


@router.get("", response_model=ModelFilesResponse)
def get_model_files():
    
    base = settings.model_files_path

    if not base:
            raise ValueError("MODEL_FILES_PATH is not set in .env")
    
    if not base.exists() or not base.is_dir():
        raise ValueError(f"MODEL_FILES_PATH '{base}' does not exist or is not a directory")

    return ModelFilesResponse(
        **{key: (base / filename).exists() for key, filename in _FILES.items()}
    )
