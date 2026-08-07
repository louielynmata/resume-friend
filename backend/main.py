import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import (
    editor,
    extract_job_meta,
    generate,
    locations,
    model_files,
    notion,
    open_folder,
    scrape,
)
from .services.editor_service import PERSONAL_FILE_REGISTRY, PROMPT_FILE_REGISTRY

logger = logging.getLogger("uvicorn.error")

_ROOT = Path(__file__).parent.parent
_DEFAULT_FRONTEND_DIST = _ROOT / "frontend" / "dist"
_MODEL_FILES = [definition.filename for definition in PERSONAL_FILE_REGISTRY.values()]
_APP_MODEL_FILES = [definition.filename for definition in PROMPT_FILE_REGISTRY.values()]


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
        path = base / filename
        if not path.exists():
            logger.warning("models_personal/%s is missing", filename)
        elif path.read_text(encoding="utf-8").strip().startswith("[PLACEHOLDER"):
            logger.warning("models_personal/%s still contains placeholder content", filename)
        else:
            logger.info("models_personal/%s OK", filename)


def health() -> dict[str, str]:
    return {"status": "ok", "owner": settings.owner_name}


def create_app(*, frontend_dist: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="Resume Friend API",
        description="Local tool for generating tailored resumes and cover letters with AI.",
        version="1.0.0",
    )

    # CORS allows the separate Vite development server to call the API.
    application.add_middleware(
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

    application.include_router(generate.router)
    application.include_router(scrape.router)
    application.include_router(extract_job_meta.router)
    application.include_router(model_files.router)
    application.include_router(editor.router)
    application.include_router(locations.router)
    application.include_router(notion.router)
    application.include_router(open_folder.router)
    application.router.add_event_handler("startup", _check_model_files)
    application.add_api_route("/api/health", health, methods=["GET"])

    resolved_frontend_dist = frontend_dist or _DEFAULT_FRONTEND_DIST
    if (resolved_frontend_dist / "index.html").is_file():
        application.mount(
            "/",
            StaticFiles(directory=str(resolved_frontend_dist), html=True),
            name="frontend",
        )

    return application


app = create_app()
