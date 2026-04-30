from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_brave_location(data: dict[str, Any]) -> dict[str, str]:
    """Normaliza respuesta de Brave Local Search al formato esperado.

    Extrae del primer resultado de locations: phone, address, hours, website, email.
    Retorna {} si no hay resultados o si ocurre error.
    """
    try:
        locations = data.get("locations", {})
        if not isinstance(locations, dict):
            return {}

        results = locations.get("results", [])
        if not isinstance(results, list) or not results:
            return {}

        first = results[0]
        if not isinstance(first, dict):
            return {}

        # Construir dirección desde componentes
        address_parts = []
        if first.get("address"):
            address_parts.append(str(first["address"]))
        if first.get("city"):
            address_parts.append(str(first["city"]))
        if first.get("state"):
            address_parts.append(str(first["state"]))
        if first.get("postal_code"):
            address_parts.append(str(first["postal_code"]))

        address = ", ".join(p for p in address_parts if p)

        # Horas: array de strings → joined por ";"
        hours_raw = first.get("openingHours", [])
        if isinstance(hours_raw, list):
            hours = "; ".join(str(h) for h in hours_raw if h)
        else:
            hours = ""

        return {
            "phone": str(first.get("phone", "")).strip() or "",
            "address": address,
            "hours": hours,
            "website": str(first.get("url", "")).strip() or "",
            "email": str(first.get("email", "")).strip() or "",
            "source": "brave_local",
        }
    except Exception as exc:
        logger.warning("Error normalizando respuesta Brave: %s", exc)
        return {}


class BraveSearchClient:
    """Async client for Brave Local Search API."""

    BASE_URL = "https://api.search.brave.com/res/v1"

    def __init__(self, api_key: str, timeout_seconds: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def local_search(self, query: str) -> dict[str, str]:
        """Busca info de negocio local. Retorna {phone, address, hours, website, email, source}.

        Si ocurre error o no hay resultados, retorna {} (degrade safe).
        """
        try:
            import httpx

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{self.BASE_URL}/web/search",
                    params={
                        "q": query,
                        "result_filter": "locations",
                        "count": 3,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                return _normalize_brave_location(data)
        except Exception as exc:
            logger.warning("Brave local search para '%s' falló (degrade safe): %s", query, exc)
            return {}
