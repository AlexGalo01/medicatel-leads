from __future__ import annotations

from typing import Any


class ExaClient:
    """Async client for Exa Search and WebSets APIs."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.exa.ai"
        self.websets_base_url = "https://api.exa.ai/websets/v0"

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

    async def create_webset(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.websets_base_url}/websets/",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return dict(response.json())

    async def get_webset(self, webset_id: str, expand_items: bool = False) -> dict[str, Any]:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        query_params = {"expand": "items"} if expand_items else None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.websets_base_url}/websets/{webset_id}",
                headers=headers,
                params=query_params,
            )
            response.raise_for_status()
            return dict(response.json())

    async def list_webset_items(self, webset_id: str, limit: int = 200) -> list[dict[str, Any]]:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        all_items: list[dict[str, Any]] = []
        cursor: str | None = None

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while True:
                params: dict[str, Any] = {"limit": limit}
                if cursor:
                    params["cursor"] = cursor

                response = await client.get(
                    f"{self.websets_base_url}/websets/{webset_id}/items",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                payload = dict(response.json())
                page_items = payload.get("data", [])
                if isinstance(page_items, list):
                    all_items.extend(item for item in page_items if isinstance(item, dict))

                has_more = bool(payload.get("hasMore", False))
                next_cursor = payload.get("nextCursor")
                if not has_more or not isinstance(next_cursor, str) or not next_cursor.strip():
                    break
                cursor = next_cursor

        return all_items

