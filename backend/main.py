import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import extract_job_meta, generate, scrape, model_files, notion, open_folder

logger = logging.getLogger("uvicorn.error")

_MODEL_FILES = [
    "design_resume.md",
    "dev_resume.md",
    "instructions_prompt.md",
    "writing_examples.md",
    "school_transcript.md",
]
_APP_MODEL_FILES = ["system_prompt.md", "qa_prompt.md", "visual_qa_prompt.md"]

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


@app.on_event("startup")
async def _check_model_files() -> None:
    app_base = settings.app_model_files_path
    for filename in _APP_MODEL_FILES:
        path = app_base / filename
        if not path.exists():
            logger.warning("prompts/%s is missing", filename)
        elif not path.read_text(encoding="utf-8").strip():
            logger.warning("prompts/%s is empty", filename)
        else:
            logger.info("prompts/%s OK", filename)

    base = settings.model_files_path
    if not base.exists() or not base.is_dir():
        logger.warning(
            "models_personal/ directory not found at %s. "
            "Copy models_personal_example/ to models_personal/ and fill in your content.",
            base,
        )
        return
    for filename in _MODEL_FILES:
        p = base / filename
        if not p.exists():
            logger.warning("models_personal/%s is missing", filename)
        elif p.read_text(encoding="utf-8").strip().startswith("[PLACEHOLDER"):
            logger.warning("models_personal/%s still contains placeholder content", filename)
        else:
            logger.info("models_personal/%s OK", filename)


@app.get("/api/health")
def health():
    return {"status": "ok", "owner": settings.owner_name}
