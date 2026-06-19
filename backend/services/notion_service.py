from datetime import date
from typing import Optional
from ..config import settings


async def log_application(
    position: str,
    company: str,
    folder_name: str,
    location: Optional[str] = None,
    salary_annual: Optional[float] = None,
    salary_hourly: Optional[float] = None,
    ai_used: str = "",
    contact_email: Optional[str] = None,
    date_job_posted: Optional[str] = None,
) -> Optional[str]:
    from notion_client import AsyncClient

    client = AsyncClient(auth=settings.notion_token)

    properties: dict = {
        # Company is the title/Name column; Title is a plain rich_text column
        "Company": {"title": [{"text": {"content": company}}]},
        "Title": {"rich_text": [{"text": {"content": folder_name}}]},
        "Position": {"rich_text": [{"text": {"content": position}}]},
        # Status is multi_select in this database
        "Status": {"multi_select": [{"name": "Applied"}]},
        "Sent Resume": {"checkbox": False},
        "AI Resume": {"checkbox": bool(ai_used)},
        "ATS Use": {"checkbox": True},
        "Folder Name": {"rich_text": [{"text": {"content": folder_name}}]},
        "Date of Submission": {"date": {"start": date.today().isoformat()}},
    }

    if location:
        properties["Location"] = {"select": {"name": location}}
    if salary_annual is not None:
        properties["Salary (Annual)"] = {"number": salary_annual}
    if salary_hourly is not None:
        properties["Salary (By Hour)"] = {"number": salary_hourly}
    if contact_email:
        properties["Contact"] = {"email": contact_email}
    if date_job_posted:
        properties["Date of Job Posting"] = {"date": {"start": date_job_posted}}

    response = await client.pages.create(
        parent={"database_id": settings.notion_database_id},
        properties=properties,
    )
    return response.get("url")
