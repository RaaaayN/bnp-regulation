from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIA_", extra="ignore")

    app_name: str = "Regulatory Intelligence Assistant"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://regulatory:regulatory@postgres:5432/regulatory",
        repr=False,
    )
    evidence_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    max_results: int = Field(default=5, ge=1, le=50)
    auto_create_schema: bool = False
    gemini_api_key: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("RIA_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    gemini_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int | None = Field(default=768, ge=128, le=3072)
    gemini_cache_dir: Path = Path("artifacts/gemini-cache")
    gemini_max_attempts: int = Field(default=3, ge=1, le=10)
    gemini_backoff_seconds: float = Field(default=1.0, ge=0.0, le=60.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
