"""Environment-based backend settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
BACKEND_ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./verifywise.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"
    jwt_secret_key: SecretStr | None = None
    access_token_expire_minutes: int = 15
    document_storage_dir: Path = Path.home() / ".verifywise-ai" / "private_documents"
    max_document_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_extracted_text_chars: int = Field(default=2_000_000, gt=0)
    pdf_max_pages: int = Field(default=200, ge=1, le=2000)
    ocr_max_pages: int = Field(default=20, ge=1, le=500)
    ocr_dpi: int = Field(default=150, ge=72, le=300)
    ocr_min_digital_chars: int = Field(default=16, ge=1, le=2000)
    ocr_max_page_pixels: int = Field(default=12_000_000, ge=250_000, le=30_000_000)
    ocr_page_timeout_seconds: int = Field(default=10, ge=1, le=120)
    pdf_processing_timeout_seconds: int = Field(default=60, ge=1, le=600)
    llm_api_key: SecretStr | None = None
    llm_base_url: AnyHttpUrl = "https://api.openai.com/v1"
    llm_model: str | None = None
    llm_timeout_seconds: int = Field(default=30, ge=1, le=180)
    max_llm_input_chars: int = Field(default=50_000, ge=1000, le=250_000)

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Load settings from the environment and optional local .env file."""
    return Settings()
