from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import extract_job_meta, generate, scrape, model_files, notion, open_folder

app = FastAPI(
    title="Resume Friend API",
    description="Local tool for generating tailored resumes and cover letters with AI.",
    version="1.0.0",
)

# CORS — allows the Vite dev server (and future auth frontend) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.frontend_port}",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router)
app.include_router(scrape.router)
app.include_router(extract_job_meta.router)
app.include_router(model_files.router)
app.include_router(notion.router)
app.include_router(open_folder.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "owner": settings.owner_name}
