"""Filtrado post-Exa por relevancia (ubicación / intención) con Gemini y heurística ligera."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from mle.services.country_iso_resolution import (
    extract_parenthesized_iso_codes,
    first_matching_non_target_country_iso,
)


class SupportsJsonPrompt(Protocol):
    async def complete_json_prompt(self, prompt: str) -> dict[str, Any]: ...

logger = logging.getLogger(__name__)

# Calidad sobre latencia: lotes pequeños para mejor precisión del modelo
DEFAULT_CHUNK_SIZE = 8


def _highlights_blob(item: dict[str, Any]) -> str:
    top_hl = item.get("highlights")
    if isinstance(top_hl, list) and top_hl:
        return " ".join(str(x) for x in top_hl if x)
    contents = item.get("contents")
    if isinstance(contents, dict):
        hl = contents.get("highlights")
        if isinstance(hl, list) and hl:
            return " ".join(str(x) for x in hl if x)
        txt = contents.get("text")
        if isinstance(txt, str):
            return txt
    return str(item.get("text", "") or "")


def _full_profile_blob(item: dict[str, Any]) -> str:
    """Concatena campos que Exa suele devolver para ubicación y rol."""
    parts = [
        str(item.get("title", "") or ""),
        str(item.get("text", "") or ""),
        _highlights_blob(item),
    ]
    for key in ("snippet", "summary", "description", "subtitle"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts)


def _excerpt(item: dict[str, Any], max_len: int = 900) -> str:
    parts = [
        str(item.get("title", "") or ""),
        str(item.get("url", "") or ""),
        _full_profile_blob(item),
    ]
    blob = " ".join(parts).strip()
    if len(blob) <= max_len:
        return blob
    return blob[: max_len - 1] + "…"


def filter_exa_list_heuristic_only(
    items: list[dict[str, Any]],
    target_iso: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Filtra solo con heurística (sin LLM). Útil tras enriquecer con snippet largo o al fusionar 'cargar más'.
    """
    if not target_iso or len(str(target_iso).strip()) != 2:
        return [x for x in items if isinstance(x, dict)], {"relevance_heuristic_only": "skipped_no_iso"}
    t = str(target_iso).strip().upper()
    kept: list[dict[str, Any]] = []
    drops = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if _heuristic_should_drop(item, t):
            drops += 1
            continue
        kept.append(item)
    return kept, {
        "relevance_heuristic_only_drops": drops,
        "relevance_heuristic_only_kept": len(kept),
    }


def _heuristic_should_drop(item: dict[str, Any], target_iso: str | None) -> bool:
    """
    Descarta sin LLM cuando:
    - El último código (XX) entre paréntesis (típico LinkedIn: ciudad, país (ISO)) difiere del objetivo, o
    - No hay señales del país objetivo pero sí mención explícita de otro país (palabra completa).
    """
    if not target_iso or len(target_iso) != 2:
        return False
    t = target_iso.strip().upper()
    blob = _full_profile_blob(item)
    codes = extract_parenthesized_iso_codes(blob)
    if codes:
        primary = codes[-1].upper()
        if primary != t:
            return True
    if first_matching_non_target_country_iso(blob, t):
        return True
    return False


def _compact_items_for_chunk(
    results: list[dict[str, Any]],
    indices: list[int],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in indices:
        item = results[i]
        out.append({"index": i, "title": str(item.get("title", "") or "")[:400], "url": str(item.get("url", "") or ""), "excerpt": _excerpt(item)})
    return out


def _parse_verdicts(parsed: dict[str, Any]) -> dict[int, bool]:
    verdicts = parsed.get("verdicts")
    if not isinstance(verdicts, list):
        return {}
    out: dict[int, bool] = {}
    for row in verdicts:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        match = row.get("match")
        if isinstance(match, bool):
            out[idx] = match
        elif str(match).lower() in ("true", "1", "yes", "si", "sí"):
            out[idx] = True
        elif str(match).lower() in ("false", "0", "no"):
            out[idx] = False
    return out


async def filter_exa_raw_results_by_relevance(
    *,
    raw_results: list[dict[str, Any]],
    user_query: str,
    relevance_criteria: dict[str, Any],
    gemini_client: SupportsJsonPrompt,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Devuelve (resultados_filtrados, metadata) con conteos y muestras de descartes.
    Si Gemini falla por completo, se conservan todos los resultados (degradación segura).
    """
    if not raw_results:
        return [], {"relevance_filter_kept": 0, "relevance_filter_dropped": 0, "relevance_filter_mode": "empty"}

    target_iso = str(relevance_criteria.get("country_iso2") or "").strip().upper() or None
    if len(target_iso or "") != 2:
        target_iso = None

    heuristic_drop: set[int] = set()
    for i, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        if _heuristic_should_drop(item, target_iso):
            heuristic_drop.add(i)

    pending_indices = [i for i in range(len(raw_results)) if i not in heuristic_drop]
    match_by_index: dict[int, bool] = {i: False for i in heuristic_drop}
    reasons: dict[int, str] = {}
    for i in heuristic_drop:
        item = raw_results[i]
        blob = _full_profile_blob(item) if isinstance(item, dict) else ""
        codes = extract_parenthesized_iso_codes(blob)
        if codes and codes[-1].upper() != str(target_iso or "").upper():
            reasons[i] = "Ubicación (código ISO en el perfil) no coincide con el país objetivo."
        elif first_matching_non_target_country_iso(blob, target_iso):
            reasons[i] = "El texto describe otro país distinto al objetivo."
        else:
            reasons[i] = "Ubicación explícita en el texto no coincide con el país objetivo."

    if pending_indices:
        criteria_compact = {
            "country_iso2": relevance_criteria.get("country_iso2"),
            "city": relevance_criteria.get("city"),
            "country_text": relevance_criteria.get("country_text"),
            "role_or_stack_hint": relevance_criteria.get("role_or_stack_hint"),
            "normalized_location": relevance_criteria.get("normalized_location"),
        }
        try:
            for start in range(0, len(pending_indices), chunk_size):
                chunk_idx = pending_indices[start : start + chunk_size]
                items_payload = _compact_items_for_chunk(raw_results, chunk_idx)
                strict_geo = bool(criteria_compact.get("country_iso2"))
                geo_rules = (
                    "Reglas estrictas de ubicación:\n"
                    "- Si country_iso2 del criterio indica un país (ej. HN = Honduras) y el candidato muestra "
                    "residencia o empleo principal en otro país (ej. Egipto, Cairo, (EG)), match=false aunque el rol "
                    "(ej. .NET, sistemas) coincida.\n"
                    "- match=true solo si la ubicación actual o principal alinea con ese país o no hay señal "
                    "contradictoria clara.\n"
                    "- Trabajo remoto sin país: match=true solo si no hay señales fuertes de otro país como sede.\n"
                )
                if strict_geo:
                    geo_rules += (
                        "- Ejemplo: usuario pide Honduras; candidato en Cairo, Egypt (EG) → match=false.\n"
                    )
                prompt = (
                    "Eres un validador estricto de relevancia para prospección B2B.\n"
                    f"Consulta original del usuario (máxima prioridad): {user_query}\n"
                    f"Criterios (JSON): {json.dumps(criteria_compact, ensure_ascii=False)}\n"
                    f"{geo_rules}"
                    "Cada ítem tiene index (posición global en la lista original), title, url, excerpt.\n"
                    "Decide si el resultado cumple la intención geográfica y profesional del usuario.\n"
                    "Devuelve SOLO JSON con la forma exacta:\n"
                    '{"verdicts":[{"index":0,"match":true,"reason_es":"breve"}]}\n'
                    "Debes incluir un veredicto por cada index enviado (un objeto por index).\n"
                    f"Ítems: {json.dumps(items_payload, ensure_ascii=False)}"
                )
                parsed = await gemini_client.complete_json_prompt(prompt)
                verdicts_map = _parse_verdicts(parsed)
                reason_by_index: dict[int, str] = {}
                for v in parsed.get("verdicts") or []:
                    if not isinstance(v, dict):
                        continue
                    try:
                        ix = int(v.get("index"))
                    except (TypeError, ValueError):
                        continue
                    reason_by_index[ix] = str(v.get("reason_es", "")).strip() or "No cumple criterios de relevancia."
                for idx in chunk_idx:
                    if idx in verdicts_map:
                        match_by_index[idx] = verdicts_map[idx]
                        if not verdicts_map[idx]:
                            reasons[idx] = reason_by_index.get(idx, "No cumple criterios de relevancia.")
                    elif target_iso:
                        match_by_index[idx] = False
                        reasons[idx] = "Sin veredicto del modelo; se excluye por criterio de país estricto."
                    else:
                        match_by_index[idx] = True
                        reasons[idx] = "Sin veredicto del modelo; se conserva."
        except Exception as exc:  # noqa: BLE001
            logger.warning("Filtro de relevancia Gemini omitido, se conservan ítems no heurísticos: %s", exc)
            for idx in pending_indices:
                if idx not in match_by_index:
                    match_by_index[idx] = True

    kept: list[dict[str, Any]] = []
    discarded_meta: list[dict[str, Any]] = []
    for i, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        if match_by_index.get(i, True):
            kept.append(item)
        else:
            discarded_meta.append(
                {
                    "index": i,
                    "url": str(item.get("url", "") or "")[:500],
                    "reason_es": reasons.get(i, "Descartado."),
                }
            )

    meta: dict[str, Any] = {
        "relevance_filter_kept": len(kept),
        "relevance_filter_dropped": len(discarded_meta),
        "relevance_filter_heuristic_drops": len(heuristic_drop),
        "relevance_filter_discarded_sample": discarded_meta[:40],
        "relevance_filter_mode": "applied",
    }
    return kept, meta
