import re
from datetime import date
from pathlib import Path
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import GenerateRequest, GenerateResponse
from ..services.ai_service import generate_content
from ..services.document_service import build_documents
from ..services.notion_service import log_application

router = APIRouter(prefix="/api/generate", tags=["generate"])


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", text.title().replace(" ", ""))


def _read_model(filename: str) -> str:
    p = settings.model_files_path / filename
    if not p.exists():
        return f"[{filename} — file not found. Add it to model_files/]"
    content = p.read_text(encoding="utf-8").strip()
    if content.startswith("[PLACEHOLDER"):
        return f"[{filename} — placeholder not yet filled in]"
    return content


@router.post("", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    # Validate provider
    if req.ai_provider not in ("claude", "openai", "ollama"):
        raise HTTPException(400, "ai_provider must be claude, openai, or ollama")
    if req.job_type not in ("design", "development"):
        raise HTTPException(400, "job_type must be design or development")

    # Load model files
    resume_file = "design_resume.md" if req.job_type == "design" else "dev_resume.md"
    resume_content = _read_model(resume_file)
    instructions = _read_model("instructions_prompt.md")
    writing_examples = _read_model("writing_examples.md")
    transcript = _read_model("school_transcript.md")

    system_prompt = f"""You are a professional resume and cover letter writer assisting {settings.owner_name}.

RULES — follow strictly:
1. TRUTHFUL: Only use information present in the provided resume. Never invent skills, experiences, or qualifications.
2. ATS-OPTIMIZED: Identify keywords and required skills from the job description. Naturally incorporate matching terms where they reflect actual experience.
3. HUMANIZED: Match the writing style shown in the examples. Avoid generic AI phrases like "results-driven professional" or "dynamic team player."

--- {req.job_type.upper()} RESUME ---
{resume_content}

--- INSTRUCTIONS ---
{instructions}

--- WRITING STYLE EXAMPLES ---
{writing_examples}

--- EDUCATION / TRANSCRIPT ---
{transcript}

OUTPUT FORMAT — use these exact XML tags. Output ONLY the two tagged sections, nothing else:

<RESUME>
# {settings.owner_name}
[contact: email | phone | location | linkedin/github]

## PROFESSIONAL SUMMARY
[2-3 sentences tailored to the job]

## WORK EXPERIENCE
### [Job Title] | [Company] | [Start Date – End Date]
- [Achievement bullet with metric where possible]
- [Achievement bullet]

## EDUCATION
### [Degree/Diploma] | [Institution] | [Year]

## SKILLS
[Category]: skill1, skill2, skill3
</RESUME>

<COVER_LETTER>
{date.today().strftime("%B %d, %Y")}

Hiring Manager
[Company Name]

Dear Hiring Manager,

[Paragraph 1: Why this specific role and company — be concrete]

[Paragraph 2: 2-3 specific examples of relevant experience from resume]

[Paragraph 3: Enthusiastic close + call to action]

Sincerely,
{settings.owner_name}
</COVER_LETTER>"""

    user_prompt = f"""Job Description:
{req.job_description}

Target Position: {req.position}
Target Company: {req.company}"""

    try:
        ai_response = await generate_content(req.ai_provider, system_prompt, user_prompt)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"AI provider error: {exc}")

    # Build output folder
    position_slug = _slugify(req.position)
    company_slug = _slugify(req.company)
    today_str = date.today().strftime("%Y-%m-%d")
    folder_name = f"{company_slug}_{position_slug}_{today_str}"

    output_dir = settings.output_path / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        docs = await build_documents(
            ai_response=ai_response,
            owner_name=settings.owner_name,
            position_slug=position_slug,
            output_dir=output_dir,
        )
    except ValueError as exc:
        raise HTTPException(422, f"Document generation error: {exc}")
    except Exception as exc:
        raise HTTPException(500, f"Document generation failed: {exc}")

    # Log to Notion (non-blocking — failure does not fail the request)
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
            pass  # Notion failure never blocks document generation

    return GenerateResponse(
        output_folder=str(output_dir.resolve()),
        resume_docx=docs.get("resume_docx", ""),
        resume_pdf=docs.get("resume_pdf"),
        cover_letter_docx=docs.get("cover_letter_docx", ""),
        cover_letter_pdf=docs.get("cover_letter_pdf"),
        notion_page_url=notion_url,
        message="Generated successfully",
    )
