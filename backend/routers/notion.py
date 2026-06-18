from fastapi import APIRouter
from ..config import settings

router = APIRouter(prefix="/api/notion", tags=["notion"])

REQUIRED_PROPERTIES = {
    "ID": "title",
    "Company": "rich_text",
    "Position": "rich_text",
    "Status": "select",
    "Sent Resume": "checkbox",
    "AI Resume": "checkbox",
    "ATS Use": "checkbox",
    "Folder Name": "rich_text",
    "Salary (Annual)": "number",
    "Salary (By Hour)": "number",
    "Date of Submission": "date",
    "Contact": "email",
}


@router.get("/status")
def notion_status():
    configured = bool(settings.notion_token and settings.notion_database_id)
    return {"configured": configured}


@router.get("/test")
async def notion_test():
    if not settings.notion_token or not settings.notion_database_id:
        return {"ok": False, "error": "NOTION_TOKEN or NOTION_DATABASE_ID is not set in .env"}

    try:
        from notion_client import AsyncClient
        client = AsyncClient(auth=settings.notion_token)
        db = await client.databases.retrieve(database_id=settings.notion_database_id)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "hint": "Check your token and that the integration has access to the database."}

    db_props: dict = db.get("properties", {})
    db_title = ""
    for block in db.get("title", []):
        db_title += block.get("plain_text", "")

    missing = []
    type_mismatch = []
    for name, expected_type in REQUIRED_PROPERTIES.items():
        if name not in db_props:
            missing.append({"property": name, "expected_type": expected_type})
        elif db_props[name].get("type") != expected_type:
            type_mismatch.append({
                "property": name,
                "expected_type": expected_type,
                "actual_type": db_props[name].get("type"),
            })

    return {
        "ok": len(missing) == 0 and len(type_mismatch) == 0,
        "database_title": db_title,
        "database_id": settings.notion_database_id,
        "your_properties": {k: v.get("type") for k, v in db_props.items()},
        "missing_properties": missing,
        "type_mismatches": type_mismatch,
    }
