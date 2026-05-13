from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from langsmith import traceable

from mle.clients.brave_client import BraveSearchClient
from mle.core.config import get_settings
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.services.exa_preview_enrich_service import enrich_exa_preview_rows
from mle.services.relevance_filter_service import filter_exa_list_heuristic_only
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

PIPELINE_MODE_SEARCH_ONLY = "presearch_and_search_only"
MAX_EXA_PREVIEW_ITEMS = 80
MAX_EXA_ACCUMULATED_RAW = 120
MIN_SUGGESTED_SOURCES = 10


def _url_key_for_merge(url: str) -> str:
    return str(url or "").strip().lower().rstrip("/")


def _normalize_title(title: str) -> str:
    """Limpia títulos de ruido: navegación, separadores, afiliaciones.

    Ejemplos:
    - "Dr. Dacarett: Inicio" → "Dr. Dacarett"
    - "Dra. Gabriela López - Doctores de Honduras" → "Dra. Gabriela López"
    - "Karina Egans | Gerente de ventas" → "Karina Egans"
    - "Inicio - Dr. Reichmann - Clínica..." → "Dr. Reichmann"
    """
    t = str(title or "").strip()
    if not t:
        return ""

    # Palabras de navegación a eliminar al inicio/final
    nav_words = {"inicio", "home", "principal", "index"}

    # Si contiene pipe |, tomar solo la primera parte (antes de rol/descripción)
    if "|" in t:
        parts = [p.strip() for p in t.split("|")]
        t = parts[0]

    # Si contiene " - ", buscar patrón "Dr./Dra." en las partes
    if " - " in t:
        parts = [p.strip() for p in t.split(" - ")]
        # Buscar primero la parte con Dr./Dra. o nombre completo
        doctor_part = None
        for part in parts:
            if re.match(r"^(Dr\.|Dra\.)\s+", part, re.IGNORECASE):
                doctor_part = part
                break
        if doctor_part:
            # Tomar hasta el primer separador adicional (: o segunda parte)
            t = re.split(r"[:|-]", doctor_part)[0].strip()
        else:
            # Sin Dr/Dra, tomar el primer non-nav word
            for part in parts:
                if part.lower() not in nav_words:
                    t = part
                    break

    # Si contiene ":", tomar solo la parte antes del ":"
    if ":" in t:
        t = t.split(":")[0].strip()

    # Remover palabras de navegación al inicio
    words = t.split()
    while words and words[0].lower() in nav_words:
        words.pop(0)
    t = " ".join(words)

    # Remover palabras de navegación al final
    words = t.split()
    while words and words[-1].lower() in nav_words:
        words.pop()
    t = " ".join(words)

    return t.strip()


def _preview_item(raw: dict[str, Any], index: int) -> dict[str, Any]:
    s = get_settings()
    title_max = s.exa_preview_title_max_chars
    join_max = s.exa_preview_snippet_max_chars
    hl_slots = s.exa_preview_num_highlights
    raw_title = str(raw.get("title", "")).strip()[:title_max]
    title = _normalize_title(raw_title)
    url = str(raw.get("url", "")).strip()[:2000]
    highlights = raw.get("highlights")
    snippet = ""
    if isinstance(highlights, list):
        snippet = " | ".join(str(h) for h in highlights[:hl_slots])[:join_max]
    elif raw.get("text"):
        snippet = str(raw.get("text", ""))[:join_max]

    # Extraer LinkedIn URL si está presente
    linkedin_url = None
    if url and "linkedin.com" in url.lower():
        linkedin_url = url

    out = {
        "index": index + 1,
        "title": title or url or "Sin titulo",
        "url": url,
        "snippet": snippet or None,
    }
    if linkedin_url:
        out["linkedin_url"] = linkedin_url
    if "_prefetched_maps" in raw:
        out["_prefetched_maps"] = raw["_prefetched_maps"]
    return out


async def _fetch_brave_directory_sources(
    query_text: str,
    planner_output: dict[str, Any],
    existing_urls: set[str],
) -> list[dict[str, str]]:
    """Busca fuentes/directorios con Brave para complementar suggested_source_urls."""
    settings = get_settings()
    if not settings.brave_search_enabled or not settings.brave_search_api_key:
        return []

    rel = planner_output.get("relevance_criteria", {}) if isinstance(planner_output.get("relevance_criteria"), dict) else {}
    country = str(rel.get("country_text") or "").strip()
    city = str(rel.get("city") or "").strip()
    entity = str(rel.get("role_or_stack_hint") or "").strip()
    location = " ".join(p for p in (city, country) if p) or ""
    base_term = entity or query_text

    # Queries orientadas a directorios y listados
    brave_queries = [
        f"directorio {base_term} {location}",
        f"{base_term} {location} listado profesionales equipo staff",
        f"{base_term} {location} asociación colegio gremio",
    ]

    iso = str(rel.get("country_iso2") or "").strip().upper()
    brave_country = iso if len(iso) == 2 else None

    brave_client = BraveSearchClient(
        api_key=settings.brave_search_api_key,
        timeout_seconds=settings.brave_search_timeout_seconds,
    )

    coros = [brave_client.web_search(q, country=brave_country, count=20, pages=1) for q in brave_queries]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)

    sources: list[dict[str, str]] = []
    seen = set(existing_urls)
    for outcome in outcomes:
        if isinstance(outcome, Exception) or not isinstance(outcome, list):
            continue
        for item in outcome:
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            key = url.lower().rstrip("/")
            if not url or key in seen:
                continue
            # Excluir LinkedIn profiles individuales (solo queremos directorios/empresas)
            if "linkedin.com/in/" in url.lower():
                continue
            seen.add(key)
            sources.append({"url": url, "title": title or url, "source": "brave_directory_search"})

    return sources


_ENTITY_NOISE_RE = re.compile(
    r"^\s*(hospital y cl[íi]nica|hospital y clinica|cl[íi]nica m[eé]dica|centro m[eé]dico|"
    r"hospital|cl[íi]nica|clinica|fundaci[oó]n|fundacion|grupo|dr\.|dra\.)\s+",
    re.IGNORECASE,
)

_URL_QUALITY_RULES: list[tuple] = [
    (lambda u: u.endswith(".hn") or ".hn/" in u, 10),
    (lambda u: "linkedin.com/company" in u, 6),
    (lambda u: any(x in u for x in ("facebook.com", "instagram.com")), 3),
    (lambda u: any(x in u for x in ("wikipedia", "ecured", "mapcarta", "waze", "geonames", "mindat")), 1),
]


def _entity_key(title: str) -> str:
    key = _ENTITY_NOISE_RE.sub("", title.lower().strip())
    key = re.split(r"[\s\u2013\-|:/]+", key)[0]
    return key[:40].strip()


def _url_quality(url: str) -> int:
    u = url.lower()
    for fn, score in _URL_QUALITY_RULES:
        if fn(u):
            return score
    return 5


def _build_exa_preview(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    entity_seen: dict[str, int] = {}  # entity_key → best quality score seen so far
    for item in results[:MAX_EXA_PREVIEW_ITEMS]:
        if not isinstance(item, dict):
            continue
        raw_title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        key = _entity_key(_normalize_title(raw_title))
        quality = _url_quality(url)
        if key and len(key) > 3:
            if key in entity_seen:
                if quality <= entity_seen[key]:
                    continue  # already have a better URL for this entity
                # this URL is better — replace the previous entry
                out = [r for r in out if _entity_key(r.get("title", "")) != key]
            entity_seen[key] = quality
        out.append(_preview_item(item, len(out)))
    # re-index sequentially
    for idx, row in enumerate(out):
        row["index"] = idx + 1
    return out


@traceable(
    name="search_finalize_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def search_finalize_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Cierra el pipeline en modo demo: solo prebusqueda + Exa.
    Serializa una vista previa acotada de resultados para la API y el frontend.
    """
    await asyncio.sleep(0)
    accumulated = [dict(item) for item in state.exa_raw_results[:MAX_EXA_ACCUMULATED_RAW] if isinstance(item, dict)]
    logger.info("search_finalize: job_id=%s acumulados=%s", state.job_id, len(accumulated))

    preview = _build_exa_preview(accumulated)
    logger.info("search_finalize: preview inicial job_id=%s items=%s", state.job_id, len(preview))

    try:
        preview = await enrich_exa_preview_rows(preview)
        logger.info("search_finalize: preview enriquecido job_id=%s items=%s", state.job_id, len(preview))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Enriquecimiento preview Exa omitido job_id=%s: %s", state.job_id, exc, exc_info=True)

    finalize_heuristic_meta: dict[str, Any] = {}
    planner_out = state.planner_output if isinstance(state.planner_output, dict) else {}
    rel = planner_out.get("relevance_criteria") if isinstance(planner_out.get("relevance_criteria"), dict) else {}
    iso = str(rel.get("country_iso2") or "").strip().upper()
    if len(iso) == 2 and accumulated and preview:
        enriched_by_url: dict[str, dict[str, Any]] = {}
        for row in preview:
            if isinstance(row, dict):
                uk = _url_key_for_merge(str(row.get("url", "")))
                if uk:
                    enriched_by_url[uk] = row
        composite: list[dict[str, Any]] = []
        for raw_row in accumulated:
            if not isinstance(raw_row, dict):
                continue
            merged_row = dict(raw_row)
            uk = _url_key_for_merge(str(merged_row.get("url", "")))
            if uk and uk in enriched_by_url:
                sn = enriched_by_url[uk].get("snippet")
                if isinstance(sn, str) and sn.strip():
                    merged_row["snippet"] = sn.strip()
            composite.append(merged_row)
        filtered_composite, finalize_heuristic_meta = filter_exa_list_heuristic_only(composite, iso)
        order_urls = [_url_key_for_merge(str(x.get("url", ""))) for x in filtered_composite if str(x.get("url", "")).strip()]
        by_url = {
            _url_key_for_merge(str(x.get("url", ""))): x
            for x in accumulated
            if isinstance(x, dict) and str(x.get("url", "")).strip()
        }
        accumulated = []
        for uk in order_urls:
            if uk in by_url:
                accumulated.append(by_url[uk])
        accumulated = accumulated[:MAX_EXA_ACCUMULATED_RAW]
        preview_out: list[dict[str, Any]] = []
        for i, raw_row in enumerate(accumulated):
            base = _preview_item(raw_row, i)
            uk = _url_key_for_merge(str(raw_row.get("url", "")))
            if uk and uk in enriched_by_url:
                old = enriched_by_url[uk]
                base["specialty"] = str(old.get("specialty") or "")
                base["city"] = str(old.get("city") or "")
            preview_out.append(base)
        preview = preview_out

    logger.info(
        "search_finalize job_id=%s resultados_exa=%s acumulados_guardados=%s preview=%s heuristic_meta=%s",
        state.job_id,
        len(state.exa_raw_results),
        len(accumulated),
        len(preview),
        finalize_heuristic_meta,
    )
    meta_out = {
        **state.langsmith_metadata,
        "pipeline_mode": PIPELINE_MODE_SEARCH_ONLY,
        "exa_results_preview": preview,
        "exa_accumulated_raw": accumulated,
        "exa_more_rounds": 0,
    }
    if finalize_heuristic_meta:
        meta_out = {**meta_out, **finalize_heuristic_meta}

    # Completar fuentes sugeridas si hay menos de MIN_SUGGESTED_SOURCES
    existing_sources: list[dict[str, str]] = meta_out.get("suggested_source_urls", [])
    if not isinstance(existing_sources, list):
        existing_sources = []
    if len(existing_sources) < MIN_SUGGESTED_SOURCES:
        existing_source_urls = {s.get("url", "").strip().lower().rstrip("/") for s in existing_sources}
        # También excluir URLs ya en resultados
        result_urls = {_url_key_for_merge(str(r.get("url", ""))) for r in accumulated}
        all_seen = existing_source_urls | result_urls
        try:
            brave_sources = await _fetch_brave_directory_sources(
                query_text=state.query_text,
                planner_output=planner_out,
                existing_urls=all_seen,
            )
            needed = MIN_SUGGESTED_SOURCES - len(existing_sources)
            existing_sources.extend(brave_sources[:needed])
            logger.info(
                "search_finalize: fuentes complementadas con Brave job_id=%s, total=%s",
                state.job_id, len(existing_sources),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Brave directory sources falló job_id=%s: %s", state.job_id, exc)
    meta_out["suggested_source_urls"] = existing_sources

    # Construir preview de LPA desde los raw results
    lpa_raw = meta_out.get("lpa_results") or []
    if isinstance(lpa_raw, list) and lpa_raw:
        lpa_preview = _build_exa_preview(lpa_raw)
        meta_out["lpa_preview"] = lpa_preview
        logger.info("search_finalize: lpa_preview job_id=%s items=%s", state.job_id, len(lpa_preview))

    return {
        "status": "running",
        "current_stage": "auto_enrich",
        "progress": 80,
        "langsmith_metadata": meta_out,
    }
