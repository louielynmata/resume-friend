import re
from datetime import date

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import GenerateRequest, GenerateResponse
from ..services.ai_service import generate_content
from ..services.document_service import build_documents
from ..services.notion_service import log_application

router = APIRouter(prefix="/api/generate", tags=["generate"])


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


def _extract_analysis(text: str) -> str | None:
    match = re.search(r"<ANALYSIS>(.*?)</ANALYSIS>", text, re.DOTALL)
    return match.group(1).strip() if match else None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", text.title().replace(" ", ""))


def _read_model(filename: str) -> str:
    p = settings.model_files_path / filename
    if not p.exists():
        raise FileNotFoundError(f"{filename} was not found in model_files/.")
    content = p.read_text(encoding="utf-8").strip()
    if content.startswith("[PLACEHOLDER"):
        raise ValueError(f"{filename} still contains placeholder content.")
    return content


def _classify_ai_error(provider: str, exc: Exception) -> tuple[int, str, str, str, bool]:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()

    if "api key" in lowered or "authentication" in lowered or "unauthorized" in lowered or "invalid_api_key" in lowered:
        return 401, "AI_PROVIDER_AUTH_ERROR", f"{provider} authentication failed.", message, False
    if "rate limit" in lowered or "quota" in lowered or "429" in lowered:
        return 429, "AI_PROVIDER_RATE_LIMIT", f"{provider} rate limit or quota was hit.", message, True
    if "timed out" in lowered or "timeout" in lowered:
        return 504, "AI_PROVIDER_TIMEOUT", f"{provider} did not respond in time.", message, True
    if "connect" in lowered or "connection" in lowered or "dns" in lowered or "refused" in lowered:
        return 502, "AI_PROVIDER_NETWORK_ERROR", f"{provider} could not be reached.", message, True
    return 502, "AI_PROVIDER_REQUEST_FAILED", f"{provider} request failed.", message, True


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
        resume_file = "design_resume.md" if req.job_type == "design" else "dev_resume.md"
        resume_content = _read_model(resume_file)
        instructions = _read_model("instructions_prompt.md")
        writing_examples = _read_model("writing_examples.md")
        transcript = _read_model("school_transcript.md")
    except FileNotFoundError as exc:
        raise _http_error(
            500,
            stage="load_model_files",
            code="MODEL_FILE_MISSING",
            message="A required model file is missing.",
            detail=str(exc),
            hint="Add the missing file under model_files/ and try again.",
        )
    except ValueError as exc:
        raise _http_error(
            500,
            stage="load_model_files",
            code="MODEL_FILE_PLACEHOLDER",
            message="A required model file still contains placeholder content.",
            detail=str(exc),
            hint="Fill in the model file with your real resume or prompt content before generating.",
        )

    system_prompt = f"""You are a professional resume and cover letter writer assisting {settings.owner_name}.

CORE RULES — follow strictly:
1. TRUTHFUL: Only use information present in the provided resume. Never invent skills, experiences, or qualifications.
2. JD KEYWORD ANALYSIS: Before writing, extract must-have keywords, skills, tools, and phrases from the job description. Naturally incorporate every matching keyword where it genuinely reflects actual experience. Prioritize and reorder content so the most JD-relevant items appear first.
3. HUMANIZED: Match the writing style shown in the examples. Avoid generic AI phrases like "results-driven professional" or "dynamic team player." No em dashes.
4. FORMATTING: Follow the INSTRUCTIONS section exactly — section names, header structure, bullet style, entry format, and horizontal rule placement. Do not invent your own structure.

--- {req.job_type.upper()} RESUME ---
{resume_content}

--- INSTRUCTIONS ---
{instructions}

--- WRITING STYLE EXAMPLES ---
{writing_examples}

--- EDUCATION / TRANSCRIPT ---
{transcript}

OUTPUT FORMAT — output exactly three XML-tagged sections, nothing else outside the tags:

<RESUME>
[Full resume following the INSTRUCTIONS formatting rules exactly — section headers in ALL CAPS, name in ALL CAPS centered, horizontal rule directly under name, bullets using ●, bold key phrases inline, work entries using the two-pattern system from the instructions, skills categories inline on same line as bold label]
</RESUME>

<COVER_LETTER>
Cover Letter

To the [Hiring Team / specific team name if known],

[Opening paragraph — specific, tailored to this company and role, do NOT open with "I am excited to apply" or generic lines]

[Body paragraph — 2-3 concrete examples from the resume that match this specific role]

[Closing paragraph — why this company or team, forward-looking]

Cheers and all the best!


Sincerely and thankfully,
{settings.owner_name}
louielynmata@gmail.com
http://www.linkedin.com/in/louielynmata
</COVER_LETTER>

<ANALYSIS>
ATS_SCORE: [0-100 integer]

SCORE_RATIONALE: [2-3 sentences explaining the score — what drove it up, what held it back]

KEYWORDS_APPLIED:
- [keyword or phrase from JD] — [where it was placed in the resume]
- [repeat for each applied keyword]

KEYWORDS_MISSING:
- [keyword or phrase from JD not yet in the resume] — [reason: not in source resume / could not be placed truthfully]

KEY_DECISIONS:
- [A specific tailoring decision made — what was changed from the base resume and why]
- [repeat for each major decision — reordered bullets, swapped section, emphasized specific experience, etc.]

GAPS:
- [A genuine gap between the JD requirements and the resume — be specific]
</ANALYSIS>"""

    user_prompt = f"""Job Description:
{req.job_description}

Target Position: {req.position}
Target Company: {req.company}"""

    try:
        ai_response = await generate_content(req.ai_provider, system_prompt, user_prompt)
    except ValueError as exc:
        raise _http_error(
            400,
            stage="call_ai_provider",
            code="AI_PROVIDER_CONFIG_ERROR",
            message="The selected AI provider is not configured correctly.",
            detail=str(exc),
            hint="Check the provider-specific settings in .env and confirm the selected model is available.",
        )
    except Exception as exc:
        status_code, code, message, detail, retryable = _classify_ai_error(req.ai_provider, exc)
        raise _http_error(
            status_code,
            stage="call_ai_provider",
            code=code,
            message=message,
            detail=detail,
            hint=(
                "If you are using Ollama, make sure the local server is running and the model is installed."
                if req.ai_provider == "ollama"
                else "Check your API key, model name, network access, and provider account limits."
            ),
            retryable=retryable,
        )

    analysis_text = _extract_analysis(ai_response)

    position_slug = _slugify(req.position)
    company_slug = _slugify(req.company)
    today_str = date.today().strftime("%Y-%m-%d")
    folder_name = f"{company_slug}_{position_slug}_{today_str}"

    output_dir = settings.output_path / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    if analysis_text:
        analysis_path = output_dir / "analysis.md"
        analysis_path.write_text(analysis_text, encoding="utf-8")

    try:
        docs = await build_documents(
            ai_response=ai_response,
            owner_name=settings.owner_name,
            position_slug=position_slug,
            output_dir=output_dir,
        )
    except ValueError as exc:
        raise _http_error(
            422,
            stage="build_documents",
            code="DOCUMENT_PARSE_ERROR",
            message="The AI response could not be converted into documents.",
            detail=str(exc),
            hint="Try regenerating or switch providers. The model likely missed the required <RESUME> or <COVER_LETTER> tags.",
            retryable=True,
        )
    except Exception as exc:
        raise _http_error(
            500,
            stage="build_documents",
            code="DOCUMENT_BUILD_FAILED",
            message="Document generation failed.",
            detail=str(exc),
        )

    notion_url = None
    if settings.notion_token and settings.notion_database_id:
        try:
            notion_url = await log_application(
                position=req.position,
                company=req.company,
                folder_name=folder_name,
                location=req.location,
                salary_annual=req.salary_annual,
                salary_hourly=req.salary_hourly,
                ai_used=req.ai_provider,
                contact_email=req.contact_email,
            )
        except Exception:
            pass

    return GenerateResponse(
        output_folder=str(output_dir.resolve()),
        resume_docx=docs.get("resume_docx", ""),
        resume_pdf=docs.get("resume_pdf"),
        cover_letter_docx=docs.get("cover_letter_docx", ""),
        cover_letter_pdf=docs.get("cover_letter_pdf"),
        notion_page_url=notion_url,
        analysis=analysis_text,
        message="Generated successfully",
    )
