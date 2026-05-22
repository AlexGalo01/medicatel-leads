"""Nodo de búsqueda de negocios locales via Google Places API + Brave Local.

Phase 2: Grid Search — divide la ciudad en NxN celdas y busca en paralelo
usando locationBias por celda. Potencial: grid 3x3 × 60 resultados = 540 por búsqueda.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langsmith import traceable

from mle.clients.google_places_client import GooglePlacesAPIError, GooglePlacesClient
from mle.core.config import get_settings
from mle.nodes.planner_node import _build_planner_output
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.services.geocoding_service import BoundingBox, GridCell, build_grid, get_city_bbox
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

MAX_RESULTS = 600  # cap final después de dedup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_query_variations(query: str, city: str, country: str) -> list[str]:
    """Genera variaciones del query principal para búsquedas sin grid (fallback)."""
    queries = [query]
    q_lower = query.lower()
    city_lower = city.lower() if city else ""

    if city_lower and city_lower in q_lower:
        if country and country.lower() not in q_lower:
            queries.append(f"{query} {country}")
    else:
        if city:
            queries.append(f"{query} en {city}")
        if city and country:
            queries.append(f"{query} {city} {country}")

    if city and "cerca" not in q_lower:
        queries.append(f"{query} cerca de {city}")

    return queries[:4]


def _dedup_by_place_id(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Elimina duplicados por place_id (Places) o título+dirección (Brave)."""
    seen_place_ids: set[str] = set()
    seen_keys: set[str] = set()
    unique: list[dict[str, Any]] = []

    for r in results:
        place_id = str(r.get("place_id", "") or "").strip()
        if place_id:
            if place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)
        else:
            title = str(r.get("title", "") or "").strip().lower()
            addr = str(r.get("address", "") or "").strip().lower()[:40]
            key = f"{title}|{addr}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

        unique.append(r)

    return unique


def _cell_to_location_bias(cell: GridCell) -> dict[str, Any]:
    """Convierte una GridCell al formato locationBias de Google Places API."""
    return {
        "circle": {
            "center": {"latitude": cell.lat, "longitude": cell.lng},
            "radius": cell.radius_m,
        }
    }


# ---------------------------------------------------------------------------
# Búsqueda con Google Places (con semaphore para rate limiting)
# ---------------------------------------------------------------------------

async def _search_cell(
    client: GooglePlacesClient,
    query: str,
    cell: GridCell | None,
    semaphore: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    """Busca en una celda (o sin bias si cell=None) con control de concurrencia."""
    async with semaphore:
        location_bias = _cell_to_location_bias(cell) if cell else None
        return await client.text_search(query, location_bias=location_bias)


async def _run_grid_search(
    client: GooglePlacesClient,
    query: str,
    cells: list[GridCell],
    concurrency: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Ejecuta búsqueda en todas las celdas del grid en paralelo.

    Retorna (resultados, error_message_si_hubo_error_de_api).
    """
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(_search_cell(client, query, cell, semaphore))
        for cell in cells
    ]

    results: list[dict[str, Any]] = []
    api_error: str | None = None

    raw = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(raw):
        if isinstance(r, GooglePlacesAPIError):
            api_error = str(r)
            logger.error("Google Places API error en celda %d: %s", i, r)
            # Cancelar tasks restantes ya no tiene efecto tras gather, pero registramos
            break
        elif isinstance(r, Exception):
            logger.warning("Google Places celda %d falló (degrade): %s", i, r)
        elif isinstance(r, list):
            results.extend(r)

    return results, api_error


# ---------------------------------------------------------------------------
# Nodo principal
# ---------------------------------------------------------------------------

@traceable(
    name="local_business_search_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def local_business_search_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Busca negocios locales usando Google Places API con grid search + Brave Local."""
    try:
        settings = get_settings()

        # 1. Obtener contexto geográfico del planner
        planner_output = _build_planner_output(state).model_dump()
        relevance = planner_output.get("relevance_criteria", {})
        city = str(relevance.get("city", "") or "").strip()
        country = str(relevance.get("country_text", "") or "").strip()

        all_results: list[dict[str, Any]] = []
        places_api_error: str | None = None
        grid_used = False
        bbox: BoundingBox | None = None
        cells: list[GridCell] = []

        # 2. Google Places
        if settings.google_places_enabled:
            fallback_api_key = settings.other_google_api_key
            grid_size = settings.google_places_grid_size
            concurrency = settings.google_places_concurrency

            # 2a. Geocodificar ciudad → bbox → celdas (solo una vez, independiente de la key)
            if grid_size >= 2 and city:
                bbox = await get_city_bbox(city, country or None)

            if bbox and grid_size >= 2:
                cells = build_grid(bbox, grid_size)
                logger.info(
                    "Grid search job_id=%s: %dx%d=%d celdas, ciudad='%s' (%.1fkm×%.1fkm)",
                    state.job_id, grid_size, grid_size, len(cells), city,
                    bbox.width_km, bbox.height_km,
                )
            else:
                if not bbox and city and grid_size >= 2:
                    logger.warning(
                        "Nominatim no devolvió bbox para '%s' — usando variaciones de query sin grid",
                        city,
                    )

            # 2b. Función interna para ejecutar Places con una API key dada
            async def _places_search(api_key: str) -> tuple[list[dict[str, Any]], str | None]:
                _client = GooglePlacesClient(
                    api_key=api_key,
                    timeout_seconds=15.0,
                    max_pages=settings.google_places_max_pages,
                )
                if cells:
                    return await _run_grid_search(_client, state.query_text, cells, concurrency)
                # Sin grid: variaciones de query
                qvars = _generate_query_variations(state.query_text, city, country)
                logger.info("Variaciones job_id=%s: %d queries: %s", state.job_id, len(qvars), qvars)
                sem = asyncio.Semaphore(concurrency)
                _res: list[dict[str, Any]] = []
                _err: str | None = None
                raw_r = await asyncio.gather(
                    *[asyncio.create_task(_search_cell(_client, q, None, sem)) for q in qvars],
                    return_exceptions=True,
                )
                for i, r in enumerate(raw_r):
                    if isinstance(r, GooglePlacesAPIError):
                        _err = str(r)
                        logger.error("Google Places API error variacion %d: %s", i, r)
                        break
                    elif isinstance(r, Exception):
                        logger.warning("Google Places variacion %d falló: %s", i, r)
                    elif isinstance(r, list):
                        _res.extend(r)
                return _res, _err

            # 2c. OTHER_GOOGLE_API_KEY es la clave dedicada a Places (si está disponible);
            #     GOOGLE_API_KEY se usa para Gemini — solo la usamos en Places como último recurso.
            primary_places_key = fallback_api_key or settings.google_api_key
            secondary_places_key = settings.google_api_key if fallback_api_key else None

            places_results, places_api_error = await _places_search(primary_places_key)
            if places_api_error and secondary_places_key:
                logger.warning(
                    "Primary Places key falló (job_id=%s): %s — reintentando con GOOGLE_API_KEY",
                    state.job_id, places_api_error,
                )
                places_results, places_api_error = await _places_search(secondary_places_key)
                if not places_api_error:
                    logger.info("Fallback Google API key exitosa job_id=%s", state.job_id)

            all_results.extend(places_results)
            if cells:
                grid_used = True
                logger.info(
                    "Grid search completado job_id=%s: %d resultados brutos en %d celdas",
                    state.job_id, len(places_results), len(cells),
                )

        # 3. Brave Local — complemento gratuito (siempre con el query original)
        brave_count = 0
        if settings.brave_search_enabled and settings.brave_search_api_key:
            from mle.clients.brave_client import BraveSearchClient
            brave_client = BraveSearchClient(
                api_key=settings.brave_search_api_key,
                timeout_seconds=settings.brave_search_timeout_seconds,
            )
            try:
                brave_items = await _brave_local_bulk(brave_client, state.query_text)
                all_results.extend(brave_items)
                brave_count = len(brave_items)
            except Exception as exc:
                logger.warning("Brave local bulk falló job_id=%s: %s", state.job_id, exc)

        # 3b. Exa Search — complemento web para negocios locales
        exa_count = 0
        if settings.exa_api_key:
            try:
                from mle.clients.exa_client import ExaClient, exa_contents_highlights_config, finalize_exa_search_payload
                exa_client = ExaClient(api_key=settings.exa_api_key)
                exa_query = state.query_text
                if "Honduras" not in exa_query and "honduras" not in exa_query:
                    exa_query = f"{exa_query} Honduras"
                exa_payload = finalize_exa_search_payload({
                    "query": exa_query,
                    "type": "neural",
                    "numResults": 50,
                    "category": "company",
                    "userLocation": "HN",
                    "contents": exa_contents_highlights_config(300),
                })
                exa_resp = await exa_client.search(exa_payload)
                for r in exa_resp.get("results", []):
                    all_results.append({
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "text": r.get("text", ""),
                        "highlights": r.get("highlights", []),
                        "source_type": "exa_company",
                        "phone": "",
                        "address": "",
                        "website": r.get("url", ""),
                        "hours": "",
                        "rating": None,
                        "review_count": None,
                        "place_id": "",
                        "lat": None,
                        "lng": None,
                    })
                exa_count = len(exa_resp.get("results", []))
                logger.info("Exa company search job_id=%s: %d results", state.job_id, exa_count)
            except Exception as exc:
                logger.warning("Exa local search failed job_id=%s: %s", state.job_id, exc)

        # 4. Dedup global por place_id + cap
        unique_results = _dedup_by_place_id(all_results)[:MAX_RESULTS]

        # 5. Warnings
        warnings: list[str] = list(state.langsmith_metadata.get("warnings", []))
        if places_api_error:
            warnings.append(f"PLACES_API_ERROR:{places_api_error}")

        logger.info(
            "Local business search finalizado job_id=%s: %d brutos → %d únicos (grid=%s, celdas=%d, brave=%d)",
            state.job_id, len(all_results), len(unique_results),
            grid_used, len(cells), brave_count,
        )

        return {
            "status": "running",
            "current_stage": "search_finalize",
            "progress": 70,
            "planner_output": planner_output,
            "exa_raw_results": unique_results,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "warnings": warnings,
                "local_business_search": {
                    "grid_used": grid_used,
                    "grid_size": settings.google_places_grid_size,
                    "grid_cells": len(cells),
                    "bbox": {
                        "lat_min": bbox.lat_min, "lat_max": bbox.lat_max,
                        "lon_min": bbox.lon_min, "lon_max": bbox.lon_max,
                        "width_km": round(bbox.width_km, 1),
                        "height_km": round(bbox.height_km, 1),
                    } if bbox else None,
                    "raw_count": len(all_results),
                    "unique_count": len(unique_results),
                    "brave_count": brave_count,
                    "exa_count": exa_count,
                    "places_api_error": places_api_error,
                },
                "results_count": len(unique_results),
                "pipeline_phase": "directory",
            },
        }

    except Exception as exc:  # noqa: BLE001
        error_message = f"Local business search node falló: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "local_business_search",
            "progress": state.progress,
            "exa_raw_results": [],
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "local_business_error": error_message,
            },
        }


# ---------------------------------------------------------------------------
# Brave Local bulk helper
# ---------------------------------------------------------------------------

async def _brave_local_bulk(brave_client: Any, query: str) -> list[dict[str, Any]]:
    """Busca en Brave Local y retorna todos los resultados normalizados."""
    try:
        import httpx

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Cache-Control": "no-cache",
            "X-Subscription-Token": brave_client.api_key,
        }
        async with httpx.AsyncClient(timeout=brave_client.timeout_seconds) as client:
            response = await client.get(
                f"{brave_client.BASE_URL}/web/search",
                params={"q": query, "result_filter": "locations", "count": 20},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        locations = data.get("locations", {})
        results = locations.get("results", []) if isinstance(locations, dict) else []
        if not isinstance(results, list):
            return []

        items: list[dict[str, Any]] = []
        for loc in results:
            if not isinstance(loc, dict):
                continue
            name = str(loc.get("name", "") or "").strip()
            if not name:
                continue

            address_parts = [str(loc.get(f) or "") for f in ("address", "city", "state", "postal_code") if loc.get(f)]
            address = ", ".join(address_parts)

            hours_raw = loc.get("openingHours", [])
            hours = "; ".join(str(h) for h in hours_raw if h) if isinstance(hours_raw, list) else ""

            items.append({
                "url": str(loc.get("url", "") or ""),
                "title": name,
                "text": address,
                "highlights": [address] if address else [],
                "source_type": "brave_local",
                "phone": str(loc.get("phone", "") or "").strip(),
                "address": address,
                "website": str(loc.get("url", "") or "").strip(),
                "hours": hours,
                "rating": loc.get("rating"),
                "review_count": loc.get("review_count"),
                "place_id": "",
                "lat": None,
                "lng": None,
            })

        logger.info("Brave local bulk: query=%r, results=%d", query, len(items))
        return items

    except Exception as exc:
        logger.warning("Brave local bulk para '%s' falló (degrade safe): %s", query, exc)
        return []
