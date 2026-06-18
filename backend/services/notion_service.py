from datetime import date
from typing import Optional
from ..config import settings


async def log_application(
    position: str,
    company: str,
    location: Optional[str] = None,
    salary_annual: Optional[float] = None,
    salary_hourly: Optional[float] = None,
    date_job_posted: Optional[date] = None,
    ai_used: str = "",
    contact_email: Optional[str] = None,
) -> Optional[str]:
    from notion_client import AsyncClient

    client = AsyncClient(auth=settings.notion_token)

    ai_label = {"claude": "Claude", "openai": "OpenAI", "ollama": "Ollama"}.get(ai_used, ai_used.title())

    properties: dict = {
        "Name": {"title": [{"text": {"content": f"{position} @ {company}"}}]},
        "Company": {"rich_text": [{"text": {"content": company}}]},
        "Position": {"rich_text": [{"text": {"content": position}}]},
        "Status": {"select": {"name": "Applied"}},
        "AI Used": {"select": {"name": ai_label}},
        "ATS Use": {"checkbox": True},
        "Date Submitted": {"date": {"start": date.today().isoformat()}},
    }

    if location:
        properties["Location"] = {"rich_text": [{"text": {"content": location}}]}
    if salary_annual is not None:
        properties["Salary Annual"] = {"number": salary_annual}
    if salary_hourly is not None:
        properties["Salary Hourly"] = {"number": salary_hourly}
    if date_job_posted:
        properties["Date of Job Posting"] = {"date": {"start": date_job_posted.isoformat()}}
    if contact_email:
        properties["Contact Email"] = {"email": contact_email}

    response = await client.pages.create(
        parent={"database_id": settings.notion_database_id},
        properties=properties,
    )
    return response.get("url")
