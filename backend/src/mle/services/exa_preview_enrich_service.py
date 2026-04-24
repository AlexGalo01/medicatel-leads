from __future__ import annotations

import json
import logging
from typing import Any

from langsmith import traceable

from mle.core.config import get_settings
from mle.clients.llm_factory import get_llm_client

logger = logging.getLogger(__name__)

BATCH_SIZE = 12
ENRICH_TIMEOUT_SECONDS = 90.0
MAX_SPECIALTY_LEN = 160
MAX_CITY_LEN = 120
MAX_ORGANIZATION_LEN = 200


def _preview_prompt_batch(batch: list[dict[str, Any]]) -> str:
    rows: list[dict[str, Any]] = []
    prompt_snip = get_settings().exa_enrich_snippet_prompt_max
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
                "snippet": str(item.get("snippet") or "").strip()[:prompt_snip],
            }
        )
    payload = json.dumps(rows, ensure_ascii=False)
    return (
        "Eres un asistente de extraccion factual para resultados de busqueda web.\n"
        "Para cada fila en FILAS_JSON debes devolver:\n"
        "- specialty: especialidad, rol profesional o tipo de negocio/servicio\n"
        "- city: ciudad o localidad\n"
        "- organization: empresa, clínica, hospital, consultorio, organización o lugar de trabajo\n"
        "Extrae SOLO si aparecen de forma clara en title, snippet o url. "
        "Si no hay dato fiable, deja el campo como cadena vacía. No inventes ni infieras.\n"
        "OBLIGATORIO: Responde SIEMPRE en español. Si el texto original está en inglés, tradúcelo. "
        "Ejemplos: 'Cardiologist' → 'Cardiólogo', 'Private Clinic' → 'Clínica Privada'.\n\n"
        f"FILAS_JSON: {payload}\n\n"
        "Devuelve SOLO un JSON con esta forma exacta:\n"
        '{"items":[{"index":<numero>,"specialty":"<texto o vacio>","city":"<texto o vacio>","organization":"<texto o vacio>"},...]}\n'
        "Debe haber exactamente una entrada por cada index presente en FILAS_JSON, en cualquier orden."
    )


def _normalize_enrich_item(raw: dict[str, Any]) -> tuple[int, str, str, str] | None:
    try:
        idx = int(raw.get("index"))
    except (TypeError, ValueError):
        return None
    sp = str(raw.get("specialty", "")).strip()[:MAX_SPECIALTY_LEN]
    city = str(raw.get("city", "")).strip()[:MAX_CITY_LEN]
    org = str(raw.get("organization", "")).strip()[:MAX_ORGANIZATION_LEN]
    return idx, sp, city, org


@traceable(name="exa_preview_enrich_batch", run_type="chain")
async def _enrich_batch(llm_client, batch: list[dict[str, Any]]) -> dict[int, tuple[str, str, str]]:
    out: dict[int, tuple[str, str, str]] = {}
    if not batch:
        return out
    prompt = _preview_prompt_batch(batch)
    try:
        parsed = await llm_client.complete_json_prompt(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM enriquecimiento preview lote fallo: %s", exc)
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
        idx, sp, city, org = norm
        out[idx] = (sp, city, org)
    return out


async def enrich_exa_preview_rows(preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Añade specialty y city a cada dict de exa_results_preview usando Gemini por lotes.
    Si falla el modelo o un lote, esas filas quedan con specialty y city vacios.
    """
    if not preview:
        return preview
    settings = get_settings()
    llm_client = get_llm_client(settings)
    merged: dict[int, tuple[str, str, str]] = {}
    for i in range(0, len(preview), BATCH_SIZE):
        batch = [dict(x) for x in preview[i : i + BATCH_SIZE] if isinstance(x, dict)]
        if not batch:
            continue
        part = await _enrich_batch(llm_client, batch)
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
        triple = merged.get(idx)
        if triple:
            new_row["specialty"] = triple[0]
            new_row["city"] = triple[1]
            new_row["organization"] = triple[2]
        else:
            new_row.setdefault("specialty", "")
            new_row.setdefault("city", "")
            new_row.setdefault("organization", "")
        enriched.append(new_row)
    return enriched
