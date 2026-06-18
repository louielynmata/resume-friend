from fastapi import APIRouter
from ..config import settings
from ..schemas import ModelFilesResponse

router = APIRouter(prefix="/api/model-files", tags=["model-files"])

_FILES = {
    "design_resume": "design_resume.txt",
    "dev_resume": "dev_resume.txt",
    "instructions_prompt": "instructions_prompt.txt",
    "writing_examples": "writing_examples.txt",
    "sait_transcript": "sait_transcript.txt",
}


@router.get("", response_model=ModelFilesResponse)
def get_model_files():
    base = settings.model_files_path
    return ModelFilesResponse(
        **{key: (base / filename).exists() for key, filename in _FILES.items()}
    )
