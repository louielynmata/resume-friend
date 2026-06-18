from fastapi import APIRouter, HTTPException

from ..schemas import ExtractJobMetaRequest, ExtractJobMetaResponse
from ..services.job_meta_extractor import extract_job_meta

router = APIRouter(prefix="/api/extract-job-meta", tags=["extract"])


@router.post("", response_model=ExtractJobMetaResponse)
async def extract_meta(req: ExtractJobMetaRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")
    return ExtractJobMetaResponse(**extract_job_meta(req.text))
