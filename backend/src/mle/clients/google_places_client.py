from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GooglePlacesAPIError(Exception):
    """Error de configuración de Google Places API (key inválida, API no habilitada)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.regularOpeningHours",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
    "places.location",
])


def _normalize_place(p: dict[str, Any]) -> dict[str, Any]:
    """Normaliza un resultado de Google Places al formato compatible con exa_raw_results."""
    display_name = p.get("displayName", {})
    name = display_name.get("text", "") if isinstance(display_name, dict) else str(display_name)

    location = p.get("location", {})
    lat = location.get("latitude") if isinstance(location, dict) else None
    lng = location.get("longitude") if isinstance(location, dict) else None

    address = str(p.get("formattedAddress", "") or "")

    # Horarios
    hours_obj = p.get("regularOpeningHours", {})
    hours = ""
    if isinstance(hours_obj, dict):
        descriptions = hours_obj.get("weekdayDescriptions", [])
        if isinstance(descriptions, list):
            hours = "; ".join(str(h) for h in descriptions if h)

    phone = str(p.get("nationalPhoneNumber", "") or "").strip()
    if not phone:
        phone = str(p.get("internationalPhoneNumber", "") or "").strip()

    return {
        "url": str(p.get("googleMapsUri", "") or ""),
        "title": name.strip(),
        "text": address,
        "highlights": [address] if address else [],
        "source_type": "google_places",
        "phone": phone,
        "address": address,
        "website": str(p.get("websiteUri", "") or "").strip(),
        "hours": hours,
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "place_id": str(p.get("id", "") or ""),
        "lat": lat,
        "lng": lng,
    }


class GooglePlacesClient:
    """Async client for Google Places API (New) — Text Search."""

    BASE_URL = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self, api_key: str, timeout_seconds: float = 15.0, max_pages: int = 3) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_pages = min(max_pages, 3)

    async def text_search(
        self,
        query: str,
        location_bias: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Busca negocios locales por texto. Retorna hasta max_pages * 20 resultados normalizados.

        Raises GooglePlacesAPIError si la API no está habilitada o la key es inválida.
        Degrade safe para otros errores: retorna [].
        """
        try:
            import httpx

            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": _FIELD_MASK,
            }

            all_items: list[dict[str, Any]] = []
            page_token: str | None = None

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for page_num in range(self.max_pages):
                    body: dict[str, Any] = {
                        "textQuery": query,
                        "pageSize": 20,
                    }
                    if page_token:
                        body["pageToken"] = page_token
                    if location_bias and page_num == 0:
                        body["locationBias"] = location_bias

                    response = await client.post(
                        self.BASE_URL,
                        json=body,
                        headers=headers,
                    )

                    if not response.is_success:
                        status = response.status_code
                        body_text = response.text[:600]
                        logger.warning(
                            "Google Places HTTP %s — query=%r body=%s",
                            status, query, body_text,
                        )
                        # Errores de configuración — propagar explícitamente para alertar al usuario
                        if status in (401, 403):
                            raise GooglePlacesAPIError(
                                f"Google Places API no autorizada (HTTP {status}). "
                                "Verifica que la 'Places API (New)' esté habilitada en Google Cloud Console "
                                "y que tu GOOGLE_API_KEY tenga acceso a ella.",
                                status_code=status,
                            )
                        if status == 400:
                            raise GooglePlacesAPIError(
                                f"Google Places API rechazó la solicitud (HTTP 400): {body_text[:300]}",
                                status_code=status,
                            )
                        response.raise_for_status()

                    data = response.json()
                    places = data.get("places", [])
                    if not isinstance(places, list) or not places:
                        break

                    for p in places:
                        if isinstance(p, dict):
                            all_items.append(_normalize_place(p))

                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break

                    # Breve pausa entre páginas para respetar rate limits
                    if page_num < self.max_pages - 1:
                        await asyncio.sleep(0.3)

            logger.info("Google Places text_search: query=%r, results=%d", query, len(all_items))
            return all_items

        except GooglePlacesAPIError:
            raise  # propagar errores de configuración para que el nodo los detecte
        except Exception as exc:
            logger.warning("Google Places text_search para '%s' falló (degrade safe): %s", query, exc)
            return []
