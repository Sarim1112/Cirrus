"""Application settings, read from CIRRUS_* environment variables."""

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CIRRUS_", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+psycopg://cirrus:cirrus@localhost:5432/cirrus"
    allowed_origins: str = "http://localhost:3000"
    public_url: str = "http://localhost:3000"
    timezone: str = "America/Toronto"
    docs_enabled: bool = True

    cookie_secure: bool = False
    session_days: int = 14
    demo_enabled: bool = True
    demo_ttl_hours: int = 24
    trust_proxy: bool = False

    ai_enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: float = 90.0
    ollama_max_concurrency: int = 2

    max_upload_mb: int = 10
    max_import_rows: int = 50_000
    max_pdf_pages: int = 100

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Cirrus <no-reply@example.com>"

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def validate_for_runtime(self) -> None:
        if self.is_production and not self.cookie_secure:
            raise RuntimeError("Set CIRRUS_COOKIE_SECURE=true in production (HTTPS only cookies).")
        if self.is_production and "cirrus:cirrus@" in self.database_url:
            raise RuntimeError(
                "Replace the default database password before running in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def local_today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()
