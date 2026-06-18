from fastapi import APIRouter, HTTPException
from ..config import settings
from ..services.notion_service import log_application
from ..schemas import GenerateRequest

router = APIRouter(prefix="/api/notion", tags=["notion"])


@router.get("/status")
def notion_status():
    configured = bool(settings.notion_token and settings.notion_database_id)
    return {"configured": configured}
