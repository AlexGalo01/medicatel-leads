from functools import lru_cache

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = Field(alias="DATABASE_URL")
    exa_api_key: str = Field(alias="EXA_API_KEY")
    exa_search_type: str = Field(default="auto", alias="EXA_SEARCH_TYPE")
    exa_search_timeout_seconds: float = Field(default=45.0, alias="EXA_SEARCH_TIMEOUT_SECONDS")
    google_api_key: str = Field(alias="GOOGLE_API_KEY")
    google_model: str = Field(default="gemini-1.5-flash-latest", alias="GOOGLE_MODEL")
    google_reviewer_model: str = Field(default="gemini-2.0-flash", alias="GOOGLE_REVIEWER_MODEL")
    export_dir: str = Field(default="/app/exports", alias="EXPORT_DIR")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_endpoint: AnyUrl | None = Field(default=None, alias="LANGSMITH_ENDPOINT")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str | None = Field(default=None, alias="LANGSMITH_PROJECT")
    jwt_secret: str = Field(
        default="dev-change-jwt-secret-in-production",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expires_hours: int = Field(default=24, ge=1, le=168, alias="JWT_EXPIRES_HOURS")
    mle_initial_admin_email: str | None = Field(default=None, alias="MLE_INITIAL_ADMIN_EMAIL")
    mle_initial_admin_password: str | None = Field(default=None, alias="MLE_INITIAL_ADMIN_PASSWORD")
    mle_initial_admin_display_name: str = Field(
        default="Administrador",
        alias="MLE_INITIAL_ADMIN_DISPLAY_NAME",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

