from __future__ import annotations

from typing import Any

from langsmith import traceable

from mle.observability.langsmith_setup import trace_inputs_exa_search, trace_outputs_exa_response


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

