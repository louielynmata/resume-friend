from fastapi import APIRouter
from ..config import settings
from ..schemas import ModelFilesResponse

router = APIRouter(prefix="/api/model-files", tags=["model-files"])

_FILES = {
    "design_resume": "design_resume.md",
    "dev_resume": "dev_resume.md",
    "instructions_prompt": "instructions_prompt.md",
    "writing_examples": "writing_examples.md",
    "school_transcript": "school_transcript.md",
}


@router.get("", response_model=ModelFilesResponse)
def get_model_files():
    base = settings.model_files_path
    if not base.exists() or not base.is_dir():
        return ModelFilesResponse(**{key: False for key in _FILES})
    return ModelFilesResponse(
        **{key: (base / filename).exists() for key, filename in _FILES.items()}
    )
