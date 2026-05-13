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
# Para búsqueda de empresas: umbral más bajo porque la homepage/perfil de la empresa ya es el lead
COMPANY_CONFIDENCE_THRESHOLD = 6


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
        f"PASO 1 — LEE EL TÍTULO. Si el título contiene palabras de sector DIFERENTE al buscado → STOP, match=false, confidence=1. NO leas el excerpt.\n"
        f"  Ejemplos de títulos que deben rechazarse INMEDIATAMENTE (independientemente del excerpt):\n"
        f"    - Búsqueda 'psicólogos': título dice 'Hotel', 'Hostal', 'Trivago', 'Hotelmix', 'Booking', 'Rentas', 'Inmobiliaria', 'Consultora de comercio', 'Profesor', 'Ingeniero' → match=false, confidence=1\n"
        f"    - Búsqueda 'cardiólogos': título dice 'Hotel', 'Ferretería', 'Consultor de negocios', 'Recursos Humanos', 'Renta', 'Abogado' → match=false, confidence=1\n"
        f"  La geografía compartida (ej: ambos en Honduras) NO hace relevante a un hotel cuando se busca un médico.\n"
        f"PASO 2 — Solo si el título NO descarta: verifica excerpt para confirmar que el resultado ES del sector buscado.\n"
        f"- match=true SOLO si título o excerpt demuestran positivamente que el resultado ES del sector/profesión objetivo.\n"
        f"- REGLA CRÍTICA: si no puedes identificar DIRECTAMENTE la profesión/sector buscado → match=false, confidence=1.\n"
        f"- Cuando en duda → DESCARTA. Buscamos precisión, no cobertura.\n"
    )


def _company_search_intent_block(user_query: str) -> str:
    """Bloque de prompt para búsqueda de empresas/clínicas: recall > precisión."""
    return (
        f"*** REGLA PRINCIPAL — Búsqueda de EMPRESAS/CLÍNICAS ***\n"
        f"Consulta: \"{user_query}\"\n"
        "OBJETIVO: Encontrar empresas, clínicas, hospitales, centros médicos del sector. NO personas individuales.\n"
        "REGLA 1 — match=true si: es una empresa/clínica/hospital/centro del sector buscado. "
        "Incluye: homepage, página de servicios, perfil empresarial, página de contacto.\n"
        "REGLA 2 — is_source_page=false para: homepage de clínica/hospital individual = LEAD DIRECTO (NO fuente).\n"
        "REGLA 3 — is_source_page=true SOLO para: páginas que listan MÚLTIPLES empresas distintas "
        "(Páginas Amarillas, Google Maps lista, directorios tipo 'Hospitales en Honduras').\n"
        "REGLA 4 — CUANDO EN DUDA → INCLUYE (match=true). Preferimos false positives sobre perder leads.\n"
        "REGLA 5 — match=false SOLO si: claramente otro sector (hotel, ferretería, software) "
        "o claramente otro país sin relación con la búsqueda.\n"
        "REGLA 6 — NO diferencies entre clínica y hospital — ambos son leads válidos del sector salud.\n"
        "EJEMPLO CORRECTO: 'Hospital Santa Lucía | https://hospitalsantalucia.hn' → match=true, is_source_page=false, confidence=9\n"
        "EJEMPLO INCORRECTO: marcar un hospital como is_source_page=true porque tiene múltiples departamentos.\n"
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


_EMOJI_RE = re.compile(
    "[\U00010000-\U0010FFFF"   # Supplementary planes (most emojis)
    "\U00002600-\U000027BF"    # Misc symbols / Dingbats
    "\U0001F300-\U0001F9FF"    # Main emoji block
    "\U00002700-\U000027BF"    # Dingbats
    "]+",
    flags=re.UNICODE,
)

_EMOJI_TEXT_JUNK_RE = re.compile(
    r"^\s*[\U00010000-\U0010FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF\U00002700-\U000027BF📍🚨✅❗🔴🟢🔵]+\s*",
    flags=re.UNICODE,
)

_SOURCE_TITLE_NOISE_RE = re.compile(
    r"(?i)"
    r"\s*\(@[\w.]+\)"          # (@handle)
    r"|\s*[·•]\s*.+$"          # · Tegucigalpa (keep only what's before the dot)
    r"|\s*[-–—|]\s*inicio\s*$" # - Inicio
    r"|\s*\|\s*$"               # trailing pipe
)

_URL_SOCIAL_PRIORITY = {
    "facebook.com": 3,
    "instagram.com": 3,
    "twitter.com": 3,
    "tiktok.com": 3,
    "linkedin.com/company": 2,
    "linkedin.com": 2,
}


def _strip_emojis(text: str) -> str:
    """Quita emojis y limpia el texto resultante."""
    cleaned = _EMOJI_RE.sub("", text)
    # Remove leftover junk chars that often accompany emojis (📍, 🚨, etc.)
    cleaned = re.sub(r"[\U0001F000-\U0001FFFF]", "", cleaned)
    # Collapse multiple spaces and strip
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _normalize_source_title(title: str) -> str:
    """Normaliza título de fuente para comparación de duplicados."""
    t = _strip_emojis(title)
    t = _SOURCE_TITLE_NOISE_RE.sub("", t)
    return t.strip().lower()


def _url_social_rank(url: str) -> int:
    """Menor número = mejor (preferimos sitio propio sobre redes sociales)."""
    u = url.lower()
    for domain, rank in _URL_SOCIAL_PRIORITY.items():
        if domain in u:
            return rank
    return 1  # main website


def _deduplicate_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    """Agrupa fuentes por entidad (título normalizado) y conserva la URL de mejor calidad."""
    groups: dict[str, list[dict[str, str]]] = {}
    for s in sources:
        raw_title = s.get("title") or s.get("url") or ""
        key = _normalize_source_title(raw_title)
        if not key:
            key = s.get("url", "").lower().rstrip("/")
        groups.setdefault(key, []).append(s)

    result: list[dict[str, str]] = []
    for entries in groups.values():
        # Pick best URL: lowest social rank wins
        best = min(entries, key=lambda e: _url_social_rank(e.get("url", "")))
        # Use cleaned title from best entry
        clean_title = _strip_emojis(best.get("title") or best.get("url") or "")
        result.append({"url": best["url"], "title": clean_title, "source": best.get("source", "")})
    return result


def _source_page_rules_block(exa_category: str) -> str:
    """Bloque de prompt: reglas is_source_page diferenciadas por categoría."""
    if exa_category == "company":
        return (
            "ADEMÁS — reglas para is_source_page:\n"
            "  • is_source_page=true: SOLO páginas que LISTAN múltiples empresas (directorios de negocios, buscadores de empresas, páginas amarillas)\n"
            "  • is_source_page=false: homepage de hospital, clínica, empresa, negocio del sector — son el LEAD DIRECTO, NO una fuente para explorar\n"
            "  • is_source_page=false: perfiles de empresa en LinkedIn company, Facebook page, Instagram de la empresa\n"
            "  • is_source_page=false + match=false: artículos de noticias, blogs, reportajes\n"
            "EJEMPLOS is_source_page=false (son leads directos — NO marcar como fuente):\n"
            "  - 'Hospital Y Clínicas Viera | https://hospitalyclinicasviera.hn/' → is_source_page=FALSE\n"
            "  - 'MEDICASA Hospital | https://medicasa.hn/' → is_source_page=FALSE\n"
            "  - 'GyV Medical | https://gyvmedical.com/' → is_source_page=FALSE\n"
            "  - 'Honduras Medical Center | https://hmc.com.hn/' → is_source_page=FALSE\n"
            "  - Cualquier clínica u hospital individual → is_source_page=FALSE\n"
            "EJEMPLOS is_source_page=true (son directorios, NO leads):\n"
            "  - 'Hospitales en Tegucigalpa - yelu.hn' → is_source_page=TRUE\n"
            "  - 'Directorio médico de Honduras | infopaginas.com' → is_source_page=TRUE\n"
        )
    return (
        "ADEMÁS — reglas para is_source_page:\n"
        "  • is_source_page=true: páginas que LISTAN múltiples profesionales (equipo, directorio, personal)\n"
        "  • is_source_page=true: homepages de hospitales, clínicas, centros médicos, centros oftalmológicos (aunque no sean directorios)\n"
        "  • is_source_page=true: páginas de servicios médicos de una institución (no un perfil individual)\n"
        "  • is_source_page=false + match=false: artículos de noticias, blogs, reportajes — NO guardar como fuente, solo descartar\n"
        "  • is_source_page=false: perfiles de médicos individuales\n"
        "  is_source_page=true indica: 'guardar esta URL para explorarla después en busca de más contactos'.\n"
    )


def _match_categories_block(exa_category: str) -> str:
    """Bloque de prompt: definición de match=true/lpa/false diferenciada por categoría."""
    if exa_category == "company":
        return (
            "CATEGORÍAS para el campo match:\n"
            "  • match=true: empresa/clínica/hospital/centro médico/negocio del sector identificado — homepage, página de contacto, perfil de empresa, página de servicios\n"
            "  • match=\"lpa\": empresa con información incompleta, perfil de red social con poca info, entidad del sector probable pero no confirmada\n"
            "  • match=false: listado de múltiples empresas, artículo de noticias/blog, ubicación incorrecta (otro país/ciudad), sector completamente diferente\n"
        )
    return (
        "CATEGORÍAS para el campo match:\n"
        "  • match=true: lead confirmado del sector (profesional individual claramente identificado)\n"
        "  • match=\"lpa\": posible lead a averiguar — página de Facebook/Instagram de clínica o centro del sector, "
        "profesional de especialidad adyacente relevante, perfil con poca info pero del sector correcto, "
        "post con teléfono de clínica relevante\n"
        "  • match=false: ubicación incorrecta, sector completamente diferente, obituario, nota de prensa, "
        "lista/directorio genérico, solo coordenadas o dirección sin persona ni clínica\n"
    )


def _confidence_hint_block(threshold: int) -> str:
    """Bloque de prompt: descripción del campo confidence adaptada al threshold real."""
    return (
        f"- confidence (entero 0-10): qué tan seguro estás de que el resultado ES del sector buscado. "
        f"10 = 100% seguro que sí es. 1-3 = dudoso o parece ser de otro sector. "
        f"Si confidence < {threshold} y match=true, el resultado será descartado automáticamente. "
        f"Solo marca confidence≥{threshold} si estás SEGURO de que es del sector.\n"
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
    

def _aggregator_exclusion_rules_block() -> str:
    """Regla obligatoria para excluir listados, agregadores y noticias generales."""
    return (
        "*** REGLA DE EXCLUSIÓN — Agregadores, Listicles y Noticias ***\n"
        "- match=false si el resultado es un LISTADO o AGREGADOR: 'Los 5 mejores...', 'Directorio de...', "
        "'Páginas amarillas', 'Lista de psicólogos', 'Encuentra tu especialista', etc.\n"
        "- match=false si es una NOTICIA o ARTÍCULO DE PRENSA: 'Psicólogos brindan atención...', 'El gremio de psicólogos dice...', "
        "'Noticias sobre salud en...'\n"
        "- match=false si es una PÁGINA DE CATEGORÍA de un sitio web (ej. Doctoralia, Encuentra24) que no representa un perfil individual.\n"
        "- Solo son válidos RESULTADOS DIRECTOS: el sitio web personal del profesional, su perfil individual (no listado), "
        "o el sitio oficial de su clínica.\n"
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

_SOURCE_URL_PATH_FRAGMENTS = frozenset({
    "/equipo", "/staff", "/team", "/nuestro-equipo", "/our-team",
    "/directorio", "/medicos", "/doctors", "/profesionales", "/especialistas",
    "/empleo", "/empleos", "/jobs", "/vacantes", "/trabajo", "/ofertas-de-empleo"
})

_NEWS_URL_FRAGMENTS = frozenset({
    "/noticias/", "/news/", "/blog/", "/articulo/",
    "/nota/", "/reportaje/", "/prensa/", "/opinion/",
})

_NEWS_DOMAINS = frozenset({
    "eldiario.hn", "laprensa.hn", "latribuna.hn", "criterio.hn",
    "proceso.hn", "tiempo.hn", "hondurastv.hn", "elheraldo.hn",
    "diarioel.hn", "radiohrn.hn",
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
    r"|(^equipo\s*[-—])"
    r"|(nuestro\s+equipo)"
    r"|(personal\s+m[eé]dico)"
    r"|(staff\s+m[eé]dico)"
    r"|(m[eé]dicos?\s+del\s+hospital)"
    r"|(nuestros?\s+especialistas?)"
    r"|(nuestros?\s+m[eé]dicos?)"
    r"|(^\d+\s*empleos?\s+de\s+)"
    r"|(empleos?\s+en\s+)"
    r"|(trabajos?\s+en\s+)"
    r"|(ofertas?\s+de\s+empleo)"
    r"|(\bvacantes?\b)"
    r"|(\bcomunidad\b)"
    r"|(\bbusca\s+empleo\b)"
    r"|(\bbuscamos\b.*\btalento\b)"
    r"|(computrabajo\.)"
    r"|(tecoloco\.)"
    r"|(opcionempleo\.)"
    r"|(glassdoor\.)"
    r"|(\bc[aá]mara\s+de\b)"
    r"|(^seguros?\s+de\s+)"
    r"|(instagram\s+photos\s+and\s+videos)"
    r"|(facebook\s+[-–—]\s+\w)"
    r"|(fotos?\s+y\s+videos?\s+de\s+instagram)"
    r"|(\bperfil\s+de\s+empresa\b)"
    r"|(^psic[oó]logos?\s+(en|de)\s)"         # "Psicólogos en Tegucigalpa" sin nombre
    r"|(^m[eé]dicos?\s+(en|de)\s)"            # "Médicos en Honduras" sin nombre
    r"|(^especialistas?\s+(en|de)\s)"
    r"|(^cl[ií]nicas?\s+(en|de)\s)"
    r"|(^odont[oó]logos?\s+(en|de)\s)"
)

_NEWS_TITLE_RE = re.compile(
    r"(?i)"
    r"(^por\s+la\s+\w+\s+de\s+)"
    r"|(^cómo\s+\w+\s+(puede|logr|evit|mejorar))"
    r"|(^por\s+qué\s+debes?\s+)"
    r"|(médicos?\s+cubanos?)"
    r"|(dejaron\s+.{0,30}a\s+la\s+deriva)"
    r"|(pacientes?\s+quedaron)"
    r"|(conoce\s+el\s+mejor\s+)"
    r"|(por\s+qué\s+visit)"
    r"|(^historia\s+de\b)"
    r"|(\blanza\b.*\bbolet[ií]n\b)"
    r"|(\bpagan\s+(l\d+|usd|millones))"
    r"|(\bmillones\s+en\b)"
)

_NEWS_PROFILE_TITLE_RE = re.compile(
    r"(?i)^(dr\.|dra\.|doctor\s|doctora\s)\s*\w[\w\s]+\s*:"
)

_INSTITUTIONAL_PAGE_TITLE_RE = re.compile(
    r"(?i)"
    r"(\s*[-–—|]\s*inicio\s*$)"   # "CERVO - Inicio", "X | Inicio"
    r"|(^\w[\w\s]+\s*[|]\s*$)"    # "laservision |" — título vacío tras pipe
    r"|(^hospital\s+\w)"           # "Hospital MEDICASA", "Hospital de Especialidades"
    r"|(^centro\s+(m[eé]dico|oftalmol[oó]gic|de\s+salud|de\s+ojos|visual|cl[ií]nico))"
    r"|(^policl[ií]nica\s)"
    r"|(^cl[ií]nica\s+(?!del?\s+dr|del?\s+dra|dr\.|dra\.))"  # "Clínica Robles" pero NO "Clínica del Dr. X"
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


def _source_page_is_sector_relevant(item: dict[str, Any], user_query: str) -> bool:
    """True si una página de directorio/listado es relevante al sector buscado.
    Evita guardar como fuente hoteles, restaurantes, páginas de sector incorrecto."""
    if not user_query.strip():
        return True  # sin query no podemos filtrar, conservar
    title = str(item.get("title") or "").lower()
    url = str(item.get("url") or "").lower()
    blob = (title + " " + url).lower()

    # Extraer términos clave de la query (palabras de 4+ chars, excluyendo stopwords geo)
    _STOPWORDS = frozenset({"honduras", "tegucigalpa", "pedro", "ceiba", "comayagua", "en", "de", "los", "las", "para"})
    query_terms = [
        w.strip(".,;:") for w in user_query.lower().split()
        if len(w.strip(".,;:")) >= 4 and w.strip(".,;:") not in _STOPWORDS
    ]
    if not query_terms:
        return True

    # Exact match OR stem-based match (primeros 8 chars para plurales/variantes españolas)
    # Ej: "oftalmólogos" (stem: "oftalm") coincida con "oftalmología"
    for term in query_terms:
        if term in blob:
            return True
        stem = term[:8] if len(term) >= 8 else term
        if stem in blob:
            return True
    return False


def _is_directory_source_page(item: dict[str, Any]) -> bool:
    """True si el item parece una página de listado/directorio, no un contacto directo."""
    url = str(item.get("url") or "").lower()
    # Check URL path fragments (equipo/, staff/, directorio/, etc.)
    for frag in _SOURCE_URL_PATH_FRAGMENTS:
        if frag in url:
            return True

    title = str(item.get("title") or "").strip()
    if not title:
        return False
    return bool(_DIRECTORY_TITLE_RE.search(title))


def _heuristic_entity_page_for_people_search(item: dict[str, Any], exa_category: str | None) -> bool:
    """
    Detecta páginas de organización/entidad (no personas individuales).
    Retorna True si el item es una organización/directorio que debe guardarse como fuente, no como lead.
    """
    title = str(item.get("title") or "").strip()
    title_lower = title.lower()
    if not title_lower:
        return False

    # Si el título tiene nombre personal explícito al inicio (Dr., Dra., nombre propio), es persona
    if re.match(r"(?i)^(dr\.|dra\.|doctor\s|doctora\s|lic\.|licda\.|ing\.|prof\.)\s*[A-ZÁÉÍÓÚÑ]", title):
        return False

    # Gremios / colegios profesionales
    if re.search(r'(?i)\b(colegio|asociaci[oó]n|federaci[oó]n|gremio|sindicato)\s+de\b', title_lower):
        return True

    # Social media de organizaciones: "@handle" en el título
    if re.search(r'@\w{3,}', title):
        return True

    # Instagram/FB pages con "• Instagram" o "• Facebook"
    if re.search(r'(?i)[•·]\s*(instagram|facebook|twitter|tiktok)', title_lower):
        return True

    # Plataformas o portales de servicios (terminan en dominio de país como "HN", "MX" etc.)
    if re.search(r'(?i)^[A-Z][a-zA-Z]+HN\b', title):  # e.g. "TuPsicologaHN"
        return True

    exa_cat_lower = (exa_category or "").strip().lower()
    if exa_cat_lower == "people":
        # Homepage indicators
        if re.search(r'\bbienvenidos\b', title_lower):
            return True
        if re.search(r'\bcontácten(?:os|os)\b', title_lower):
            return True

    # Organization indicators (Consultora, Consultoría, S.A., Ltda., etc.)
    if re.search(r'\bconsultor[aí]s?\b', title_lower):
        return True
    if re.search(r'\b(s\.a\.|s\.a|srl|s\.r\.l\.|ltda\.|c\.a\.|s\.a\.s\.|s\.a\.c\.|inc\.|corp\.)\b', title_lower):
        return True

    return False


def _is_news_article(item: dict[str, Any]) -> bool:
    """True si el item parece un artículo de noticias o blog, no un perfil ni directorio."""
    url = str(item.get("url") or "").lower()
    for frag in _NEWS_URL_FRAGMENTS:
        if frag in url:
            return True
    title = str(item.get("title") or "").strip()
    return bool(_NEWS_TITLE_RE.search(title))


def _is_news_professional_profile(item: dict[str, Any]) -> bool:
    """True si el item es un artículo periodístico cuyo sujeto principal es un profesional nombrado.
    Ej: 'Dra. Carolina Palma: una trayectoria brillante en la oftalmología - eldiario.hn'
    Estos artículos son fuentes de exploración, no leads directos."""
    url = str(item.get("url") or "").lower()
    title = str(item.get("title") or "").strip()
    is_news_domain = any(domain in url for domain in _NEWS_DOMAINS)
    is_professional_profile_title = bool(_NEWS_PROFILE_TITLE_RE.search(title))
    return is_news_domain and is_professional_profile_title


def _is_institutional_clinic_page(item: dict[str, Any]) -> bool:
    """True si el item parece homepage de hospital, clínica o centro médico (no perfil individual)."""
    title = str(item.get("title") or "").strip()
    if not title:
        return False
    # No confundir con perfiles individuales: si tiene "Dr." prominente al inicio, es perfil
    if re.match(r"(?i)^(dr\.|dra\.|doctor\s|doctora\s)", title.strip()):
        return False
    return bool(_INSTITUTIONAL_PAGE_TITLE_RE.search(title))


def _heuristic_drop_reason(item: dict[str, Any], target_iso: str | None, exa_category: str = "") -> str | None:
    """Razón de descarte heurístico, o None si el ítem pasa a revisión con Gemini / se conserva."""
    if not target_iso or len(target_iso) != 2:
        return None
    t = target_iso.strip().upper()
    url = str(item.get("url") or "").lower()
    # Para company search: dominio local (.hn) siempre pasa — es un lead válido
    if exa_category == "company" and (".hn/" in url or url.endswith(".hn")):
        return None
    blob = _full_profile_blob(item)
    codes = extract_parenthesized_iso_codes(blob)
    # Para company search: omitir check de ISO en texto — demasiados falsos positivos
    # (clínicas hondureñas mencionan equipamiento "(US FDA)", certificaciones "(ISO)", etc.)
    if codes and exa_category != "company":
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
) -> dict[int, str]:
    """Retorna dict[index, "keep"|"lpa"|"drop"]."""
    verdicts = parsed.get("verdicts")
    if not isinstance(verdicts, list):
        return {}
    out: dict[int, str] = {}
    for row in verdicts:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        match = row.get("match")
        m_str = str(match).lower().strip() if match is not None else ""
        if m_str == "lpa":
            out[idx] = "lpa"
        elif isinstance(match, bool) and match or m_str in ("true", "1", "yes", "si", "sí"):
            try:
                confidence = int(row.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0
            out[idx] = "keep" if confidence >= confidence_threshold else "drop"
        else:
            out[idx] = "drop"
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
    heuristic_lpa: set[int] = set()
    reasons: dict[int, str] = {}
    directory_sources: list[dict[str, str]] = []
    for i, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        drop_reason = _heuristic_drop_reason(item, target_iso, exa_category=exa_cat_s)
        if not drop_reason:
            drop_reason = _heuristic_obituary_drop_reason(item)
        if not drop_reason:
            drop_reason = _heuristic_academic_drop_reason(item)
        if drop_reason:
            heuristic_drop.add(i)
            reasons[i] = drop_reason
            continue
        # Check for news articles → discard completely
        if _is_news_article(item):
            heuristic_drop.add(i)
            reasons[i] = "Artículo de noticias o blog — no es un contacto ni directorio."
            continue
        # Check for news profile articles about professionals → save as exploration source
        if _is_news_professional_profile(item) and _source_page_is_sector_relevant(item, user_query):
            directory_sources.append({
                "url": str(item.get("url", "")).strip(),
                "title": str(item.get("title", "")).strip(),
                "source": "heuristic_news_profile",
            })
            heuristic_drop.add(i)
            reasons[i] = "Artículo de perfil sobre profesional — guardado como fuente para explorar."
            continue
        # Check for institutional clinic/hospital homepages
        # For company search: the clinic IS the lead — let it through to LLM evaluation
        # For people search: save as exploration source to find individual contacts later
        if _is_institutional_clinic_page(item):
            if exa_cat_s != "company" and _source_page_is_sector_relevant(item, user_query):
                directory_sources.append({
                    "url": str(item.get("url", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                    "source": "heuristic_institutional",
                })
                heuristic_drop.add(i)
                reasons[i] = "Homepage institucional (hospital/clínica) — guardada como fuente para explorar."
                continue
            elif exa_cat_s != "company":
                heuristic_drop.add(i)
                reasons[i] = "Homepage institucional no relevante al sector buscado."
                continue
            # exa_cat_s == "company": fall through to LLM
        if _is_directory_source_page(item):
            if _source_page_is_sector_relevant(item, user_query):
                directory_sources.append({
                    "url": str(item.get("url", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                })
                heuristic_drop.add(i)
                reasons[i] = "Página de listado/directorio — guardada como fuente para explorar."
            else:
                heuristic_drop.add(i)
                reasons[i] = "Página de directorio pero no relevante al sector buscado."
            continue
        # For company search: org entity pages (S.A., LinkedIn company, etc.) are the target leads
        if exa_cat_s != "company" and _heuristic_entity_page_for_people_search(item, exa_cat_s):
            if _source_page_is_sector_relevant(item, user_query):
                directory_sources.append({
                    "url": str(item.get("url", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                })
                heuristic_drop.add(i)
                reasons[i] = "Organización/entidad en búsqueda de personas — guardada como fuente potencial."
            else:
                heuristic_drop.add(i)
                reasons[i] = "Página de entidad pero no relevante al sector buscado."
            continue

    pending_indices = [i for i in range(len(raw_results)) if i not in heuristic_drop]
    match_by_index: dict[int, str] = {i: "drop" for i in heuristic_drop}
    # Heuristic LPA items (set in future heuristic passes, currently unused at init)
    for i in heuristic_lpa:
        match_by_index[i] = "lpa"
    is_source_page_by_index: dict[int, bool] = {}

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
                target_country = criteria_compact.get("country_iso2", "").strip().upper()
                if exa_cat_s == "company":
                    # Para búsqueda de empresas: geo más suave — no descartar por certificaciones/equipamiento internacional
                    geo_rules = (
                        "Reglas de ubicación para búsqueda de empresas:\n"
                        "- Si el resultado es CLARAMENTE de otro país (UK clinic, US hospital, clínica en Australia) → match=false.\n"
                        f"- Si hay señal positiva del país buscado (dominio local, menciona {criteria_compact.get('country_text', 'el país objetivo')}) → match=true.\n"
                        "- Si no hay señal clara de ubicación pero el sector coincide → match=true (beneficio de la duda).\n"
                        "- NO descartes por equipamiento internacional o certificaciones (FDA, ISO, JCI, etc.) — son señales técnicas, no de ubicación.\n"
                    )
                else:
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
                    if target_country == "HN":
                        geo_rules += (
                            "*** REGLA CRÍTICA PARA HONDURAS (HN) ***\n"
                            "- Honduras es país pequeño con baja cobertura LinkedIn. EXCLUSIÓN TOTAL de cualquier resultado que NO sea HN.\n"
                            "- Candidato muestra: país diferente a HN, ciudad fuera de Honduras (ej. Ciudad de México, Bogotá, Miami, USA, etc.) → MATCH=FALSE AUTOMÁTICAMENTE, confidence=1.\n"
                            "- Aceptar SOLO si hay SEÑAL POSITIVA clara de Honduras: (HN) en paréntesis, ciudad hondureña (Tegucigalpa, San Pedro Sula, La Ceiba, Comayagua, etc.), texto que diga 'Honduras'.\n"
                            "- Trabajo remoto SIN mención de Honduras → RECHAZA, confidence=1.\n"
                        )
                confidence_threshold = COMPANY_CONFIDENCE_THRESHOLD if exa_cat_s == "company" else DEFAULT_CONFIDENCE_THRESHOLD
                entity_rules = _exa_category_entity_rules(exa_cat_s or None)
                sector_rules = _sector_intent_rules_block(user_query)
                academic_rules = _academic_exclusion_rules_block()
                obituary_rules = _obituary_exclusion_rules_block()
                if exa_cat_s == "company":
                    professional_rules = _company_search_intent_block(user_query)
                    aggregator_rules = ""  # Para empresas: páginas de servicios de una sola empresa son leads válidos
                else:
                    professional_rules = _professional_intent_rules_block(
                        user_query, criteria_compact.get("role_or_stack_hint"),
                    )
                    aggregator_rules = _aggregator_exclusion_rules_block()
                source_page_rules = _source_page_rules_block(exa_cat_s)
                match_categories = _match_categories_block(exa_cat_s)
                confidence_hint = _confidence_hint_block(confidence_threshold)
                doubt_rule = (
                    "En caso de duda → INCLUYE (match=true). Ver REGLA 4 arriba.\n"
                    if exa_cat_s == "company" else
                    "Si la respuesta no es un SÍ claro → match=false.\n"
                )
                prompt = (
                    "Eres un validador estricto de relevancia para prospección B2B.\n"
                    f"Consulta original del usuario (máxima prioridad): {user_query}\n"
                    f"Criterios (JSON): {json.dumps(criteria_compact, ensure_ascii=False)}\n"
                    f"{professional_rules}"
                    f"{geo_rules}"
                    f"{entity_rules}"
                    f"{aggregator_rules}"
                    f"{academic_rules}"
                    f"{obituary_rules}"
                    f"{sector_rules}"
                    "Cada ítem tiene index (posición global en la lista original), title, url, excerpt.\n"
                    "Para CADA ítem pregúntate: ¿Este resultado ES realmente del sector/rubro/profesión que busca el usuario? "
                    "Si el título menciona OTRA profesión explícitamente (educador, ingeniero, IT, etc.) → MATCH=FALSE AUTOMÁTICAMENTE. "
                    f"{doubt_rule}"
                    f"{source_page_rules}"
                    f"{match_categories}"
                    "Devuelve SOLO JSON con la forma exacta:\n"
                    '{"verdicts":[{"index":0,"match":true,"confidence":8,"is_source_page":false,"reason_es":"breve"}]}\n'
                    "- match puede ser: true, \"lpa\", o false\n"
                    f"{confidence_hint}"
                    "Debes incluir un veredicto por cada index enviado (un objeto por index).\n"
                    f"Ítems: {json.dumps(items_payload, ensure_ascii=False)}"
                )
                parsed = await gemini_client.complete_json_prompt(prompt)
                verdicts_map = _parse_verdicts(parsed, confidence_threshold=confidence_threshold)
                reason_by_index: dict[int, str] = {}
                for v in parsed.get("verdicts") or []:
                    if not isinstance(v, dict):
                        continue
                    try:
                        ix = int(v.get("index"))
                    except (TypeError, ValueError):
                        continue
                    reason_by_index[ix] = str(v.get("reason_es", "")).strip() or "No cumple criterios de relevancia."
                    is_source_page_by_index[ix] = bool(v.get("is_source_page", False))
                for idx in chunk_idx:
                    if idx in verdicts_map:
                        match_by_index[idx] = verdicts_map[idx]
                        if verdicts_map[idx] != "keep":
                            reasons[idx] = reason_by_index.get(idx, "No cumple criterios de relevancia.")
                    elif target_iso:
                        match_by_index[idx] = "drop"
                        reasons[idx] = "Sin veredicto del modelo; se excluye por criterio de país estricto."
                    else:
                        match_by_index[idx] = "keep"
                        reasons[idx] = "Sin veredicto del modelo; se conserva."
        except Exception as exc:  # noqa: BLE001
            logger.warning("Filtro de relevancia Gemini omitido: %s", exc)
            for idx in pending_indices:
                if idx not in match_by_index:
                    match_by_index[idx] = "keep" if target_iso is None else "drop"

    # Para company search: si LLM marcó is_source_page=true pero match=true → es un lead, no fuente
    # (el LLM confunde hospitales con múltiples departamentos con "páginas que listan empresas")
    if exa_cat_s == "company":
        for idx, is_source in list(is_source_page_by_index.items()):
            if is_source and match_by_index.get(idx) == "keep":
                is_source_page_by_index[idx] = False

    # Procesar items marcados como is_source_page=true del LLM (URLs para explorar)
    for idx, is_source in is_source_page_by_index.items():
        if is_source:
            item = raw_results[idx] if idx < len(raw_results) else {}
            if isinstance(item, dict):
                match_by_index[idx] = "drop"
                # For company search: if LLM says it's a source page, save it without extra check
                # (the LLM already validated sector relevance in its evaluation)
                # For people search: apply sector relevance check to avoid saving unrelated directories
                if exa_cat_s == "company" or _source_page_is_sector_relevant(item, user_query):
                    directory_sources.append({
                        "url": str(item.get("url", "")).strip(),
                        "title": str(item.get("title", "")).strip(),
                        "source": "llm",
                    })
                    reasons[idx] = "Página que lista múltiples empresas — guardada como fuente para explorar."
                else:
                    reasons[idx] = "Clasificada como fuente por LLM pero no relevante al sector buscado — descartada."

    kept: list[dict[str, Any]] = []
    lpa_items: list[dict[str, Any]] = []
    discarded_meta: list[dict[str, Any]] = []

    # Log detallado de evaluación por ítem
    logger.info(
        "FILTRO DE RELEVANCIA — Evaluación de %d ítems (heurística: %d descartados, %d pendientes LLM)",
        len(raw_results),
        len(heuristic_drop),
        len(pending_indices),
    )

    for i, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", ""))[:100]
        url = str(item.get("url", ""))[:80]
        reason = reasons.get(i, "")
        verdict = match_by_index.get(i, "keep")
        is_source = "fuente para explorar" in reason.lower() or "source" in reason.lower()

        if is_source and verdict == "drop":
            logger.info("  [%d] 📁 FUENTE: %s | %s", i, title[:80], url)
        elif verdict == "keep":
            logger.info("  [%d] ✓ KEEP: %s | %s", i, title[:80], url)
        elif verdict == "lpa":
            logger.info("  [%d] ⚠ LPA: %s | %s | Razón: %s", i, title[:80], url, reason)
        else:
            logger.info("  [%d] ✗ DROP: %s | %s | Razón: %s", i, title[:80], url, reason)

        if verdict == "keep":
            kept.append(item)
        elif verdict == "lpa":
            lpa_items.append(item)
        else:
            discarded_meta.append({
                "index": i,
                "url": url[:500],
                "reason_es": reason,
            })

    exa_for_meta = str(relevance_criteria.get("exa_category") or "").strip().lower()
    if exa_for_meta not in ("people", "company"):
        exa_for_meta = ""

    meta: dict[str, Any] = {
        "relevance_filter_kept": len(kept),
        "relevance_filter_dropped": len(discarded_meta),
        "relevance_filter_heuristic_drops": len(heuristic_drop),
        "relevance_filter_discarded_sample": discarded_meta[:40],
        "relevance_filter_mode": "applied",
        "lpa_results": lpa_items,
        "lpa_count": len(lpa_items),
    }
    if exa_for_meta:
        meta["relevance_filter_exa_category"] = exa_for_meta
    deduped_sources = _deduplicate_sources([s for s in directory_sources if s.get("url")])
    meta["suggested_source_urls"] = deduped_sources
    return kept, meta
