from __future__ import annotations

import json
import logging
from typing import Any

from langsmith import traceable

from mle.clients.gemini_client import GeminiClient
from mle.core.config import get_settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 12
ENRICH_TIMEOUT_SECONDS = 90.0
MAX_SPECIALTY_LEN = 160
MAX_CITY_LEN = 120


def _preview_prompt_batch(batch: list[dict[str, Any]]) -> str:
    rows: list[dict[str, Any]] = []
    for item in batch:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        try:
            index_int = int(idx) if idx is not None else 0
        except (TypeError, ValueError):
            index_int = 0
        rows.append(
            {
                "index": index_int,
                "title": str(item.get("title", "")).strip()[:400],
                "url": str(item.get("url", "")).strip()[:800],
                "snippet": str(item.get("snippet") or "").strip()[:700],
            }
        )
    payload = json.dumps(rows, ensure_ascii=False)
    return (
        "Eres un asistente de extraccion factual para resultados de busqueda web (sector medico y profesional).\n"
        "Para cada fila en FILAS_JSON debes devolver specialty (especialidad o rol profesional) y city (ciudad o localidad) "
        "SOLO si aparecen de forma clara en title, snippet o url. Si no hay dato fiable, deja specialty y city como "
        "cadena vacia. No inventes ni infieras a partir de suposiciones.\n"
        "Responde en español para los valores de specialty y city cuando haya texto extraible.\n\n"
        f"FILAS_JSON: {payload}\n\n"
        "Devuelve SOLO un JSON con esta forma exacta:\n"
        '{"items":[{"index":<numero>,"specialty":"<texto o vacio>","city":"<texto o vacio>"},...]}\n'
        "Debe haber exactamente una entrada por cada index presente en FILAS_JSON, en cualquier orden."
    )


def _normalize_enrich_item(raw: dict[str, Any]) -> tuple[int, str, str] | None:
    try:
        idx = int(raw.get("index"))
    except (TypeError, ValueError):
        return None
    sp = str(raw.get("specialty", "")).strip()[:MAX_SPECIALTY_LEN]
    city = str(raw.get("city", "")).strip()[:MAX_CITY_LEN]
    return idx, sp, city


@traceable(name="exa_preview_enrich_batch", run_type="chain")
async def _enrich_batch(gemini: GeminiClient, batch: list[dict[str, Any]]) -> dict[int, tuple[str, str]]:
    out: dict[int, tuple[str, str]] = {}
    if not batch:
        return out
    prompt = _preview_prompt_batch(batch)
    try:
        parsed = await gemini.complete_json_prompt(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini enriquecimiento preview lote fallo: %s", exc)
        return out
    items = parsed.get("items")
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        norm = _normalize_enrich_item(it)
        if norm is None:
            continue
        idx, sp, city = norm
        out[idx] = (sp, city)
    return out


async def enrich_exa_preview_rows(preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Añade specialty y city a cada dict de exa_results_preview usando Gemini por lotes.
    Si falla el modelo o un lote, esas filas quedan con specialty y city vacios.
    """
    if not preview:
        return preview
    settings = get_settings()
    gemini = GeminiClient(
        api_key=settings.google_api_key,
        model_name=settings.google_model,
        timeout_seconds=ENRICH_TIMEOUT_SECONDS,
    )
    merged: dict[int, tuple[str, str]] = {}
    for i in range(0, len(preview), BATCH_SIZE):
        batch = [dict(x) for x in preview[i : i + BATCH_SIZE] if isinstance(x, dict)]
        if not batch:
            continue
        part = await _enrich_batch(gemini, batch)
        merged.update(part)

    enriched: list[dict[str, Any]] = []
    for row in preview:
        if not isinstance(row, dict):
            enriched.append(row)
            continue
        new_row = dict(row)
        try:
            idx = int(new_row.get("index", 0))
        except (TypeError, ValueError):
            idx = 0
        pair = merged.get(idx)
        if pair:
            new_row["specialty"] = pair[0]
            new_row["city"] = pair[1]
        else:
            new_row.setdefault("specialty", "")
            new_row.setdefault("city", "")
        enriched.append(new_row)
    return enriched
