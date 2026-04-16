from functools import lru_cache

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = Field(alias="DATABASE_URL")
    exa_api_key: str = Field(alias="EXA_API_KEY")
    google_api_key: str = Field(alias="GOOGLE_API_KEY")
    google_model: str = Field(default="gemini-1.5-flash-latest", alias="GOOGLE_MODEL")
    google_reviewer_model: str = Field(default="gemini-2.0-flash", alias="GOOGLE_REVIEWER_MODEL")
    export_dir: str = Field(default="/app/exports", alias="EXPORT_DIR")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_endpoint: AnyUrl | None = Field(default=None, alias="LANGSMITH_ENDPOINT")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str | None = Field(default=None, alias="LANGSMITH_PROJECT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

