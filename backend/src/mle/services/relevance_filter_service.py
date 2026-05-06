"""Filtrado post-Exa por relevancia (ubicación, intención y tipo de entidad people/company) con Gemini."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from mle.core.config import get_settings
from mle.services.country_iso_resolution import (
    blob_has_target_country_markers,
    extract_parenthesized_iso_codes,
    first_matching_non_target_country_iso,
)


class SupportsJsonPrompt(Protocol):
    async def complete_json_prompt(self, prompt: str) -> dict[str, Any]: ...

logger = logging.getLogger(__name__)

# Calidad sobre latencia: lotes pequeños para mejor precisión del modelo
DEFAULT_CHUNK_SIZE = 8
DEFAULT_CONFIDENCE_THRESHOLD = 8


def _exa_category_entity_rules(exa_category: str | None) -> str:
    """Bloque de prompt: alinear con category people/company de Exa (resultados puros de persona u organización)."""
    c = (exa_category or "").strip().lower()
    if c == "people":
        return (
            "Reglas estrictas de tipo de entidad (búsqueda Exa: modo PERSONAS / people):\n"
            "- match=true si el sujeto principal del resultado es una PERSONA: perfil de individuo, nombre propio, "
            "rol 'X at [organización]', URL tipo linkedin.com/in/ de persona, etc.\n"
            "- match=false si el sujeto es esencialmente una EMPRESA, HOSPITAL, CLÍNICA, MARCA u ORGANIZACIÓN sin lead "
            "persona: landing corporativa, ficha de institución, linkedin.com/company/ sin individuo, directorio de "
            "empresas, páginas 'nosotros' de marca.\n"
            "- Caso híbrido (ej. clínica): match=true si título o excerpt identifica claramente a una persona; si solo "
            "aparece la entidad, match=false.\n"
            "Combina: match final true solo si cumple ubicación (reglas de geo) y este criterio de entidad.\n"
        )
    if c == "company":
        return (
            "Reglas estrictas de tipo de entidad (búsqueda Exa: modo EMPRESAS / company):\n"
            "- match=true si el sujeto principal es una ORGANIZACIÓN: web corporativa, ficha de negocio, "
            "linkedin.com/company/ o equivalente, hospital/clínica/marca como entidad a prospectar.\n"
            "- match=false para perfiles de INDIVIDUO (p. ej. linkedin.com/in/) cuando el foco de la búsqueda es la "
            "entidad, no un profesional aislado.\n"
            "- match=true aun haya nombres propios en el texto, si el resultado es claramente la ficha o sede de la entidad; "
            "si es básicamente un CV personal, match=false.\n"
            "Combina: match final true solo si cumple ubicación (reglas de geo) y este criterio de entidad.\n"
        )
    return ""


def _professional_intent_rules_block(user_query: str, role_or_stack_hint: str | None) -> str:
    """Bloque de prompt: alineación obligatoria con la intención de búsqueda del usuario."""
    hint = (role_or_stack_hint or "").strip()
    search_term = hint or user_query.strip()
    if not search_term:
        return ""
    return (
        f"*** REGLA PRINCIPAL — OBLIGATORIA — Alineación con la intención de búsqueda ***\n"
        f"Consulta del usuario: \"{user_query}\"\n"
        f"Sector/profesión objetivo: \"{search_term}\"\n"
        f"IMPORTANTE: Si '{search_term}' contiene palabras geográficas ('en Honduras', 'en Tegucigalpa', etc.), "
        f"esas son contexto de ubicación, no el sector. Evalúa SECTOR, no geografía.\n"
        f"DEBES verificar que cada resultado sea DIRECTAMENTE del sector/profesión buscada.\n"
        f"- match=true SOLO si título o excerpt demuestran que el resultado ES del sector/profesión objetivo.\n"
        f"- match=false INMEDIATAMENTE si el resultado es de OTRO sector, rubro o actividad.\n"
        f"  Si el título menciona EXPLÍCITAMENTE una profesión/rol diferente (educador, ingeniero, contador, IT, etc.) → match=false, confidence=1.\n"
        f"  Ejemplo: si el usuario busca 'psicólogos' y el título dice 'Profesional de Educación' o 'Ingeniero Industrial' → MATCH=FALSE AUTOMÁTICAMENTE.\n"
        f"- El nombre comercial por sí solo NO prueba nada. Verifica el excerpt para confirmar profesión.\n"
        f"- Si no puedes confirmar con CERTEZA que el resultado es del sector buscado (ni educador, ni IT, ni otro sector diferente) → match=false y confidence=1.\n"
        f"- REGLA CRÍTICA: Cuando en duda sobre profesión → DESCARTA, no conserves. Buscamos precisión, no cobertura.\n"
    )


def _sector_intent_rules_block(user_query: str) -> str:
    """Alineación sectorial con balance entre precisión y cobertura."""
    return (
        "*** Alineación sectorial ***\n"
        "- Si el resultado CLARAMENTE no pertenece al sector buscado → match=false.\n"
        "- Si hay duda razonable y no puedes confirmar que el resultado sea del sector → match=false.\n"
        "- Solo marca match=true cuando el título o excerpt demuestren de forma positiva que el resultado "
        "pertenece al sector buscado.\n"
        "- Un negocio de rubro completamente distinto al buscado es match=false (ej: si el usuario busca "
        "clínicas y el resultado es una ferretería, match=false).\n"
        "- confidence 1-3 solo para resultados que claramente NO son del sector.\n"
        "- confidence 8-10 para resultados que demuestran CLARAMENTE alineación sectorial.\n"
    )


def _academic_exclusion_rules_block() -> str:
    """Regla obligatoria para excluir páginas académicas e informacionales."""
    return (
        "*** REGLA DE EXCLUSIÓN — Páginas académicas e informacionales ***\n"
        "- Páginas de universidad, facultad, plan de estudios, carrera académica, "
        "artículo histórico o documental sobre el sector → match=false, confidence=0.\n"
        "- URL que apunta a un PDF académico → match=false, confidence=0.\n"
        "- Solo son válidos resultados que representen un contacto directo activo "
        "(persona o empresa/clínica que ofrece el servicio buscado).\n"
    )


def _obituary_exclusion_rules_block() -> str:
    """Regla obligatoria para excluir obituarios y personas fallecidas."""
    return (
        "*** REGLA DE EXCLUSIÓN OBLIGATORIA — Personas fallecidas y obituarios ***\n"
        "- Si el resultado es un obituario, noticia de fallecimiento, artículo 'in memoriam', "
        "'homenaje póstumo' o cualquier texto sobre una persona que ya no vive → match=false, confidence=0.\n"
        "- Señales de fallecimiento en título o excerpt: 'muere', 'murió', 'falleció', 'fallecido', "
        "'obituario', 'víctima del covid', 'perdió la vida', 'died', 'obituary', 'passed away' → match=false, confidence=0.\n"
        "- Esta regla aplica aunque la persona sea del sector buscado: NO PODEMOS CONTACTAR A ALGUIEN FALLECIDO.\n"
    )


def _heuristic_sede_extranjera_sin_senal_local(blob: str, target_iso: str) -> bool:
    """
    Heurística: sede/razón social fuera del país (p. ej. India + Private Limited) sin menciones al país objetivo.
    Complementa códigos (XX) entre paréntesis cuando el snippet de Exa no trae (IN) pero sí texto indio.
    """
    t = target_iso.strip().upper()
    if t == "IN":
        return False
    if blob_has_target_country_markers(blob, t):
        return False
    bl = blob.lower()
    if f"({t.lower()})" in bl:
        return False
    if re.search(
        r"\b(india|bangalore|bengaluru|mumbai|bombay|hyderabad|new delhi|gurgaon|gurugram|noida|chennai|pune|kolkata)\b",
        bl,
    ) and re.search(r"private limited|pvt\.?\s*ltd|ltd\.\s*company|limited liability", bl):
        return True
    if "private limited" in bl and re.search(r"\b(india|indian)\b", bl):
        return True
    return False


_OBITUARY_TITLE_KEYWORDS = frozenset({
    "muere ", "murió", "murio ", "falleció", "fallecio", "fallecido", "fallecida",
    "fallece ", "obituario", "in memoriam", "homenaje póstumo", "homenaje postumo",
    "víctima del covid", "victima del covid", "perdió la vida", "perdio la vida",
    "died", "death of", "obituary", "in memory of", "passed away", "deceased",
})

_OBITUARY_URL_FRAGMENTS = frozenset({
    "obituario", "obituarios", "in-memoriam", "fallecio", "fallecimiento",
})

_PDF_URL_RE = re.compile(r"\.pdf(\?.*)?$", re.IGNORECASE)

_ACADEMIC_URL_FRAGMENTS = frozenset({
    ".edu.",
    ".edu/",
    "/dmsdocument/",
    "/oferta-academica/",
    "/oferta_academica/",
    "/carrera/",
})

_ACADEMIC_TITLE_KEYWORDS = frozenset({
    "historia de la ", "historia del ",
    "licenciatura en ", "licenciatura de ",
    "carrera de psicolog", "plan de estudios",
    "programa académico", "programa academico",
    "oferta académica", "oferta academica",
    "faculty of ", "school of ",
})

_DIRECTORY_TITLE_RE = re.compile(
    r"(?i)"
    r"(¿busca\s+(un|una|al)\s+)"
    r"|(¿necesita\s+(un|una)\s+)"
    r"|(directorio\s+de\s+)"
    r"|(lista\s+de\s+\w+\s+en\s+)"
    r"|(encuentra\s+(un|una|los|las|al)\s+\w+\s+en\s+)"
    r"|(los\s+mejores\s+\w+\s+en\s+)"
    r"|(las\s+mejores\s+\w+\s+en\s+)"
    r"|(cerca\s+de\s+(usted|ti|tí)\b)"
    r"|(¿dónde\s+(encontrar|hallar)\s+)"
    r"|(compare\s+\w+\s+en\s+)"
    r"|(find\s+(a|an|the\s+best)\s+\w+\s+(near|in)\s+)"
    r"|(best\s+\w+\s+near\s+(me|you))"
    r"|(compara\s+y\s+reserva)"
    r"|(\d+\s+mejores?\s+\w+\s+en\s+)"
    r"|(profesionales\s+en\s+\w+\s*[—–-])"
)


def _heuristic_obituary_drop_reason(item: dict[str, Any]) -> str | None:
    """Descarta obituarios/fallecidos por heurística antes de llamar a Gemini."""
    title = str(item.get("title") or "").lower()
    url = str(item.get("url") or "").lower()

    for kw in _OBITUARY_TITLE_KEYWORDS:
        if kw in title:
            return f"Obituario/fallecido detectado en título: '{kw}'"

    url_path = url.split("?")[0]
    for frag in _OBITUARY_URL_FRAGMENTS:
        if f"/{frag}" in url_path or f"-{frag}" in url_path or f"{frag}-" in url_path:
            return f"URL indica obituario/fallecimiento: '{frag}'"

    return None


def _heuristic_academic_drop_reason(item: dict[str, Any]) -> str | None:
    """Descarta páginas académicas, documentos PDF universitarios e informacionales."""
    url = str(item.get("url") or "").lower()
    title = str(item.get("title") or "").lower()

    if _PDF_URL_RE.search(url):
        return "URL apunta a un documento PDF."

    url_path = url.split("?")[0]
    for frag in _ACADEMIC_URL_FRAGMENTS:
        if frag in url_path:
            return f"URL de dominio/ruta académica: '{frag}'"

    for kw in _ACADEMIC_TITLE_KEYWORDS:
        if kw in title:
            return f"Título académico/informacional: '{kw}'"

    return None


def _is_directory_source_page(item: dict[str, Any]) -> bool:
    """True si el item parece una página de listado/directorio, no un contacto directo."""
    title = str(item.get("title") or "").strip()
    if not title:
        return False
    return bool(_DIRECTORY_TITLE_RE.search(title))


def _heuristic_entity_page_for_people_search(item: dict[str, Any], exa_category: str | None) -> bool:
    """
    Detecta páginas de organización/entidad cuando se busca en modo 'people'.
    Retorna True si el item es una organización que debe guardarse como directorio, no como lead.
    """
    if (exa_category or "").strip().lower() != "people":
        return False

    title = str(item.get("title") or "").strip().lower()
    if not title:
        return False

    # Homepage indicators (Bienvenidos, Welcome, Contáctenos, etc.)
    if re.search(r'\bbienvenidos\b', title):
        return True
    if re.search(r'\bcontácten(?:os|os)\b', title):
        return True

    # Organization indicators (Consultora, Consultoría, S.A., Ltda., etc.)
    if re.search(r'\bconsultor[aí]s?\b', title):
        return True
    if re.search(r'\b(s\.a\.|s\.a|srl|s\.r\.l\.|ltda\.|c\.a\.|s\.a\.s\.|s\.a\.c\.|inc\.|corp\.)\b', title):
        return True

    return False


def _heuristic_drop_reason(item: dict[str, Any], target_iso: str | None) -> str | None:
    """Razón de descarte heurístico, o None si el ítem pasa a revisión con Gemini / se conserva."""
    if not target_iso or len(target_iso) != 2:
        return None
    t = target_iso.strip().upper()
    blob = _full_profile_blob(item)
    codes = extract_parenthesized_iso_codes(blob)
    if codes:
        primary = codes[-1].upper()
        if primary != t:
            return "Ubicación (código ISO en el perfil) no coincide con el país objetivo."
    if first_matching_non_target_country_iso(blob, target_iso):
        return "El texto describe otro país distinto al objetivo."
    if _heuristic_sede_extranjera_sin_senal_local(blob, t):
        return "Sede o registro foráneo (p. ej. India) sin señal clara del país objetivo en el texto."
    return None


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


def _subpages_text_blob(item: dict[str, Any]) -> str:
    """Concatena texto/highlights de subpáginas crawleadas por Exa (subpages: N)."""
    subs = item.get("subpages")
    if not isinstance(subs, list):
        return ""
    parts: list[str] = []
    for sp in subs:
        if not isinstance(sp, dict):
            continue
        t = sp.get("text")
        if isinstance(t, str) and t.strip():
            parts.append(t.strip())
        hl = sp.get("highlights")
        if isinstance(hl, list):
            parts.append(" ".join(str(x) for x in hl if x))
    return " ".join(parts)


def _full_profile_blob(item: dict[str, Any]) -> str:
    """Concatena campos que Exa suele devolver para ubicación y rol, incluyendo texto completo y subpáginas."""
    parts = [
        str(item.get("title", "") or ""),
        str(item.get("text", "") or ""),
        _highlights_blob(item),
        _subpages_text_blob(item),
    ]
    for key in ("snippet", "summary", "description", "subtitle"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts)


def _excerpt(item: dict[str, Any], max_len: int | None = None) -> str:
    if max_len is None:
        max_len = get_settings().relevance_filter_excerpt_max_chars
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
    return _heuristic_drop_reason(item, target_iso) is not None


def _compact_items_for_chunk(
    results: list[dict[str, Any]],
    indices: list[int],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in indices:
        item = results[i]
        out.append({"index": i, "title": str(item.get("title", "") or "")[:400], "url": str(item.get("url", "") or ""), "excerpt": _excerpt(item)})
    return out


def _parse_verdicts(
    parsed: dict[str, Any],
    confidence_threshold: int = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict[int, bool]:
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
        # Apply confidence threshold: low-confidence matches become rejections
        if out.get(idx) is True:
            try:
                confidence = int(row.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0
            if confidence < confidence_threshold:
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

    # Deduplicación por URL antes de heurísticas
    seen_urls: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for _item in raw_results:
        if not isinstance(_item, dict):
            continue
        _url = str(_item.get("url", "")).strip().lower().rstrip("/")
        if _url and _url in seen_urls:
            continue
        if _url:
            seen_urls.add(_url)
        deduped.append(_item)
    raw_results = deduped

    # Extraer categoría Exa temprano (antes del loop heurístico)
    exa_cat = relevance_criteria.get("exa_category")
    exa_cat_s = str(exa_cat).strip().lower() if exa_cat is not None else ""

    heuristic_drop: set[int] = set()
    reasons: dict[int, str] = {}
    directory_sources: list[dict[str, str]] = []
    for i, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        drop_reason = _heuristic_drop_reason(item, target_iso)
        if not drop_reason:
            drop_reason = _heuristic_obituary_drop_reason(item)
        if not drop_reason:
            drop_reason = _heuristic_academic_drop_reason(item)
        if drop_reason:
            heuristic_drop.add(i)
            reasons[i] = drop_reason
            continue
        if _is_directory_source_page(item):
            directory_sources.append({
                "url": str(item.get("url", "")).strip(),
                "title": str(item.get("title", "")).strip(),
            })
            heuristic_drop.add(i)
            reasons[i] = "Página de listado/directorio — guardada como fuente para explorar."
            continue
        if _heuristic_entity_page_for_people_search(item, exa_cat_s):
            directory_sources.append({
                "url": str(item.get("url", "")).strip(),
                "title": str(item.get("title", "")).strip(),
            })
            heuristic_drop.add(i)
            reasons[i] = "Organización/entidad en búsqueda de personas — guardada como fuente potencial."
            continue

    pending_indices = [i for i in range(len(raw_results)) if i not in heuristic_drop]
    match_by_index: dict[int, bool] = {i: False for i in heuristic_drop}

    if pending_indices:
        if exa_cat_s not in ("people", "company"):
            exa_cat_s = ""

        criteria_compact: dict[str, Any] = {
            "country_iso2": relevance_criteria.get("country_iso2"),
            "city": relevance_criteria.get("city"),
            "country_text": relevance_criteria.get("country_text"),
            "role_or_stack_hint": relevance_criteria.get("role_or_stack_hint"),
            "normalized_location": relevance_criteria.get("normalized_location"),
        }
        if exa_cat_s:
            criteria_compact["exa_category"] = exa_cat_s
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
                entity_rules = _exa_category_entity_rules(exa_cat_s or None)
                sector_rules = _sector_intent_rules_block(user_query)
                academic_rules = _academic_exclusion_rules_block()
                obituary_rules = _obituary_exclusion_rules_block()
                professional_rules = _professional_intent_rules_block(
                    user_query, criteria_compact.get("role_or_stack_hint"),
                )
                prompt = (
                    "Eres un validador estricto de relevancia para prospección B2B.\n"
                    f"Consulta original del usuario (máxima prioridad): {user_query}\n"
                    f"Criterios (JSON): {json.dumps(criteria_compact, ensure_ascii=False)}\n"
                    f"{professional_rules}"
                    f"{geo_rules}"
                    f"{entity_rules}"
                    f"{academic_rules}"
                    f"{obituary_rules}"
                    f"{sector_rules}"
                    "Cada ítem tiene index (posición global en la lista original), title, url, excerpt.\n"
                    "Para CADA ítem pregúntate: ¿Este resultado ES realmente del sector/rubro/profesión que busca el usuario? "
                    "Si el título menciona OTRA profesión explícitamente (educador, ingeniero, IT, etc.) → MATCH=FALSE AUTOMÁTICAMENTE. "
                    "Si la respuesta no es un SÍ claro → match=false.\n"
                    "Devuelve SOLO JSON con la forma exacta:\n"
                    '{"verdicts":[{"index":0,"match":true,"confidence":8,"reason_es":"breve"}]}\n'
                    "- confidence (entero 0-10): qué tan seguro estás de que el resultado ES del sector buscado. "
                    "10 = 100% seguro que sí es. 1-3 = dudoso o parece ser de otro sector. "
                    "Si confidence < 8, el resultado será descartado automáticamente. Solo marca confidence≥8 si estás MUY SEGURO de que es del sector.\n"
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
            logger.warning("Filtro de relevancia Gemini omitido: %s", exc)
            for idx in pending_indices:
                if idx not in match_by_index:
                    match_by_index[idx] = target_iso is None

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

    exa_for_meta = str(relevance_criteria.get("exa_category") or "").strip().lower()
    if exa_for_meta not in ("people", "company"):
        exa_for_meta = ""

    meta: dict[str, Any] = {
        "relevance_filter_kept": len(kept),
        "relevance_filter_dropped": len(discarded_meta),
        "relevance_filter_heuristic_drops": len(heuristic_drop),
        "relevance_filter_discarded_sample": discarded_meta[:40],
        "relevance_filter_mode": "applied",
    }
    if exa_for_meta:
        meta["relevance_filter_exa_category"] = exa_for_meta
    meta["suggested_source_urls"] = [s for s in directory_sources if s["url"]]
    return kept, meta
