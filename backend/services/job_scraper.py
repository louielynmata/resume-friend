import re
import httpx
from bs4 import BeautifulSoup


async def scrape_job_description(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
        tag.decompose()

    # Try common job-posting content containers first
    main = (
        soup.find("div", {"id": re.compile(r"job.?(description|detail|posting)", re.I)})
        or soup.find("div", {"class": re.compile(r"job.?(description|detail|posting|content)", re.I)})
        or soup.find("section", {"class": re.compile(r"description|job", re.I)})
        or soup.find("main")
        or soup.body
    )

    raw = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)

    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    return "\n".join(lines)
