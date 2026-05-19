"""Servicio de geocodificación usando Nominatim (OpenStreetMap) — sin API key."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# User-Agent requerido por la política de uso de Nominatim
_NOMINATIM_UA = "LeadGenAI/1.0 (contact@leadgenai.app)"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@dataclass(frozen=True)
class BoundingBox:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    @property
    def center_lat(self) -> float:
        return (self.lat_min + self.lat_max) / 2

    @property
    def center_lon(self) -> float:
        return (self.lon_min + self.lon_max) / 2

    @property
    def width_km(self) -> float:
        """Ancho aproximado en km."""
        return _haversine_km(self.center_lat, self.lon_min, self.center_lat, self.lon_max)

    @property
    def height_km(self) -> float:
        """Alto aproximado en km."""
        return _haversine_km(self.lat_min, self.center_lon, self.lat_max, self.center_lon)


@dataclass(frozen=True)
class GridCell:
    lat: float        # centro de la celda
    lng: float        # centro de la celda
    radius_m: float   # radio de búsqueda en metros


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia entre dos coordenadas en kilómetros."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def build_grid(bbox: BoundingBox, grid_size: int) -> list[GridCell]:
    """Divide un bounding box en grid_size × grid_size celdas.

    Retorna una lista de GridCell con el centro y radio de cada celda.
    El radio es la mitad de la diagonal de la celda + 20% de overlap para no perder negocios en bordes.
    """
    n = max(1, grid_size)
    lat_step = (bbox.lat_max - bbox.lat_min) / n
    lon_step = (bbox.lon_max - bbox.lon_min) / n

    cells: list[GridCell] = []
    for i in range(n):
        for j in range(n):
            cell_lat = bbox.lat_min + (i + 0.5) * lat_step
            cell_lon = bbox.lon_min + (j + 0.5) * lon_step

            # Radio = mitad de la diagonal de la celda en metros + 20% overlap
            cell_h_km = _haversine_km(
                bbox.lat_min + i * lat_step, cell_lon,
                bbox.lat_min + (i + 1) * lat_step, cell_lon,
            )
            cell_w_km = _haversine_km(
                cell_lat, bbox.lon_min + j * lon_step,
                cell_lat, bbox.lon_min + (j + 1) * lon_step,
            )
            diagonal_km = math.sqrt(cell_h_km ** 2 + cell_w_km ** 2)
            radius_m = (diagonal_km / 2) * 1000 * 1.2  # +20% overlap

            cells.append(GridCell(lat=cell_lat, lng=cell_lon, radius_m=round(radius_m)))

    logger.debug(
        "Grid %dx%d generado: %d celdas, bbox=%.4f,%.4f→%.4f,%.4f",
        n, n, len(cells), bbox.lat_min, bbox.lon_min, bbox.lat_max, bbox.lon_max,
    )
    return cells


async def get_city_bbox(city: str, country: str | None = None) -> BoundingBox | None:
    """Obtiene el bounding box de una ciudad usando Nominatim (OpenStreetMap).

    Degrade safe: retorna None si falla o la ciudad no se encuentra.
    """
    try:
        import httpx

        query = city.strip()
        if country:
            query = f"{query}, {country.strip()}"

        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "limit": 3,
            "featuretype": "city,town,municipality,administrative",
        }

        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": _NOMINATIM_UA},
        ) as client:
            response = await client.get(_NOMINATIM_URL, params=params)
            response.raise_for_status()
            results = response.json()

        if not isinstance(results, list) or not results:
            logger.warning("Nominatim: no resultados para '%s'", query)
            return None

        # Tomar el primer resultado con boundingbox válido
        for r in results:
            bb = r.get("boundingbox")
            if not isinstance(bb, list) or len(bb) < 4:
                continue
            try:
                lat_min, lat_max, lon_min, lon_max = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
                bbox = BoundingBox(lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max)
                logger.info(
                    "Nominatim bbox para '%s': %.4f,%.4f → %.4f,%.4f (%.1fkm × %.1fkm)",
                    query, lat_min, lon_min, lat_max, lon_max, bbox.width_km, bbox.height_km,
                )
                return bbox
            except (ValueError, TypeError):
                continue

        logger.warning("Nominatim: ningún resultado con boundingbox válido para '%s'", query)
        return None

    except Exception as exc:
        logger.warning("Nominatim geocoding para '%s' falló (degrade safe): %s", city, exc)
        return None
