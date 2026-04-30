from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_brave_web_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza resultados de Brave Web Search al formato de items de Exa.

    Cada resultado Exa tiene: url, title, text, highlights (lista), etc.
    Brave devuelve: url, title, description, extra_snippets (lista).
    """
    try:
        web = data.get("web", {})
        results = web.get("results", [])
        if not isinstance(results, list):
            return []
        items = []
        for r in results:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url", "")).strip()
            if not url:
                continue
            title = str(r.get("title", "") or "").strip()
            description = str(r.get("description", "") or "").strip()
            extra = r.get("extra_snippets")
            highlights = [description] if description else []
            if isinstance(extra, list):
                highlights.extend(str(s) for s in extra if s)
            items.append({
                "url": url,
                "title": title,
                "text": description,
                "highlights": highlights,
                "source_type": "brave_web",
            })
        return items
    except Exception as exc:
        logger.warning("Error normalizando resultados Brave Web: %s", exc)
        return []


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

    async def web_search(
        self,
        query: str,
        country: str | None = None,
        count: int = 20,
        pages: int = 2,
    ) -> list[dict[str, Any]]:
        """Busca en la web con Brave y normaliza resultados al formato Exa.

        Simplifica queries muy largas (>120 chars) para evitar 422. Pagina hasta `pages` veces.
        Degrade safe: retorna [] en error.
        """
        try:
            import httpx

            # Simplificar query si es muy larga (Brave rechaza queries complejas con 422)
            simplified_query = query.strip()
            if len(simplified_query) > 120:
                # Tomar solo las primeras palabras clave (tipicamente antes de "incluyendo", "con datos", etc)
                parts = simplified_query.split()
                simplified_query = " ".join(parts[:8])  # primeras ~8 palabras

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }
            all_items: list[dict[str, Any]] = []
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for offset in range(pages):
                    params: dict[str, Any] = {
                        "q": simplified_query,
                        "count": min(count, 20),
                        "offset": offset,
                        "extra_snippets": "true",
                    }
                    if country:
                        params["country"] = country.lower()
                    response = await client.get(
                        f"{self.BASE_URL}/web/search",
                        params=params,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()
                    batch = _normalize_brave_web_results(data)
                    all_items.extend(batch)
                    # Si no hay más resultados disponibles, dejar de paginar
                    more = data.get("query", {}).get("more_results_available", True)
                    if not more:
                        break
            return all_items
        except Exception as exc:
            logger.warning("Brave web search para '%s' falló (degrade safe): %s", query, exc)
            return []
