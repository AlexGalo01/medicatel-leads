"""Enriquecimiento profundo de contactos: Exa (texto + /contents) + Brave (local + web) + Gemini reviewer.

La función central `enrich_lead_contacts` es pura (no toca DB) — se usa desde
`auto_enrich_node` en lotes y desde el wrapper legacy `deep_enrich_lead` por id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from mle.clients.brave_client import BraveSearchClient
from mle.clients.exa_client import ExaClient, exa_contents_full_config, finalize_exa_search_payload
from mle.clients.gemini_client import GeminiClient
from mle.core.config import Settings, effective_exa_search_timeout_seconds, get_settings
from mle.db.base import async_session_factory
from mle.db.models import Lead
from mle.repositories.leads_repository import LeadsRepository
from mle.schemas.leads import LeadRead

logger = logging.getLogger(__name__)

NO_DATA_ES = "No se encontró información adicional verificable en las fuentes recuperadas."


@dataclass
class LeadCore:
    """Campos mínimos de un lead para alimentar el enriquecimiento (independiente del ORM)."""

    full_name: str
    specialty: str
    city: str
    country: str
    entity_type: str = "person"  # "person" | "company"
    linkedin_url: str = ""
    email: str = ""
    whatsapp: str = ""
    phone: str = ""
    address: str = ""
    schedule_text: str = ""
    primary_source_url: str = ""


@dataclass
class EnrichmentResult:
    email: str = ""
    whatsapp: str = ""
    phone: str = ""
    address: str = ""
    schedule_text: str = ""
    website: str = ""
    facebook_url: str = ""
    instagram_url: str = ""
    linkedin_url: str = ""
    description: str = ""
    primary_source_url: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    enriched_sources: dict[str, Any] = field(default_factory=dict)
    contact_sources: dict[str, str] = field(default_factory=dict)
    audit: list[dict[str, Any]] = field(default_factory=list)
    status: str = "no_verified_data"
    message: str = ""


# ---------------- Exa helpers ----------------


def _extract_results(search_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = search_response.get("results", [])
    if isinstance(raw_results, list):
        return [r for r in raw_results if isinstance(r, dict)]
    return []


def _flatten_evidence(results: list[dict[str, Any]]) -> str:
    MAX_HEAD = 1400
    MAX_TAIL = 600
    parts: list[str] = []
    for index, item in enumerate(results):
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        highlights = item.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        hl_join = " | ".join(str(h) for h in highlights[:8])
        text = str(item.get("text", ""))
        if len(text) > MAX_HEAD + MAX_TAIL:
            text_slice = text[:MAX_HEAD] + "\n[...]\n" + text[-MAX_TAIL:]
        else:
            text_slice = text
        parts.append(f"[{index}] URL: {url}\nTitulo: {title}\nHighlights: {hl_join}\nTexto: {text_slice}\n")
    return "\n".join(parts)


def _digits_only(raw: str) -> str:
    return re.sub(r"\D+", "", raw)


def _email_in_evidence(email: str, evidence_lower: str) -> bool:
    normalized = email.strip().lower()
    if "@" not in normalized or len(normalized) < 5:
        return False
    return normalized in evidence_lower


def _phone_in_evidence(phone: str, evidence_lower: str) -> bool:
    digits = _digits_only(phone)
    if len(digits) < 8:
        return False
    ev_digits = _digits_only(evidence_lower)
    return digits in ev_digits


def _linkedin_in_evidence(url: str, evidence_lower: str) -> bool:
    u = url.strip().lower()
    if "linkedin.com" not in u:
        return False
    if u in evidence_lower:
        return True
    return u.rstrip("/") in evidence_lower


def _is_crawlable_personal_site(url: str) -> bool:
    """Devuelve True si la URL vale la pena hacer deep-fetch (excluye solo LinkedIn)."""
    return "linkedin.com" not in url.lower()


def _extract_regex_contacts(text: str, source_url: str) -> list[dict[str, str]]:
    """Extrae emails y teléfonos del texto crudo con regex.

    Devuelve lista de {field: "email"|"phone"|"whatsapp", value, source_url}.
    """
    contacts: list[dict[str, str]] = []
    text_lower = text.lower()

    # Extraer emails
    email_pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    for match in re.finditer(email_pattern, text):
        email = match.group()
        if not any(x in email.lower() for x in ["@example.com", "@test.", "@fake"]):
            contacts.append({"field": "email", "value": email.strip(), "source_url": source_url})

    # Extraer teléfonos LATAM (Honduras: 7-8 dígitos, prefijos +504, (504), etc.)
    phone_patterns = [
        r"\+504\s?(?:\()?(\d{4})?(?:\))?\s?(\d{4})",  # +504 XXXX-XXXX
        r"\(504\)\s?(\d{4})?[\s\-]?(\d{4})",           # (504) XXXX-XXXX
        r"(?:tel|phone|teléfono|telefono)[\s:]*\(?(\d{4})[\s\-]?(\d{4})\)?",
        r"(?:^|\s)(\d{4})[\s\-](\d{4})(?:\s|$)",       # XXXX-XXXX en contexto
    ]

    found_phones: set[str] = set()
    for pattern in phone_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            groups = [g for g in match.groups() if g]
            phone_str = "".join(groups) if groups else ""
            digits = _digits_only(phone_str)
            if 7 <= len(digits) <= 8 and digits not in ["0000000", "00000000"]:
                phone_formatted = f"{digits[:4]}-{digits[4:]}" if len(digits) == 8 else digits
                found_phones.add(phone_formatted)

    for phone in found_phones:
        contacts.append({"field": "phone", "value": phone, "source_url": source_url})

    # Detectar WhatsApp (número cercano a la palabra "whatsapp")
    whatsapp_pattern = r"(?:whatsapp|wa\.me|whatsapp\.com)[:\s/]*(\+?\d{1,3}[\s\-]?\d{3,4}[\s\-]?\d{4})"
    for match in re.finditer(whatsapp_pattern, text, re.IGNORECASE):
        whatsapp = match.group(1)
        digits = _digits_only(whatsapp)
        if 7 <= len(digits) <= 15:
            # Preferir el que ya encontramos como phone
            if not any(c["field"] == "whatsapp" and c["value"] == digits for c in contacts):
                contacts.append({"field": "whatsapp", "value": digits, "source_url": source_url})

    # Deduplicar por (field, value)
    seen = set()
    unique_contacts = []
    for c in contacts:
        key = (c["field"], c["value"].lower())
        if key not in seen:
            seen.add(key)
            unique_contacts.append(c)

    return unique_contacts


def _build_exa_search_payload(lead: LeadCore, settings: Settings, exclude_linkedin: bool = False) -> dict[str, Any]:
    from urllib.parse import urlparse

    parts = [
        lead.full_name,
        lead.specialty,
        lead.city,
        lead.country,
    ]
    # Anclar búsqueda al dominio conocido del lead para priorizar resultados correctos
    if lead.primary_source_url:
        netloc = urlparse(lead.primary_source_url).netloc.lower().replace("www.", "")
        if netloc and "linkedin" not in netloc:
            parts.append(netloc)

    query = " ".join(p.strip() for p in parts if p and p.strip())
    payload: dict[str, Any] = {
        "query": query[:900],
        "type": settings.exa_search_type,
        "numResults": 18,
        "contents": exa_contents_full_config(
            text_max_characters=settings.exa_text_max_characters,
            highlights_max_characters=settings.exa_highlights_max_characters,
            subpages=settings.exa_subpages,
        ),
    }
    if exclude_linkedin:
        payload["excludeDomains"] = ["linkedin.com"]
    return finalize_exa_search_payload(payload)


async def _exa_evidence(
    exa_client: ExaClient,
    lead: LeadCore,
    settings: Settings,
    exclude_linkedin: bool = False,
) -> tuple[list[dict[str, Any]], str, list[dict[str, str]]]:
    """Combina /contents sobre primary_source_url (si existe) + /search genérica.

    Retorna (results, evidence_para_llm, regex_contacts_directos).
    """
    results: list[dict[str, Any]] = []
    if lead.primary_source_url:
        try:
            contents_payload: dict[str, Any] = {
                "ids": [lead.primary_source_url],
                "text": {"maxCharacters": settings.exa_text_max_characters},
                "highlights": {"maxCharacters": settings.exa_highlights_max_characters},
                "subpages": settings.exa_subpages,
            }
            contents_response = await exa_client.get_contents(contents_payload)
            results.extend(_extract_results(contents_response))
        except Exception as exc:  # noqa: BLE001
            logger.info("Exa /contents para %s falló (degrade safe): %s", lead.primary_source_url, exc)

    try:
        search_payload = _build_exa_search_payload(lead, settings, exclude_linkedin=exclude_linkedin)
        search_response = await exa_client.search(search_payload)
        results.extend(_extract_results(search_response))
    except Exception as exc:  # noqa: BLE001
        logger.info("Exa /search para %s falló (degrade safe): %s", lead.full_name, exc)

    evidence = _flatten_evidence(results)

    # Extraer contacts con regex del texto completo (no truncado)
    regex_contacts: list[dict[str, str]] = []
    for item in results:
        if isinstance(item, dict) and item.get("text"):
            regex_contacts.extend(_extract_regex_contacts(item["text"], item.get("url", "")))
        # También extraer de subpages
        for sp in item.get("subpages", []) if isinstance(item, dict) else []:
            if isinstance(sp, dict) and sp.get("text"):
                regex_contacts.extend(_extract_regex_contacts(sp["text"], sp.get("url", "")))

    return results, evidence, regex_contacts


async def _deep_fetch_contacts(
    exa_client: ExaClient,
    search_results: list[dict[str, Any]],
    settings: Settings,
    primary_source_url: str = "",
) -> list[dict[str, str]]:
    """Visita TODOS los URLs útiles de los resultados de búsqueda (excluye LinkedIn y primary_source_url).

    Retorna lista de contactos extraídos con regex del texto completo.
    """
    if not search_results:
        return []

    primary_lower = primary_source_url.strip().lower().rstrip("/")

    candidates = [
        r for r in search_results
        if isinstance(r, dict)
        and _is_crawlable_personal_site(r.get("url", ""))
        and str(r.get("url", "")).strip().lower().rstrip("/") != primary_lower
    ]

    if not candidates:
        return []

    async def _fetch_one(url: str) -> list[dict[str, str]]:
        try:
            payload: dict[str, Any] = {
                "ids": [url],
                "text": {"maxCharacters": 50000},
                "highlights": {"maxCharacters": 8000},
                "subpages": 3,
            }
            response = await exa_client.get_contents(payload)
            items = _extract_results(response)
            contacts: list[dict[str, str]] = []
            for item in items:
                if isinstance(item, dict) and item.get("text"):
                    contacts.extend(_extract_regex_contacts(item["text"], item.get("url", url)))
                for sp in item.get("subpages", []) if isinstance(item, dict) else []:
                    if isinstance(sp, dict) and sp.get("text"):
                        contacts.extend(_extract_regex_contacts(sp["text"], sp.get("url", url)))
            return contacts
        except Exception as exc:  # noqa: BLE001
            logger.info("Deep fetch para %s falló (degrade safe): %s", url, exc)
            return []

    all_batches = await asyncio.gather(*[_fetch_one(r["url"]) for r in candidates])
    merged: list[dict[str, str]] = []
    for batch in all_batches:
        merged.extend(batch)
    return merged


async def _generate_brave_search_query(lead: LeadCore, proposer: GeminiClient) -> str:
    """Usa Gemini para generar la query de Brave más efectiva para el lead."""
    prompt = (
        "Genera una query de búsqueda web corta para encontrar datos de contacto "
        "(teléfono, dirección, email) de este profesional médico.\n"
        "REGLAS:\n"
        "- Extrae solo el nombre real (ignora texto después de '|', '/' o '-')\n"
        "- Incluye especialidad médica en español (máximo 2 palabras)\n"
        "- Incluye ciudad y país\n"
        "- Máximo 8 palabras en total\n"
        f"full_name: {lead.full_name}\n"
        f"specialty: {lead.specialty}\n"
        f"city: {lead.city}\n"
        f"country: {lead.country}\n"
        'Devuelve SOLO JSON: {"query": "texto de la query"}'
    )
    try:
        result = await proposer.complete_json_prompt(prompt)
        q = str(result.get("query", "")).strip()
        if q:
            return q
    except Exception:  # noqa: BLE001
        pass
    # Fallback determinista
    name = re.split(r"[|/\-]", lead.full_name)[0].strip()
    return " ".join(p for p in [name, lead.specialty, lead.city, lead.country] if p)[:120]


async def _brave_web_evidence(
    brave: BraveSearchClient,
    exa_client: ExaClient,
    lead: LeadCore,
    proposer: GeminiClient,
) -> tuple[str, list[dict[str, str]]]:
    """Búsqueda Brave web + fetch de top 3 URLs → evidence string + regex contacts."""
    try:
        query = await _generate_brave_search_query(lead, proposer)
        # Mapear país a ISO (Brave acepta None para no mapeados)
        _COUNTRY_ISO = {
            "Honduras": "HN", "Mexico": "MX", "Guatemala": "GT",
            "El Salvador": "SV", "Costa Rica": "CR", "Panama": "PA",
            "Colombia": "CO", "Venezuela": "VE", "Peru": "PE",
            "Argentina": "AR", "Chile": "CL", "España": "ES"
        }
        country_iso = _COUNTRY_ISO.get(lead.country)

        brave_items = await brave.web_search(query, country=country_iso, count=10, pages=1)
        top3_urls = [item["url"] for item in brave_items[:3] if item.get("url")]
        if not top3_urls:
            return ("", [])

        # Fetch contenido completo con Exa
        contents_payload: dict[str, Any] = {
            "ids": top3_urls,
            "text": {"maxCharacters": 50000},
            "highlights": {"maxCharacters": 8000},
            "subpages": 2,
        }
        response = await exa_client.get_contents(contents_payload)
        full_items = _extract_results(response)

        # Enriquecer items de Brave con texto completo de Exa
        url_to_full = {item.get("url", ""): item for item in full_items}
        enriched = []
        for bi in brave_items[:3]:
            url = bi.get("url", "")
            ei = url_to_full.get(url)
            enriched.append({**bi, "text": ei.get("text", bi.get("text", ""))} if ei else bi)

        evidence = _flatten_evidence(enriched)

        # Extraer regex contacts del texto completo
        regex_contacts: list[dict[str, str]] = []
        for item in full_items:
            if item.get("text"):
                regex_contacts.extend(_extract_regex_contacts(item["text"], item.get("url", "")))
            for sp in item.get("subpages") or []:
                if sp.get("text"):
                    regex_contacts.extend(_extract_regex_contacts(sp["text"], sp.get("url", "")))

        return (evidence, regex_contacts)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_brave_web_evidence falló: %s", exc)
        return ("", [])


async def _brave_local_evidence(brave: BraveSearchClient, lead: LeadCore) -> dict[str, str]:
    """Brave Local Search → phone, address, hours, website."""
    name_query = re.split(r"[|/\-]", lead.full_name)[0].strip()
    if lead.specialty:
        name_query = f"{name_query} {lead.specialty}".strip()
    if lead.city:
        name_query = f"{name_query} {lead.city}".strip()
    try:
        result = await brave.local_search(name_query)
        if isinstance(result, dict) and result:
            return {
                "phone": str(result.get("phone", "") or "").strip(),
                "address": str(result.get("address", "") or "").strip(),
                "schedule_text": str(result.get("hours", result.get("schedule_text", "")) or "").strip(),
                "website": str(result.get("website", "") or "").strip(),
                "email": str(result.get("email", "") or "").strip(),
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Brave local search falló: %s", exc)
    return {}


async def _brave_social_profiles(brave: BraveSearchClient, lead: LeadCore) -> dict[str, str]:
    """Busca perfiles de Facebook e Instagram del lead en Brave."""
    name = re.split(r"[|/\-]", lead.full_name)[0].strip()
    city = lead.city or ""
    specialty = lead.specialty or ""
    _COUNTRY_ISO = {
        "Honduras": "HN", "Mexico": "MX", "Guatemala": "GT",
        "El Salvador": "SV", "Costa Rica": "CR", "Panama": "PA",
        "Colombia": "CO", "Venezuela": "VE", "Peru": "PE",
        "Argentina": "AR", "Chile": "CL", "España": "ES",
    }
    country_iso = _COUNTRY_ISO.get(lead.country)
    out: dict[str, str] = {}
    try:
        fb_q = f'site:facebook.com "{name}" {city}'.strip()
        fb_items = await brave.web_search(fb_q, country=country_iso, count=5, pages=1)
        for item in fb_items:
            url = str(item.get("url", "")).strip()
            if "facebook.com/" in url and "/profile.php" not in url and "/posts/" not in url:
                out["facebook_url"] = url
                break
    except Exception:  # noqa: BLE001
        pass
    try:
        ig_q = f'site:instagram.com "{name}" {specialty} {city}'.strip()
        ig_items = await brave.web_search(ig_q, country=country_iso, count=5, pages=1)
        for item in ig_items:
            url = str(item.get("url", "")).strip()
            if "instagram.com/" in url and "/p/" not in url and "/reel/" not in url:
                out["instagram_url"] = url
                break
    except Exception:  # noqa: BLE001
        pass
    logger.debug("_brave_social_profiles lead=%s result=%s", lead.full_name, out)
    return out


# ---------------- Prompts ----------------


def _proposer_prompt(evidence: str, lead: LeadCore) -> str:
    ctx = json.dumps(
        {
            "full_name": lead.full_name,
            "specialty": lead.specialty,
            "city": lead.city,
            "country": lead.country,
            "linkedin_url_known": lead.linkedin_url,
            "email_known": lead.email,
            "whatsapp_known": lead.whatsapp,
        },
        ensure_ascii=False,
    )
    return (
        "Eres analista de datos de contacto B2B médico. SOLO puedes usar datos que aparezcan literalmente en EVIDENCIA.\n"
        "Si un dato no está escrito en EVIDENCIA, deja cadena vacía. No infieras ni completes.\n\n"
        f"CONTEXTO_LEAD_JSON: {ctx}\n\n"
        f"EVIDENCIA:\n{evidence}\n\n"
        "Devuelve SOLO JSON con claves exactas:\n"
        '{"description": "texto breve en español solo con hechos de EVIDENCIA, máximo 600 caracteres", '
        '"email": "", "whatsapp": "", "linkedin_url": ""}\n'
        "email, whatsapp y linkedin_url deben ser copias exactas de fragmentos de EVIDENCIA o vacíos."
    )


def _reviewer_prompt(evidence: str, proposal: dict[str, Any]) -> str:
    proposal_txt = json.dumps(proposal, ensure_ascii=False)
    return (
        "Eres un auditor estricto anti-alucinaciones. Recibes EVIDENCIA (texto) y una PROPUESTA_JSON.\n"
        "Tu trabajo: para description_final, email_final, whatsapp_final, linkedin_url_final, copia SOLO valores "
        "que sean subcadenas exactas reproducibles desde EVIDENCIA o deja cadena vacía si no hay prueba.\n"
        "Si la propuesta inventa datos, rechazalos (cadena vacía).\n"
        "Incluye lista rejected con objetos {field, reason} en español para cada campo vaciado.\n\n"
        f"EVIDENCIA:\n{evidence}\n\nPROPUESTA_JSON:\n{proposal_txt}\n\n"
        "Devuelve SOLO JSON con claves exactas:\n"
        '{"description_final": "", "email_final": "", "whatsapp_final": "", "linkedin_url_final": "", '
        '"rejected": []}'
    )


def _gate_finals(evidence_lower: str, finals: dict[str, str]) -> dict[str, str]:
    out = {
        k: (finals.get(k) or "").strip()
        for k in ("description_final", "email_final", "whatsapp_final", "linkedin_url_final")
    }
    desc = out["description_final"]
    if desc and desc.lower() not in evidence_lower:
        out["description_final"] = ""
    em = out["email_final"]
    if em and not _email_in_evidence(em, evidence_lower):
        out["email_final"] = ""
    wa = out["whatsapp_final"]
    if wa and not _phone_in_evidence(wa, evidence_lower):
        out["whatsapp_final"] = ""
    li = out["linkedin_url_final"]
    if li and not _linkedin_in_evidence(li, evidence_lower):
        out["linkedin_url_final"] = ""
    return out


# ---------------- Core enrichment function ----------------


async def enrich_lead_contacts(
    lead: LeadCore,
    *,
    exa_client: ExaClient,
    proposer: GeminiClient,
    reviewer: GeminiClient,
    settings: Settings | None = None,
    brave: BraveSearchClient | None = None,
    exclude_linkedin: bool = False,
    progress_callback: callable | None = None,
) -> EnrichmentResult:
    """Enriquece un lead con Exa (evidencia textual) + Brave (local + web) + Gemini reviewer.

    Función pura: no persiste en DB. El caller decide qué hacer con el resultado.
    Si brave está configurado, lo usa para búsqueda local y web.
    exclude_linkedin: si True, excluye linkedin.com de los resultados Exa (solo para enriquecimiento manual).
    progress_callback: callable async que recibe un string con el mensaje de progreso.
    """
    st = settings or get_settings()

    # Notificar inicio
    if progress_callback:
        await progress_callback("Buscando información del perfil en la web...")

    # Ejecutar exa usando create_task para mejor control
    exa_task = asyncio.create_task(_exa_evidence(exa_client, lead, st, exclude_linkedin=exclude_linkedin))

    # Esperar a que exa termine, luego lanzar deep_fetch
    exa_results, evidence, regex_contacts = await exa_task

    if progress_callback:
        await progress_callback("Visitando páginas personales y redes sociales...")

    deep_fetch_task = asyncio.create_task(
        _deep_fetch_contacts(
            exa_client, exa_results, st,
            primary_source_url=lead.primary_source_url,
        )
    )

    local_task: asyncio.Task | None = None
    if brave is not None:
        local_task = asyncio.create_task(_brave_local_evidence(brave, lead))

    brave_task: asyncio.Task | None = None
    if brave is not None and st.brave_search_enabled:
        brave_task = asyncio.create_task(
            _brave_web_evidence(brave, exa_client, lead, proposer)
        )

    social_task: asyncio.Task | None = None
    if brave is not None and st.brave_search_enabled:
        social_task = asyncio.create_task(_brave_social_profiles(brave, lead))

    # Esperar a deep_fetch, local_task, brave_task y social_task en paralelo
    if progress_callback:
        await progress_callback("Consultando datos locales y redes sociales...")

    gather_tasks: list = [deep_fetch_task]
    if local_task:
        gather_tasks.append(local_task)
    if brave_task:
        gather_tasks.append(brave_task)
    if social_task:
        gather_tasks.append(social_task)

    results = await asyncio.gather(*gather_tasks)
    deep_contacts = results[0]
    idx = 1
    if local_task:
        brave_local: dict[str, str] = results[idx]; idx += 1
    else:
        brave_local = {}
    if brave_task:
        brave_evidence, brave_regex = results[idx]; idx += 1
    else:
        brave_evidence, brave_regex = "", []
    if social_task:
        social_profiles: dict[str, str] = results[idx]; idx += 1
    else:
        social_profiles = {}

    if progress_callback:
        await progress_callback("Verificando datos con inteligencia artificial...")

    # Combinar todos los contactos directos (regex + deep_fetch + brave), deduplicar
    all_direct_contacts = regex_contacts + deep_contacts + brave_regex
    seen = set()
    unique_direct_contacts = []
    for c in all_direct_contacts:
        key = (c["field"], c["value"].lower())
        if key not in seen:
            seen.add(key)
            unique_direct_contacts.append(c)

    result = EnrichmentResult()

    # Contactos estructurados de Brave Local Search
    if brave_local.get("phone") and not lead.phone:
        result.phone = brave_local["phone"][:40]
        result.contact_sources["phone"] = "brave_local"
    if brave_local.get("email") and not lead.email:
        result.email = brave_local["email"][:255]
        result.contact_sources["email"] = "brave_local"
    if brave_local.get("address") and not lead.address:
        result.address = brave_local["address"][:500]
    if brave_local.get("schedule_text") and not lead.schedule_text:
        result.schedule_text = brave_local["schedule_text"][:500]
    if brave_local.get("website"):
        result.website = brave_local["website"][:500]

    # Perfiles sociales encontrados por Brave (Facebook / Instagram)
    if social_profiles.get("facebook_url") and not (lead.facebook_url or "").strip():
        result.facebook_url = social_profiles["facebook_url"]
        result.contact_sources["facebook_url"] = social_profiles["facebook_url"]
    if social_profiles.get("instagram_url") and not (lead.instagram_url or "").strip():
        result.instagram_url = social_profiles["instagram_url"]
        result.contact_sources["instagram_url"] = social_profiles["instagram_url"]

    # Aplicar contactos extraídos con regex del texto completo (prioridad: OpenCLI > regex > LLM)
    for direct_contact in unique_direct_contacts:
        field = direct_contact.get("field", "")
        value = direct_contact.get("value", "").strip()
        source_url = direct_contact.get("source_url", "")

        if field == "email" and not result.email and not lead.email and value:
            result.email = value[:255]
            if source_url:
                result.contact_sources["email"] = source_url
            result.citations.append({
                "url": source_url,
                "title": f"Email (regex extraction)",
                "confidence": "high",
                "source": "direct_regex",
            })
        elif field == "phone" and not result.phone and not lead.phone and value:
            result.phone = value[:40]
            if source_url:
                result.contact_sources["phone"] = source_url
            result.citations.append({
                "url": source_url,
                "title": f"Phone (regex extraction)",
                "confidence": "high",
                "source": "direct_regex",
            })
        elif field == "whatsapp" and not result.whatsapp and not lead.whatsapp and value:
            result.whatsapp = value[:30]
            if source_url:
                result.contact_sources["whatsapp"] = source_url
            result.citations.append({
                "url": source_url,
                "title": f"WhatsApp (regex extraction)",
                "confidence": "high",
                "source": "direct_regex",
            })

    # Añadir evidencia de Brave si la hay
    if brave_evidence.strip():
        evidence = evidence + "\n\n--- FUENTES BRAVE WEB SEARCH ---\n" + brave_evidence

    # Si no hay evidencia ni de Exa ni de OpenCLI, termina no_verified_data.
    if not evidence.strip() and not any([result.phone, result.address, result.schedule_text]):
        result.message = NO_DATA_ES
        return result

    # Gemini proposer + reviewer sobre evidencia Exa.
    if evidence.strip():
        try:
            proposal = await proposer.complete_json_prompt(_proposer_prompt(evidence, lead))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini proponente falló: %s", exc)
            proposal = {"description": "", "email": "", "whatsapp": "", "linkedin_url": ""}

        try:
            reviewed = await reviewer.complete_json_prompt(_reviewer_prompt(evidence, proposal))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini revisora falló: %s", exc)
            reviewed = {
                "description_final": "",
                "email_final": "",
                "whatsapp_final": "",
                "linkedin_url_final": "",
                "rejected": [{"field": "all", "reason": "revisora no disponible"}],
            }

        finals = _gate_finals(
            evidence.lower(),
            {
                "description_final": str(reviewed.get("description_final", "")),
                "email_final": str(reviewed.get("email_final", "")),
                "whatsapp_final": str(reviewed.get("whatsapp_final", "")),
                "linkedin_url_final": str(reviewed.get("linkedin_url_final", "")),
            },
        )

        if finals["email_final"] and not lead.email:
            result.email = finals["email_final"][:255]
        if finals["whatsapp_final"] and not lead.whatsapp:
            result.whatsapp = finals["whatsapp_final"][:30]
        if finals["linkedin_url_final"] and not lead.linkedin_url:
            result.linkedin_url = finals["linkedin_url_final"][:500]
        result.description = finals["description_final"]
        result.audit = list(reviewed.get("rejected") or [])[:20]

    # Citations: URLs de Exa (se agregan a las ya existentes de regex, sin duplicar).
    seen_urls: set[str] = {c["url"] for c in result.citations if c.get("url")}
    first_exa_url: str = ""
    for item in exa_results:
        u = str(item.get("url", "")).strip()
        if u and u not in seen_urls:
            result.citations.append(
                {
                    "url": u,
                    "title": str(item.get("title", "") or "Fuente")[:240],
                    "confidence": "medium",
                    "source": "auto_enrich_exa",
                }
            )
            seen_urls.add(u)
            if not first_exa_url:
                first_exa_url = u
    if first_exa_url and not lead.primary_source_url:
        result.primary_source_url = first_exa_url[:500]

    has_contact = any([result.email, result.whatsapp, result.linkedin_url, result.phone, result.address])
    has_desc = bool(result.description)
    if has_contact or has_desc or result.schedule_text:
        result.status = "enriched"
        result.message = "Datos verificados en fuentes recuperadas."
    else:
        result.status = "no_verified_data"
        result.message = NO_DATA_ES
    return result


def _lead_to_core(lead: Lead) -> LeadCore:
    return LeadCore(
        full_name=str(lead.full_name or ""),
        specialty=str(lead.specialty or ""),
        city=str(lead.city or ""),
        country=str(lead.country or ""),
        entity_type="person",  # Default; el auto_enrich_node puede sobrescribir
        linkedin_url=str(lead.linkedin_url or ""),
        email=str(lead.email or ""),
        whatsapp=str(lead.whatsapp or ""),
        phone=str(lead.phone or ""),
        address=str(lead.address or ""),
        schedule_text=str(lead.schedule_text or ""),
        primary_source_url=str(lead.primary_source_url or ""),
    )


def build_lead_updates(lead: Lead, enrichment: EnrichmentResult) -> dict[str, Any]:
    """Convierte un EnrichmentResult en un diff aplicable por LeadsRepository.apply_field_updates."""
    updates: dict[str, Any] = {}

    if enrichment.email and not (lead.email or "").strip():
        updates["email"] = enrichment.email
    if enrichment.whatsapp and not (lead.whatsapp or "").strip():
        updates["whatsapp"] = enrichment.whatsapp
    if enrichment.linkedin_url and not (lead.linkedin_url or "").strip():
        updates["linkedin_url"] = enrichment.linkedin_url
    if enrichment.phone and not (lead.phone or "").strip():
        updates["phone"] = enrichment.phone
    if enrichment.address and not (lead.address or "").strip():
        updates["address"] = enrichment.address
    if enrichment.schedule_text and not (lead.schedule_text or "").strip():
        updates["schedule_text"] = enrichment.schedule_text
    if enrichment.website and not (lead.website or "").strip():
        updates["website"] = enrichment.website
    if enrichment.facebook_url and not (lead.facebook_url or "").strip():
        updates["facebook_url"] = enrichment.facebook_url
    if enrichment.instagram_url and not (lead.instagram_url or "").strip():
        updates["instagram_url"] = enrichment.instagram_url

    if enrichment.citations:
        existing = lead.source_citations if isinstance(lead.source_citations, list) else []
        existing_normalized = [c for c in existing if isinstance(c, dict)]
        seen_urls = {str(c.get("url", "")).strip() for c in existing_normalized if c.get("url")}
        merged = list(existing_normalized)
        for c in enrichment.citations:
            u = str(c.get("url", "")).strip()
            if u and u not in seen_urls:
                merged.append(c)
                seen_urls.add(u)
        updates["source_citations"] = merged

    if enrichment.primary_source_url and not (lead.primary_source_url or "").strip():
        updates["primary_source_url"] = enrichment.primary_source_url[:500]

    if enrichment.enriched_sources:
        base = dict(lead.enriched_sources or {})
        base.update(enrichment.enriched_sources)
        updates["enriched_sources"] = base

    base_reason = (lead.score_reasoning or "").strip()
    enrich_block = enrichment.description if enrichment.description else NO_DATA_ES
    new_reasoning = (
        f"{base_reason}\n\n[Búsqueda extensiva]\n{enrich_block}".strip()
        if base_reason
        else f"[Búsqueda extensiva]\n{enrich_block}".strip()
    )
    updates["score_reasoning"] = new_reasoning[:1000]

    updates["langsmith_metadata"] = {
        "last_deep_enrich": {
            "status": enrichment.status,
            "message": enrichment.message,
            "audit": enrichment.audit,
        }
    }
    return updates


async def deep_enrich_lead(lead_id: UUID) -> LeadRead | None:
    """Wrapper legacy para el endpoint manual: carga lead, enriquece, persiste."""
    settings = get_settings()
    async with async_session_factory() as session:
        repo = LeadsRepository(session)
        lead_orm = await repo.get_orm_by_id(lead_id)
        if lead_orm is None:
            return None

        exa_client = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )
        proposer = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_model)
        reviewer = GeminiClient(api_key=settings.google_api_key, model_name=settings.google_reviewer_model)

        brave = None
        if settings.brave_search_api_key and settings.brave_search_enabled:
            brave = BraveSearchClient(
                api_key=settings.brave_search_api_key,
                timeout_seconds=settings.brave_search_timeout_seconds,
            )

        enrichment = await enrich_lead_contacts(
            _lead_to_core(lead_orm),
            exa_client=exa_client,
            proposer=proposer,
            reviewer=reviewer,
            settings=settings,
            brave=brave,
        )
        updates = build_lead_updates(lead_orm, enrichment)
        await repo.apply_field_updates(lead_id, updates)
        return await repo.get_by_id(lead_id)
