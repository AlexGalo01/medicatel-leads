from mle.core.config import Settings
from mle.clients.gemini_client import GeminiClient
from mle.clients.openai_client import OpenAIClient


def get_llm_client(settings: Settings) -> GeminiClient | OpenAIClient:
    """Factory para instanciar el cliente LLM correcto según configuración."""
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model_name=settings.openai_model,
        )
    return GeminiClient(
        api_key=settings.google_api_key,
        model_name=settings.google_model,
    )


def get_reviewer_llm_client(settings: Settings) -> GeminiClient | OpenAIClient:
    """Factory para el cliente reviewer (usado en auto_enrich_node)."""
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model_name=settings.openai_model,
        )
    return GeminiClient(
        api_key=settings.google_api_key,
        model_name=settings.google_reviewer_model,
    )
