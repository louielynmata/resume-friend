from fastapi import APIRouter, HTTPException
from ..schemas import ScrapeRequest, ScrapeResponse
from ..services.job_scraper import scrape_job_description

router = APIRouter(prefix="/api/scrape-job", tags=["scrape"])


@router.post("", response_model=ScrapeResponse)
async def scrape_job(req: ScrapeRequest):
    try:
        text = await scrape_job_description(req.url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not scrape URL: {exc}")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Scraped page returned no text.")
    return ScrapeResponse(text=text, source_url=req.url)
