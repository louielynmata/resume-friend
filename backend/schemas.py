from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date


class ScrapeRequest(BaseModel):
    url: str


class ScrapeResponse(BaseModel):
    text: str
    source_url: str


class GenerateRequest(BaseModel):
    job_description: str
    ai_provider: str        # "claude" | "openai" | "ollama"
    job_type: str           # "design" | "development"
    position: str
    company: str
    location: Optional[str] = None
    salary_annual: Optional[float] = None
    salary_hourly: Optional[float] = None
    date_job_posted: Optional[date] = None
    contact_email: Optional[str] = None


class GenerateResponse(BaseModel):
    output_folder: str
    resume_docx: str
    resume_pdf: Optional[str] = None
    cover_letter_docx: str
    cover_letter_pdf: Optional[str] = None
    notion_page_url: Optional[str] = None
    message: str


class ModelFilesResponse(BaseModel):
    design_resume: bool
    dev_resume: bool
    instructions_prompt: bool
    writing_examples: bool
    sait_transcript: bool
