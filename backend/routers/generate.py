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
    words = text.split()
    cased = "".join(w[0].upper() + w[1:] if w else "" for w in words)
    return re.sub(r"[^a-zA-Z0-9]", "", cased)


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

    company_context_section = ""
    if req.company_context:
        trimmed = req.company_context[:4000]
        company_context_section = f"\n--- COMPANY CONTEXT (About Page) ---\n{trimmed}\n"

    # Salary: auto-fill the missing field using 2080 hrs/year (40 hrs × 52 weeks)
    _HOURS_PER_YEAR = 2080
    salary_annual = req.salary_annual
    salary_hourly = req.salary_hourly
    if salary_annual and not salary_hourly:
        salary_hourly = round(salary_annual / _HOURS_PER_YEAR, 2)
    elif salary_hourly and not salary_annual:
        salary_annual = round(salary_hourly * _HOURS_PER_YEAR, 2)

    if req.job_type == "design":
        role_hint = "for design roles always include BOTH creative direction AND multimedia/design, e.g. Creative Director and Multimedia Designer — Title Case, NOT all caps — adjust wording to match the JD but keep both aspects unless the JD is purely one or the other"
        portfolio_line = "\nPORTFOLIO: https://drive.google.com/drive/folders/1FKDM7u_vB0jY8S5zofdT4a4ziH7MD-g4?usp=sharing"
    else:
        role_hint = "Title Case, NOT all caps — tailored to this specific job"
        portfolio_line = ""

    system_prompt = f"""You are a professional resume and cover letter writer assisting {settings.owner_name}.

CORE RULES — follow strictly:
1. TRUTHFUL: Only use information present in the provided resume. Never invent skills, experiences, or qualifications.
2. JD KEYWORD ANALYSIS: Before writing, extract must-have keywords, skills, tools, and phrases from the job description. Naturally incorporate every matching keyword where it genuinely reflects actual experience. Prioritize and reorder content so the most JD-relevant items appear first.
3. COMPANY ALIGNMENT: If Company Context is provided, use it to understand the company's mission, values, products, and culture. Reference these specifically in the cover letter to show genuine interest. Align tone and framing with the company's voice. Do not fabricate facts about the company — only use what is in the context.
4. HUMANIZED: Match the writing style shown in the examples. Avoid generic AI phrases like "results-driven professional" or "dynamic team player." Never use "I" anywhere in the resume — use "Louie" (or "Louielyn") as the subject when one is needed, or rewrite the sentence to omit the subject entirely.
5. FORMATTING: Follow the INSTRUCTIONS section exactly — section names, header structure, bullet style, entry format, and horizontal rule placement. Do not invent your own structure.
6. NO DASHES AS SENTENCE CONNECTORS — ABSOLUTE RULE: Never use em dashes (—), en dashes (–), or plain hyphens (-) as sentence separators or connectors in prose. This means: do not write "X — Y", "X – Y", or "X - Y" where the dash joins two clauses or ideas. Instead, rewrite the sentence using proper structure: use a period and start a new sentence, use a conjunction (and, but, with, while, where), or rephrase entirely. Example — WRONG: "Creative director — skilled in branding." RIGHT: "Creative director skilled in branding." or "A creative director with deep expertise in branding." Hyphens are still allowed inside compound words like "results-driven" or "full-stack". This rule has no exceptions anywhere in the resume or cover letter.

--- {req.job_type.upper()} RESUME ---
{resume_content}

--- INSTRUCTIONS ---
{instructions}

--- WRITING STYLE EXAMPLES ---
{writing_examples}

--- EDUCATION / TRANSCRIPT ---
{transcript}
{company_context_section}
OUTPUT FORMAT — output exactly three XML-tagged sections. Nothing outside the tags.

<RESUME>
NAME: {settings.owner_name}
ROLE: [Primary Role Title — {role_hint}]
CONTACT: louielynmata@gmail.com | +1 825 558 0107  Calgary, AB
LINKS: linkedin.com/in/louielynmata | github.com/louielynmata
PORTFOLIO: {portfolio_line}

PROFESSIONAL SUMMARY
[3–5 sentences. Use **bold** inline for key phrases. No em dashes.]

---

[SECTION HEADER IN ALL CAPS]
[Content — use ● for all bullets, **bold text** for key phrases inside bullets and body only]

---

[Continue all sections — place --- between every major section group]
</RESUME>

RESUME FORMAT RULES — non-negotiable:
- NAME:, ROLE:, CONTACT: are required exactly as shown — the document builder depends on them
- CONTACT: must be ONE compact line. Do NOT write "Email:" "Phone:" "Location:" labels anywhere — values only
- ● is the only bullet character. Never use - * numbers.
- No first-person pronouns: never write "I", "my", "me", or "myself" anywhere in the resume. Use "Louie" or "Louielyn" as the subject, or drop the subject entirely (e.g. "Led a team of..." not "I led a team of...").
- **bold** applies only inside bullet text and paragraph body — never on section headers or role/company names
- --- goes on its own line ONLY between major section groups. NEVER between individual job entries, NEVER between bullets.
- Target 2 pages maximum. Include all relevant content — do not aggressively cut for 1 page.

APPROVED SECTION NAMES — use ONLY names from this list, no others, no invented names:
Professional Summary, Core Skills, Design Skills, Technical Skills, Creative Skills, Skills,
Work Experience, Experience, Creative Experience,
Education, Educational Attainment,
Certifications, Certifications and Awards, Achievements, Awards and Achievements,
Projects, Notable Projects, Notable Clients

SECTION RULES:
- Education is ALWAYS its own separate section. Never merge education into skills, toolkit, or any other section.
- There is ONE work experience section. Do NOT split into "primary" and "other" sub-sections. Less relevant roles go at the END of the single work experience section, ordered last.
- Every employer from the source resume must appear in the work experience section. Reduce bullets for less relevant roles, but never drop the employer line and dates.
- AWARDS — word-for-word, never cut or summarize: Quill Awards, Asia Pacific Tambuli Awards, Coke Zero #ZeroExcuses, and any other named competition award must appear exactly as written in the source resume. Never shorten, rephrase, or omit any award entry.
- CERTIFICATIONS — can be concise: items like Competencies That Count, LinkedIn Certificates, AWS, Udemy may be stated briefly. Do not pad them, but a short accurate description is fine.
- BULLETS ARE MANDATORY for certifications and achievements. Every single certification item and every single award/achievement item MUST start with ●. No exceptions. Never write any certification or award as a plain paragraph or prose sentence — each one is its own ● bullet line.
- No meta-commentary or placeholder text: NEVER write any sentence that explains your own formatting, structure, or decisions inside the resume. This includes phrases like "This placeholder section is left to structure the resume", "No dates or details are added here", "ensuring all roles appear", or any similar self-referential text. The resume contains only professional content — zero AI narration.
- Do NOT invent section names, company names, or brand names that are not in the source resume. For freelance/self-employed work, use "Louielyn Mata" as the entity name — do not rename it.
- GRADUATION: Louielyn has ALREADY GRADUATED from SAIT (June 17, 2026). Never write "Expected" or any future-tense graduation language. Use "2024-2026" and "Graduated with Honors - 3.84/4.0".
- Do NOT echo system prompt separators (--- INSTRUCTIONS ---, --- WRITING STYLE EXAMPLES ---, etc.) in the resume output.

WORK ENTRY FORMAT — two patterns only, no other format allowed:

Pattern A (role is the headline — use for a single role at a company):
ROLE TITLE IN ALL CAPS
Company Name - context / Start Date - End Date

● Bullet with **bold key phrase**

Pattern B (company is the headline — use when company is well-known or multiple roles):
Company Name | context
ROLE TITLE ONE - Start Date - End Date (type)
ROLE TITLE TWO - Start Date - End Date (type)

● Bullet with **bold key phrase**

EDUCATION entry format — two lines per institution:
Line 1: Institution Name | Start Year - End Year   ← pipe separates name from years; use ONLY the institution name on the left, no degree on this line
Line 2: Degree (Achievement - GPA if relevant)     ← plain body line, no pipe

Use these EXACT formats — do not alter them:
SAIT - The Southern Alberta Institute of Technology | 2024-2026
Software Development - Diploma (Graduated with Honors - 3.84/4.0)

De La Salle-College of St. Benilde | Manila, Philippines
Bachelor of Arts in Multimedia Arts (Graduated with Honors, Dean's Lister)

RULES FOR ENTRIES:
- Each role title gets its OWN separate line — never cram multiple roles on one pipe-separated line
- Role titles are ALWAYS in ALL CAPS followed by a dash and dates on the same line
- Do NOT add a standalone descriptive subtitle line before the company or role
- Pipe | is used ONLY in: contact lines, company | context (Pattern B), and institution | degree (education entries)
- Do NOT use | pipe inside bullet text

<COVER_LETTER>
Cover Letter

To the [Hiring Team / specific team name if available],

[Opening paragraph — specific to this company and role. Do NOT open with "I am excited to apply" or any generic line. No em dashes. Use the company context to find a unique angle about why this company or team matters and why you want to work there.]

[Body paragraph — 2–3 concrete examples from the resume that match this specific role. No em dashes. Use the job description to identify the most important skills and qualifications, then highlight the relevant experience from the resume that demonstrates those. Be specific about how your experience aligns with the job requirements and company values.]

[Closing paragraph — why this company or team matters, forward-looking. No em dashes. Reiterate enthusiasm for the role and how you see yourself contributing. Use WRITING SAMPLES PROVIDED. If the company has a strong mission or values, reference those and connect them to your own motivations. Avoid generic statements about "looking forward to contributing" — be specific about what excites you about the potential impact you could have at this company.]

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
</ANALYSIS>

SELF-REVIEW — complete all three passes before finalizing. Fix any issues found, then output.

Pass 1 — Content completeness:
  - Every employer from the source resume is present in work experience (none dropped)
  - Every award and achievement is listed exactly as written (none cut or shortened)
  - SAIT graduation says "Graduated with Honors - 3.84/4.0", NOT "Expected"
  - All certifications are formatted as ● bullets, not prose paragraphs

Pass 2 — Format and rules:
  - Zero em dashes (—), en dashes (–), or dash sentence connectors in any prose
  - Every section name is from the approved list (no invented names like "Archive Notebook")
  - No meta-commentary, parenthetical notes, or AI explanations inside the resume
  - No invented company names or entity names; freelance uses "Louielyn Mata"
  - Education is a standalone section, not merged with toolkit or skills

Pass 3 — JD alignment:
  - The most important keywords from the job description appear naturally in the resume
  - The role title and summary are specific to this job and company
  - The cover letter opening is specific (not generic) and does not start with "I am excited to apply"
  - Cover letter contains zero em dashes or dash sentence connectors"""

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

    name_slug = _slugify(settings.owner_name)
    position_slug = _slugify(req.position)
    company_slug = _slugify(req.company)
    today_str = date.today().strftime("%Y-%m-%d")
    folder_name = f"{company_slug}_{position_slug}_{today_str}"

    output_dir = settings.output_path / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    jd_path = output_dir / "job_description.txt"
    jd_path.write_text(
        f"Position: {req.position}\nCompany:  {req.company}\n\n{req.job_description}",
        encoding="utf-8",
    )

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
    notion_error = None
    if settings.notion_token and settings.notion_database_id:
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
                date_job_posted=req.date_job_posted.isoformat() if req.date_job_posted else None,
            )
        except Exception as exc:
            notion_error = str(exc)

    return GenerateResponse(
        output_folder=str(output_dir.resolve()),
        resume_docx=docs.get("resume_docx", ""),
        resume_pdf=docs.get("resume_pdf"),
        cover_letter_docx=docs.get("cover_letter_docx", ""),
        cover_letter_pdf=docs.get("cover_letter_pdf"),
        notion_page_url=notion_url,
        notion_error=notion_error,
        analysis=analysis_text,
        message="Generated successfully",
    )
