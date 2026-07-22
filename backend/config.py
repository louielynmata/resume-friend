from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).parent.parent  # project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Personal
    owner_name: str = "Applicant"
    owner_email: str = ""

    # AI Providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    ollama_think: bool = True
    claude_model: str = "claude-sonnet-5-6"
    openai_model: str = "gpt-5o"

    # Independent QA reviewer/fixer
    qa_enabled: bool = True
    qa_provider: str = "same"
    # Four retries plus the mandatory independent review = five total attempts.
    qa_max_repairs: int = 4
    qa_language: str = "en-CA"
    qa_fail_open: bool = False
    qa_visual_enabled: bool = True
    qa_resume_max_pages: int = 2
    qa_design_resume_max_pages: int = 3
    qa_cover_letter_max_pages: int = 1

    # Notion
    notion_token: str = ""
    notion_database_id: str = ""

    # Paths (relative to project root)
    app_model_files_dir: str = "./prompts"
    model_files_dir: str = "./models_personal"
    output_dir: str = "./outputs"
    qa_temp_dir: str = "./tmp/pdfs"
    reference_dir: str = "./ref"

    # App
    backend_port: int = 8000
    frontend_port: int = 5173

    @property
    def model_files_path(self) -> Path:
        p = Path(self.model_files_dir)
        return p if p.is_absolute() else _ROOT / p

    @property
    def app_model_files_path(self) -> Path:
        p = Path(self.app_model_files_dir)
        return p if p.is_absolute() else _ROOT / p

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir)
        return p if p.is_absolute() else _ROOT / p

    @property
    def qa_temp_path(self) -> Path:
        p = Path(self.qa_temp_dir)
        return p if p.is_absolute() else _ROOT / p

    @property
    def reference_path(self) -> Path:
        p = Path(self.reference_dir)
        return p if p.is_absolute() else _ROOT / p


settings = Settings()
