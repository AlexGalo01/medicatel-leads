from __future__ import annotations

from typing import Any

from langsmith import traceable

from mle.observability.langsmith_setup import (
    trace_inputs_exa_contents,
    trace_inputs_exa_search,
    trace_outputs_exa_contents_response,
    trace_outputs_exa_response,
)

_DEEP_SEARCH_TYPES = frozenset({"deep", "deep-reasoning", "deep-lite"})


def exa_contents_highlights_config(max_characters: int) -> dict[str, Any]:
    """Bloque `contents` para /search: highlights con tope de caracteres por Exa (ver docs)."""
    return {"highlights": {"maxCharacters": int(max_characters)}}


def exa_contents_full_config(
    text_max_characters: int,
    highlights_max_characters: int,
    subpages: int = 0,
) -> dict[str, Any]:
    """
    Bloque `contents` rico para /search: texto completo + highlights + subpáginas.

    `text.maxCharacters` cap sobre lo que Exa devuelve por página.
    `subpages > 0` hace que Exa crawlée N subpáginas (p. ej. /contacto, /about) por resultado.
    """
    block: dict[str, Any] = {
        "text": {"maxCharacters": int(text_max_characters)},
        "highlights": {"maxCharacters": int(highlights_max_characters)},
    }
    if subpages and int(subpages) > 0:
        block["subpages"] = int(subpages)
    return block


def finalize_exa_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Ajustes finales antes de POST /search:
    - category people/company es incompatible con includeDomains/excludeDomains (API Exa).
    - category no funciona correctamente con deep-reasoning (retorna muy pocos resultados).
    """
    if payload.get("includeDomains") or payload.get("excludeDomains"):
        payload.pop("category", None)
    if payload.get("type") in _DEEP_SEARCH_TYPES:
        payload.pop("category", None)
    return payload


class ExaClient:
    """Async client for Exa Search API."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.exa.ai"

    @traceable(
        name="exa_search_api",
        run_type="tool",
        process_inputs=trace_inputs_exa_search,
        process_outputs=trace_outputs_exa_response,
    )
    async def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/search",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return dict(response.json())

    @traceable(
        name="exa_contents_api",
        run_type="tool",
        process_inputs=trace_inputs_exa_contents,
        process_outputs=trace_outputs_exa_contents_response,
    )
    async def get_contents(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/contents",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return dict(response.json())

