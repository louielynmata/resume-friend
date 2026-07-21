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
    owner_name: str = "LouielynMata"
    owner_email: str = ""

    # AI Providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    ollama_think: bool = True
    claude_model: str = "claude-sonnet-5-6"
    openai_model: str = "gpt-5o"

    # Notion
    notion_token: str = ""
    notion_database_id: str = ""

    # Paths (relative to project root)
    model_files_dir: str = "./models_personal"
    output_dir: str = "./outputs"

    # App
    backend_port: int = 8000
    frontend_port: int = 5173

    @property
    def model_files_path(self) -> Path:
        p = Path(self.model_files_dir)
        return p if p.is_absolute() else _ROOT / p

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir)
        return p if p.is_absolute() else _ROOT / p


settings = Settings()
