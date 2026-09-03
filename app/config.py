from functools import lru_cache

from pydantic import Field
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
    auto_create_schema: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
