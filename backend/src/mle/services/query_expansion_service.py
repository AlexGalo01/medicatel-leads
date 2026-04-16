from __future__ import annotations

import logging
from typing import Any

from langsmith import traceable

from mle.clients.gemini_client import GeminiClient
from mle.core.config import get_settings

logger = logging.getLogger(__name__)


@traceable(name="expand_user_search_query", run_type="chain")
async def expand_user_search_query(
    user_query: str,
    contact_channels: list[str],
    search_focus: str | None,
    notes: str | None,
) -> tuple[str, dict[str, Any]]:
    """
    Devuelve (texto_expandido_para_Exa, metadata_de_expansion).
    Si Gemini falla, devuelve el query del usuario sin cambios.
    """
    normalized_user = user_query.strip()
    if not normalized_user:
        return "", {"fallback": True, "reason": "empty_user_query"}

    settings = get_settings()
    client = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_model)
    try:
        payload = await client.expand_search_query(
            user_query=normalized_user,
            contact_channels=contact_channels,
            search_focus=search_focus or "general",
            notes=(notes or "").strip() or None,
        )
        expanded = str(payload.get("expanded_query", "")).strip()
        if not expanded:
            raise ValueError("expanded_query vacio en respuesta del modelo")

        expansion_meta: dict[str, Any] = {
            "model": settings.google_model,
            "focus": search_focus or "general",
            "channel_instructions": payload.get("channel_instructions"),
            "negative_constraints": payload.get("negative_constraints"),
            "fallback": False,
        }
        return expanded, expansion_meta
    except Exception as exc:  # noqa: BLE001
        logger.warning("Expansion de query con Gemini no disponible, usando texto del usuario: %s", exc)
        return normalized_user, {
            "fallback": True,
            "model": settings.google_model,
            "focus": search_focus or "general",
            "error": str(exc)[:240],
        }
