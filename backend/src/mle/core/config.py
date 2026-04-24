from functools import lru_cache
from typing import Self

from pydantic import AnyUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# La API de Google dejó de exponer estos ids en v1beta; se redirigen al arranque.
_DEPRECATED_GEMINI_MODELS: dict[str, str] = {
    "gemini-1.5-flash-latest": "gemini-flash-latest",
    "gemini-1.5-flash": "gemini-flash-latest",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = Field(alias="DATABASE_URL")
    exa_api_key: str = Field(alias="EXA_API_KEY")
    exa_search_type: str = Field(default="deep-reasoning", alias="EXA_SEARCH_TYPE")
    exa_search_timeout_seconds: float = Field(default=45.0, alias="EXA_SEARCH_TIMEOUT_SECONDS")
    # Suma fija (p. ej. demo) al timeout HTTP de /search y /contents de Exa. 0 lo desactiva.
    exa_search_demo_extra_seconds: float = Field(default=20.0, ge=0.0, le=300.0, alias="EXA_SEARCH_DEMO_EXTRA_SECONDS")
    # Límite de caracteres que Exa genera por resultado en highlights (search + contents alineado con la API).
    exa_highlights_max_characters: int = Field(default=4000, ge=500, le=32_000, alias="EXA_HIGHLIGHTS_MAX_CHARACTERS")
    # Texto completo de cada resultado (contents.text.maxCharacters) — alimenta filtro de relevancia y auto-enrich.
    exa_text_max_characters: int = Field(default=12_000, ge=2_000, le=100_000, alias="EXA_TEXT_MAX_CHARACTERS")
    # Número de subpáginas a crawlear por resultado (páginas /contacto, /about, etc.).
    exa_subpages: int = Field(default=2, ge=0, le=5, alias="EXA_SUBPAGES")
    # Tamaño máximo del snippet de vista previa tras unir highlights/text (UI y JSON del job).
    exa_preview_snippet_max_chars: int = Field(default=12_000, ge=2_000, le=100_000, alias="EXA_PREVIEW_SNIPPET_MAX_CHARS")
    exa_preview_num_highlights: int = Field(default=16, ge=4, le=32, alias="EXA_PREVIEW_NUM_HIGHLIGHTS")
    exa_preview_title_max_chars: int = Field(default=500, ge=100, le=2_000, alias="EXA_PREVIEW_TITLE_MAX_CHARS")
    # Contexto de snippet en el prompt de enriquecimiento (especialidad/ciudad) por fila.
    exa_enrich_snippet_prompt_max: int = Field(default=2000, ge=400, le=8_000, alias="EXA_ENRICH_SNIPPET_PROMPT_MAX")
    # Excerpt del filtro de relevancia (antes 1400, ahora amplio porque ya tenemos text completo).
    relevance_filter_excerpt_max_chars: int = Field(default=6000, ge=1_000, le=20_000, alias="RELEVANCE_FILTER_EXCERPT_MAX_CHARS")
    # === Playwright Search (contact enrichment via Chrome automation - Knowledge Panel + Google Maps) ===
    opencli_enabled: bool = Field(default=True, alias="OPENCLI_ENABLED")
    opencli_binary_path: str = Field(default="/app/playwright_tool/bin/mle-search", alias="OPENCLI_BINARY_PATH")
    opencli_chrome_profile_path: str = Field(default="", alias="OPENCLI_CHROME_PROFILE_PATH")
    opencli_concurrency: int = Field(default=5, ge=1, le=20, alias="OPENCLI_CONCURRENCY")
    opencli_timeout_seconds: int = Field(default=60, ge=5, le=120, alias="OPENCLI_TIMEOUT_SECONDS")
    opencli_include_facebook: bool = Field(default=False, alias="OPENCLI_INCLUDE_FACEBOOK")
    opencli_include_instagram: bool = Field(default=False, alias="OPENCLI_INCLUDE_INSTAGRAM")
    google_api_key: str = Field(alias="GOOGLE_API_KEY")
    google_model: str = Field(default="gemini-flash-latest", alias="GOOGLE_MODEL")
    google_reviewer_model: str = Field(default="gemini-flash-latest", alias="GOOGLE_REVIEWER_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPEN_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    # Concurrencia de auto_enrich_node — separada de opencli para controlar rate limit LLM (OpenAI 500 RPM, Gemini 15 RPM).
    auto_enrich_concurrency: int = Field(default=5, ge=1, le=20, alias="AUTO_ENRICH_CONCURRENCY")
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
    mle_open_registration: bool = Field(default=True, alias="MLE_OPEN_REGISTRATION")

    @model_validator(mode="after")
    def _remap_deprecated_gemini_models(self) -> Self:
        updates: dict[str, str] = {}
        if self.google_model in _DEPRECATED_GEMINI_MODELS:
            updates["google_model"] = _DEPRECATED_GEMINI_MODELS[self.google_model]
        if self.google_reviewer_model in _DEPRECATED_GEMINI_MODELS:
            updates["google_reviewer_model"] = _DEPRECATED_GEMINI_MODELS[self.google_reviewer_model]
        if updates:
            return self.model_copy(update=updates)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def effective_exa_search_timeout_seconds(settings: Settings) -> float:
    """Timeout HTTP hacia Exa: base + extra (p. ej. ventana de demo)."""
    return float(settings.exa_search_timeout_seconds) + float(settings.exa_search_demo_extra_seconds)

