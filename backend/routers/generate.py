import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import GenerateRequest, GenerateResponse
from ..services.ai_service import generate_content
from ..services.notion_service import log_application
from ..services.qa_pipeline import (
    QAPipelineReviewError,
    QAPipelineValidationError,
    run_qa_pipeline,
)
from ..services.qa_service import parse_document_draft

router = APIRouter(prefix="/api/generate", tags=["generate"])

_SYSTEM_PROMPT_FILE = "system_prompt.md"
_SYSTEM_PROMPT_TOKEN_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def _http_error(
    status_code: int,
    *,
    stage: str,
    code: str,
    message: str,
    detail: str | None = None,
    hint: str | None = None,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "stage": stage,
            "code": code,
            "message": message,
            "detail": detail,
            "hint": hint,
            "retryable": retryable,
            "status_code": status_code,
        },
    )


def _slugify(text: str) -> str:
    words = text.split()
    cased = "".join(w[0].upper() + w[1:] if w else "" for w in words)
    return re.sub(r"[^a-zA-Z0-9]", "", cased)


def _create_run_output_dir(base_path: Path) -> Path:
    """Create a run-specific folder without overwriting prior same-day output."""
    base_path.parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, 1000):
        candidate = (
            base_path
            if index == 1
            else base_path.with_name(f"{base_path.name}_{index}")
        )
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise OSError(f"Could not create a unique output folder for {base_path.name}.")


def _read_model(filename: str) -> str:
    path = settings.model_files_path / filename
    if not path.exists():
        raise FileNotFoundError(
            f"{filename} was not found in {settings.model_files_path}."
        )
    content = path.read_text(encoding="utf-8").strip()
    if content.startswith("[PLACEHOLDER"):
        raise ValueError(f"{filename} still contains placeholder content.")
    return content


def _read_system_prompt_template() -> str:
    path = settings.app_model_files_path / _SYSTEM_PROMPT_FILE
    if not path.exists():
        raise FileNotFoundError(f"{_SYSTEM_PROMPT_FILE} was not found in {path.parent}.")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"{_SYSTEM_PROMPT_FILE} is empty.")
    return content


def _render_system_prompt(template: str, values: dict[str, str]) -> str:
    template_tokens = set(_SYSTEM_PROMPT_TOKEN_RE.findall(template))
    expected_tokens = set(values)

    missing_tokens = sorted(expected_tokens - template_tokens)
    unknown_tokens = sorted(template_tokens - expected_tokens)
    if missing_tokens or unknown_tokens:
        problems = []
        if missing_tokens:
            problems.append(f"missing tokens: {', '.join(missing_tokens)}")
        if unknown_tokens:
            problems.append(f"unknown tokens: {', '.join(unknown_tokens)}")
        raise ValueError(f"{_SYSTEM_PROMPT_FILE} has invalid placeholders ({'; '.join(problems)}).")

    rendered = template
    for token, value in values.items():
        rendered = rendered.replace(f"{{{{{token}}}}}", value)
    return rendered


def _classify_ai_error(provider: str, exc: Exception) -> tuple[int, str, str, str, bool]:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()

    if (
        "api key" in lowered
        or "authentication" in lowered
        or "unauthorized" in lowered
        or "invalid_api_key" in lowered
    ):
        return (
            401,
            "AI_PROVIDER_AUTH_ERROR",
            f"{provider} authentication failed.",
            message,
            False,
        )
    if "rate limit" in lowered or "quota" in lowered or "429" in lowered:
        return (
            429,
            "AI_PROVIDER_RATE_LIMIT",
            f"{provider} rate limit or quota was hit.",
            message,
            True,
        )
    if "timed out" in lowered or "timeout" in lowered:
        return (
            504,
            "AI_PROVIDER_TIMEOUT",
            f"{provider} did not respond in time.",
            message,
            True,
        )
    if (
        "connect" in lowered
        or "connection" in lowered
        or "dns" in lowered
        or "refused" in lowered
    ):
        return (
            502,
            "AI_PROVIDER_NETWORK_ERROR",
            f"{provider} could not be reached.",
            message,
            True,
        )
    return (
        502,
        "AI_PROVIDER_REQUEST_FAILED",
        f"{provider} request failed.",
        message,
        True,
    )


@router.post("", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    if req.ai_provider not in ("claude", "openai", "ollama"):
        raise _http_error(
            400,
            stage="validate_request",
            code="INVALID_AI_PROVIDER",
            message="Invalid AI provider.",
            detail="ai_provider must be claude, openai, or ollama.",
        )
    if req.job_type not in ("design", "development"):
        raise _http_error(
            400,
            stage="validate_request",
            code="INVALID_JOB_TYPE",
            message="Invalid job type.",
            detail="job_type must be design or development.",
        )

    try:
        resume_file = (
            "design_resume.md" if req.job_type == "design" else "dev_resume.md"
        )
        resume_content = _read_model(resume_file)
        instructions = _read_model("instructions_prompt.md")
        writing_examples = _read_model("writing_examples.md")
        transcript = _read_model("school_transcript.md")
        system_prompt_template = _read_system_prompt_template()
    except FileNotFoundError as exc:
        raise _http_error(
            500,
            stage="load_model_files",
            code="MODEL_FILE_MISSING",
            message="A required model or prompt file is missing.",
            detail=str(exc),
            hint=(
                "Restore prompts/system_prompt.md and add the required files under "
                "models_personal/ before trying again."
            ),
        ) from exc
    except ValueError as exc:
        raise _http_error(
            500,
            stage="load_model_files",
            code="MODEL_FILE_INVALID",
            message="A required model or prompt file is invalid.",
            detail=str(exc),
            hint=(
                "Fill in each personal model file and keep the documented placeholders "
                "in prompts/system_prompt.md."
            ),
        ) from exc

    company_context_section = ""
    if req.company_context:
        trimmed = req.company_context[:4000]
        company_context_section = (
            f"\n--- COMPANY CONTEXT (About Page) ---\n{trimmed}\n"
        )

    role_hint = "Title Case, not all caps, and tailored to this job description"
    try:
        system_prompt = _render_system_prompt(
            system_prompt_template,
            {
                "APPLICANT_NAME": settings.owner_name,
                "JOB_TYPE": req.job_type.upper(),
                "RESUME_CONTENT": resume_content,
                "INSTRUCTIONS": instructions,
                "WRITING_EXAMPLES": writing_examples,
                "TRANSCRIPT": transcript,
                "COMPANY_CONTEXT_SECTION": company_context_section,
                "ROLE_HINT": role_hint,
            },
        )
    except ValueError as exc:
        raise _http_error(
            500,
            stage="load_model_files",
            code="SYSTEM_PROMPT_TEMPLATE_INVALID",
            message="The system prompt template could not be rendered.",
            detail=str(exc),
            hint=(
                "Restore the placeholders documented in "
                "prompts/system_prompt.md and try again."
            ),
        ) from exc

    # Auto-fill a missing salary field using 2,080 hours per year.
    hours_per_year = 2080
    salary_annual = req.salary_annual
    salary_hourly = req.salary_hourly
    if salary_annual and not salary_hourly:
        salary_hourly = round(salary_annual / hours_per_year, 2)
    elif salary_hourly and not salary_annual:
        salary_annual = round(salary_hourly * hours_per_year, 2)

    user_prompt = f"""Job Description:
{req.job_description}

Target Position: {req.position}
Target Company: {req.company}"""

    try:
        ai_response = await generate_content(
            req.ai_provider, system_prompt, user_prompt
        )
    except ValueError as exc:
        raise _http_error(
            400,
            stage="call_ai_provider",
            code="AI_PROVIDER_CONFIG_ERROR",
            message="The selected AI provider is not configured correctly.",
            detail=str(exc),
            hint=(
                "Check the provider-specific settings in .env and confirm the "
                "selected model is available."
            ),
        ) from exc
    except Exception as exc:
        status_code, code, message, detail, retryable = _classify_ai_error(
            req.ai_provider, exc
        )
        raise _http_error(
            status_code,
            stage="call_ai_provider",
            code=code,
            message=message,
            detail=detail,
            hint=(
                "If you are using Ollama, make sure the local server is running "
                "and the model is installed."
                if req.ai_provider == "ollama"
                else (
                    "Check your API key, model name, network access, and provider "
                    "account limits."
                )
            ),
            retryable=retryable,
        ) from exc

    position_slug = _slugify(req.position)
    company_slug = _slugify(req.company)
    today_str = date.today().strftime("%Y-%m-%d")
    folder_name = f"{company_slug}_{position_slug}_{today_str}"

    output_dir = _create_run_output_dir(settings.output_path / folder_name)
    folder_name = output_dir.name

    jd_path = output_dir / "job_description.txt"
    jd_path.write_text(
        f"Position: {req.position}\nCompany:  {req.company}\n\n{req.job_description}",
        encoding="utf-8",
    )

    try:
        draft = parse_document_draft(ai_response)
    except ValueError as exc:
        raise _http_error(
            422,
            stage="qa_review",
            code="DOCUMENT_PARSE_ERROR",
            message="The AI response could not be parsed for QA.",
            detail=str(exc),
            hint=(
                "Try regenerating or switch providers. The writer likely missed "
                "the required <RESUME> or <COVER_LETTER> tags."
            ),
            retryable=True,
        ) from exc

    try:
        qa_result = await run_qa_pipeline(
            selected_provider=req.ai_provider,
            draft=draft,
            owner_name=settings.owner_name,
            source_resume=resume_content,
            instructions=instructions,
            writing_examples=writing_examples,
            transcript=transcript,
            job_description=req.job_description,
            company_context=req.company_context or "",
            position=req.position,
            company=req.company,
            position_slug=position_slug,
            output_dir=output_dir,
        )
        docs = qa_result.docs
        draft = qa_result.draft
        qa_report = qa_result.report
        qa_report_path = qa_result.report_path
    except QAPipelineValidationError as exc:
        raise _http_error(
            422,
            stage=exc.stage,
            code="QA_VALIDATION_FAILED",
            message=(
                "The generated files did not pass QA."
                if exc.stage == "artifact_validation"
                else "The generated content did not pass QA."
            ),
            detail=f"{exc} QA report: {exc.report_path}",
            hint=(
                "Open qa_report.json and qa_draft.xml in the output folder. The final "
                "reviewed text was retained, but the application was not logged to Notion."
            ),
            retryable=True,
        ) from exc
    except QAPipelineReviewError as exc:
        qa_provider = (
            req.ai_provider if settings.qa_provider == "same" else settings.qa_provider
        )
        status_code, code, message, detail, retryable = _classify_ai_error(
            qa_provider, exc
        )
        raise _http_error(
            status_code,
            stage="qa_review",
            code=f"QA_{code}",
            message=f"QA review failed: {message}",
            detail=detail,
            hint=(
                "Check QA_PROVIDER and the selected provider configuration. For "
                "local QA, make sure Ollama is running and the model is installed."
            ),
            retryable=retryable,
        ) from exc
    except ValueError as exc:
        raise _http_error(
            422,
            stage="qa_review",
            code="QA_CONFIG_ERROR",
            message="The QA reviewer is configured incorrectly.",
            detail=str(exc),
            hint=(
                "QA_PROVIDER must be same, claude, openai, or ollama, and all "
                "QA prompt files must exist under prompts/."
            ),
        ) from exc
    except Exception as exc:
        raise _http_error(
            500,
            stage="build_documents",
            code="DOCUMENT_BUILD_FAILED",
            message="Document generation failed.",
            detail=str(exc),
        ) from exc

    analysis_text = draft.analysis or None
    if analysis_text:
        analysis_path = output_dir / "analysis.md"
        analysis_path.write_text(analysis_text, encoding="utf-8")

    notion_url = None
    notion_error = None
    if (
        qa_report.status != "needs_review"
        and settings.notion_token
        and settings.notion_database_id
    ):
        try:
            notion_url = await log_application(
                position=req.position,
                company=req.company,
                folder_name=folder_name,
                location=req.location,
                salary_annual=salary_annual,
                salary_hourly=salary_hourly,
                ai_used=req.ai_provider,
                contact_email=req.contact_email,
                date_job_posted=(
                    req.date_job_posted.isoformat()
                    if req.date_job_posted
                    else None
                ),
            )
        except Exception as exc:
            notion_error = str(exc)
    elif qa_report.status == "needs_review":
        notion_error = "Not logged because generated files still need manual QA review."

    return GenerateResponse(
        output_folder=str(output_dir.resolve()),
        resume_docx=docs.get("resume_docx", ""),
        resume_pdf=docs.get("resume_pdf"),
        cover_letter_docx=docs.get("cover_letter_docx", ""),
        cover_letter_pdf=docs.get("cover_letter_pdf"),
        notion_page_url=notion_url,
        notion_error=notion_error,
        analysis=analysis_text,
        qa_status=qa_report.status,
        qa_iterations=qa_report.iterations,
        qa_report_path=str(qa_report_path.resolve()),
        qa_issues=[issue.message for issue in qa_report.issues],
        qa_changes=qa_report.changes_made,
        message=(
            "Generated with unresolved QA issues; manual review is required"
            if qa_report.status == "needs_review"
            else "Generated and QA-verified successfully"
        ),
    )
